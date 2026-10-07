"""AI-assisted recommendation.

Comparative, per-tender evaluation over STORED compliance + risk results —
this service NEVER recomputes pass/fail. Bidders are compared only within
the same tender using real persisted data:

- Disqualified (blacklisted/debarred, or a mandatory FAIL) → REJECT
- Strongest eligible bidder → APPROVE
- Everyone else (middle, ambiguous, or close cases) → REVIEW_REQUIRED

A mandatory FAIL or MISSING always prevents APPROVE. Serious risk or
integrity issues are never ignored because of a high compliance score.

Template text + RAG policy quotes; the human officer always decides.
Risk Level, AI Recommendation and Officer Decision remain separate.
"""

from __future__ import annotations

PROVIDER = "rules+policy-retrieval"
FINAL_LINE = "Final decision remains with the Procurement Officer."

NON_PASS = ("MISSING", "EXPIRED", "MISMATCH", "REVIEW_REQUIRED")

# Retrieval fires for every non-PASS compliance finding (including FAIL —
# a failed finding is exactly when policy context matters most) and for
# critical/high-severity blacklist or debarment risk signals.
RETRIEVAL_STATUSES = NON_PASS + ("FAIL",)
SIGNAL_RETRIEVAL_CODES = ("BLACKLISTED", "DEBARRED")

# Topic -> authoritative document titles allowed for retrieval. Only topics
# with a verified authoritative source are listed here; findings on any
# other topic (GST, PAN, OEM authorization, turnover, missing documents, ...)
# produce no retrieval at all — "No authoritative policy source is currently
# configured for this topic." Matching is keyword-based over the requirement
# name, description, threshold and category.
RETRIEVAL_TOPICS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("make in india", "mii", "local content", "class-i", "class-ii"),
        ("Public Procurement (Preference to Make in India), Order 2017 — Revision dated 19.07.2024",),
    ),
    (
        ("udyam", "msme", "micro small", "small medium"),
        ("Udyam Registration — MSME Classification (Ministry of MSME)",),
    ),
    (
        ("blacklist", "debar"),
        (
            "General Financial Rules, 2017 — Procurement Provisions",
            "Debarment of Firms from Bidding — DoE Guidelines",
        ),
    ),
]


def _retrieval_topic(item: dict) -> tuple[str, ...] | None:
    """Authoritative document titles configured for the finding's topic.

    Returns None when no authoritative policy source is configured.
    """
    haystack = " ".join(
        [
            str(item.get("requirement_name") or ""),
            str(item.get("description") or ""),
            str(item.get("threshold") or ""),
            str(item.get("expected_value") or ""),
            str(item.get("category") or ""),
        ]
    ).lower()
    for keywords, titles in RETRIEVAL_TOPICS:
        if any(k in haystack for k in keywords):
            return titles
    return None


def _topic_titles(keywords: tuple[str, ...]) -> tuple[str, ...] | None:
    """Document titles for a known topic entry (lookup by its keywords)."""
    for entry_keywords, titles in RETRIEVAL_TOPICS:
        if entry_keywords == keywords:
            return titles
    return None

# Minimum cosine-similarity score for a policy chunk to be cited. Prevents
# top-k from being returned merely for being the least irrelevant chunk.
# Retrieval is additionally scoped to the authoritative documents configured
# for the finding's topic, so this gate only filters weak matches within
# an already topically-coherent corpus. Calibrated against the seeded
# authoritative corpus (TF-IDF path).
MIN_RELEVANCE = 0.10


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
        evidence_items = list(r.evidence or []) if isinstance(r.evidence, list) else []
        doc_types = sorted(
            {
                str(e.get("document_type") or e.get("doc_type") or "")
                for e in evidence_items
                if isinstance(e, dict)
            }
            - {""}
        )
        items.append(
            {
                "requirement_id": r.requirement_id,
                "requirement_name": t.requirement_name if t else "",
                "description": t.description if t else "",
                "category": t.category if t else "",
                "threshold": t.threshold if t else None,
                "expected_value": t.expected_value if t else None,
                "mandatory": bool(t.mandatory) if t else False,
                "weight": r.weight,
                "status": r.status,
                "explanation": r.explanation or "",
                "source": r.source or "",
                "document_types": doc_types,
            }
        )
    return items


