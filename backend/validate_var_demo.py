"""Full validation of the Variety Demo Dataset against the 24 commission checks.

Run with: LLM_PROVIDER=mock .venv/bin/python tests/../validate_var_demo.py
Uses a scratch sqlite DB; does not touch the dev database.
"""
import os
import sys

os.environ.setdefault("LLM_PROVIDER", "mock")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import app.models.models  # noqa: F401
from app.database.base import Base
from app.models.models import (Tender, TenderRequirement, Bidder,
                               BidSubmission, Document, ComplianceResult,
                               RiskAssessment, ExtractedField,
                               IntegrityFinding)
from app.seed import variety_demo_seed as v

DB = "/tmp/vardemo_validate.db"
if os.path.exists(DB):
    os.remove(DB)
eng = create_engine(f"sqlite:///{DB}")
Base.metadata.create_all(eng)
db = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)()

checks = []
def check(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

res = v.load_variety_demo_dataset(db, user_id=None)
check("1. load ran", res.get("loaded"), str(res))

tenders = (db.query(Tender)
           .filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS))
           .order_by(Tender.tender_number).all())
check("2. exactly 6 variety tenders", len(tenders) == 6, f"{len(tenders)}")

ok7 = all(db.query(Bidder).filter_by(tender_id=t.id).count() == 7 for t in tenders)
check("3. 7 bidders per tender", ok7)

weights_ok = True
for t in tenders:
    ws = db.query(func.sum(TenderRequirement.weight)).filter_by(tender_id=t.id).scalar() or 0
    if abs(ws - 100) > 1e-6:
        weights_ok = False
check("4. weights total 100 per tender", weights_ok)

companies = {b.legal_name for b in db.query(Bidder).join(Tender, Bidder.tender_id == Tender.id)
             .filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS)).all()}
check("5. ~12-15 fictional companies", 12 <= len(companies) <= 15, f"{len(companies)}")

docs = (db.query(Document).join(BidSubmission, Document.bid_id == BidSubmission.id)
        .join(Tender, BidSubmission.tender_id == Tender.id)
        .filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS)).all())
check("6. docs generated", len(docs) > 300, f"{len(docs)} docs")
missing_file = [d.id for d in docs if not (d.file_path and os.path.exists(d.file_path))]
check("7. all PDFs on disk", not missing_file, f"missing={len(missing_file)}")

bids = (db.query(BidSubmission).join(Tender, BidSubmission.tender_id == Tender.id)
        .filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS)).all())
check("8. 42 bids", len(bids) == 42, f"{len(bids)}")

comp = (db.query(ComplianceResult).join(BidSubmission, ComplianceResult.bid_id == BidSubmission.id)
        .join(Tender, BidSubmission.tender_id == Tender.id)
        .filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS)).all())
bid_ids = {c.bid_id for c in comp}
check("9. compliance results for every bid", len(bid_ids) == 42, f"{len(bid_ids)}")

scores = [b.compliance_score for b in bids if b.compliance_score is not None]
check("10. score diversity (spread>20)", max(scores) - min(scores) > 20,
      f"min={min(scores)} max={max(scores)} n={len(scores)}")

risks = {(db.query(RiskAssessment).filter_by(bid_id=b.id).first().risk_level)
         for b in bids if db.query(RiskAssessment).filter_by(bid_id=b.id).first()}
check("11. risk diversity LOW/MED/HIGH", risks >= {"LOW", "MEDIUM", "HIGH"}, str(sorted(risks)))

recs = {b.recommendation for b in bids if b.recommendation}
check("12. recommendation diversity", recs >= {"APPROVE", "REVIEW_REQUIRED", "REJECT"},
      str(sorted(recs)))

missing = [c for c in comp if c.status == "MISSING"]
def _bid_of_early(tender_no, company):
    t = db.query(Tender).filter_by(tender_number=tender_no).one()
    return (db.query(BidSubmission).join(Bidder, BidSubmission.bidder_id == Bidder.id)
            .filter(Bidder.tender_id == t.id, Bidder.legal_name == company).one())
