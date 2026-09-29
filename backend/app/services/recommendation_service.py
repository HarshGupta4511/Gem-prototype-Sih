"""AI-assisted recommendation (§12 of CONTRACT.md).

Deterministic mapping over STORED compliance + risk results — this service
NEVER recomputes pass/fail. Template text + RAG policy quotes; the human
officer always decides.
"""

from __future__ import annotations

PROVIDER = "rules+rag-demo"
FINAL_LINE = "Final decision remains with the Procurement Officer."

NON_PASS = ("MISSING", "EXPIRED", "MISMATCH", "REVIEW_REQUIRED")


def _load_items(db, results):
    from app.models.models import TenderRequirement

    req_ids = [r.requirement_id for r in results if r.requirement_id is not None]
    reqs = {}
    if req_ids:
        reqs = {
            t.id: t
            for t in db.query(TenderRequirement)
            .filter(TenderRequirement.id.in_(req_ids))
            .all()
        }
    items = []
    for r in results:
        t = reqs.get(r.requirement_id)
        items.append(
            {
                "requirement_id": r.requirement_id,
                "requirement_name": t.requirement_name if t else "",
                "description": t.description if t else "",
                "mandatory": bool(t.mandatory) if t else False,
                "weight": r.weight,
                "status": r.status,
                "explanation": r.explanation or "",
                "source": r.source or "",
            }
        )
    return items


def generate_recommendation(db, bid_id: int, *, user_id=None) -> dict:
    """Generate a recommendation from stored compliance/risk results.

    Returns {"recommendation", "reason", "evidence", "policy_context", "provider"}.
    """
    from app.models.models import BidSubmission, ComplianceResult, RiskAssessment, VerificationCheck
    from app.services import rag_service
    from app.services.audit_service import append_audit

    results = (
        db.query(ComplianceResult)
        .filter(ComplianceResult.bid_id == bid_id)
        .order_by(ComplianceResult.id)
        .all()
    )
    if not results:
        raise ValueError(
            f"No compliance results stored for bid {bid_id}; "
            "run compliance evaluation first."
        )
    risk = db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid_id).one_or_none()

    items = _load_items(db, results)
    signals = list(risk.signals or []) if risk else []
    risk_level = risk.risk_level if risk else "LOW"

    # Deterministic mapping (§12).
    blacklisted = any(s.get("code") in ("BLACKLISTED", "DEBARRED") for s in signals)
    fail_mandatory = any(i["status"] == "FAIL" and i["mandatory"] for i in items)
    non_pass = [i for i in items if i["status"] in NON_PASS]
    medium_plus = any((s.get("severity") or "") in ("medium", "high") for s in signals)

    if risk_level == "CRITICAL" or blacklisted:
        recommendation = "NOT_RECOMMENDED"
    elif fail_mandatory:
        recommendation = "NOT_RECOMMENDED"
    elif non_pass:
        recommendation = "REVIEW_REQUIRED"
    elif medium_plus:
        recommendation = "PROCEED_WITH_CONDITIONS"
    else:
        recommendation = "PROCEED"

    # Evidence-backed reason bullets.
    bullets = []
    for i in items:
        if i["status"] != "PASS":
            expl = i["explanation"]
            prefix = f"{i['status']} — "
            if expl.startswith(prefix):  # explanations already carry the status lead
                expl = expl[len(prefix):]
            bullets.append(
                f"• {i['requirement_name']}: {i['status']} — {expl} "
                f"(Source: {i['source']})"
            )
    for s in signals:
        if (s.get("severity") or "") in ("critical", "high"):
            msg = s.get("message", "")
            # Signal messages embed the requirement explanation (which carries a
            # "STATUS — " lead); drop that duplication for readability.
            for st in ("PASS", "FAIL", "MISSING", "EXPIRED", "MISMATCH", "REVIEW_REQUIRED"):
                msg = msg.replace(f": {st} — ", ": ")
            bullets.append(f"• Risk signal {s.get('code')}: {msg}")
    if recommendation == "PROCEED":
        bullets.append(
            f"• All {len(items)} requirements evaluated PASS with no blocking risk signals."
        )
    elif recommendation == "PROCEED_WITH_CONDITIONS":
        bullets.append(
            "• All requirements PASS; medium-severity risk signals require "
            "officer attention before award."
        )
    elif recommendation == "NOT_RECOMMENDED" and blacklisted:
        bullets.append(
            "• Blacklist/debarment signal present — the bid cannot proceed "
            "without officer review of the listing."
        )

    # RAG policy context for each non-PASS requirement (top-1 chunk each).
    policy_context = []
    seen = set()
    for i in non_pass:
        query = f"{i['requirement_name']} {i['description']}".strip()
        try:
            res = rag_service.search(db, query, top_k=1)
        except Exception:
            continue
        for hit in res.get("results", []):
            key = (hit.get("doc_id"), hit.get("chunk"))
            if key in seen:
                continue
            seen.add(key)
            policy_context.append(
                {
                    "title": hit.get("doc_title"),
                    "chunk": hit.get("chunk"),
                    "score": hit.get("score"),
                }
            )

    check_ids = [
        row[0]
        for row in db.query(VerificationCheck.id)
        .filter(VerificationCheck.bid_id == bid_id)
        .all()
    ]
    evidence = {
        "requirement_ids": [i["requirement_id"] for i in non_pass],
        "check_ids": check_ids,
    }
    # API-facing shape (contract §5: evidence is a list): flat reference list.
    evidence_refs = [{"type": "requirement", "id": rid} for rid in evidence["requirement_ids"]]
    evidence_refs += [{"type": "verification_check", "id": cid} for cid in evidence["check_ids"]]

    reason = "\n".join(bullets) + "\n\n" + FINAL_LINE

    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"BidSubmission {bid_id} not found")
    bid.recommendation = recommendation
    bid.recommendation_reason = reason
    bid.recommendation_evidence = evidence_refs

    append_audit(
        db,
        user_id=user_id,
        action="RECOMMENDATION_GENERATED",
        entity_type="bid_submission",
        entity_id=str(bid_id),
        metadata={"recommendation": recommendation, "non_pass_count": len(non_pass)},
    )
    db.commit()

    return {
        "recommendation": recommendation,
        "reason": reason,
        "evidence": evidence_refs,
        "policy_context": policy_context,
        "provider": PROVIDER,
    }
