"""Phase 3 — read-only Zoho lifecycle review endpoints.

Covers the pure serialization plus the endpoints mounted on a minimal app with
get_db / get_current_user overridden (no real DB), asserting shape, the
read_only contract, and RBAC (VIEW_INTEGRATIONS).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.models.external_record_map import ExternalRecordMap
from app.models.zoho_payload_observation import ZohoPayloadObservation
from app.models.zoho_subscription_record import ZohoSubscriptionRecord
from app.routers.zoho_review import (
    router,
    serialize_observation,
    serialize_review_row,
)

_NOW = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def _rec(**kw):
    base = dict(
        id=1, org_id="webber", subscription_mgmt_id="ZSM-WEBBER-001",
        account_name="Webber Infra", facility_name="Bldg A", msisdn="+15555550123",
        device_activation_status="De-activated", lifecycle_state="deactivated",
        connection_type="Static IP", subscription_type="IoT Data",
        mrc=45.00, service_term_ends=date(2026, 12, 31),
        external_record_map_id=10, last_event_id=7,
        first_seen_at=_NOW, updated_at=_NOW,
    )
    base.update(kw)
    return ZohoSubscriptionRecord(**base)


def _map(**kw):
    base = dict(
        id=10, org_id="webber", source="zoho_crm", module="Subscription_Mgmt",
        external_record_id="ZSM-WEBBER-001", map_status="unmapped",
    )
    base.update(kw)
    return ExternalRecordMap(**base)


# ── Result/session fakes ─────────────────────────────────────────────
class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def scalars(self):
        return _Scalars(self._rows)


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, *a, **k):
        return self._results.pop(0)


def _client(results, *, role="Admin", tenant_id="webber"):
    app = FastAPI()
    app.include_router(router, prefix="/api/integrations")
    fake = _FakeDB(results)

    async def _db():
        yield fake

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role=role, tenant_id=tenant_id, email="op@x.io"
    )
    return TestClient(app)


# ── Pure serialization ───────────────────────────────────────────────
class TestSerialize:
    def test_deactivated_row_unmapped(self):
        out = serialize_review_row(_rec(), None)
        assert out["device_activation_status"] == "De-activated"   # raw preserved
        assert out["lifecycle_state"] == "deactivated"             # normalized
        assert out["presents_as_active_monitoring"] is False
        assert out["map_status"] == "unmapped"
        assert out["linked"] is None
        assert out["mrc"] == 45.0
        assert out["service_term_ends"] == "2026-12-31"

    def test_mapped_row_exposes_links(self):
        rec_map = _map(map_status="confirmed", site_id="WEBBER-A", customer_id=99)
        out = serialize_review_row(_rec(), rec_map)
        assert out["map_status"] == "confirmed"
        assert out["linked"]["site_id"] == "WEBBER-A"
        assert out["linked"]["customer_id"] == 99

    def test_active_presents_as_active(self):
        out = serialize_review_row(_rec(device_activation_status="Active", lifecycle_state="active"), None)
        assert out["presents_as_active_monitoring"] is True

    def test_observation_serialization(self):
        obs = ZohoPayloadObservation(
            id=5, org_id="webber", module="Subscription_Mgmt", event_type="changed",
            matched_subscription=True, top_level_keys=["Account_Name"],
            sanitized_payload={"auth_token": "<redacted>"}, integration_event_id=7,
            created_at=_NOW,
        )
        out = serialize_observation(obs)
        assert out["matched_subscription"] is True
        assert out["sanitized_payload"]["auth_token"] == "<redacted>"
        assert out["created_at"].startswith("2026-06-02")


# ── Endpoints ────────────────────────────────────────────────────────
class TestEndpoints:
    def test_subscriptions_returns_items_and_readonly(self):
        results = [_Result(rows=[(_rec(), _map())]), _Result(scalar=1)]
        r = _client(results).get("/api/integrations/zoho/review/subscriptions")
        assert r.status_code == 200
        body = r.json()
        assert body["read_only"] is True
        assert "No production records are modified" in body["note"]
        assert body["total"] == 1
        assert body["items"][0]["subscription_mgmt_id"] == "ZSM-WEBBER-001"
        assert body["items"][0]["lifecycle_state"] == "deactivated"
        assert body["items"][0]["presents_as_active_monitoring"] is False

    def test_unmapped_returns_items(self):
        results = [_Result(rows=[(_rec(), _map())]), _Result(scalar=1)]
        r = _client(results).get("/api/integrations/zoho/review/unmapped")
        assert r.status_code == 200
        assert r.json()["items"][0]["map_status"] == "unmapped"

    def test_observations_returns_items(self):
        obs = ZohoPayloadObservation(
            id=5, org_id="webber", module="Subscription_Mgmt", event_type="changed",
            matched_subscription=True, top_level_keys=["Account_Name"],
            sanitized_payload={"x": 1}, integration_event_id=7, created_at=_NOW,
        )
        results = [_Result(rows=[obs]), _Result(scalar=1)]
        r = _client(results).get("/api/integrations/zoho/review/observations")
        assert r.status_code == 200
        assert r.json()["items"][0]["matched_subscription"] is True

    def test_forbidden_for_role_without_permission(self):
        # User role lacks VIEW_INTEGRATIONS -> 403, no DB access needed.
        r = _client([], role="User").get("/api/integrations/zoho/review/subscriptions")
        assert r.status_code == 403

    def test_manager_is_allowed(self):
        results = [_Result(rows=[]), _Result(scalar=0)]
        r = _client(results, role="Manager").get("/api/integrations/zoho/review/subscriptions")
        assert r.status_code == 200
        assert r.json()["total"] == 0
