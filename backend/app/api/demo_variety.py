"""Variety Demo Dataset API.

Surgical load/status/reset for the VAR-DEMO variety showcase dataset
(6 tenders x 7 bidders demonstrating the full matrix of document,
verification, compliance, risk, recommendation and integrity outcomes).

Single role: PROCUREMENT_OFFICER. No DB schema change. Reset touches
only variety-demo rows (idempotent ``/load`` too: a second load is a
no-op unless reset was used in between).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_officer
from app.seed.variety_demo_seed import (
    load_variety_demo_dataset,
    reset_variety_demo_dataset,
    variety_demo_dataset_status,
)

router = APIRouter(
    prefix="/api/demo-variety",
    tags=["demo-variety"],
)

_OFFICER = require_officer()


@router.post("/dataset")
def load_dataset(db: Session = Depends(get_db),
                 user=Depends(_OFFICER)):
    """Idempotently load the 6-tender variety demo dataset.

    Returns 409 if a load is already in progress (double-click protection).
    """
    try:
        result = load_variety_demo_dataset(db, user_id=user.id)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500,
                            detail=f"Variety dataset load failed: {exc}")
    if result.get("already_running"):
        raise HTTPException(status_code=409, detail=result["reason"])
    return {
        "message": ("Variety demo dataset already loaded."
                    if result["already_loaded"]
                    else "Variety demo dataset loaded successfully."),
        **result,
    }


@router.get("/dataset")
def dataset_status(db: Session = Depends(get_db),
                   user=Depends(_OFFICER)):
    return variety_demo_dataset_status(db)


@router.delete("/dataset")
def delete_dataset(db: Session = Depends(get_db),
                   user=Depends(_OFFICER)):
    """Surgically reset only variety-demo rows (tenders, bids, bidders,
    documents, verifications, compliance, risk, recommendations,
    integrity findings on this dataset, fixtures)."""
    try:
        result = reset_variety_demo_dataset(db)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500,
                            detail=f"Variety dataset reset failed: {exc}")
    return {
        "message": "Variety demo dataset reset successfully.",
        **result,
    }
