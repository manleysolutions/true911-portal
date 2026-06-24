"""Tests for the AI Customer Operations Center / Support Center.

No Postgres / aiosqlite fixture exists in this project, so these tests
follow the established pattern: pure-function unit tests for the logic, a
small queued in-memory AsyncSession substitute for the OTP service flow,
and TestClient + dependency overrides for router gating.  They pin:

  * feature-flag gating (404 when FEATURE_OPS_CENTER off)
  * identifier normalization + phone masking
  * OTP code is never stored/echoed in plaintext; send → verify round-trip
  * attempt limiting + expiry
  * verification gating of sensitive session fields (tenant/device hidden)
  * lookup-match redaction (full contact never exposed)
  * triage blocked until verified
  * emergency path bypasses verification for a limited incident
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import dependencies as deps
from app.models.ops_center import OpsOtpChallenge, OpsSessionEvent, OpsSupportSession
from app.routers import ops_center
from app.services.ops_center import lookup as lookup_svc
from app.services.ops_center import sessions as session_svc
from app.services.ops_center import triage as triage_svc
from app.services.ops_center.normalize import (
    mask_phone,
    normalize_identifier,
    normalize_name,
    normalize_phone,
    normalize_token,
)
from app.services.ops_center.otp import get_otp_provider
from app.services.ops_center.otp.stub import ConsoleOtpProvider, StubOtpProvider


# ════════════════════════════════════════════════════════════════════
# In-memory async-session substitute (queued execute results)
# ════════════════════════════════════════════════════════════════════

class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeDB:
    """Returns queued result sets in order; records added objects."""

    def __init__(self, results=None):
        self._queue = list(results or [])
        self.added = []
        self.commits = 0

    async def execute(self, stmt, *a, **k):
        rows = self._queue.pop(0) if self._queue else []
        return _Result(rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if hasattr(obj, "id") and getattr(obj, "id", None) is None:
                obj.id = uuid4()

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass

    def added_of(self, cls):
        return [o for o in self.added if isinstance(o, cls)]


def _session(**kw):
    base = dict(
        id=uuid4(),
        session_ref="OPS-TEST0001",
        source="phone",
        is_emergency=False,
        status="open",
        verification_status="unverified",
        escalation_status="none",
        matched_tenant_id=None,
        matched_device_id=None,
        meta=None,
    )
    base.update(kw)
    return OpsSupportSession(**base)


# ════════════════════════════════════════════════════════════════════
# Pure-function unit tests
# ════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+1 (856) 308-1391", "8563081391"),
        ("18563081391", "8563081391"),
        ("8563081391", "8563081391"),
        ("856.308.1391", "8563081391"),
    ],
)
def test_normalize_phone_variants_match(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_name_and_token():
    assert normalize_name("  RH   Yountville ") == "rh yountville"
    assert normalize_token("8901 2402 0421 9434 247") == "8901240204219434247"
    assert normalize_token("napco-123_456") == "NAPCO123456"


def test_normalize_identifier_dispatch():
    assert normalize_identifier("elevator_phone", "+1 856 308 1391") == "8563081391"
    assert normalize_identifier("site_name", "Tower A") == "tower a"
    assert normalize_identifier("iccid", "8901 2402") == "89012402"


def test_mask_phone_keeps_last_four():
    assert mask_phone("+18563081391") == "•••-•••-1391"
    assert mask_phone("") == ""
    assert mask_phone("12") == "••"


def test_generate_code_length_and_digits():
    code = session_svc.generate_code(6)
    assert len(code) == 6 and code.isdigit()
    assert len(session_svc.generate_code(4)) == 4


def test_hash_code_is_deterministic_and_salted():
    sid = uuid4()
    h1 = session_svc.hash_code("123456", sid)
    h2 = session_svc.hash_code("123456", sid)
    assert h1 == h2
    assert h1 != "123456"  # plaintext is never the stored value
    assert session_svc.hash_code("123456", uuid4()) != h1  # bound to session


def test_session_ref_format():
    ref = session_svc.new_session_ref()
    assert ref.startswith("OPS-") and len(ref) == 12


@pytest.mark.asyncio
async def test_stub_provider_simulated_and_no_send():
    res = await StubOtpProvider().send(destination="+18563081391", code="999111", session_ref="OPS-X")
    assert res.ok and res.simulated and res.provider == "stub"


def test_get_otp_provider_selection():
    assert get_otp_provider(SimpleNamespace(OPS_CENTER_OTP_PROVIDER="stub")).name == "stub"
    assert get_otp_provider(SimpleNamespace(OPS_CENTER_OTP_PROVIDER="console")).name == "console"
    # Future providers degrade to the stub rather than failing.
    assert get_otp_provider(SimpleNamespace(OPS_CENTER_OTP_PROVIDER="twilio")).name == "stub"


def test_attach_match_masks_contact_and_stashes_destination():
    s = _session()
    m = lookup_svc.RawAssetMatch(
        asset_kind="device", asset_ref="dev-1", match_source="asset_identity",
        tenant_id="rh", site_id="S1", device_id="dev-1",
        matched_identifier_type="msisdn", label="Elevator 3",
        contact_name="Judy", contact_phone="+18563081391",
    )
    session_svc.attach_match(s, m)
    assert s.matched_tenant_id == "rh"
    assert s.contact_phone_masked == "•••-•••-1391"
    assert s.meta["_contact_phone"] == "+18563081391"  # server-only
    assert "msisdn" in s.meta["identifiers_used"]
    assert s.status == "matched"


def test_build_handoff_summary_shape():
    s = _session(
        matched_tenant_id="rh", matched_site_id="S1", matched_device_id="dev-1",
        issue_category="no_dial_tone", issue_summary="No dial tone on elevator",
        verification_status="verified", matched_label="Elevator 3",
        meta={"identifiers_used": ["msisdn"]},
    )
    h = session_svc.build_handoff_summary(s, diagnostics=[{"check": "last_seen"}])
    assert h["session_ref"] == "OPS-TEST0001"
    assert h["customer"] == "rh" and h["device_id"] == "dev-1"
    assert h["identifiers_used"] == ["msisdn"]
    assert h["diagnostics"] == [{"check": "last_seen"}]
    assert h["recommended_next_action"]


# ════════════════════════════════════════════════════════════════════
# Serialization redaction (router helpers — pure)
# ════════════════════════════════════════════════════════════════════

def test_serialize_session_hides_sensitive_until_verified():
    s = _session(matched_tenant_id="rh", matched_device_id="dev-1", verification_status="unverified")
    out = ops_center._serialize_session(s)
    assert out.matched_tenant_id is None
    assert out.matched_device_id is None


def test_serialize_session_reveals_when_verified():
    s = _session(matched_tenant_id="rh", matched_device_id="dev-1", verification_status="verified", status="verified")
    out = ops_center._serialize_session(s)
    assert out.matched_tenant_id == "rh"
    assert out.matched_device_id == "dev-1"


def test_serialize_session_reveals_for_emergency():
    s = _session(matched_tenant_id="rh", matched_device_id="dev-1", is_emergency=True)
    out = ops_center._serialize_session(s)
    assert out.matched_tenant_id == "rh"


def test_match_to_schema_redacts_contact_and_tenant():
    m = lookup_svc.RawAssetMatch(
        asset_kind="device", asset_ref="dev-1", match_source="device",
        tenant_id="rh", contact_name="Judy", contact_phone="+18563081391",
    )
    redacted = ops_center._match_to_schema(m, reveal_tenant=False)
    assert redacted.has_contact_on_file is True
    assert redacted.contact_phone_masked == "•••-•••-1391"
    assert redacted.tenant_id is None  # hidden from non-platform callers
    revealed = ops_center._match_to_schema(m, reveal_tenant=True)
    assert revealed.tenant_id == "rh"


# ════════════════════════════════════════════════════════════════════
# OTP service flow (queued FakeDB)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_issue_otp_without_contact_fails_gracefully():
    s = _session()  # no meta / contact
    db = FakeDB(results=[[]])
    res = await session_svc.issue_otp(db, s, destination_override=None, actor="op@t.io")
    assert res["ok"] is False and res["otp_status"] == "failed"
    assert db.added_of(OpsSessionEvent)  # a failure event was recorded
    assert not db.added_of(OpsOtpChallenge)  # no challenge created


@pytest.mark.asyncio
async def test_issue_then_verify_otp_roundtrip(monkeypatch):
    monkeypatch.setattr(session_svc, "generate_code", lambda *a, **k: "424242")
    s = _session(matched_tenant_id="rh", meta={"_contact_phone": "+18563081391"})

    # issue: first execute() = "cancel prior open" → []
    db = FakeDB(results=[[]])
    res = await session_svc.issue_otp(db, s, destination_override=None, actor="op@t.io")
    assert res["ok"] and res["otp_status"] == "otp_sent"
    assert res["destination_masked"] == "•••-•••-1391"
    assert s.verification_status == "otp_sent"

    challenge = db.added_of(OpsOtpChallenge)[0]
    # Plaintext code is never stored anywhere on the challenge.
    assert "424242" not in (challenge.code_hash or "")
    assert challenge.destination_masked == "•••-•••-1391"

    # verify with the correct code: execute() returns the stored challenge.
    db2 = FakeDB(results=[[challenge]])
    out = await session_svc.verify_otp(db2, s, code="424242", actor="op@t.io")
    assert out["verified"] is True
    assert s.verification_status == "verified" and s.status == "verified"
    assert challenge.status == "verified"


@pytest.mark.asyncio
async def test_verify_otp_wrong_code_decrements_attempts(monkeypatch):
    monkeypatch.setattr(session_svc, "generate_code", lambda *a, **k: "111222")
    s = _session(matched_tenant_id="rh", meta={"_contact_phone": "+18563081391"})
    db = FakeDB(results=[[]])
    await session_svc.issue_otp(db, s, destination_override=None, actor="op@t.io")
    challenge = db.added_of(OpsOtpChallenge)[0]
    challenge.max_attempts = 5

    db2 = FakeDB(results=[[challenge]])
    out = await session_svc.verify_otp(db2, s, code="000000", actor="op@t.io")
    assert out["verified"] is False
    assert out["attempts_remaining"] == 4
    assert s.verification_status != "verified"


@pytest.mark.asyncio
async def test_verify_otp_expired(monkeypatch):
    monkeypatch.setattr(session_svc, "generate_code", lambda *a, **k: "333444")
    s = _session(matched_tenant_id="rh", meta={"_contact_phone": "+18563081391"})
    db = FakeDB(results=[[]])
    await session_svc.issue_otp(db, s, destination_override=None, actor="op@t.io")
    challenge = db.added_of(OpsOtpChallenge)[0]
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    db2 = FakeDB(results=[[challenge]])
    out = await session_svc.verify_otp(db2, s, code="333444", actor="op@t.io")
    assert out["verified"] is False
    assert challenge.status == "expired"


# ════════════════════════════════════════════════════════════════════
# Triage service (graceful degrade)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_triage_unavailable_without_device():
    s = _session(matched_tenant_id="rh")  # no matched_device_id
    db = FakeDB(results=[])  # _load_device not called (no device id)
    result = await triage_svc.run_triage(db, s)
    names = {c["check"] for c in result["checks"]}
    assert {"device_health", "last_seen", "carrier_sim_status", "sip_ata_registration",
            "signal_strength", "recent_events", "open_tickets", "billing_service_status"} <= names
    assert result["overall"] in ("unknown", "unavailable")
    # billing is never surfaced as real data in the stub
    billing = next(c for c in result["checks"] if c["check"] == "billing_service_status")
    assert billing["status"] == "unavailable"


@pytest.mark.asyncio
async def test_triage_reads_device_when_linked():
    device = SimpleNamespace(
        device_id="dev-1", tenant_id="rh", status="active",
        last_heartbeat=datetime.now(timezone.utc), iccid="8901240200000000000",
    )
    s = _session(matched_tenant_id="rh", matched_device_id="dev-1")
    db = FakeDB(results=[[device]])  # _load_device → device
    result = await triage_svc.run_triage(db, s)
    health = next(c for c in result["checks"] if c["check"] == "device_health")
    assert health["status"] == "ok"
    last_seen = next(c for c in result["checks"] if c["check"] == "last_seen")
    assert last_seen["status"] == "ok"


# ════════════════════════════════════════════════════════════════════
# Router gating (TestClient + dependency overrides)
# ════════════════════════════════════════════════════════════════════

def _client(*, role="Admin", tenant="default"):
    app = FastAPI()
    app.include_router(ops_center.router, prefix="/api/ops-center")
    user = SimpleNamespace(role=role, tenant_id=tenant, email="op@true911.com", id=uuid4())
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[deps.get_db] = lambda: FakeDB()
    return TestClient(app, raise_server_exceptions=False)


def test_feature_off_returns_404(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_OPS_CENTER", "false")
    c = _client()
    # permitted role, but feature off → 404 (not 403): surface stays hidden
    r = c.post("/api/ops-center/lookup-asset", json={"identifier": "8563081391"})
    assert r.status_code == 404
    r2 = c.get("/api/ops-center/meta")
    assert r2.status_code == 404


def test_meta_returns_vocabularies_when_on(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_OPS_CENTER", "true")
    c = _client()
    r = c.get("/api/ops-center/meta")
    assert r.status_code == 200
    body = r.json()
    assert "no_dial_tone" in body["issue_categories"]
    assert "napco_radio" in body["identifier_types"]
    assert "customer_portal" in body["sources"]


def test_create_session_rejects_unknown_category(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_OPS_CENTER", "true")
    c = _client()
    r = c.post("/api/ops-center/session", json={"source": "phone", "issue_category": "not_a_real_category"})
    assert r.status_code == 422


def test_triage_blocked_until_verified(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_OPS_CENTER", "true")
    sid = uuid4()
    unverified = _session(id=sid, matched_tenant_id="rh", matched_device_id="dev-1",
                          verification_status="otp_sent")

    async def _fake_load(db, session_id, user):
        return unverified

    monkeypatch.setattr(ops_center, "_load_session", _fake_load)
    c = _client()
    r = c.post(f"/api/ops-center/session/{sid}/triage")
    assert r.status_code == 403
    assert "not verified" in r.json()["detail"].lower()


def test_lookup_requires_operate_permission(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_OPS_CENTER", "true")
    # CUSTOMER_READONLY has no OPS_CENTER_OPERATE grant → 403 before feature body
    c = _client(role="CUSTOMER_READONLY", tenant="rh")
    r = c.post("/api/ops-center/lookup-asset", json={"identifier": "8563081391"})
    assert r.status_code == 403


def test_features_endpoint_exposes_ops_center_flag(monkeypatch):
    from app.main import app as main_app
    monkeypatch.setattr("app.config.settings.FEATURE_OPS_CENTER", "true")
    client = TestClient(main_app, raise_server_exceptions=False)
    body = client.get("/api/config/features").json()
    assert body.get("ops_center") is True
