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


# ── audit analyzer (archive-aware, pure over gathered reports) ───────
def _report(tid, *, is_active=True, customers=None, sites=None, users=None,
            devices=0, archived_customers=0, archived_sites=0):
    customers = customers or []
    sites = sites or []
    users = users or []
    op_customers = sum(1 for c in customers if (c.get("status") or "active") not in ("archived", "retired"))
    op_sites = sum(1 for s in sites if (s.get("status") or "active") not in ("archived", "retired"))
    return {
        "tenant_id": tid,
        "is_active": is_active,
        "exists": True,
        "customers": customers,
        "sites": sites,
        "users": users,
        "operational": {
            "customers": op_customers, "sites": op_sites, "service_units": 0,
            "devices": devices, "sims": 0, "users": len(users),
            "registrations": 0, "subscriptions": 0,
        },
        "archived": {"customers": archived_customers, "sites": archived_sites},
        "subscriptions_active": 0,
    }


def test_analyze_retired_archive_only():
    # Post-cleanup ipm: retired, no operational records, only archived rows.
    ipm = _report("ipm", is_active=False, archived_customers=2, archived_sites=2)
    real = _report(
        "integrity-pm",
        customers=[{"id": 9, "name": "Integrity Property Management", "zoho": "337391000069074135", "status": "active"}],
        sites=[{"site_id": "IPM-BELLE-TERRE", "name": "Belle Terre", "customer_id": 9, "status": "active", "e911": "validated"}],
        users=[{"email": "cindy@ipmflorida.com", "role": "Admin", "active": True}],
        devices=3,
    )
    notes = " ".join(_analyze([ipm, real]))
    assert "Survivor: 'integrity-pm'" in notes
    assert "RETIRED / ARCHIVE ONLY" in notes               # not "would need migration"
    assert "would need migration" not in notes


def test_analyze_flags_operational_duplicate_zoho():
    a = _report("ipm", customers=[{"id": 1, "name": "IPM", "zoho": "Z1", "status": "active"}])
    b = _report("integrity-pm", customers=[{"id": 2, "name": "IPM", "zoho": "Z1", "status": "active"}])
    notes = " ".join(_analyze([a, b]))
    assert "Duplicate OPERATIONAL customer by Zoho account Z1" in notes


def test_analyze_ignores_archived_duplicate_zoho():
    # An archived duplicate is the intended cleanup result — not flagged.
    a = _report("ipm", is_active=False,
                customers=[{"id": 1, "name": "IPM", "zoho": "Z1", "status": "archived"}])
    b = _report("integrity-pm",
                customers=[{"id": 2, "name": "IPM", "zoho": "Z1", "status": "active"}])
    notes = " ".join(_analyze([a, b]))
    assert "Duplicate OPERATIONAL customer" not in notes


def test_analyze_flags_cross_tenant_operational_site_customer():
    a = _report("ipm", customers=[{"id": 1, "name": "IPM", "zoho": None, "status": "active"}])
    b = _report(
        "integrity-pm",
        customers=[{"id": 2, "name": "IPM", "zoho": None, "status": "active"}],
        sites=[{"site_id": "X", "name": "X", "customer_id": 1, "status": "active", "e911": None}],
    )
    notes = " ".join(_analyze([a, b]))
    assert "Cross-tenant site" in notes and "owned by tenant 'ipm'" in notes
