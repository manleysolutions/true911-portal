"""Durable public acquisition (D-031): a prospect is told "received" only after
the submission is committed; notification is a recorded side effect; retries
are idempotent; abuse controls never produce a false receipt."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.acquisition import AcquisitionRecord
from app.models.registration import Registration
from app.models.registration_location import RegistrationLocation
from app.models.registration_service_unit import RegistrationServiceUnit
from app.models.registration_status_event import RegistrationStatusEvent
from app.models.site import Site
from app.routers import acquisition as acq_router
from app.routers import public
from app.services import acquisition_service as acq

from tests._customer_db import client_for

TABLES = [m.__table__ for m in (AcquisitionRecord, Registration, RegistrationLocation,
                                RegistrationServiceUnit, RegistrationStatusEvent)]
RETRY_TOKEN = "test-retry-attempt-0001"


@pytest.fixture(autouse=True)
def _fresh_limits(monkeypatch):
    for lim in (acq.SHORT_LIMITER, acq.DAILY_LIMITER, acq.LOOKUP_LIMITER):
        lim.reset()
    calls = []

    async def _notify(db, rec, **kw):            # count notifications; real logic tested below
        calls.append(rec.record_ref)
        return "not_configured"
    monkeypatch.setattr(acq, "notify", _notify)
    yield calls
    for lim in (acq.SHORT_LIMITER, acq.DAILY_LIMITER, acq.LOOKUP_LIMITER):
        lim.reset()


async def _db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
    return engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _client(sm, user=None):
    return client_for([(public.router, "/api/public"), (acq_router.router, "/api/acquisition")],
                      sm, {"user": user})


async def _count(sm):
    async with sm() as s:
        return (await s.execute(select(func.count()).select_from(AcquisitionRecord))).scalar()


async def _all(sm):
    async with sm() as s:
        return (await s.execute(select(AcquisitionRecord))).scalars().all()


def quote(**kw):
    body = {"company": "Acme Properties", "name": "Pat Doe", "email": "Pat@Example.com",
            "phone": "555-0100", "num_locations": 12, "service_interests": ["elevator", "bogus"],
            "needs": ["copper_replacement"], "notes": "Twelve buildings", "idempotency_key": RETRY_TOKEN}
    body.update(kw)
    return body


def run(coro):
    return asyncio.run(coro)


# ── durable success ──────────────────────────────────────────────────
def test_quote_receipt_only_after_commit(_fresh_limits):
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/quote-request", json=quote())
        assert r.status_code == 201
        body = r.json()
        assert body["received"] is True and body["record_ref"].startswith("ACQ-")
        (rec,) = await _all(sm)
        assert rec.record_ref == body["record_ref"]          # receipt names a durable row
        assert (rec.kind, rec.status, rec.entry_point) == ("quote_request", "inquiry", "quote_form")
        assert rec.email == "pat@example.com"
        assert json.loads(rec.service_interests) == ["elevator"]   # allow-listed
        assert _fresh_limits == [rec.record_ref]
    run(go())


def test_assessment_request_persists(_fresh_limits):
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/request-access", json={
                "company": "City Campus", "name": "Lee", "email": "lee@example.org",
                "role": "Facilities", "message": "hi", "idempotency_key": RETRY_TOKEN})
        assert r.status_code == 201
        (rec,) = await _all(sm)
        assert (rec.kind, rec.status) == ("assessment_request", "inquiry")
    run(go())


def test_retry_with_same_key_is_idempotent(_fresh_limits):
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            a = (await c.post("/api/public/quote-request", json=quote())).json()
            b = (await c.post("/api/public/quote-request", json=quote())).json()
        assert a["record_ref"] == b["record_ref"]
        assert await _count(sm) == 1
        assert len(_fresh_limits) == 1                      # no duplicate notification
    run(go())


# ── validation never yields a receipt ────────────────────────────────
@pytest.mark.parametrize("override", [
    {"email": "not-an-email"},
    {"company": "x" * 201},
    {"notes": "x" * 4001},
    {"company": "   "},
    {"num_locations": 0},
    {"idempotency_key": "short"},
    {"idempotency_key": "bad key with spaces!!"},
])
def test_invalid_input_is_rejected(override, _fresh_limits):
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/quote-request", json=quote(**override))
        assert r.status_code == 422
        assert "received" not in r.text
        assert await _count(sm) == 0 and _fresh_limits == []
    run(go())


def test_oversized_payload_is_413():
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/quote-request", content=json.dumps(quote(pad="x" * 20000)),
                             headers={"content-type": "application/json"})
        assert r.status_code == 413
        assert await _count(sm) == 0
    run(go())


def test_honeypot_never_acknowledged(_fresh_limits):
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/quote-request", json=quote(website="http://spam"))
        assert r.status_code == 422 and "received" not in r.text
        assert await _count(sm) == 0
    run(go())


def test_rate_limit_is_429_without_receipt():
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            codes = [(await c.post("/api/public/quote-request",
                                   json=quote(idempotency_key=f"k-{i:016d}"))).status_code
                     for i in range(6)]
        assert codes == [201] * 5 + [429]
        assert await _count(sm) == 5
    run(go())


# ── attribution ──────────────────────────────────────────────────────
def test_attribution_is_normalized():
    out = acq.normalize_attribution({
        "landing_path": "https://evil.example/x?token=1", "referrer": "javascript:alert(1)",
        "utm_source": "news\r\nletter" + "x" * 200, "initial_cta": "Hero Start!<b>",
        "unknown": "dropped"})
    assert out["landing_path"].startswith("/") and "?" not in out["landing_path"]
    assert "referrer" not in out
    assert "\n" not in out["utm_source"] and len(out["utm_source"]) == 100
    assert out["initial_cta"] == "herostartb"
    assert "unknown" not in out
    assert acq.normalize_attribution({"referrer": "https://g.example/s?q=secret"})["referrer"] \
        == "https://g.example/s"
    assert acq.normalize_attribution("nope") == {}


def test_attribution_stored_on_record():
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            await c.post("/api/public/quote-request", json=quote(attribution={
                "landing_path": "/quote?utm_source=x", "utm_source": "linkedin",
                "utm_campaign": "q3", "initial_cta": "hero_assessment"}))
        (rec,) = await _all(sm)
        assert (rec.landing_path, rec.utm_source, rec.utm_campaign, rec.initial_cta) == \
            ("/quote", "linkedin", "q3", "hero_assessment")
    run(go())


# ── notification: escaped, recorded, never loses the lead ─────────────
def _rec(**kw):
    base = dict(record_ref="ACQ-TEST", kind="quote_request", status="inquiry", email="a@b.co",
                company="<script>x</script>\r\nBcc: evil@x", contact_name="<b>n</b>",
                message="<img src=x onerror=1>", service_interests=None, needs=None,
                notification_attempts=0, entry_point="quote_form")
    base.update(kw)
    return AcquisitionRecord(**base)


def test_notification_content_is_escaped():
    subject, body = acq.notification_content(_rec())
    assert "\r" not in subject and "\n" not in subject
    assert "<script>" not in body and "&lt;script&gt;" in body
    assert "<img" not in body and "<b>n</b>" not in body
    assert "not verified" in body


class _FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _settings(host):
    return SimpleNamespace(SMTP_HOST=host, TRUE911_BOOTSTRAP_SUPERADMIN_EMAIL="ops@example.com")


@pytest.mark.parametrize("host,sender,expected", [
    ("", None, "not_configured"),
    ("smtp.example", "ok", "sent"),
    ("smtp.example", "false", "failed"),
    ("smtp.example", "raise", "failed"),
])
def test_notify_records_outcome(host, sender, expected):
    async def send(to, subject, body, settings=None):
        if sender == "raise":
            raise ConnectionError("down")
        return sender == "ok"

    async def go():
        rec, db = _rec(), _FakeDB()
        state = await _REAL_NOTIFY(db, rec, settings=_settings(host), sender=send)
        assert state == expected == rec.notification_status
        assert rec.notification_attempts == 1 and db.commits == 1
        assert (rec.notified_at is not None) == (expected == "sent")
        if expected == "failed":
            assert rec.notification_error
    run(go())


_REAL_NOTIFY = acq.notify       # captured at import, before the autouse fixture patches it


def test_notification_failure_keeps_the_lead(monkeypatch):
    async def boom(db, rec, **kw):
        return await _REAL_NOTIFY(db, rec, settings=_settings("smtp.example"),
                                  sender=_raise)

    async def _raise(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(acq, "notify", boom)

    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/quote-request", json=quote())
        assert r.status_code == 201 and r.json()["received"] is True
        (rec,) = await _all(sm)
        assert rec.notification_status == "failed" and rec.notification_attempts == 1
    run(go())


# ── registration wizard is linked, not a second pipeline ─────────────
def test_registration_creates_linked_assessment_record_and_no_site(_fresh_limits):
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/registrations", json={
                "submitter_email": "ops@portfolio.example", "submitter_name": "Sam",
                "customer_name": "Portfolio Co", "attribution": {"utm_source": "email"}})
            assert r.status_code == 201, r.text
            reg_id = r.json()["registration"]["registration_id"]
            token = r.json()["resume_token"]
            (rec,) = await _all(sm)
            assert (rec.kind, rec.status, rec.registration_ref) == ("assessment", "assessment_draft", reg_id)
            assert rec.utm_source == "email"
            assert _fresh_limits == []                    # drafts don't notify
            s = await c.post(f"/api/public/registrations/{reg_id}/submit", params={"token": token})
            assert s.status_code == 200, s.text
        (rec,) = await _all(sm)
        assert rec.status == "assessment_submitted"
        assert _fresh_limits == [rec.record_ref]
        # Site table isn't even created here: the public path cannot materialise sites.
        assert Site.__tablename__ not in {t.name for t in TABLES}
    run(go())


def test_registration_honeypot_rejected():
    async def go():
        _, sm = await _db()
        async with _client(sm) as c:
            r = await c.post("/api/public/registrations", json={
                "submitter_email": "a@b.example", "website": "spam"})
        assert r.status_code == 422
        assert await _count(sm) == 0
    run(go())


# ── internal queue is gated ──────────────────────────────────────────
def test_internal_list_requires_platform_role():
    async def go():
        _, sm = await _db()
        async with _client(sm, SimpleNamespace(role="User", tenant_id="acme", email="u@x", id=1,
                                               is_active=True)) as c:
            await c.post("/api/public/quote-request", json=quote())
            r = await c.get("/api/acquisition/records")
        assert r.status_code == 403
    run(go())
