"""BidVerify FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    audit,
    auth,
    bids,
    compliance,
    consistency,
    dashboard,
    documents,
    integrity,
    officer,
    recommendation,
    seed,
    tenders,
    verification,
    verification_summaries,
)
from app.core.config import is_dev_secret, settings
from app.database.base import Base
from app.database.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def _ensure_tender_wizard_columns() -> None:
    """Additive, idempotent migration for the tender-wizard fields.

    ``create_all`` does not add columns to an existing ``tenders`` table, so
    databases created before the wizard shipped would otherwise miss the new
    nullable columns. This adds only the missing ones and never touches data.
    """
    from sqlalchemy import inspect, text

    wanted = {
        "tender_type": "VARCHAR(20)",
        "bid_type": "VARCHAR(20)",
        "emd_amount_inr": "INTEGER",
        "delivery_period": "VARCHAR(255)",
        "place_of_delivery": "VARCHAR(255)",
    }
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("tenders")}
    except Exception:
        logger.exception("Could not inspect tenders table; skipping column migration")
        return
    missing = [name for name in wanted if name not in existing]
    if not missing:
        return
    try:
        with engine.begin() as conn:
            for name in missing:
                conn.execute(text(f"ALTER TABLE tenders ADD COLUMN {name} {wanted[name]}"))
        logger.info("Added tender columns: %s", ", ".join(missing))
    except Exception:
        logger.exception("Failed to add tender wizard columns")


def _ensure_policy_context_column() -> None:
    """Additive, idempotent migration for bid_submissions.policy_context.

    ``create_all`` does not add columns to an existing ``bid_submissions``
    table, so databases created before the source-grounded RAG policy context
    shipped would otherwise miss the new nullable JSON column. Adds it only
    when missing and never touches existing data.
    """
    from sqlalchemy import inspect, text

    try:
        existing = {c["name"] for c in inspect(engine).get_columns("bid_submissions")}
    except Exception:
        logger.exception("Could not inspect bid_submissions table; skipping column migration")
        return
    if "policy_context" in existing:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE bid_submissions ADD COLUMN policy_context JSON"))
        logger.info("Added policy_context column to bid_submissions")
    except Exception:
        logger.exception("Could not add policy_context column; continuing")


def _ensure_demo_history_column() -> None:
    """Additive, idempotent migration for tenders.is_demo_history.

    Flags the clearly-labelled synthetic DEMO procurement history used by the
    integrity engine. Hidden from the normal tender list; included in analysis.
    """
    from sqlalchemy import inspect, text

    try:
        existing = {c["name"] for c in inspect(engine).get_columns("tenders")}
    except Exception:
        logger.exception("Could not inspect tenders table; skipping column migration")
        return
    if "is_demo_history" in existing:
        return
    try:
        dialect = engine.dialect.name
        coldef = (
            "is_demo_history BOOLEAN DEFAULT 0"
            if dialect == "sqlite"
            else "is_demo_history BOOLEAN DEFAULT FALSE"
        )
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE tenders ADD COLUMN {coldef}"))
        logger.info("Added is_demo_history column to tenders")
    except Exception:
        logger.exception("Could not add is_demo_history column; continuing")


def _backfill_tender_wizard_fields(db=None) -> None:
    """Fill Step-1 wizard fields on demo tenders that predate the wizard.

    Databases seeded before the tender-wizard fields existed have NULLs in
    the new columns, so Tender Detail would show blanks for the synthetic
    demo tenders. This fills only NULL fields, only for the known demo
    tender numbers in ``DEMO_TENDER_WIZARD_FIELDS`` — officer-created
    tenders are never touched. Idempotent.
    """
    from app.models.models import Tender
    from app.seed.seed_data import DEMO_TENDER_WIZARD_FIELDS

    own_session = db is None
    if own_session:
        from app.database.session import SessionLocal
        db = SessionLocal()
    try:
        for number, fields in DEMO_TENDER_WIZARD_FIELDS.items():
            tender = db.query(Tender).filter(Tender.tender_number == number).first()
            if tender is None:
                continue
            changed = False
            for field, value in fields.items():
                if getattr(tender, field, None) is None and value is not None:
                    setattr(tender, field, value)
                    changed = True
            if changed:
                db.commit()
                logger.info("Backfilled tender-wizard fields for %s", number)
    except Exception:
        logger.exception("Tender-wizard field backfill failed; continuing")
        db.rollback()
    finally:
        if own_session:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_tender_wizard_columns()
    _ensure_policy_context_column()
    _ensure_demo_history_column()
    _backfill_tender_wizard_fields()
    if is_dev_secret():
        logger.warning("JWT_SECRET is the dev default — set JWT_SECRET env var")
    # Demo bootstrap: seed the database on startup so the app is immediately
    # usable (docker compose up → working demo). run_seed is idempotent per
    # tender — it backfills any demo tender missing from the database, so
    # databases seeded before a new demo tender existed still get it.
    # Disable with AUTO_SEED=false.
    if settings.AUTO_SEED:
        db = SessionLocal()
        try:
            from app.seed.seed_data import run_seed
            result = run_seed(db)
            logger.info("Demo seed check complete: %s", result)
        except Exception:
            logger.exception("Auto-seed failed; continuing with existing database")
        finally:
            db.close()
    yield


app = FastAPI(
    title="BidVerify — AI-Powered Bid Compliance Verification Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        # Hosted frontend(s), e.g. Render: set CORS_ORIGINS env var.
        *[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    tenders.router,
    bids.router,
    documents.router,
    verification.router,
    compliance.router,
    recommendation.router,
    officer.router,
    audit.router,
    dashboard.router,
    seed.router,
    verification_summaries.router,
    integrity.router,
    consistency.router,
):
    app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
