"""Phase 5 — Zoho lifecycle promotion (the only Zoho path that writes a site).

Asserts the safety contract: apply writes ONLY the additive lifecycle columns
(never sites.status), is gated by FEATURE_ZOHO_LIFECYCLE_PROMOTION, is idempotent,
and the promote endpoint defaults to a dry run.  Mapping confirmation and
promotion are Admin-only (MANAGE_INTEGRATIONS).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.zoho_lifecycle_promotion as promo
from app.dependencies import get_current_user, get_db
from app.models.external_record_map import ExternalRecordMap
from app.models.site import Site
from app.routers.zoho_promote import router


def _site(**kw):
    base = dict(
        site_id="WEBBER-A", status="active", lifecycle_status=None,
        lifecycle_source=None, lifecycle_synced_at=None, tenant_id="webber",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _rec(**kw):
    base = dict(subscription_mgmt_id="ZSM-WEBBER-001", lifecycle_state="deactivated", org_id="webber")
    base.update(kw)
    return SimpleNamespace(**base)


class _FlushDB:
    def __init__(self):
        self.flushed = False

    async def flush(self):
        self.flushed = True


# ── Service: planner + apply ─────────────────────────────────────────
class TestPromotionService:
    @pytest.mark.asyncio
    async def test_plan_reports_would_change(self, monkeypatch):
        rows = [(_rec(), object(), _site())]

        async def fake_rows(db, org):
            return rows

        monkeypatch.setattr(promo, "_confirmed_rows", fake_rows)
        plan = await promo.plan_site_promotion(None, "webber")
        assert plan[0]["proposed_lifecycle_status"] == "deactivated"
        assert plan[0]["current_lifecycle_status"] is None
        assert plan[0]["would_change"] is True
        assert plan[0]["operational_status"] == "active"

    @pytest.mark.asyncio
    async def test_apply_disabled_raises(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_LIFECYCLE_PROMOTION", "false")
        with pytest.raises(RuntimeError, match="disabled"):
            await promo.apply_site_promotion(_FlushDB(), "webber")

    @pytest.mark.asyncio
    async def test_apply_writes_only_lifecycle_not_operational(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_LIFECYCLE_PROMOTION", "true")
        site = _site()
        rows = [(_rec(lifecycle_state="deactivated"), object(), site)]

        async def fake_rows(db, org):
            return rows

        monkeypatch.setattr(promo, "_confirmed_rows", fake_rows)
        res = await promo.apply_site_promotion(_FlushDB(), "webber")

        assert res["applied_count"] == 1
        assert site.lifecycle_status == "deactivated"
        assert site.lifecycle_source == "zoho_crm"
        assert site.lifecycle_synced_at is not None
        # Operational status is NEVER touched.
        assert site.status == "active"

    @pytest.mark.asyncio
    async def test_apply_is_idempotent(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_LIFECYCLE_PROMOTION", "true")
        site = _site(lifecycle_status="deactivated")  # already matches
        rows = [(_rec(lifecycle_state="deactivated"), object(), site)]

        async def fake_rows(db, org):
            return rows

        monkeypatch.setattr(promo, "_confirmed_rows", fake_rows)
        res = await promo.apply_site_promotion(_FlushDB(), "webber")
        assert res["applied_count"] == 0


# ── Router: confirm + promote ────────────────────────────────────────
class _Result:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.committed = False

    async def execute(self, *a, **k):
        return self._results.pop(0)

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True


def _client(results=None, *, role="Admin", tenant_id="webber"):
    app = FastAPI()
    app.include_router(router, prefix="/api/integrations")
    fake = _FakeDB(results or [])

    async def _db():
        yield fake

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role=role, tenant_id=tenant_id, email="op@x.io"
    )
    client = TestClient(app)
    client._fake = fake
    return client


class TestConfirmEndpoint:
    def test_admin_confirms_mapping(self):
        rec_map = ExternalRecordMap(
            id=10, org_id="webber", source="zoho_crm", module="Subscription_Mgmt",
            external_record_id="ZSM-WEBBER-001", map_status="unmapped",
        )
        site = Site(site_id="WEBBER-A", tenant_id="webber")
        c = _client([_Result(rec_map), _Result(site)])
        r = c.post("/api/integrations/zoho/mappings/10/confirm", json={"site_id": "WEBBER-A"})
        assert r.status_code == 200
        body = r.json()
        assert body["mapping"]["map_status"] == "confirmed"
        assert body["mapping"]["site_id"] == "WEBBER-A"
        assert c._fake.committed is True

    def test_wrong_tenant_is_404(self):
        rec_map = ExternalRecordMap(
            id=10, org_id="other-tenant", source="zoho_crm", module="Subscription_Mgmt",
            external_record_id="X", map_status="unmapped",
        )
        c = _client([_Result(rec_map)])
        r = c.post("/api/integrations/zoho/mappings/10/confirm", json={"site_id": "WEBBER-A"})
        assert r.status_code == 404

    def test_unknown_site_is_400(self):
        rec_map = ExternalRecordMap(
            id=10, org_id="webber", source="zoho_crm", module="Subscription_Mgmt",
            external_record_id="X", map_status="unmapped",
        )
        c = _client([_Result(rec_map), _Result(None)])  # site lookup misses
        r = c.post("/api/integrations/zoho/mappings/10/confirm", json={"site_id": "NOPE"})
        assert r.status_code == 400

    def test_non_admin_forbidden(self):
        c = _client([], role="Manager")
        r = c.post("/api/integrations/zoho/mappings/10/confirm", json={})
        assert r.status_code == 403


class TestPromoteEndpoint:
    def test_dry_run_default_writes_nothing(self, monkeypatch):
        plan = [{"site_id": "WEBBER-A", "would_change": True, "proposed_lifecycle_status": "deactivated"}]

        async def fake_plan(db, org):
            return plan

        monkeypatch.setattr(promo, "plan_site_promotion", fake_plan)
        monkeypatch.setattr(promo, "promotion_enabled", lambda: False)

        c = _client()
        r = c.post("/api/integrations/zoho/promote")  # dry_run defaults True
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        assert body["applied"] is False
        assert body["would_change_count"] == 1
        assert c._fake.committed is False  # nothing committed on a dry run

    def test_apply_blocked_when_flag_off(self, monkeypatch):
        async def fake_plan(db, org):
            return []

        monkeypatch.setattr(promo, "plan_site_promotion", fake_plan)
        monkeypatch.setattr(promo, "promotion_enabled", lambda: False)

        c = _client()
        r = c.post("/api/integrations/zoho/promote?dry_run=false")
        assert r.status_code == 409

    def test_apply_when_flag_on(self, monkeypatch):
        async def fake_plan(db, org):
            return [{"would_change": True}]

        async def fake_apply(db, org):
            return {"applied_count": 1, "applied": [{"site_id": "WEBBER-A", "from": None, "to": "deactivated"}]}

        monkeypatch.setattr(promo, "plan_site_promotion", fake_plan)
        monkeypatch.setattr(promo, "promotion_enabled", lambda: True)
        monkeypatch.setattr(promo, "apply_site_promotion", fake_apply)

        c = _client()
        r = c.post("/api/integrations/zoho/promote?dry_run=false")
        assert r.status_code == 200
        body = r.json()
        assert body["applied"] is True
        assert body["applied_count"] == 1
        assert c._fake.committed is True

    def test_promote_forbidden_for_non_admin(self):
        c = _client([], role="Manager")
        r = c.post("/api/integrations/zoho/promote")
        assert r.status_code == 403
