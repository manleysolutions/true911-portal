"""PR-C2 — customer dashboard endpoint + portfolio aggregation/mapping.

Covers GET /api/customer/dashboard (flag gate, RBAC, portfolio counts, headline,
attention feed, recent_manley_activity deferred) and the assurance->StatusObject
mapping in services/customer/portfolio.py (label map, no-false-green).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs
from app.services.assurance.signals import AssuranceLabel

RH = "restoration-hardware"
NOW = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


def _user(role="CUSTOMER_ADMIN", tenant=RH):
    return SimpleNamespace(role=role, tenant_id=tenant, email="judy@rh.example", id=1)


def _enable(monkeypatch, flag="true", allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_API", flag)
    monkeypatch.setattr("app.config.settings.CUSTOMER_API_TENANT_ALLOWLIST", allow)


def _client(role="CUSTOMER_ADMIN", tenant=RH):
    app = FastAPI()
    app.include_router(customer.router, prefix="/api/customer")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: _user(role=role, tenant=tenant)
    return TestClient(app, raise_server_exceptions=False)


def _site(sid, name, **kw):
    base = dict(id=sid, site_name=name, building_type="Gallery",
                e911_street="1 Main St", e911_city="Boston", e911_state="MA",
                e911_zip="02116", e911_status="validated", status="active",
                e911_confirmation_required=False,
                poc_name="Ops", poc_phone="555-0100", poc_email="ops@rh.example")
    base.update(kw)
    return SimpleNamespace(**base)


def _protected():
    return cs.status_object("Protected", as_of="t", evidence=cs.evidence_object("t", ["online"]))


async def _noop_lp(db, tenant, now):
    return []


async def _noop_cn(db, tenant):
    return "RH"


# ── Endpoint: dashboard ──────────────────────────────────────────────
def test_dashboard_200_with_portfolio(monkeypatch):
    _enable(monkeypatch)
    sites = [
        (_site(1, "RH A"), _protected()),
        (_site(2, "RH B"), cs.status_object("Critical", as_of="t", reason="Emergency address not verified")),
        (_site(3, "RH C"), cs.status_object("Attention Needed", as_of="t", reason="Reviewing an item")),
    ]

    async def _lp(db, tenant, now):
        return sites

    async def _cn(db, tenant):
        return "Restoration Hardware"

    monkeypatch.setattr(cportfolio, "load_portfolio", _lp)
    monkeypatch.setattr(cportfolio, "company_name", _cn)

    r = _client().get("/api/customer/dashboard")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["company"] == "Restoration Hardware"
    assert d["portfolio"] == {"total": 3, "protected": 1, "attention_needed": 1,
                              "critical": 1, "pending_install": 0, "inactive": 0, "unknown": 0}
    assert d["headline"].startswith("1 of 3 locations Protected")
    assert d["recent_manley_activity"] == []
    assert [it["status"] for it in d["attention_feed"]] == ["Critical", "Attention Needed"]
    assert d["attention_feed"][0]["location_ref"].startswith("loc_")
    assert "LEAK" not in r.text


def test_dashboard_empty_portfolio(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(cportfolio, "load_portfolio", _noop_lp)
    monkeypatch.setattr(cportfolio, "company_name", _noop_cn)
    d = _client().get("/api/customer/dashboard").json()["data"]
    assert d["portfolio"]["total"] == 0
    assert "setup" in d["headline"].lower()
    assert d["attention_feed"] == []


def test_dashboard_404_when_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false")
    monkeypatch.setattr(cportfolio, "load_portfolio", _noop_lp)
    assert _client().get("/api/customer/dashboard").status_code == 404


def test_dashboard_403_when_role_lacks_perm(monkeypatch):
    _enable(monkeypatch)  # flag on, RH allowlisted -> gate passes
    monkeypatch.setattr(cportfolio, "load_portfolio", _noop_lp)
    monkeypatch.setattr(cportfolio, "company_name", _noop_cn)
    # internal User sitting in the allowlisted tenant lacks CUSTOMER_VIEW_DASHBOARD
    assert _client(role="User").get("/api/customer/dashboard").status_code == 403


# ── Portfolio aggregation / mapping (no DB) ──────────────────────────
def test_label_map_covers_all_and_within_six_labels():
    assert set(cportfolio._LABEL_MAP) == set(AssuranceLabel)
    assert all(v in cs.SIX_LABELS for v in cportfolio._LABEL_MAP.values())


def test_protection_inactive_maps_to_inactive(monkeypatch):
    monkeypatch.setattr(cportfolio, "compute_site_assurance",
                        lambda signals, now: SimpleNamespace(label=AssuranceLabel.INACTIVE, reason_codes=(), devices=()))
    p = cportfolio.protection_from_assurance(SimpleNamespace(last_test=None), NOW)
    assert p["status"] == "Inactive"


def test_protection_protected_without_evidence_downgrades(monkeypatch):
    monkeypatch.setattr(cportfolio, "compute_site_assurance",
                        lambda signals, now: SimpleNamespace(label=AssuranceLabel.PROTECTED, reason_codes=(), devices=()))
    p = cportfolio.protection_from_assurance(SimpleNamespace(last_test=None), NOW)
    assert p["status"] == "Unknown"  # no evidence => no false green


def test_protection_protected_with_evidence(monkeypatch):
    dev = SimpleNamespace(last_heartbeat_at=NOW)
    monkeypatch.setattr(cportfolio, "compute_site_assurance",
                        lambda signals, now: SimpleNamespace(label=AssuranceLabel.PROTECTED, reason_codes=(), devices=(dev,)))
    p = cportfolio.protection_from_assurance(SimpleNamespace(last_test=None), NOW)
    assert p["status"] == "Protected" and p["evidence"]["signals"]
