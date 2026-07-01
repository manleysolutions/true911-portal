"""RH customer login readiness check — pure evaluation + E911 aggregation.

Covers scripts/rh_customer_readiness_check.py: the evaluate() exit-code matrix
(READY/BLOCKED/CONFIG) and summarize_e911 (verified only when stored, missing
endpoint detail surfaced) — all deterministic, no DB.
"""

from __future__ import annotations

from scripts import rh_customer_readiness_check as rc

RH = "restoration-hardware"


def _full_config():
    return {"feature_customer_api": True, "api_allowlisted": True,
            "feature_customer_preview": True, "preview_allowlisted": True}


def _ready_snapshot(**over):
    snap = {
        "tenant_id": RH, "tenant_exists": True, "tenant_active": True,
        "config": _full_config(),
        "customer_users": [{"email": "j***@rh.example", "role": "CUSTOMER_ADMIN",
                            "is_active": True, "name": "Judy"}],
        "judy_present": True,
        "counts": {"locations": 42, "devices": 51, "service_units": 51},
        "e911": {"total_locations": 42, "with_address": 42, "verified": 42,
                 "missing_or_unverified": 0, "missing_endpoint_detail": 0, "gap_sites": []},
    }
    snap.update(over)
    return snap


# ── evaluate() exit-code matrix ──────────────────────────────────────
def test_ready_when_all_present():
    report, code = rc.evaluate(_ready_snapshot())
    assert code == rc.READY and report["verdict"] == "READY"
    assert not report["blockers"] and not report["config_missing"]


def test_config_when_tenant_missing():
    _, code = rc.evaluate(_ready_snapshot(tenant_exists=False))
    assert code == rc.CONFIG


def test_config_when_flags_off():
    snap = _ready_snapshot(config={"feature_customer_api": False, "api_allowlisted": False,
                                   "feature_customer_preview": False, "preview_allowlisted": False})
    report, code = rc.evaluate(snap)
    assert code == rc.CONFIG and report["verdict"] == "CONFIG"
    assert len(report["config_missing"]) == 4


def test_blocked_when_e911_unverified():
    snap = _ready_snapshot(e911={"total_locations": 42, "with_address": 42, "verified": 40,
                                 "missing_or_unverified": 2, "missing_endpoint_detail": 0, "gap_sites": []})
    report, code = rc.evaluate(snap)
    assert code == rc.BLOCKED
    assert any("UNVERIFIED" in b for b in report["blockers"])


def test_blocked_when_missing_endpoint_detail():
    snap = _ready_snapshot(e911={"total_locations": 42, "with_address": 42, "verified": 42,
                                 "missing_or_unverified": 0, "missing_endpoint_detail": 3, "gap_sites": []})
    _, code = rc.evaluate(snap)
    assert code == rc.BLOCKED


def test_blocked_when_no_customer_users():
    _, code = rc.evaluate(_ready_snapshot(customer_users=[], judy_present=False))
    assert code == rc.BLOCKED


def test_blocked_when_zero_locations():
    snap = _ready_snapshot(counts={"locations": 0, "devices": 0, "service_units": 0})
    _, code = rc.evaluate(snap)
    assert code == rc.BLOCKED


def test_config_precedence_over_data_blockers():
    # config missing AND E911 gaps -> CONFIG wins (can't log in without config)
    snap = _ready_snapshot(
        config={"feature_customer_api": False, "api_allowlisted": True,
                "feature_customer_preview": True, "preview_allowlisted": True},
        e911={"total_locations": 42, "with_address": 40, "verified": 40,
              "missing_or_unverified": 2, "missing_endpoint_detail": 0, "gap_sites": []})
    _, code = rc.evaluate(snap)
    assert code == rc.CONFIG


# ── summarize_e911: E911 truth ───────────────────────────────────────
def _site(sid, status="validated", **over):
    base = dict(site_id=sid, site_name=f"Site {sid}", e911_street="1 Main St",
                e911_city="Boston", e911_state="MA", e911_zip="02116", e911_status=status)
    base.update(over)
    return base


def _unit(**over):
    base = dict(unit_id="SU-1", unit_name="Elevator", unit_type="elevator_phone",
                floor="1", location_description="Elevator #1", callback_number="6175550100")
    base.update(over)
    return base


def test_summarize_verified_only_when_stored():
    sites = [_site("A", status="validated"), _site("B", status="pending")]
    units = {"A": [_unit()], "B": [_unit()]}
    out = rc.summarize_e911(sites, units)
    assert out["total_locations"] == 2
    assert out["verified"] == 1                 # only the validated site
    assert out["missing_or_unverified"] == 1    # the pending one


def test_summarize_missing_endpoint_detail_when_no_units():
    sites = [_site("A", status="validated")]
    out = rc.summarize_e911(sites, {"A": []})   # verified + addressed, but NO service units
    assert out["verified"] == 1
    assert out["missing_endpoint_detail"] == 1  # no emergency endpoint on file
    assert out["missing_or_unverified"] == 0


def test_summarize_missing_callback_flags_endpoint_gap():
    sites = [_site("A", status="validated")]
    units = {"A": [_unit(callback_number=None, floor=None, location_description=None)]}
    out = rc.summarize_e911(sites, units)
    assert out["missing_endpoint_detail"] == 1


def test_summarize_missing_address():
    sites = [_site("A", status="pending", e911_street=None)]
    out = rc.summarize_e911(sites, {"A": [_unit()]})
    assert out["with_address"] == 0
    assert out["missing_or_unverified"] == 1


# ── helpers ──────────────────────────────────────────────────────────
def test_is_customer_role_prefix():
    assert rc.is_customer_role("CUSTOMER_ADMIN") is True
    assert rc.is_customer_role("CUSTOMER_MANAGER") is True
    assert rc.is_customer_role("Admin") is False
    assert rc.is_customer_role("User") is False
    assert rc.is_customer_role(None) is False


def test_mask_email_does_not_leak_local_part():
    assert rc._mask_email("judy@rh.example") == "j***@rh.example"
    assert rc._mask_email(None) == "—"
    assert "udy" not in rc._mask_email("judy@rh.example")
