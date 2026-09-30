"""Login CAPTCHA tests.

- Challenge generation returns an id + renderable SVG data URI.
- Verification is case-insensitive, single-use and time-bound.
- ``POST /api/auth/login`` rejects bad/expired/missing CAPTCHAs with 400
  *before* checking credentials, and accepts a valid one.
"""
import time

import pytest
from fastapi import HTTPException

import app.api.auth as auth_mod
from app.core.security import get_password_hash
from app.models.models import User
from app.schemas.schemas import LoginRequest
from app.services import captcha_service


@pytest.fixture(autouse=True)
def _clean_store():
    captcha_service._test_reset()
    yield
    captcha_service._test_reset()


def test_generate_returns_id_and_svg_image():
    captcha_id, image = captcha_service.generate()
    assert captcha_id
    assert image.startswith("data:image/svg+xml,")
    assert "%3Csvg" in image  # encoded markup present


def test_verify_accepts_correct_solution_case_insensitive():
    captcha_id, _ = captcha_service.generate()
    solution = captcha_service._STORE[captcha_id][0]
    assert captcha_service.verify(captcha_id, solution.lower()) is True


def test_verify_rejects_wrong_solution():
    captcha_id, _ = captcha_service.generate()
    assert captcha_service.verify(captcha_id, "XXXXXX") is False


def test_verify_rejects_missing_fields():
    captcha_id, _ = captcha_service.generate()
    solution = captcha_service._STORE[captcha_id][0]
    assert captcha_service.verify(None, solution) is False
    assert captcha_service.verify(captcha_id, "") is False
    assert captcha_service.verify("no-such-id", solution) is False


def test_challenge_is_single_use():
    captcha_id, _ = captcha_service.generate()
    solution = captcha_service._STORE[captcha_id][0]
    assert captcha_service.verify(captcha_id, solution) is True
    # Replaying the same challenge must fail even with the right solution.
    assert captcha_service.verify(captcha_id, solution) is False


def test_challenge_expires():
    captcha_id, _ = captcha_service.generate()
    solution, _ = captcha_service._STORE[captcha_id]
    captcha_service._STORE[captcha_id] = (solution, time.time() - 1)
    assert captcha_service.verify(captcha_id, solution) is False


def _seed_officer(db):
    user = User(
        name="Officer",
        email="officer@demo.cpcl.in",
        password_hash=get_password_hash("secret123"),
        role="PROCUREMENT_OFFICER",
    )
    db.add(user)
    db.commit()
    return user


def _login_payload(captcha_id, captcha_text):
    return LoginRequest(
        email="officer@demo.cpcl.in",
        password="secret123",
        captcha_id=captcha_id,
        captcha_text=captcha_text,
    )


def test_login_rejects_bad_captcha_before_checking_credentials(db):
    _seed_officer(db)
    with pytest.raises(HTTPException) as exc_info:
        auth_mod.login(_login_payload("bogus-id", "bogus"), db)
    assert exc_info.value.status_code == 400
    assert "security code" in exc_info.value.detail


def test_login_rejects_replayed_captcha(db):
    _seed_officer(db)
    captcha_id, _ = captcha_service.generate()
    solution = captcha_service._STORE[captcha_id][0]
    first = auth_mod.login(_login_payload(captcha_id, solution), db)
    assert first.access_token
    with pytest.raises(HTTPException) as exc_info:
        auth_mod.login(_login_payload(captcha_id, solution), db)
    assert exc_info.value.status_code == 400


def test_login_accepts_valid_captcha_and_credentials(db):
    _seed_officer(db)
    captcha_id, _ = captcha_service.generate()
    solution = captcha_service._STORE[captcha_id][0]
    res = auth_mod.login(_login_payload(captcha_id, solution), db)
    assert res.access_token
    assert res.user.email == "officer@demo.cpcl.in"


def test_login_with_valid_captcha_but_wrong_password_still_401(db):
    _seed_officer(db)
    captcha_id, _ = captcha_service.generate()
    solution = captcha_service._STORE[captcha_id][0]
    payload = LoginRequest(
        email="officer@demo.cpcl.in",
        password="wrong",
        captcha_id=captcha_id,
        captcha_text=solution,
    )
    with pytest.raises(HTTPException) as exc_info:
        auth_mod.login(payload, db)
    assert exc_info.value.status_code == 401


def test_get_captcha_endpoint_shape():
    out = auth_mod.get_captcha()
    assert out.captcha_id
    assert out.image.startswith("data:image/svg+xml,")
