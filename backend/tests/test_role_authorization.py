"""Role authorization matrix test.

Validates that every backend write-gate allows exactly the intended roles:
- PROCUREMENT_OFFICER: full procurement workflow + final decisions
- VERIFIER: procurement staff actions (upload/process/verify/evaluate/recommend)
- AUDITOR: read-only (audit integrity check only, no procurement writes)
- ADMIN: system administration only (seed); no procurement writes/decisions

Each gate is the ``require_roles(...)`` dependency used by the endpoints;
invoking it directly exercises the exact allow/deny logic FastAPI applies.
"""
import pytest
from fastapi import HTTPException

import app.api.audit as audit_mod
import app.api.bids as bids_mod
import app.api.compliance as compliance_mod
import app.api.documents as documents_mod
import app.api.officer as officer_mod
import app.api.recommendation as recommendation_mod
import app.api.seed as seed_mod
import app.api.tenders as tenders_mod
import app.api.verification as verification_mod
import app.api.verifier_reports as verifier_reports_mod
from app.models.models import User

OFFICER = "PROCUREMENT_OFFICER"
VERIFIER = "VERIFIER"
AUDITOR = "AUDITOR"
ADMIN = "ADMIN"

# gate name -> (module, attribute, allowed roles)
GATES = {
    "officer decision/override/clarification": (officer_mod, "_OFFICER", {OFFICER}),
    "tender create/requirements/analyze": (tenders_mod, "_OFFICER", {OFFICER}),
    "tender deletion": (tenders_mod, "_OFFICER", {OFFICER}),
    "bid registration": (bids_mod, "_SUBMITTER", {OFFICER, VERIFIER}),
    "bid deletion": (bids_mod, "_OFFICER", {OFFICER}),
    "demo evidence seeding (bid)": (bids_mod, "_SUBMITTER", {OFFICER, VERIFIER}),
    "document upload": (documents_mod, "_UPLOADER", {OFFICER, VERIFIER}),
    "document classification fix": (documents_mod, "_CORRECTOR", {OFFICER, VERIFIER}),
    "document processing": (documents_mod, "_PROCESSOR", {OFFICER, VERIFIER}),
    "run verification": (verification_mod, "_RUNNER", {OFFICER, VERIFIER}),
    "compliance evaluation": (compliance_mod, "_EVALUATOR", {OFFICER, VERIFIER}),
    "recommendation generation": (recommendation_mod, "_RECOMMENDER", {OFFICER, VERIFIER}),
    "report generate/send/observations": (verifier_reports_mod, "_VERIFIER", {VERIFIER}),
    "report mark opened + inbox": (verifier_reports_mod, "_OFFICER", {OFFICER}),
    "report view": (verifier_reports_mod, "_VIEWER", {OFFICER, VERIFIER, AUDITOR, ADMIN}),
    "audit integrity verify": (audit_mod, "_VERIFIER", {AUDITOR, ADMIN, OFFICER}),
    "demo seed": (seed_mod, "_ADMIN", {ADMIN}),
}


def _user(role: str) -> User:
    return User(name="t", email=f"{role}@test.local", password_hash="x", role=role)


@pytest.mark.parametrize("gate_name", sorted(GATES))
@pytest.mark.parametrize("role", [OFFICER, VERIFIER, AUDITOR, ADMIN])
def test_role_authorization_matrix(gate_name, role):
    module, attr, allowed = GATES[gate_name]
    gate = getattr(module, attr)
    user = _user(role)
    if role in allowed:
        assert gate(user=user) is user
    else:
        with pytest.raises(HTTPException) as exc_info:
            gate(user=user)
        assert exc_info.value.status_code == 403


def test_auditor_is_read_only_for_procurement_writes():
    """Auditor must be denied by every procurement write gate."""
    write_gates = [
        (officer_mod, "_OFFICER"),
        (tenders_mod, "_OFFICER"),
        (bids_mod, "_SUBMITTER"),  # also gates POST /bids/{id}/seed-demo-evidence
        (bids_mod, "_OFFICER"),  # gates DELETE /bids/{id}
        (documents_mod, "_UPLOADER"),
        (documents_mod, "_CORRECTOR"),
        (documents_mod, "_PROCESSOR"),
        (verification_mod, "_RUNNER"),
        (compliance_mod, "_EVALUATOR"),
        (recommendation_mod, "_RECOMMENDER"),
        (verifier_reports_mod, "_VERIFIER"),
        (verifier_reports_mod, "_OFFICER"),
        (seed_mod, "_ADMIN"),
    ]
    user = _user(AUDITOR)
    for module, attr in write_gates:
        with pytest.raises(HTTPException) as exc_info:
            getattr(module, attr)(user=user)
        assert exc_info.value.status_code == 403, f"{module.__name__}.{attr}"


def test_admin_has_no_procurement_write_access():
    """Admin is system-admin only: no tender/bid/decision/verification writes."""
    user = _user(ADMIN)
    staff_gates = [
        (officer_mod, "_OFFICER"),
        (tenders_mod, "_OFFICER"),
        (bids_mod, "_SUBMITTER"),
        (documents_mod, "_UPLOADER"),
        (verification_mod, "_RUNNER"),
        (compliance_mod, "_EVALUATOR"),
        (recommendation_mod, "_RECOMMENDER"),
        (verifier_reports_mod, "_VERIFIER"),
        (verifier_reports_mod, "_OFFICER"),
    ]
    for module, attr in staff_gates:
        with pytest.raises(HTTPException) as exc_info:
            getattr(module, attr)(user=user)
        assert exc_info.value.status_code == 403, f"{module.__name__}.{attr}"
    # ...but keeps system administration (seed)
    assert seed_mod._ADMIN(user=user) is user