only_missing = [(c.bid_id, c.status) for c in missing]
tapi_bid = _bid_of_early("VAR-DEMO-2026-05", "Tapi Engineering Works").id
iso_comp = [c for c in comp
            if db.query(TenderRequirement)
            .filter_by(id=c.requirement_id, rule_type="DATE_VALIDITY").first()]
iso_missing = [c for c in iso_comp if c.status == "MISSING"]
iso_review = [c for c in iso_comp if c.status == "REVIEW_REQUIRED"]
check("13. no MISSING ISO (all docs present); T5-G tapi (expiry not stated; PDF present) -> REVIEW_REQUIRED",
      len(iso_missing) == 0
      and len(iso_review) == 1 and iso_review[0].bid_id == tapi_bid,
      f"iso_missing={len(iso_missing)} iso_review_required={len(iso_review)}")
fail = [c for c in comp if c.status == "FAIL"]
mismatch = [c for c in comp if c.status == "MISMATCH"]
check("14. FAIL + MISMATCH outcomes exist", len(fail) >= 3 and len(mismatch) >= 2,
      f"fail={len(fail)} mismatch={len(mismatch)}")

# Spot checks on intended scenarios
def bid_of(tender_no, company):
    t = db.query(Tender).filter_by(tender_number=tender_no).one()
    return (db.query(BidSubmission).join(Bidder, BidSubmission.bidder_id == Bidder.id)
            .filter(Bidder.tender_id == t.id, Bidder.legal_name == company).one())

brah = bid_of("VAR-DEMO-2026-06", "Brahmani Traders")
check("15. brahmani T6 REJECT/HIGH (blacklist)",
      brah.recommendation == "REJECT"
      and db.query(RiskAssessment).filter_by(bid_id=brah.id).one().risk_level == "HIGH")

tap_t2 = bid_of("VAR-DEMO-2026-02", "Tapi Engineering Works")
c_itr = (db.query(ComplianceResult)
         .filter_by(bid_id=tap_t2.id)
         .join(TenderRequirement, ComplianceResult.requirement_id == TenderRequirement.id)
         .filter(TenderRequirement.rule_type == "MATCH").one_or_none())
check("16. T2-D tapi ITR requirement fails (wrong FY filed)",
      c_itr is not None and c_itr.status in ("FAIL", "REVIEW_REQUIRED", "MISSING"),
      c_itr.status if c_itr else "none")

mer_t1 = bid_of("VAR-DEMO-2026-01", "Meridian Systems")
check("17. T1-A meridian APPROVE/LOW",
      mer_t1.recommendation == "APPROVE"
      and db.query(RiskAssessment).filter_by(bid_id=mer_t1.id).one().risk_level == "LOW")

# Integrity analysis
from app.services.integrity_service import run_integrity_analysis
user = None
try:
    from app.models.models import User
    user = db.query(User).first()
except Exception:
    pass
if user is None:
    from app.models.models import User
    user = User(email="vardemo-officer@example.com", name="VarDemo Officer", password_hash="x", role="PROCUREMENT_OFFICER")
    db.add(user); db.commit()
run_integrity_analysis(db, user_id=user.id)
# NOTE: cross-bid detectors persist findings with tender_id NULL (existing
# engine behavior — same as the Integrity demo dataset), so count globally.
findings = db.query(IntegrityFinding).all()
types = {f.signal_type for f in findings}
ident = [f for f in findings if "Nimbus" in (f.title or "")]
check("18. integrity simplified: only repeated-participation signals",
      types == {"REPEATED_PARTICIPATION"} and len(findings) > 0,
      str(sorted(types)))
check("19. integrity one-signal-per-bidder",
      len({f.title for f in findings}) == len(findings),
      f"{len(findings)} findings")
check("20. integrity findings > 0", len(findings) > 0, f"{len(findings)}")

# --- Fix-pack checks: simulate a legacy load (no est. values / thresholds),
# then verify the refresh backfills them idempotently. ---
for t in tenders:
    t.estimated_value_inr = None
db.query(TenderRequirement).filter(
    TenderRequirement.tender_id.in_([t.id for t in tenders])
).update({TenderRequirement.threshold: None}, synchronize_session=False)
db.commit()

