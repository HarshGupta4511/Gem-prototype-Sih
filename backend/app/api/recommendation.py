"""AI-assisted recommendation endpoint (CONTRACT.md §5: Recommendation)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models.models import BidSubmission, User
from app.schemas.schemas import RecommendationOut
from app.services import recommendation_service

router = APIRouter(prefix="/api/recommendation", tags=["recommendation"])

# Generating a recommendation is an internal evaluation action: procurement
# staff only. Read-only roles (auditor) must not trigger it.
_RECOMMENDER = require_roles("PROCUREMENT_OFFICER", "VERIFIER")


@router.post("/{bid_id}", response_model=RecommendationOut)
def recommend(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_RECOMMENDER),
):
    """Generate the AI-assisted recommendation from stored compliance + risk.

    Never recomputes pass/fail; the human officer decides.
    """
    if db.get(BidSubmission, bid_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    result = recommendation_service.generate_recommendation(db, bid_id, user_id=user.id)
    return RecommendationOut(**result)
