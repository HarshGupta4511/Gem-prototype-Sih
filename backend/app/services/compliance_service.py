"""Compliance evaluation orchestration (§6–§8 of CONTRACT.md).

Builds the per-bid evaluation context, runs the rules engine (the ONLY
decider of PASS/FAIL), scores the results, assesses risk, and persists
everything: compliance_results, risk_assessment, bid_submission updates,
and audit entries.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.engines.rules_engine import RulesEngine
from app.engines import risk_engine
from app.services.scoring_service import compute_score

BIDDER_FIELDS = (
    "legal_name",
    "trade_name",
    "pan",
    "gstin",
    "udyam",
    "cin",
    "registered_address",
    "contact_name",
    "contact_email",
    "contact_phone",
)


def build_context(db, bid_id: int) -> dict:
    """Build the rules-engine evaluation context for a bid.

    Context keys (per §6): bidder, extracted, extracted_confidence,
    extracted_by_doc, evidence_index, documents, verification, today.
    Extra keys carried along: document_index (doc_type → docs) and bid.
    """
    from app.models.models import (
        Bidder,
        BidSubmission,
        Document,
        ExtractedField,
        VerificationCheck,
    )

    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"BidSubmission {bid_id} not found")

    bidder = db.get(Bidder, bid.bidder_id)
    bidder_fields = {}
    if bidder is not None:
        for f in BIDDER_FIELDS:
            bidder_fields[f] = getattr(bidder, f, None)

    docs = (
        db.query(Document)
        .filter(Document.bid_id == bid_id, Document.processing_status == "PROCESSED")
        .order_by(Document.id)
        .all()
    )
    doc_by_id = {d.id: d for d in docs}

    fields = []
    if doc_by_id:
        fields = (
            db.query(ExtractedField)
            .filter(ExtractedField.document_id.in_(list(doc_by_id)))
            .all()
        )

    extracted: dict = {}
    best_conf: dict = {}
    conf_lists: dict = {}
    evidence_index: dict = {}
    per_doc_best: dict = {}
    for ef in fields:
        fn = ef.field_name
        val = ef.normalized_value
        conf = float(ef.confidence) if ef.confidence is not None else 0.0
        d = doc_by_id.get(ef.document_id)
        evidence_index.setdefault(fn, []).append(
            {
                "document_id": ef.document_id,
                "filename": d.filename if d else None,
                "page": ef.page_number,
                "field": fn,
                "value": val,
                "confidence": conf,
            }
        )
        conf_lists.setdefault(fn, []).append(conf)
        if fn not in best_conf or conf > best_conf[fn]:
            best_conf[fn] = conf
            extracted[fn] = val  # highest-confidence value wins per §6
        if d is not None:
            key = (d.document_type, fn)
            if key not in per_doc_best or conf > per_doc_best[key][0]:
                per_doc_best[key] = (conf, val)

    extracted_by_doc: dict = {}
    for (doc_type, fn), (_c, v) in per_doc_best.items():
        extracted_by_doc.setdefault(doc_type, {})[fn] = v
    extracted_confidence = {fn: min(cs) for fn, cs in conf_lists.items()}

    documents = [d.document_type for d in docs]
    document_index: dict = {}
    for d in docs:
        document_index.setdefault(d.document_type, []).append(
            {"document_id": d.id, "filename": d.filename}
        )

    checks = (
        db.query(VerificationCheck)
        .filter(VerificationCheck.bid_id == bid_id)
        .order_by(VerificationCheck.verified_at.desc())
        .all()
    )
    verification: dict = {}
    for c in checks:
        if c.source in verification:  # latest check per source wins
            continue
        payload = c.response_payload or {}
        data = payload.get("data") if isinstance(payload, dict) else payload
        verification[c.source] = {
            "status": c.verification_status,
            "data": data or {},
            "confidence": float(c.confidence) if c.confidence is not None else 0.0,
            "check_id": c.id,
        }

    return {
        "bidder": bidder_fields,
        "extracted": extracted,
        "extracted_confidence": extracted_confidence,
        "extracted_by_doc": extracted_by_doc,
        "evidence_index": evidence_index,
        "documents": documents,
        "document_index": document_index,
        "verification": verification,
        "today": datetime.now(timezone.utc).date().isoformat(),
        "bid": bid,
    }


def _result_source(result: dict) -> str:
    """Human-readable source label, e.g. 'Bidder document + Mock GSTN'."""
    evidence = result.get("evidence") or []
    parts = []
    if any(e.get("document_id") for e in evidence):
        parts.append("Bidder document")
    elif any(e.get("source") == "bidder declaration" for e in evidence):
        parts.append("Bidder declaration")
    ver_sources = sorted(
        {
            str(e.get("source", "")).split(":", 1)[1]
            for e in evidence
            if str(e.get("source", "")).startswith("verification:")
        }
    )
    parts.extend(f"Mock {s}" for s in ver_sources)
    return " + ".join(parts) if parts else "Not available"


def evaluate_bid(db, bid_id: int, *, user_id=None) -> dict:
    """Run rules engine → scoring → risk engine; persist everything.

    Returns {"results": [...], "compliance_score", "risk": {...}}.
    """
    from app.models.models import (
        ComplianceResult,
        RiskAssessment,
        TenderRequirement,
    )
    from app.services.audit_service import append_audit

    context = build_context(db, bid_id)
    bid = context["bid"]

    requirements = (
        db.query(TenderRequirement)
        .filter(TenderRequirement.tender_id == bid.tender_id)
        .order_by(TenderRequirement.id)
        .all()
    )

    results = RulesEngine().evaluate_all(requirements, context)
    score, results = compute_score(results)

    # Integrity signals touching this bid feed the risk assessment as
    # evidence — review-grade patterns are serious risk indicators even
    # when the compliance score is high. Never fails the evaluation if
    # integrity analysis has not run (empty list).
    try:
        from app.services import integrity_service

        integrity_signals = [
            {
                "signal_type": f.signal_type,
                "severity": f.severity,
                "title": f.title,
            }
            for f in integrity_service.active_signals_for_bid(db, bid_id)
        ]
    except Exception:
        integrity_signals = []
    risk = risk_engine.assess(
        context, results, context.get("verification"),
        integrity_signals=integrity_signals,
    )

    # Persist: replace previous compliance results for this bid.
    db.query(ComplianceResult).filter(ComplianceResult.bid_id == bid_id).delete()
    for r in results:
        r["source"] = _result_source(r)
        db.add(
            ComplianceResult(
                bid_id=bid_id,
                requirement_id=r.get("requirement_id"),
                status=r["status"],
                weight=r.get("weight", 0.0),
                weighted_contribution=r.get("weighted_contribution", 0.0),
                evidence=r.get("evidence", []),
                explanation=r.get("explanation", ""),
                rule_applied=r.get("rule_applied", ""),
                source=r["source"],
                confidence=r.get("confidence", 0.95),
            )
        )

    existing = (
        db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid_id).one_or_none()
    )
    if existing is None:
        db.add(
            RiskAssessment(
                bid_id=bid_id,
                risk_level=risk["risk_level"],
                risk_score=risk["risk_score"],
                signals=risk["signals"],
                explanation=risk["explanation"],
            )
        )
    else:
        existing.risk_level = risk["risk_level"]
        existing.risk_score = risk["risk_score"]
        existing.signals = risk["signals"]
        existing.explanation = risk["explanation"]

    bid.compliance_score = score
    bid.risk_level = risk["risk_level"]
    bid.risk_reasons = risk["risk_reasons"]
    bid.risk_score = risk["risk_score"]

    append_audit(
        db,
        user_id=user_id,
        action="COMPLIANCE_EVALUATED",
        entity_type="bid_submission",
        entity_id=str(bid_id),
        metadata={"compliance_score": score, "requirement_count": len(results)},
    )
    append_audit(
        db,
        user_id=user_id,
        action="RISK_ASSESSED",
        entity_type="bid_submission",
        entity_id=str(bid_id),
        metadata={
            "risk_level": risk["risk_level"],
            "risk_score": risk["risk_score"],
            "signal_count": len(risk["signals"]),
        },
    )
    db.commit()

    return {"results": results, "compliance_score": score, "risk": risk}
