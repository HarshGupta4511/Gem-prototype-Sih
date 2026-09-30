"""Document endpoints (CONTRACT.md §5: Documents)."""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_officer
from app.models.models import (
    BidSubmission,
    Bidder,
    DocProcessingStatus,
    Document,
    DocumentType,
    ExtractedField,
    Tender,
    User,
)
from app.schemas.schemas import (
    DocumentDetailOut,
    DocumentOut,
    DocumentProcessResponse,
    DocumentTypeUpdate,
    ExtractedFieldOut,
)
from app.services import audit_service, document_service, pipeline_service

router = APIRouter(prefix="/api/documents", tags=["documents"])

_OFFICER = require_officer()

log = logging.getLogger(__name__)


class DocumentListItem(DocumentOut):
    """Document row enriched for the documents overview page."""

    legal_name: str | None = None
    tender_number: str | None = None


def _validate_processing_status(value: str) -> str:
    try:
        return DocProcessingStatus(value).value
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document status '{value}'",
        ) from None


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    bid_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all documents (newest first), with bidder legal name and tender number."""
    query = (
        db.query(Document, Bidder.legal_name, Tender.tender_number)
        .join(BidSubmission, Document.bid_id == BidSubmission.id)
        .join(Bidder, BidSubmission.bidder_id == Bidder.id)
        .join(Tender, BidSubmission.tender_id == Tender.id)
        .order_by(Document.id.desc())
    )
    if bid_id is not None:
        query = query.filter(Document.bid_id == bid_id)
    if status is not None:
        query = query.filter(Document.processing_status == _validate_processing_status(status))
    return [
        DocumentListItem(
            **DocumentOut.model_validate(doc).model_dump(),
            legal_name=legal_name,
            tender_number=tender_number,
        )
        for doc, legal_name, tender_number in query.all()
    ]


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    bid_id: int = Form(...),
    document_type: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Upload a bid document (pdf/jpg/jpeg/png, ≤ 25 MB, magic-byte checked).

    The officer does NOT select a document type — the processing pipeline
    auto-detects it from the document content (filename is supporting context
    only). ``document_type`` is accepted optionally for API compatibility and
    is only a pre-processing placeholder: the pipeline always overwrites it
    with the detected type (or UNCLASSIFIED when it cannot tell).
    """
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    doc_type = DocumentType.UNCLASSIFIED.value
    if document_type:
        try:
            doc_type = DocumentType(document_type).value
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document_type '{document_type}'",
            ) from None

    content = await file.read()
    try:
        document_service.validate_upload(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    file_path, file_hash, file_size = document_service.save_upload(
        content, file.filename or "upload", bid_id
    )
    doc = Document(
        bid_id=bid_id,
        document_type=doc_type,
        filename=file.filename or "upload",
        file_path=file_path,
        file_hash=file_hash,
        file_size=file_size,
        mime_type=document_service.mime_for(file.filename or ""),
        upload_time=datetime.now(timezone.utc),
        uploaded_by=user.id,
        processing_status=DocProcessingStatus.UPLOADED.value,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    # Auto-run the extraction pipeline on upload so fields appear immediately —
    # the user should never have to tap Re-process manually after uploading.
    # The pipeline never raises for extraction failures (it marks the doc
    # FAILED with an error instead); the try/except is only a last-resort
    # guard so an unexpected bug can never turn a good upload into a 500.
    try:
        pipeline_service.process_document(db, doc.id, user_id=user.id)
    except Exception:
        log.exception("Auto-processing failed for uploaded document %s", doc.id)
        db.rollback()
    db.refresh(doc)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="DOCUMENT_UPLOADED",
        entity_type="document",
        entity_id=str(doc.id),
        metadata={
            "bid_id": bid_id,
            "filename": doc.filename,
            "document_type": doc.document_type,
            "file_size": file_size,
        },
    )
    return DocumentOut.model_validate(doc)


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Document detail with its extracted fields."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    fields = (
        db.query(ExtractedField)
        .filter(ExtractedField.document_id == document_id)
        .order_by(ExtractedField.id)
        .all()
    )
    return DocumentDetailOut(
        document=DocumentOut.model_validate(doc),
        extracted_fields=[ExtractedFieldOut.model_validate(f) for f in fields],
    )


@router.post("/{document_id}/process", response_model=DocumentProcessResponse)
def process_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Run the full extraction/classification pipeline (§9) for a document."""
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    pipeline_service.process_document(db, document_id, user_id=user.id)
    doc = db.get(Document, document_id)
    fields = (
        db.query(ExtractedField)
        .filter(ExtractedField.document_id == document_id)
        .order_by(ExtractedField.id)
        .all()
    )
    try:
        classification = DocumentType(doc.document_type)
    except ValueError:
        classification = None
    return DocumentProcessResponse(
        document=DocumentOut.model_validate(doc),
        extracted_fields=[ExtractedFieldOut.model_validate(f) for f in fields],
        classification=classification,
    )


@router.patch("/{document_id}", response_model=DocumentOut)
def correct_classification(
    document_id: int,
    payload: DocumentTypeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Officer correction of a document's classification.

    Allowed ONLY when the system could not detect the type itself
    (document_type == UNCLASSIFIED) — the normal workflow is fully automatic
    and detected types are never manually overridden.
    """
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.document_type != DocumentType.UNCLASSIFIED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Classification was detected automatically; manual correction is "
                   "only allowed for documents the system could not identify.",
        )
    if payload.document_type == DocumentType.UNCLASSIFIED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select the actual document type.",
        )
    old_type = doc.document_type
    doc.document_type = payload.document_type.value
    # The document was already processed (fields extracted); only the type was
    # unknown. Mark it processed so it joins verification/compliance.
    if doc.processing_status == DocProcessingStatus.REVIEW_REQUIRED.value:
        doc.processing_status = DocProcessingStatus.PROCESSED.value
    db.commit()
    db.refresh(doc)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="CLASSIFICATION_CORRECTED",
        entity_type="document",
        entity_id=str(doc.id),
        metadata={"old_document_type": old_type, "new_document_type": doc.document_type},
    )
    return DocumentOut.model_validate(doc)


@router.get("/{document_id}/file")
def download_file(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve the stored document bytes (Bearer JWT auth via header)."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not doc.file_path or not os.path.isfile(doc.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File is missing from storage",
        )
    return FileResponse(
        doc.file_path,
        media_type=document_service.mime_for(doc.filename),
        filename=doc.filename,
    )
