"""Single-role authorization test.

The application has exactly one user role: PROCUREMENT_OFFICER.

- Every backend gate is ``require_officer()``: the officer passes, every
  legacy role (VERIFIER / AUDITOR / ADMIN) is rejected with 403.
- ``get_current_user`` rejects legacy-role rows even with a valid token (403)
  and bad tokens with 401 — authentication stays mandatory, nothing is public.
"""
import pytest
from fastapi import HTTPException

import app.api.audit as audit_mod
import app.api.bids as bids_mod
import app.api.compliance as compliance_mod
import app.api.consistency as consistency_mod
import app.api.documents as documents_mod
import app.api.integrity as integrity_mod
import app.api.officer as officer_mod
import app.api.recommendation as recommendation_mod
import app.api.seed as seed_mod
import app.api.tenders as tenders_mod
import app.api.verification as verification_mod
import app.api.verification_summaries as summaries_mod
from app.core.deps import get_current_user, require_officer
from app.core.security import create_access_token
from app.models.models import User

OFFICER = "PROCUREMENT_OFFICER"
LEGACY_ROLES = ["VERIFIER", "AUDITOR", "ADMIN"]

# Every module exposes a single _OFFICER gate.
GATED_MODULES = [
    audit_mod,
    bids_mod,
    compliance_mod,
    consistency_mod,
    documents_mod,
    integrity_mod,
    officer_mod,
    recommendation_mod,
    seed_mod,
    tenders_mod,
    verification_mod,
    summaries_mod,
]


def _user(role: str) -> User:
    return User(name="t", email=f"{role}@test.local", password_hash="x", role=role)


def test_require_officer_allows_procurement_officer():
    gate = require_officer()
    user = _user(OFFICER)
    assert gate(user=user) is user


@pytest.mark.parametrize("role", LEGACY_ROLES)
def test_require_officer_rejects_legacy_roles(role):
    gate = require_officer()
    with pytest.raises(HTTPException) as exc_info:
        gate(user=_user(role))
    assert exc_info.value.status_code == 403


@pytest.mark.parametrize("module", GATED_MODULES)
def test_every_module_gate_allows_officer_only(module):
    gate = module._OFFICER
    assert gate(user=_user(OFFICER)).role == OFFICER
    for role in LEGACY_ROLES:
        with pytest.raises(HTTPException) as exc_info:
            gate(user=_user(role))
        assert exc_info.value.status_code == 403, f"{module.__name__} allowed {role}"


def test_get_current_user_accepts_officer(db):
    user = User(name="Officer", email="officer-t@example.com", password_hash="x",
                role=OFFICER)
    db.add(user)
    db.commit()
    token = create_access_token(str(user.id))
    assert get_current_user(db=db, token=token).id == user.id


@pytest.mark.parametrize("role", LEGACY_ROLES)
def test_get_current_user_rejects_legacy_role_token(db, role):
    """A valid token for a legacy-role row must not authenticate."""
    user = User(name="Legacy", email=f"{role}-t@example.com", password_hash="x",
                role=role)
    db.add(user)
    db.commit()
    token = create_access_token(str(user.id))
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(db=db, token=token)
    assert exc_info.value.status_code == 403


def test_get_current_user_rejects_bad_token(db):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(db=db, token="not-a-token")
    assert exc_info.value.status_code == 401


def test_no_multi_role_gate_factory_remains():
    """The old require_roles(*roles) factory must be gone."""
    import app.core.deps as deps_mod

    assert not hasattr(deps_mod, "require_roles")
    assert hasattr(deps_mod, "require_officer")