def _retrieval_query(item: dict) -> str:
    """Build the RAG query from the full finding (§7): requirement name,
    criteria/threshold, compliance finding/explanation, verification finding,
    document type(s), extracted value, and status."""
    parts = [
        item.get("requirement_name") or "",
        item.get("threshold") or "",
        item.get("expected_value") or "",
        item.get("description") or "",
        item.get("status") or "",
        item.get("explanation") or "",
        item.get("source") or "",
        " ".join(item.get("document_types") or []),
    ]
    return " ".join(p for p in parts if p).strip()


def _policy_citation(hit: dict) -> dict:
    """Shape a retrieval hit as a citable policy context record."""
    return {
        "title": hit.get("doc_title"),
        "authority": hit.get("authority"),
        "source_url": hit.get("source_url"),
        "document_type": hit.get("document_type"),
        "version": hit.get("version"),
        "publication_date": hit.get("publication_date"),
        "effective_date": hit.get("effective_date"),
        "section": hit.get("section"),
        "why_relevant": hit.get("why_relevant"),
        "excerpt": hit.get("excerpt"),
        "score": hit.get("score"),
    }


def _risk_rank(level: str | None) -> int:
    """Order risk levels for comparison (lower is better). Legacy CRITICAL
    stored values rank as HIGH."""
    return {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 2}.get(
        (level or "").upper(), 3
    )


def _bid_assessment(db, bid) -> dict | None:
    """Build the comparative assessment for one bid from stored data.

    Returns None when the bid has no stored compliance results (cannot be
    evaluated). Never raises on missing/null fields.
    """
    from app.models.models import ComplianceResult, RiskAssessment

    results = (
        db.query(ComplianceResult)
        .filter(ComplianceResult.bid_id == bid.id)
        .order_by(ComplianceResult.id)
        .all()
    )
    if not results:
        return None
    risk = (
        db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid.id).one_or_none()
    )
    signals = list(risk.signals or []) if risk else []
    risk_level = (risk.risk_level if risk else "LOW") or "LOW"

    items = _load_items(db, results)
    blacklisted = any(s.get("code") in ("BLACKLISTED", "DEBARRED") for s in signals)
    fail_mandatory = any(i["status"] == "FAIL" and i["mandatory"] for i in items)
    missing_mandatory = any(i["status"] == "MISSING" and i["mandatory"] for i in items)
    non_pass = [i for i in items if i["status"] in NON_PASS]
    score = bid.compliance_score
    score = float(score) if score is not None else 0.0

    return {
        "bid": bid,
        "items": items,
        "signals": signals,
        "risk_level": risk_level,
        "score": score,
        "blacklisted": blacklisted,
        "fail_mandatory": fail_mandatory,
        "missing_mandatory": missing_mandatory,
        "non_pass": non_pass,
        "non_pass_count": len(non_pass),
        # Disqualified: blacklist/debarment or a failed mandatory requirement.
        "disqualified": blacklisted or fail_mandatory,
        # Eligible for APPROVE: not disqualified, no mandatory evidence
        # missing, and no serious unresolved risk.
        "approve_eligible": (
            not blacklisted
            and not fail_mandatory
            and not missing_mandatory
            and _risk_rank(risk_level) < 2
        ),
    }


def _rank_key(a: dict) -> tuple:
    """Strongest first: compliance score, then lower risk, then fewer
    non-PASS items, then bid id for determinism."""
    return (-a["score"], _risk_rank(a["risk_level"]), a["non_pass_count"], a["bid"].id)