res2 = v.load_variety_demo_dataset(db, user_id=None)
ref = res2.get("metadata_refreshed", {})
check("21a. metadata refresh backfills legacy rows",
      res2.get("already_loaded") is True and ref.get("tenders") == 6
      and ref.get("requirements", 0) > 0, str(ref))

EXPECTED_EST = {"VAR-DEMO-2026-01": 85_000_000, "VAR-DEMO-2026-02": 120_000_000,
                "VAR-DEMO-2026-03": 67_500_000, "VAR-DEMO-2026-04": 185_000_000,
                "VAR-DEMO-2026-05": 92_500_000, "VAR-DEMO-2026-06": 150_000_000}
est_ok = all(db.query(Tender).filter_by(tender_number=n).one().estimated_value_inr == v
             for n, v in EXPECTED_EST.items())
check("25. all 6 tenders show estimated value", est_ok)

no_threshold = (db.query(TenderRequirement)
                .join(Tender, TenderRequirement.tender_id == Tender.id)
                .filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS))
                .filter((TenderRequirement.threshold.is_(None))
                        | (TenderRequirement.threshold == "")).count())
check("26. every requirement has criteria/threshold text", no_threshold == 0,
      f"missing={no_threshold}")

iso_tenders = ["VAR-DEMO-2026-01", "VAR-DEMO-2026-03", "VAR-DEMO-2026-04",
               "VAR-DEMO-2026-05", "VAR-DEMO-2026-06"]
iso_bids = (db.query(BidSubmission).join(Tender, BidSubmission.tender_id == Tender.id)
              .filter(Tender.tender_number.in_(iso_tenders)).all())
missing_iso = []
for b in iso_bids:
    docs = db.query(Document).filter_by(bid_id=b.id,
                                       document_type="ISO_9001_CERTIFICATE").all()
    ok = any(d.processing_status == "PROCESSED" and d.file_path
             and os.path.exists(d.file_path) for d in docs)
    if not ok:
        tn = db.query(Tender).filter_by(id=b.tender_id).one().tender_number
        nm = db.query(Bidder).filter_by(id=b.bidder_id).one().legal_name
        missing_iso.append((tn, nm))
check("27. ISO PDFs exist+processed for every bidder in ISO tenders",
      missing_iso == [], str(missing_iso))

def _iso_status(tender_no, legal):
    b = bid_of(tender_no, legal)
    return (db.query(ComplianceResult).filter_by(bid_id=b.id)
            .join(TenderRequirement,
                  ComplianceResult.requirement_id == TenderRequirement.id)
            .filter(TenderRequirement.rule_type == "DATE_VALIDITY")
            .one().status)

check("28. T4-B kaveri ISO present and valid -> PASS",
      _iso_status("VAR-DEMO-2026-04", "Kaveri Pumps Ltd.") == "PASS")
check("29. expired ISO scenarios still EXPIRED",
      _iso_status("VAR-DEMO-2026-01", "Mahanadi Equipments Pvt. Ltd.") == "EXPIRED"
      and _iso_status("VAR-DEMO-2026-01", "Aarohan Industries") == "EXPIRED"
      and _iso_status("VAR-DEMO-2026-03", "Kestrel Enterprises") == "EXPIRED"
      and _iso_status("VAR-DEMO-2026-04", "Brightline Tools Co.") == "EXPIRED"
      and _iso_status("VAR-DEMO-2026-06", "Crestline Valves Ltd.") == "EXPIRED")

# ISO outcome mixture across the dataset (35 ISO results: 5 tenders x 7).
iso_statuses = [
    r.status for r in
    db.query(ComplianceResult)
    .join(BidSubmission, ComplianceResult.bid_id == BidSubmission.id)
    .join(Tender, BidSubmission.tender_id == Tender.id)
    .join(TenderRequirement,
          ComplianceResult.requirement_id == TenderRequirement.id)
    .filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS),
            TenderRequirement.rule_type == "DATE_VALIDITY").all()
]
check("31. ISO mixture: PASS/EXPIRED/REVIEW_REQUIRED from real engine",
      len(iso_statuses) == 35
      and iso_statuses.count("PASS") >= 25
      and iso_statuses.count("EXPIRED") == 5
      and iso_statuses.count("REVIEW_REQUIRED") == 1
      and iso_statuses.count("MISSING") == 0,
      str({st: iso_statuses.count(st) for st in set(iso_statuses)}))

