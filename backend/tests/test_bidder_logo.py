"""Tests for bidder logo upload/serve/delete (display-only, no schema change).

Logos live on disk at ``{UPLOAD_DIR}/bidder_logos/{bidder_id}.png`` — the
file's existence IS the record. These tests use a standalone FastAPI app
with only the bidder_logos router (the real app's lifespan touches the dev
database, so it is never instantiated here).
"""
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api import bidder_logos
from app.core import config as config_mod
from app.core.deps import get_current_user, get_db
from app.models.models import (
    Bidder,
    BidSubmission,
    ComplianceResult,
    Tender,
    TenderRequirement,
    User,
)
from app.seed.demo_docs import generate_demo_logo
from app.services.compliance_service import evaluate_bid
from app.services.demo_seed_service import write_demo_logo_if_missing


def _png_bytes(color=(30, 90, 160), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), (200, 40, 40)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def officer(db):
    user = User(name="Officer", email="officer@test.local", password_hash="x",
                role="PROCUREMENT_OFFICER")
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def bidder(db):
    tender = Tender(tender_number="LOGO-001", title="Logo tender",
                    organization="CPCL", department="Materials")
    db.add(tender)
    db.flush()
    b = Bidder(tender_id=tender.id, legal_name="Logo Test Pvt. Ltd.",
               bid_status="SUBMITTED")
    db.add(b)
    db.commit()
    return b


@pytest.fixture()
def client(db, tmp_path, monkeypatch, officer, bidder):
    """Standalone app: bidder_logos router only, isolated upload dir."""
    monkeypatch.setattr(config_mod.settings, "UPLOAD_DIR", tmp_path / "uploads")
    test_app = FastAPI()
    test_app.include_router(bidder_logos.router)
    test_app.dependency_overrides[get_db] = lambda: db
    test_app.dependency_overrides[get_current_user] = lambda: officer
    return TestClient(test_app)


@pytest.fixture()
def anon_client(db, tmp_path, monkeypatch):
    """Same app but WITHOUT auth override: requests carry no token."""
    monkeypatch.setattr(config_mod.settings, "UPLOAD_DIR", tmp_path / "uploads")
    test_app = FastAPI()
    test_app.include_router(bidder_logos.router)
    test_app.dependency_overrides[get_db] = lambda: db
    return TestClient(test_app)


def _upload(client, bidder_id, filename, content):
    return client.post(
        f"/api/bidders/{bidder_id}/logo",
        files={"file": (filename, content, "application/octet-stream")},
    )


# ------------------------------------------------------------ happy path
def test_upload_and_serve_png(client, bidder):
    png = _png_bytes()
    r = _upload(client, bidder.id, "logo.png", png)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bidder_id"] == bidder.id
    assert body["logo_url"] == f"/api/bidders/{bidder.id}/logo"

    g = client.get(f"/api/bidders/{bidder.id}/logo")
    assert g.status_code == 200
    assert g.headers["content-type"] == "image/png"
    assert g.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_jpg_upload_is_normalized_to_png(client, bidder):
    r = _upload(client, bidder.id, "logo.jpg", _jpg_bytes())
    assert r.status_code == 200, r.text
    g = client.get(f"/api/bidders/{bidder.id}/logo")
    assert g.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_webp_upload_accepted(client, bidder):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 200, 90)).save(buf, format="WEBP")
    r = _upload(client, bidder.id, "logo.webp", buf.getvalue())
    assert r.status_code == 200, r.text


# ------------------------------------------------------------ validation
def test_reject_unsupported_type(client, bidder):
    r = _upload(client, bidder.id, "logo.txt", b"not an image")
    assert r.status_code == 400


def test_reject_magic_mismatch(client, bidder):
    r = _upload(client, bidder.id, "logo.png", b"definitely not png bytes")
    assert r.status_code == 400


def test_reject_oversize(client, bidder):
    big = _png_bytes() + b"\x00" * (2 * 1024 * 1024 + 1)
    r = _upload(client, bidder.id, "logo.png", big)
    assert r.status_code == 400


def test_upload_unknown_bidder_404(client):
    r = _upload(client, 999999, "logo.png", _png_bytes())
    assert r.status_code == 404


