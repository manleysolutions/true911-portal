"""Customer E911 confirmation + correction workflow (append-only, safe).

Covers the service (confirm/correction never touch official records; event→review
derivation; friendly status; approve/reject/apply) and the endpoints (customer
submit RBAC + gate + 404; internal review queue RBAC; cross-tenant; backward
compatibility of existing E911 APIs).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer, e911 as e911_router
from app.services import e911_review as er
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs

RH = "restoration-hardware"
NOW = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self_inner):
                return list(rows)
        return _S()


class _FakeDB:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.committed = 0

    async def execute(self, stmt):
        return self._results.pop(0) if self._results else _Res([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _user(role="CUSTOMER_ADMIN", tenant=RH):
    return SimpleNamespace(role=role, tenant_id=tenant, email="judy@rh.example", name="Judy", id="u1")


def _site(status="active", e911_status="pending"):
    return SimpleNamespace(site_id="RH-1", site_name="RH Boston", status=status,
                           e911_status=e911_status, e911_street="1 Main", e911_city="Boston",
                           e911_state="MA", e911_zip="02116", e911_confirmation_required=False)


def _event(action_type, review_id, *, rtype="confirm", note=None, corrected=None,
           by="Judy", at=NOW, site_id="RH-1"):
    details = {"review_id": review_id, "type": rtype, "note": note, "corrected": corrected,
               "address_snapshot": "1 Main, Boston, MA 02116"}
    return SimpleNamespace(action_type=action_type, details=json.dumps(details), site_id=site_id,
                           requester_name=by, user_email="x@y.z", timestamp=at)


# ── Service: submissions never touch official records ────────────────
def test_confirmation_records_audit_only():
    db = _FakeDB()
    site = _site()
    out = asyncio.run(er.record_confirmation(db, _user(), site,
                                             snapshot={"emergency_dispatch_address": "1 Main, Boston, MA 02116",
                                                       "emergency_endpoints": [], "verification": {"verified": False}},
                                             note="looks right"))
    assert out["status"] == "pending" and out["review_id"].startswith("REV-")
    assert "pending Manley verification" in out["message"]
    # ONLY an append-only audit row was written; the official site is untouched.
    assert len(db.added) == 1 and db.committed == 1
    a = db.added[0]
    assert a.action_type == er.CONFIRM and a.site_id == "RH-1"
    assert site.e911_status == "pending"   # official record unchanged


def test_correction_records_request_only():
    db = _FakeDB()
    site = _site()
    out = asyncio.run(er.record_correction(db, _user(), site,
                                           corrected={"address": "2 Berkeley St", "floor": "3"},
                                           snapshot={"emergency_dispatch_address": "1 Main"}, note="moved"))
    assert out["status"] == "pending"
    a = db.added[0]
    assert a.action_type == er.CORRECTION
    d = json.loads(a.details)
    assert d["corrected"]["address"] == "2 Berkeley St"   # stored as a REQUEST, not applied
    assert site.e911_street == "1 Main"                    # official record unchanged


# ── Event → review derivation + friendly status ─────────────────────
def test_build_reviews_status_transitions():
    events = [
        _event(er.CONFIRM, "r1"),
        _event(er.CORRECTION, "r2", rtype="correction"),
        _event(er.REJECT, "r1"),
        _event(er.APPROVE, "r2"),
    ]
    reviews = {r["review_id"]: r for r in er._build_reviews(events)}
    assert reviews["r1"]["status"] == "rejected"
    assert reviews["r2"]["status"] == "approved" and reviews["r2"]["type"] == "correction"


def test_location_review_status_friendly_states():
    # verified official record -> Verified regardless of reviews
    v = asyncio.run(er.location_review_status(_FakeDB([_Res([])]), RH, _site(e911_status="validated")))
    assert v["state"] == "Verified" and v["verified"] is True
    # pending confirm -> Customer confirmed
    c = asyncio.run(er.location_review_status(_FakeDB([_Res([_event(er.CONFIRM, "r1")])]), RH, _site()))
    assert c["state"] == "Customer confirmed"
    # pending correction -> Correction requested
    cr = asyncio.run(er.location_review_status(
        _FakeDB([_Res([_event(er.CORRECTION, "r2", rtype="correction")])]), RH, _site()))
    assert cr["state"] == "Correction requested"
    # approved -> Under Manley review
    ap = asyncio.run(er.location_review_status(
        _FakeDB([_Res([_event(er.CONFIRM, "r1"), _event(er.APPROVE, "r1")])]), RH, _site()))
    assert ap["state"] == "Under Manley review"


def test_decide_approve_reject_apply():
    # find_review + decide each issue their own _events() query
    def db_for(events):
        return _FakeDB([_Res(events)])
    approve = asyncio.run(er.decide(db_for([_event(er.CONFIRM, "r1")]), _user(role="Admin"),
                                    "r1", decision="approve"))
    assert approve["status"] == "approved"
    apply = asyncio.run(er.decide(db_for([_event(er.CONFIRM, "r1")]), _user(role="Admin"),
                                  "r1", decision="approve", apply=True))
    assert apply["status"] == "applied"
    missing = asyncio.run(er.decide(db_for([]), _user(role="Admin"), "nope", decision="reject"))
    assert missing is None


# ── Endpoints: customer submit RBAC + gate + 404 ─────────────────────
def _cust_client(role="CUSTOMER_ADMIN", tenant=RH):
    app = FastAPI()
    app.include_router(customer.router, prefix="/api/customer")
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[get_current_user] = lambda: _user(role=role, tenant=tenant)
    return TestClient(app, raise_server_exceptions=False)


def _enable(monkeypatch, flag="true", allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_API", flag)
    monkeypatch.setattr("app.config.settings.CUSTOMER_API_TENANT_ALLOWLIST", allow)


def _patch_site(monkeypatch, site):
    async def _rs(db, t, ref):
        return site

    async def _eps(db, t, sid):
        return []
    monkeypatch.setattr(cportfolio, "resolve_site", _rs)
    monkeypatch.setattr(cportfolio, "load_e911_endpoints", _eps)


REF = cs.encode_ref("loc", 1)


def test_customer_confirm_submitter_ok(monkeypatch):
    _enable(monkeypatch)
    _patch_site(monkeypatch, _site())

    async def _rc(db, user, site, *, snapshot, note=""):
        return {"review_id": "REV-x", "status": "pending", "message": "Customer confirmed — pending Manley verification"}
    monkeypatch.setattr(er, "record_confirmation", _rc)
    r = _cust_client(role="CUSTOMER_ADMIN").post(f"/api/customer/locations/{REF}/e911/confirm", json={"note": "ok"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "pending"


def test_customer_correction_submitter_ok(monkeypatch):
    _enable(monkeypatch)
    _patch_site(monkeypatch, _site())

    async def _rc(db, user, site, *, corrected, snapshot, note=""):
        assert corrected["address"] == "2 Berkeley"
        return {"review_id": "REV-y", "status": "pending", "message": "Correction submitted — under Manley review"}
    monkeypatch.setattr(er, "record_correction", _rc)
    r = _cust_client().post(f"/api/customer/locations/{REF}/e911/correction-request",
                            json={"corrected_address": "2 Berkeley", "floor": "3", "note": "moved"})
    assert r.status_code == 200


def test_customer_viewer_cannot_submit_but_can_view(monkeypatch):
    _enable(monkeypatch)
    _patch_site(monkeypatch, _site())

    async def _st(db, t, site):
        return {"state": "Not yet verified", "verified": False, "review_count": 0, "latest_review": None}
    monkeypatch.setattr(er, "location_review_status", _st)
    # read-only role: submit 403, view 200
    assert _cust_client(role="CUSTOMER_VIEWER").post(
        f"/api/customer/locations/{REF}/e911/confirm", json={}).status_code == 403
    assert _cust_client(role="CUSTOMER_VIEWER").get(
        f"/api/customer/locations/{REF}/e911/review-status").status_code == 200


def test_customer_confirm_404_flag_off_and_unknown_ref(monkeypatch):
    _enable(monkeypatch, flag="false")
    assert _cust_client().post(f"/api/customer/locations/{REF}/e911/confirm", json={}).status_code == 404
    _enable(monkeypatch)

    async def _none(db, t, ref):
        return None
    monkeypatch.setattr(cportfolio, "resolve_site", _none)          # unknown / cross-tenant ref
    assert _cust_client().post(f"/api/customer/locations/{REF}/e911/confirm", json={}).status_code == 404


# ── Internal review queue: RBAC (customer isolated) ──────────────────
def _int_client(role="Admin", tenant=RH):
    app = FastAPI()
    app.include_router(e911_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[get_current_user] = lambda: _user(role=role, tenant=tenant)
    return TestClient(app, raise_server_exceptions=False)


def test_internal_reviews_rbac(monkeypatch):
    async def _lr(db, t, *, status="pending"):
        return {"count": 1, "status_filter": status, "reviews": [{"review_id": "r1", "status": "pending"}]}
    monkeypatch.setattr(er, "list_reviews", _lr)
    assert _int_client(role="Admin").get("/api/e911-changes/reviews").status_code == 200
    assert _int_client(role="DataSteward").get("/api/e911-changes/reviews").status_code == 200
    # customer roles are isolated from the internal queue
    assert _int_client(role="CUSTOMER_ADMIN").get("/api/e911-changes/reviews").status_code == 403
    assert _int_client(role="User").get("/api/e911-changes/reviews").status_code == 403


def test_internal_approve_reject(monkeypatch):
    async def _decide(db, user, rid, *, decision, note="", apply=False):
        return None if rid == "missing" else {"review_id": rid, "decision": decision,
                                              "status": "approved" if decision == "approve" else "rejected"}
    monkeypatch.setattr(er, "decide", _decide)
    assert _int_client(role="Admin").post("/api/e911-changes/reviews/r1/approve", json={}).status_code == 200
    assert _int_client(role="Admin").post("/api/e911-changes/reviews/r1/reject", json={}).status_code == 200
    assert _int_client(role="Admin").post("/api/e911-changes/reviews/missing/approve", json={}).status_code == 404
    # customer cannot decide
    assert _int_client(role="CUSTOMER_ADMIN").post(
        "/api/e911-changes/reviews/r1/approve", json={}).status_code == 403


# ── Backward compatibility: existing E911 change APIs unchanged ──────
def test_existing_e911_changes_list_still_works(monkeypatch):
    # GET /api/e911-changes (list_changes) is unauthenticated-permission (bare auth)
    # and must still respond for an internal user — the new routes are additive.
    async def _exec(stmt):
        return _Res([])
    db = _FakeDB()
    db.execute = _exec
    app = FastAPI()
    app.include_router(e911_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _user(role="Admin")
    r = TestClient(app, raise_server_exceptions=False).get("/api/e911-changes")
    assert r.status_code == 200
