"""Demo seed endpoint (CONTRACT.md §5: Seed)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_officer
from app.models.models import User
from app.services import audit_service

router = APIRouter(prefix="/api/seed", tags=["seed"])

_OFFICER = require_officer()


def _seed_data():
    """Lazy import: seed_data is built in parallel; fail loudly if absent."""
    try:
        from app.seed import seed_data  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Seed data module is not available",
        ) from exc
    return seed_data


@router.post("")
def run_seed(
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Run the demo seed. Idempotent per tender: tenders that already exist
    are skipped, missing demo tenders are backfilled."""
    counts = _seed_data().run_seed(db)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="SEED",
        entity_type="tender",
        entity_id="seed",
        metadata={
            "tenders": counts.get("tenders", 0),
            "bidders": counts.get("bidders", 0),
            "documents": counts.get("documents", 0),
        },
    )
    return {"seeded": True, "counts": counts}