# ------------------------------------------------------------ replace/delete
def test_replace_overwrites(client, bidder):
    _upload(client, bidder.id, "a.png", _png_bytes(color=(30, 90, 160)))
    first = client.get(f"/api/bidders/{bidder.id}/logo").content
    _upload(client, bidder.id, "b.png", _png_bytes(color=(200, 40, 40)))
    second = client.get(f"/api/bidders/{bidder.id}/logo").content
    assert first != second
    assert second[:8] == b"\x89PNG\r\n\x1a\n"


def test_delete_removes_and_is_idempotent(client, bidder):
    _upload(client, bidder.id, "logo.png", _png_bytes())
    assert client.get(f"/api/bidders/{bidder.id}/logo").status_code == 200
    assert client.delete(f"/api/bidders/{bidder.id}/logo").status_code == 204
    assert client.get(f"/api/bidders/{bidder.id}/logo").status_code == 404
    # Deleting again is still 204, not an error.
    assert client.delete(f"/api/bidders/{bidder.id}/logo").status_code == 204


def test_get_404_when_absent(client, bidder):
    assert client.get(f"/api/bidders/{bidder.id}/logo").status_code == 404


# ------------------------------------------------------------ auth
def test_auth_required(anon_client, bidder):
    assert anon_client.post(
        f"/api/bidders/{bidder.id}/logo",
        files={"file": ("logo.png", _png_bytes(), "application/octet-stream")},
    ).status_code == 401
    assert anon_client.get(f"/api/bidders/{bidder.id}/logo").status_code == 401
    assert anon_client.delete(f"/api/bidders/{bidder.id}/logo").status_code == 401


# ------------------------------------------------------------ demo seed logo
def test_generate_demo_logo_is_valid_png():
    raw = generate_demo_logo("Apex Flow Systems Private Limited")
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(io.BytesIO(raw)) as img:
        img.verify()
    # Deterministic: fixed-seed replay reproduces the same bytes.
    assert generate_demo_logo("Apex Flow Systems Private Limited") == raw
    assert generate_demo_logo("Vertex Industrial Solutions") != raw


def test_seed_writes_demo_logo_file(db, tmp_path, monkeypatch, bidder):
    monkeypatch.setattr(config_mod.settings, "UPLOAD_DIR", tmp_path / "uploads")
    assert write_demo_logo_if_missing(bidder.id, bidder.legal_name) is True
    path = bidder_logos.logo_path(bidder.id)
    assert path.exists()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    # Second call does not overwrite (officer uploads win).
    path.write_bytes(b"custom")
    assert write_demo_logo_if_missing(bidder.id, bidder.legal_name) is False
    assert path.read_bytes() == b"custom"


# ------------------------------------------------------------ display-only proof
def test_logo_never_affects_compliance_scoring(db, tmp_path, monkeypatch, bidder):
    """A logo file must not change verification/compliance outcomes."""
    monkeypatch.setattr(config_mod.settings, "UPLOAD_DIR", tmp_path / "uploads")
    tender = db.get(Tender, bidder.tender_id)
    db.add(TenderRequirement(
        tender_id=tender.id, requirement_name="GST Registration",
        category="STATUTORY", description="d", mandatory=True,
        rule_type="EXISTENCE", rule_config={"value_source": "extracted.gstin"},
        weight=100.0,
    ))
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id, status="SUBMITTED")
    db.add(bid)
    db.commit()

    evaluate_bid(db, bid.id)
    before = sorted((r.requirement_id, r.status, r.weighted_contribution)
                    for r in db.query(ComplianceResult).filter_by(bid_id=bid.id).all())
    db.refresh(bid)
    score_before = bid.compliance_score

    # Add a logo, then re-evaluate from scratch.
    assert write_demo_logo_if_missing(bidder.id, bidder.legal_name) is True
    db.query(ComplianceResult).filter_by(bid_id=bid.id).delete()
    db.commit()
    evaluate_bid(db, bid.id)
    after = sorted((r.requirement_id, r.status, r.weighted_contribution)
                   for r in db.query(ComplianceResult).filter_by(bid_id=bid.id).all())
    db.refresh(bid)

    assert after == before
    assert bid.compliance_score == score_before
