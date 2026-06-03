"""Tests for the generic portfolio audit (pure classify/score/risks)."""

from __future__ import annotations

from app.portfolio_audit import (
    TenantMetrics,
    assess_tenant,
    classify_tenant,
    has_operational_records,
    risks_and_opportunities,
    score_tenant,
)


def _healthy(**kw):
    base = dict(
        tenant_id="restoration-hardware", name="Restoration Hardware", is_active=True,
        customers_op=1, sites_op=12, service_units=20, devices=45, sims=45, users=2,
        subscriptions=1, registrations=0,
        sites_with_e911_address=12, sites_e911_verified=12,
        devices_with_heartbeat=45, devices_fresh=45,
    )
    base.update(kw)
    return TenantMetrics(**base)


# ── classification ───────────────────────────────────────────────────
def test_healthy_active_tenant():
    c = classify_tenant(_healthy())
    assert c["primary"] == "ACTIVE"
    assert "active" in c["flags"] and "healthy" in c["flags"]


def test_retired_archive_only():
    m = TenantMetrics(tenant_id="ipm", name="Integrity Property Management",
                      is_active=False, customers_archived=2, sites_archived=2)
    c = classify_tenant(m)
    assert c["primary"] == "RETIRED / ARCHIVE ONLY"
    assert "retired" in c["flags"] and "archive-only" in c["flags"]
    assert score_tenant(m)["score"] is None              # no operational records


def test_empty_active_tenant():
    m = TenantMetrics(tenant_id="default", name="Default", is_active=True)
    assert classify_tenant(m)["primary"] == "EMPTY"
    assert "empty" in classify_tenant(m)["flags"]


def test_orphaned_tenant():
    m = _healthy(customers_op=0)  # sites/devices but no customer
    c = classify_tenant(m)
    assert c["primary"] == "ORPHANED" and "orphaned" in c["flags"]
    assert "healthy" not in c["flags"]


def test_duplicate_name_flag():
    m = _healthy(duplicate_name=True)
    c = classify_tenant(m)
    assert "duplicate-name" in c["flags"] and "healthy" not in c["flags"]


def test_retired_with_operational_is_flagged():
    m = _healthy(is_active=False)
    assert "has operational records" in classify_tenant(m)["primary"]


# ── scoring ──────────────────────────────────────────────────────────
def test_perfect_score():
    s = score_tenant(_healthy())
    assert s["score"] == 100
    assert s["components"] == {"e911": 40.0, "device_health": 30.0, "ownership": 20.0, "hygiene": 10.0}


def test_partial_score():
    m = _healthy(sites_op=10, sites_e911_verified=5,   # 50% e911
                 devices=10, devices_fresh=6)           # 60% device
    s = score_tenant(m)
    assert s["components"]["e911"] == 20.0              # 0.5 * 40
    assert s["components"]["device_health"] == 18.0     # 0.6 * 30
    assert s["score"] == round(20.0 + 18.0 + 20.0 + 10.0)


def test_no_devices_zeroes_device_health():
    m = _healthy(devices=0, devices_fresh=0, devices_with_heartbeat=0)
    s = score_tenant(m)
    assert s["components"]["device_health"] == 0.0


def test_hygiene_penalties():
    m = _healthy(duplicate_name=True)
    assert score_tenant(m)["components"]["hygiene"] == 5.0   # -0.5


# ── risks + opportunities ────────────────────────────────────────────
def test_missing_e911_is_a_risk():
    m = _healthy(sites_op=12, sites_e911_verified=8)
    risks = risks_and_opportunities(m)["risks"]
    assert any("without verified E911" in r for r in risks)


def test_stale_device_is_a_risk():
    m = _healthy(devices=45, devices_fresh=40)
    risks = risks_and_opportunities(m)["risks"]
    assert any("without a fresh heartbeat" in r for r in risks)


def test_retired_archive_rows_is_an_opportunity():
    m = TenantMetrics(tenant_id="ipm", is_active=False, customers_archived=2, sites_archived=2)
    opps = risks_and_opportunities(m)["opportunities"]
    assert any("eligible for final purge" in o for o in opps)


def test_empty_active_is_purge_eligible():
    m = TenantMetrics(tenant_id="default", is_active=True)
    opps = risks_and_opportunities(m)["opportunities"]
    assert any("purge-empty" in o for o in opps)


# ── assess_tenant aggregate ──────────────────────────────────────────
def test_assess_shape():
    a = assess_tenant(_healthy())
    for key in ("tenant_id", "status", "flags", "score", "components",
                "operational", "archived", "e911", "device_health", "risks", "opportunities"):
        assert key in a
    assert a["operational"]["sites"] == 12
    assert has_operational_records(_healthy()) is True
