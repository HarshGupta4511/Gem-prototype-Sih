"""Risk read service — returns the stored risk assessment for a bid."""

from __future__ import annotations


def get_risk(db, bid_id: int) -> dict | None:
    """Read the persisted RiskAssessment for a bid. None if never assessed."""
    from app.models.models import BidSubmission, RiskAssessment

    ra = db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid_id).one_or_none()
    if ra is None:
        return None
    bid = db.get(BidSubmission, bid_id)
    created_at = getattr(ra, "created_at", None)
    return {
        "id": ra.id,
        "bid_id": ra.bid_id,
        "risk_level": ra.risk_level,
        "risk_score": ra.risk_score,
        "signals": ra.signals or [],
        "risk_reasons": (bid.risk_reasons if bid is not None else None) or [],
        "explanation": ra.explanation,
        "created_at": created_at.isoformat() if created_at else None,
    }