def generate_recommendation(db, bid_id: int, *, user_id=None) -> dict:
    """Generate a comparative per-tender recommendation.

    Evaluates every bid in the tender with stored compliance results and
    assigns APPROVE / REJECT / REVIEW_REQUIRED. The requested bid's result
    is returned; all evaluated bids in the tender are persisted so the
    ranking stays consistent. Returns {"recommendation", "reason",
    "evidence", "policy_context", "provider"}.
    """
    from app.models.models import BidSubmission, VerificationCheck
    from app.services.audit_service import append_audit

    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"BidSubmission {bid_id} not found")

    # All bids in the same tender — evaluation is strictly per-tender.
    tender_bids = (
        db.query(BidSubmission)
        .filter(BidSubmission.tender_id == bid.tender_id)
        .order_by(BidSubmission.id)
        .all()
    )
    assessments = []
    for b in tender_bids:
        a = _bid_assessment(db, b)
        if a is not None:
            assessments.append(a)
    if not assessments:
        raise ValueError(
            f"No compliance results stored for tender {bid.tender_id}; "
            "run compliance evaluation first."
        )

    # Rank the approve-eligible bids; the strongest takes APPROVE.
    eligible = sorted(
        [a for a in assessments if a["approve_eligible"]], key=_rank_key
    )
    approved_id = eligible[0]["bid"].id if eligible else None

    by_bid_id: dict[int, str] = {}
    for a in assessments:
        if a["disqualified"]:
            by_bid_id[a["bid"].id] = "REJECT"
        elif a["bid"].id == approved_id:
            by_bid_id[a["bid"].id] = "APPROVE"
        else:
            by_bid_id[a["bid"].id] = "REVIEW_REQUIRED"

    # Persist every evaluated bid so the tender ranking is consistent and
    # updates dynamically the next time any bid is (re)evaluated. Each bid
    # gets its own evidence-backed reason; RAG policy context is built for
    # the requested bid only.
    for a in assessments:
        b = a["bid"]
        b.recommendation = by_bid_id[b.id]
        b.recommendation_reason = _build_reason(
            a, assessments, approved_id, by_bid_id[b.id]
        )

    # Full per-bid detail (evidence, policy context) for the requested bid.
    target = next(a for a in assessments if a["bid"].id == bid_id)
    recommendation = by_bid_id[bid_id]
    reason = bid.recommendation_reason

    check_ids = [
        row[0]
        for row in db.query(VerificationCheck.id)
        .filter(VerificationCheck.bid_id == bid_id)
        .all()
    ]
    evidence = {
        "requirement_ids": [i["requirement_id"] for i in target["non_pass"]],
        "check_ids": check_ids,
    }
    evidence_refs = [{"type": "requirement", "id": rid} for rid in evidence["requirement_ids"]]
    evidence_refs += [{"type": "verification_check", "id": cid} for cid in evidence["check_ids"]]

    policy_context = _build_policy_context(db, target)

    bid.recommendation_reason = reason
    bid.recommendation_evidence = evidence_refs
    # Persist citable policy context alongside the recommendation so Bid
    # Detail shows the same citations when the bid is reopened. Stored as
    # plain data — never influences scores, risk, or the officer decision.
    bid.policy_context = policy_context

    append_audit(
        db,
        user_id=user_id,
        action="RECOMMENDATION_GENERATED",
        entity_type="bid_submission",
        entity_id=str(bid_id),
        metadata={
            "recommendation": recommendation,
            "tender_id": bid.tender_id,
            "bids_evaluated": len(assessments),
            "non_pass_count": target["non_pass_count"],
        },
    )
    db.commit()

    return {
        "recommendation": recommendation,
        "reason": reason,
        "evidence": evidence_refs,
        "policy_context": policy_context,
        "provider": PROVIDER,
    }