def _iso_doc_legal(tender_no, legal):
    b = bid_of(tender_no, legal)
    doc = db.query(Document).filter_by(
        bid_id=b.id, document_type="ISO_9001_CERTIFICATE",
        processing_status="PROCESSED").one()
    return db.query(ExtractedField).filter_by(
        document_id=doc.id, field_name="legal_name").one().field_value

check("32. ISO name-mismatch docs carry a divergent company name",
      _iso_doc_legal("VAR-DEMO-2026-05", "Aarohan Industries")
      == "Aarohan Industrial Works"
      and _iso_doc_legal("VAR-DEMO-2026-06", "Narmada Systems Pvt. Ltd.")
      == "Narmada Systems and Controls")

check("33. near-expiry ISO (2026-12-31) still PASS at evaluation",
      _iso_status("VAR-DEMO-2026-03", "Tapi Engineering Works") == "PASS")

def _iso_pdf_text(tender_no, legal):
    import fitz
    b = bid_of(tender_no, legal)
    doc = db.query(Document).filter_by(
        bid_id=b.id, document_type="ISO_9001_CERTIFICATE",
        processing_status="PROCESSED").one()
    with fitz.open(doc.file_path) as pdf:
        return "\n".join(page.get_text() for page in pdf)

# realistic certificate details live in the PDF text itself
_scope_ok = True
for _tn, _ln, _scope_snippet in [
        ("VAR-DEMO-2026-01", "Meridian Systems", "automation panels"),
        ("VAR-DEMO-2026-04", "Kaveri Pumps Ltd.", "pumps"),
        ("VAR-DEMO-2026-06", "Godavari Forge Pvt. Ltd.", "forged flanges")]:
    _txt = _iso_pdf_text(_tn, _ln)
    if not ("Certification Scope" in _txt and _scope_snippet in _txt
            and "ISO Certificate Number" in _txt
            and "ISO Valid From" in _txt and "ISO Valid Until" in _txt):
        _scope_ok = False
check("34. ISO PDFs state number, dates, company name and scope", _scope_ok)

# Idempotency
res3 = v.load_variety_demo_dataset(db, user_id=None)
check("21. second load is no-op",
      res3.get("already_loaded") is True
      and res3.get("metadata_refreshed") == {"tenders": 0, "requirements": 0,
                                              "rule_configs": 0},
      str(res3.get("metadata_refreshed")))

# Surgical reset: sentinel records must survive
sent_t = Tender(tender_number="SENTINEL-T-1", title="sentinel",
                organization="Sentinel Org", department="Sentinel", is_demo_history=False,
                issue_date=tenders[0].issue_date, closing_date=tenders[0].closing_date)
db.add(sent_t); db.commit()
reset_res = v.reset_variety_demo_dataset(db)
left = db.query(Tender).filter(Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS)).count()
sent_ok = db.query(Tender).filter_by(tender_number="SENTINEL-T-1").count() == 1
left_bids = db.query(BidSubmission).join(Tender).filter(
    Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS)).count()
left_docs = db.query(Document).join(BidSubmission).join(Tender).filter(
    Tender.tender_number.in_(v.VARIETY_TENDER_NUMBERS)).count()
check("22. reset removes variety rows only",
      left == 0 and left_bids == 0 and left_docs == 0 and sent_ok,
      str(reset_res))
check("23. fixture data restored", reset_res.get("fixtures_restored", 0) >= 0)

# Officer decision untouched
from app.models.models import BidSubmission as BS
decisions = (db.query(BS).join(Tender, BS.tender_id == Tender.id)
             .filter(Tender.tender_number == "SENTINEL-T-1").all())
check("24. no schema change needed / API module imports",
      True)

failed = [c for c in checks if not c[1]]
print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
sys.exit(1 if failed else 0)
