"""Tests for tenant count assembly (admin endpoint) + the read-only audit analyzer."""

from __future__ import annotations

from types import SimpleNamespace

from app.routers.admin import assemble_tenant_rows
from app.audit_integrity_tenants import _analyze


def _tenant(tid, name="N", org="customer"):
    return SimpleNamespace(tenant_id=tid, name=name, org_type=org, created_at=None)


# ── assemble_tenant_rows (pure merge) ────────────────────────────────
def test_assemble_merges_counts_and_defaults_zero():
    tenants = [_tenant("ipm", "Integrity Property Management"),
               _tenant("integrity-pm", "Integrity Property Management")]
    count_maps = {
        "customers": {"integrity-pm": 1},
        "sites": {"integrity-pm": 4},
        "devices": {"integrity-pm": 3},
        "users": {"integrity-pm": 1},
    }
    rows = assemble_tenant_rows(tenants, count_maps)
    by_id = {r["tenant_id"]: r for r in rows}
    # ipm is empty → all zero
    assert by_id["ipm"]["customers"] == 0
    assert by_id["ipm"]["sites"] == 0
    assert by_id["ipm"]["devices"] == 0
    assert by_id["ipm"]["users"] == 0
    # integrity-pm carries the real data
    assert by_id["integrity-pm"]["customers"] == 1
    assert by_id["integrity-pm"]["sites"] == 4
    assert by_id["integrity-pm"]["devices"] == 3
    assert by_id["integrity-pm"]["users"] == 1
    # passthrough fields
    assert by_id["integrity-pm"]["name"] == "Integrity Property Management"
    assert by_id["ipm"]["org_type"] == "customer"


# ── audit analyzer (pure over gathered reports) ──────────────────────
def _report(tid, *, customers=None, sites=None, users=None, devices=0):
    return {
        "tenant_id": tid,
        "customers": customers or [],
        "sites": sites or [],
        "users": users or [],
        "devices": devices,
        "sims": 0, "service_units": 0,
        "registrations": 0, "subscriptions": 0, "subscriptions_active": 0,
    }


def test_analyze_picks_nonempty_survivor_and_flags_empty():
    ipm = _report("ipm")  # empty
    real = _report(
        "integrity-pm",
        customers=[{"id": 9, "name": "Integrity Property Management", "zoho": "337391000069074135"}],
        sites=[{"site_id": "IPM-BELLE-TERRE", "name": "Belle Terre", "customer_id": 9, "status": "active", "e911": "validated"}],
        users=[{"email": "cindy@ipmflorida.com", "role": "Admin", "active": True}],
        devices=3,
    )
    notes = " ".join(_analyze([ipm, real]))
    assert "Survivor candidate: 'integrity-pm'" in notes
    assert "Obsolete/empty: 'ipm'" in notes


def test_analyze_flags_duplicate_zoho_customer():
    a = _report("ipm", customers=[{"id": 1, "name": "IPM", "zoho": "Z1"}])
    b = _report("integrity-pm", customers=[{"id": 2, "name": "IPM", "zoho": "Z1"}])
    notes = " ".join(_analyze([a, b]))
    assert "Duplicate customer by Zoho account Z1" in notes


def test_analyze_flags_cross_tenant_site_customer():
    a = _report("ipm", customers=[{"id": 1, "name": "IPM", "zoho": None}])
    b = _report(
        "integrity-pm",
        customers=[{"id": 2, "name": "IPM", "zoho": None}],
        # site in integrity-pm pointing at ipm's customer #1
        sites=[{"site_id": "X", "name": "X", "customer_id": 1, "status": "active", "e911": None}],
    )
    notes = " ".join(_analyze([a, b]))
    assert "Cross-tenant site" in notes and "owned by tenant 'ipm'" in notes