def _build_reason(
    target: dict,
    assessments: list[dict],
    approved_id: int | None,
    recommendation: str,
) -> str:
    """Evidence-backed reason for the requested bid's recommendation,
    including its comparative position within the tender."""
    items = target["items"]
    signals = target["signals"]
    bullets: list[str] = []

    # Comparative position within the tender.
    ranked = sorted(assessments, key=_rank_key)
    position = next(
        (i + 1 for i, a in enumerate(ranked) if a["bid"].id == target["bid"].id),
        None,
    )
    tender_size = len(assessments)
    if recommendation == "APPROVE":
        bullets.append(
            f"• Strongest eligible bid in this tender (rank {position} of "
            f"{tender_size}): compliance score {target['score']:.1f}, risk "
            f"level {target['risk_level']}."
        )
    elif recommendation == "REJECT":
        if target["blacklisted"]:
            bullets.append(
                "• Disqualified: blacklist/debarment signal present — the bid "
                "cannot proceed without officer review of the listing."
            )
        if target["fail_mandatory"]:
            failed = [
                i["requirement_name"]
                for i in items
                if i["status"] == "FAIL" and i["mandatory"]
            ]
            bullets.append(
                "• Disqualified: mandatory requirement(s) failed: "
                + "; ".join(failed)
                + "."
            )
    else:  # REVIEW_REQUIRED
        if target["missing_mandatory"]:
            missing = [
                i["requirement_name"]
                for i in items
                if i["status"] == "MISSING" and i["mandatory"]
            ]
            bullets.append(
                "• Mandatory evidence missing (cannot approve until resolved): "
                + "; ".join(missing)
                + "."
            )
        if _risk_rank(target["risk_level"]) >= 2:
            bullets.append(
                "• Serious unresolved risk indicators (risk level "
                f"{target['risk_level']}) require officer review despite a "
                f"compliance score of {target['score']:.1f}."
            )
        if target["bid"].id != approved_id and not target["disqualified"]:
            bullets.append(
                f"• Eligible but not the strongest bid in this tender "
                f"(rank {position} of {tender_size}); officer review required "
                f"before any award decision."
            )

    # Per-finding evidence.
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

    return "\n".join(bullets) + "\n\n" + FINAL_LINE


def _build_policy_context(db, target: dict) -> list[dict]:
    """RAG policy citations for the target bid's non-PASS findings.

    The recommendation itself stays fully deterministic — retrieval only
    adds policy context and the official source. A hit is cited only when
    it clears the relevance gate AND comes from an authoritative document.
    """
    from app.services import rag_service

    policy_context: list[dict] = []
    seen = set()

    def _retrieve(query: str, doc_titles: tuple[str, ...] | None) -> None:
        if not query or not doc_titles:
            # No authoritative policy source is configured for this topic.
            return
        try:
            res = rag_service.search(db, query, top_k=2, doc_titles=list(doc_titles))
        except Exception:
            return
        for hit in res.get("results", []):
            if float(hit.get("score") or 0) < MIN_RELEVANCE:
                continue
            meta = rag_service.doc_metadata(hit.get("doc_title") or "")
            if meta.get("authority_level") != "AUTHORITATIVE":
                continue
            key = (hit.get("doc_id"), hit.get("section"))
            if key in seen:
                continue
            seen.add(key)
            policy_context.append(_policy_citation(hit))

    items = target["items"]
    signals = target["signals"]
    flagged = [i for i in items if i["status"] in RETRIEVAL_STATUSES]
    for i in flagged:
        _retrieve(_retrieval_query(i), _retrieval_topic(i))
    # Critical/high blacklist or debarment risk signals get policy context
    # even when the compliance finding itself passed (portal-level flag).
    debar_titles = _topic_titles(("blacklist", "debar"))
    for s in signals:
        if s.get("code") in SIGNAL_RETRIEVAL_CODES and (s.get("severity") or "") in (
            "critical",
            "high",
        ):
            _retrieve(f"{s.get('code')} {s.get('message', '')}".strip(), debar_titles)
    return policy_context
