"""Hardening of the public acquisition failure boundaries (post-#198).

1. The /register wizard: a registration and its acquisition record commit
   together, and so do submit and its acquisition status.  A partial failure
   rolls back to a state the response describes accurately, and a retry never
   duplicates anything (the old "saved but reported 500" condition is gone).
2. Rate limiting is unchanged; its client-identity limitation is explicit.
3. Unhandled 500s are generic; diagnostics stay in the server log.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.main import _unhandled_exception_handler
from app.middleware import RequestVisibilityMiddleware
from app.models.acquisition import AcquisitionRecord
from app.models.registration import Registration
from app.models.registration_location import RegistrationLocation
from app.models.registration_service_unit import RegistrationServiceUnit
from app.models.registration_status_event import RegistrationStatusEvent
from app.routers import acquisition as acq_router
from app.routers import public
from app.services import acquisition_service as acq

REG_TABLES = [m.__table__ for m in (Registration, RegistrationLocation, RegistrationServiceUnit,
                                    RegistrationStatusEvent)]
ALL_TABLES = [AcquisitionRecord.__table__, *REG_TABLES]
REAL_NOTIFY = acq.notify
SQL_TEXT = "SELECT password_hash FROM users WHERE email = 'ops@example.com'"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _limits_and_quiet_notify(monkeypatch):
    for lim in (acq.SHORT_LIMITER, acq.DAILY_LIMITER, acq.LOOKUP_LIMITER):
        lim.reset()
    calls = []

    async def _notify(db, rec, **kw):
        calls.append(rec.record_ref)
        return "not_configured"
    monkeypatch.setattr(acq, "notify", _notify)
    yield calls
    for lim in (acq.SHORT_LIMITER, acq.DAILY_LIMITER, acq.LOOKUP_LIMITER):
        lim.reset()


async def _db(tables=ALL_TABLES):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _app(sm):
    """Public + internal routers behind the REAL global 500 handler and the
    request-id middleware, as in app.main."""
    app = FastAPI()
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    app.add_middleware(RequestVisibilityMiddleware)
    app.include_router(public.router, prefix="/api/public")
    app.include_router(acq_router.router, prefix="/api/acquisition")

    async def _get_db():
        async with sm() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    return app


def _client(app, **headers):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                             base_url="http://t", headers=headers)


async def _counts(sm):
    async with sm() as s:
        regs = (await s.execute(select(func.count()).select_from(Registration))).scalar()
        recs = (await s.execute(select(func.count()).select_from(AcquisitionRecord))).scalar()
    return regs, recs


async def _acq_status(sm):
    async with sm() as s:
        return [r.status for r in (await s.execute(select(AcquisitionRecord))).scalars().all()]


WIZARD = {"submitter_email": "ops@portfolio.example", "submitter_name": "Sam",
          "customer_name": "Portfolio Co"}


# ── 1. wizard create is atomic ───────────────────────────────────────
def test_create_partial_failure_saves_nothing_and_says_so(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("acquisition write failed")
    monkeypatch.setattr(acq, "stage_record", boom)

    async def go():
        sm = await _db()
        async with _client(_app(sm)) as c:
            r = await c.post("/api/public/registrations", json=WIZARD)
        assert r.status_code == 503
        assert "nothing was stored" in r.json()["detail"]
        assert "resume_token" not in r.text
        assert await _counts(sm) == (0, 0)          # no orphan registration
    run(go())


def test_create_commit_failure_rolls_back_both_rows(monkeypatch):
    """A real constraint violation at COMMIT (duplicate record_ref) rolls back
    the registration too — atomicity, not just exception catching."""
    real_stage = acq.stage_record

    async def go():
        sm = await _db()
        async with sm() as s:
            s.add(AcquisitionRecord(record_ref="ACQ-TAKEN", kind="quote_request", status="inquiry",
                                    entry_point="quote_form", email="x@y.z", idempotency_key="existing-key-000001",
                                    notification_status="pending", notification_attempts=0))
            await s.commit()

        def colliding(db, **kw):
            rec = real_stage(db, **kw)
            rec.record_ref = "ACQ-TAKEN"
            return rec
        monkeypatch.setattr(acq, "stage_record", colliding)
        async with _client(_app(sm)) as c:
            r = await c.post("/api/public/registrations", json=WIZARD)
        assert r.status_code == 503
        assert await _counts(sm) == (0, 1)          # only the pre-existing record
    run(go())


def test_retry_after_create_failure_creates_exactly_one(monkeypatch):
    real_stage = acq.stage_record
    state = {"fail": True}

    def flaky(db, **kw):
        if state["fail"]:
            raise RuntimeError("transient")
        return real_stage(db, **kw)
    monkeypatch.setattr(acq, "stage_record", flaky)

    async def go():
        sm = await _db()
        async with _client(_app(sm)) as c:
            assert (await c.post("/api/public/registrations", json=WIZARD)).status_code == 503
            state["fail"] = False
            ok = await c.post("/api/public/registrations", json=WIZARD)
            assert ok.status_code == 201
            reg_id, token = ok.json()["registration"]["registration_id"], ok.json()["resume_token"]
            # resume behaviour intact
            got = await c.get(f"/api/public/registrations/{reg_id}", params={"token": token})
            assert got.status_code == 200 and got.json()["status"] == "draft"
            assert (await c.get(f"/api/public/registrations/{reg_id}",
                                params={"token": "wrong-token"})).status_code == 403
        assert await _counts(sm) == (1, 1)
        assert await _acq_status(sm) == ["assessment_draft"]
    run(go())


# ── 1b. wizard submit is atomic ──────────────────────────────────────
async def _created(c):
    r = await c.post("/api/public/registrations", json=WIZARD)
    assert r.status_code == 201, r.text
    return r.json()["registration"]["registration_id"], r.json()["resume_token"]


def test_submit_partial_failure_keeps_draft_and_retry_submits_once(monkeypatch, _limits_and_quiet_notify):
    real_stage = acq.stage_registration_status
    state = {"fail": True}

    async def flaky(db, ref, status):
        if state["fail"]:
            raise RuntimeError("acquisition status write failed")
        return await real_stage(db, ref, status)
    monkeypatch.setattr(acq, "stage_registration_status", flaky)

    async def go():
        sm = await _db()
        async with _client(_app(sm)) as c:
            reg_id, token = await _created(c)
            r = await c.post(f"/api/public/registrations/{reg_id}/submit", params={"token": token})
            assert r.status_code == 503 and "still saved as a draft" in r.json()["detail"]
            got = await c.get(f"/api/public/registrations/{reg_id}", params={"token": token})
            assert got.json()["status"] == "draft"           # response matched durable state
            assert await _acq_status(sm) == ["assessment_draft"]
            assert _limits_and_quiet_notify == []           # nothing notified for a rolled-back submit

            state["fail"] = False
            ok = await c.post(f"/api/public/registrations/{reg_id}/submit", params={"token": token})
            assert ok.status_code == 200 and ok.json()["status"] == "submitted"
            again = await c.post(f"/api/public/registrations/{reg_id}/submit", params={"token": token})
            assert again.status_code == 409                 # existing semantics kept
        assert await _counts(sm) == (1, 1)
        assert await _acq_status(sm) == ["assessment_submitted"]
        assert len(_limits_and_quiet_notify) == 1
    run(go())


def test_submit_side_effect_failure_after_commit_still_reports_submitted(monkeypatch):
    """The exact #198 defect shape: a side effect fails and rolls the session
    back after the durable write.  The response must still reflect it."""
    async def rolls_back_and_raises(db, rec, **kw):
        await db.rollback()
        raise RuntimeError("smtp exploded")
    monkeypatch.setattr(acq, "notify", rolls_back_and_raises)

    async def go():
        sm = await _db()
        async with _client(_app(sm)) as c:
            reg_id, token = await _created(c)
            r = await c.post(f"/api/public/registrations/{reg_id}/submit", params={"token": token})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "submitted"
        assert await _acq_status(sm) == ["assessment_submitted"]
    run(go())


def test_quote_receipt_survives_a_notify_rollback(monkeypatch):
    async def rolls_back(db, rec, **kw):
        await db.rollback()
        return "failed"
    monkeypatch.setattr(acq, "notify", rolls_back)

    async def go():
        sm = await _db()
        async with _client(_app(sm)) as c:
            r = await c.post("/api/public/quote-request", json={
                "company": "Acme", "name": "Pat", "email": "pat@example.com",
                "idempotency_key": "retry-attempt-quote-0001"})
        assert r.status_code == 201 and r.json()["received"] is True
    run(go())


# ── 2. rate limiting: unchanged by this PR, limitation explicit ──────
def _req(xff=None, peer="10.0.0.5"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


def test_client_identity_is_unchanged_from_198_and_not_claimed_trustworthy():
    """Characterization, not endorsement: the key is still the FIRST
    X-Forwarded-For entry (the #198 behaviour), so a client CAN rotate it.
    The trustworthy parsing boundary is deferred (BACKLOG A14); this test pins
    the behaviour so a future change is deliberate."""
    assert acq.client_key(_req("203.0.113.9")) == "203.0.113.9"
    assert acq.client_key(_req("198.51.100.1, 203.0.113.9")) == "198.51.100.1"   # spoofable
    assert acq.client_key(_req()) == "10.0.0.5"                                  # local / tests
    assert "KNOWN LIMITATION" in acq.client_key.__doc__
    from app.config import Settings
    assert "RATE_LIMIT_TRUSTED_PROXY_HOPS" not in Settings.model_fields         # no guessed hop model


def test_rate_limiter_is_documented_process_local():
    doc = acq.RateLimiter.__doc__
    assert "PROCESS-LOCAL" in doc and "NOT fleet-wide" in doc
    a, b = acq.RateLimiter(1, 60), acq.RateLimiter(1, 60)
    assert a.allow("k") and not a.allow("k")
    assert b.allow("k")                       # separate instances share nothing


# ── 3. sanitized 500s ────────────────────────────────────────────────
def _boom_app():
    app = FastAPI()
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    app.add_middleware(RequestVisibilityMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError(f"(psycopg.errors.UndefinedTable) {SQL_TEXT} at C:\\srv\\app\\db.py")
    return app


def test_unhandled_500_body_is_generic_and_logs_keep_diagnostics(caplog):
    async def go():
        async with _client(_boom_app()) as c:
            return await c.get("/boom")
    with caplog.at_level(logging.ERROR):
        r = run(go())
    assert r.status_code == 500
    body = r.json()
    assert set(body) == {"detail", "error", "request_id"}
    assert body["detail"] == "Internal server error." and body["error"] == "internal_error"
    for leak in ("SELECT", "password_hash", "UndefinedTable", "RuntimeError", "Traceback", "C:\\srv"):
        assert leak not in r.text, leak
    assert body["request_id"] and r.headers.get("X-Request-ID") == body["request_id"]
    log = caplog.text
    assert body["request_id"] in log and "RuntimeError" in log and "Traceback" in log and SQL_TEXT in log


def test_public_endpoint_db_error_returns_no_sql():
    async def go():
        sm = await _db(tables=REG_TABLES)                     # acquisition_records missing
        async with _client(_app(sm)) as c:
            return await c.post("/api/public/quote-request", json={
                "company": "Acme", "name": "Pat", "email": "pat@example.com",
                "idempotency_key": "missing-table-attempt-01"})
    r = run(go())
    assert r.status_code == 500 and r.json()["detail"] == "Internal server error."
    for leak in ("acquisition_records", "SELECT", "OperationalError", "no such table"):
        assert leak not in r.text, leak


def test_4xx_semantics_are_unchanged():
    async def go():
        sm = await _db()
        async with _client(_app(sm)) as c:
            bad = await c.post("/api/public/quote-request", json={
                "company": "Acme", "name": "Pat", "email": "nope", "idempotency_key": "x" * 20})
            missing = await c.get("/api/public/registrations/REG-NOPE", params={"token": "t"})
            unauth = await c.get("/api/acquisition/records")
            reg_id, token = await _created(c)
            forbidden = await c.get(f"/api/public/registrations/{reg_id}", params={"token": "wrong"})
        return bad, missing, unauth, forbidden
    bad, missing, unauth, forbidden = run(go())
    assert bad.status_code == 422 and isinstance(bad.json()["detail"], list)   # still field-level
    assert any("email" in (d.get("loc") or []) for d in bad.json()["detail"])
    assert missing.status_code == 404 and missing.json()["detail"] == "Registration not found"
    assert unauth.status_code == 401
    assert forbidden.status_code == 403 and forbidden.json()["detail"] == "Invalid resume token"


def test_http_exception_details_pass_through_untouched():
    app = FastAPI()
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    @app.get("/teapot")
    async def teapot():
        raise HTTPException(400, "Location ID is required.")

    async def go():
        async with _client(app) as c:
            return await c.get("/teapot")
    r = run(go())
    assert r.status_code == 400 and r.json() == {"detail": "Location ID is required."}


def test_route_level_500_in_site_import_is_sanitized():
    import inspect
    from app.routers import command_templates
    src = inspect.getsource(command_templates)
    assert 'f"Import failed: {str(e)' not in src
    assert "Import failed due to a server error" in src
