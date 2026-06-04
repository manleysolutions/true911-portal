"""Tests for the Zoho ↔ True911 customer reconciliation audit (pure, no DB)."""

from __future__ import annotations

import json
from pathlib import Path

from app.audit_zoho_true911_customer_reconciliation import (
    ACTIVE_ZOHO_INACTIVE_T911,
    DEACT_ZOHO_ACTIVE_T911,
    DUPLICATE_CANDIDATE,
    MATCHED_OK,
    MISSING_IN_TRUE911,
    MISSING_IN_ZOHO,
    NEEDS_MAPPING,
    STATUS_MISMATCH,
    derive_zoho_lifecycle,
    normalize_msisdn,
    normalize_name,
    overall_summary,
    reconcile_customer,
    scope_true911_by_customer,
    true911_presents_active,
    write_csv,
    write_json,
)


def zrec(*, sub_id="SM-1", account="Webber Infrastructure", facility=None,
         msisdn=None, activation="Active", lifecycle=None, map_status="confirmed"):
    return {"subscription_mgmt_id": sub_id, "account_name": account,
            "facility_name": facility, "msisdn": msisdn,
            "device_activation_status": activation, "lifecycle_state": lifecycle,
            "map_status": map_status}


def t911(*, name="Webber", customer_status="active", tenant_active=True,
         devices=None, lines=None, sites=None):
    return {
        "customer": {"name": name, "status": customer_status, "tenant_id": "webber"},
        "tenant": {"tenant_id": "webber", "name": name, "is_active": tenant_active},
        "sites": sites or [],
        "devices": devices or [],
        "lines": lines or [],
    }


def _classes(rec):
    return [f.classification for f in rec.findings]


# ── pure helpers ─────────────────────────────────────────────────────────
def test_normalizers():
    assert normalize_name("Webber Infrastructure, LLC") == "webber"
    assert normalize_name("Restoration Hardware Inc.") == "restoration hardware"
    assert normalize_msisdn("+1 (856) 308-1391") == "8563081391"
    assert normalize_msisdn("8563081391") == "8563081391"


def test_derive_lifecycle_from_raw_when_column_null():
    assert derive_zoho_lifecycle(zrec(activation="De-activated", lifecycle=None)) == "deactivated"
    assert derive_zoho_lifecycle(zrec(activation="Active", lifecycle=None)) == "active"
    # explicit normalized column wins
    assert derive_zoho_lifecycle(zrec(activation="weird", lifecycle="suspended")) == "suspended"


# 1 — matched active customer
def test_matched_active_customer():
    z = [zrec(msisdn="8563081391", activation="Active")]
    t = t911(devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"}])
    rec = reconcile_customer("Webber", z, t)
    assert MATCHED_OK in _classes(rec)
    assert DEACT_ZOHO_ACTIVE_T911 not in _classes(rec)
    assert STATUS_MISMATCH not in _classes(rec)


# 2 — deactivated Zoho / active True911 (the Webber headline, task 6)
def test_webber_deactivated_zoho_active_true911():
    z = [zrec(account="Webber Infrastructure", activation="De-activated",
              msisdn="8563081391")]
    t = t911(name="Webber", customer_status="active", tenant_active=True,
             devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"}])
    rec = reconcile_customer("Webber", z, t)
    assert DEACT_ZOHO_ACTIVE_T911 in _classes(rec)
    # and the per-MSISDN axis flags the same conflict
    assert STATUS_MISMATCH in _classes(rec)


# 3 — active Zoho / inactive True911
def test_active_zoho_inactive_true911():
    z = [zrec(activation="Active", msisdn="8563081391")]
    t = t911(customer_status="inactive", tenant_active=False,
             devices=[{"device_id": "d1", "status": "decommissioned", "msisdn": "8563081391"}])
    rec = reconcile_customer("Webber", z, t)
    assert ACTIVE_ZOHO_INACTIVE_T911 in _classes(rec)


# 4 — missing/unconfirmed Zoho subscription mapping
def test_needs_mapping_when_unconfirmed():
    z = [zrec(map_status="unmapped", msisdn="8563081391")]
    t = t911(devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"}])
    rec = reconcile_customer("Webber", z, t)
    assert NEEDS_MAPPING in _classes(rec)


def test_needs_mapping_when_no_true911_entity():
    z = [zrec(msisdn="8563081391")]
    empty = {"customer": {}, "tenant": {}, "sites": [], "devices": [], "lines": []}
    rec = reconcile_customer("Ghost Co", z, empty)
    assert NEEDS_MAPPING in _classes(rec)


# 5 — duplicate MSISDN
def test_duplicate_msisdn_across_zoho_records():
    z = [zrec(sub_id="SM-1", msisdn="8563081391"),
         zrec(sub_id="SM-2", msisdn="+1-856-308-1391")]
    t = t911(devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"}])
    rec = reconcile_customer("Webber", z, t)
    assert DUPLICATE_CANDIDATE in _classes(rec)


def test_duplicate_msisdn_across_true911_entities():
    z = [zrec(msisdn="8563081391")]
    t = t911(devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"},
                      {"device_id": "d2", "status": "active", "msisdn": "18563081391"}])
    rec = reconcile_customer("Webber", z, t)
    assert DUPLICATE_CANDIDATE in _classes(rec)


# 6 — missing site
def test_missing_site():
    z = [zrec(facility="Webber Plant 5", msisdn="8563081391")]
    t = t911(sites=[{"site_id": "s1", "site_name": "Webber Plant 1", "status": "active"}],
             devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"}])
    rec = reconcile_customer("Webber", z, t)
    site_findings = [f for f in rec.findings
                     if f.classification == MISSING_IN_TRUE911 and f.scope == "site"]
    assert site_findings, "expected a missing_in_true911 site finding"


# 7 — missing device (Zoho MSISDN with no True911 entity)
def test_missing_device():
    z = [zrec(msisdn="8563081391")]
    t = t911(devices=[])  # no devices/lines carry the MSISDN
    rec = reconcile_customer("Webber", z, t)
    msisdn_missing = [f for f in rec.findings
                      if f.classification == MISSING_IN_TRUE911 and f.scope == "msisdn"]
    assert msisdn_missing


def test_missing_in_zoho_for_extra_true911_line():
    z = [zrec(msisdn="8563081391")]
    t = t911(devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"}],
             lines=[{"line_id": "L1", "status": "active", "did": "7542697860"}])
    rec = reconcile_customer("Webber", z, t)
    assert MISSING_IN_ZOHO in _classes(rec)


# ── summary + export ─────────────────────────────────────────────────────
def test_overall_summary_and_exports(tmp_path):
    recs = [
        reconcile_customer("Webber", [zrec(activation="De-activated", msisdn="8563081391")],
                           t911(devices=[{"device_id": "d1", "status": "active", "msisdn": "8563081391"}])),
        reconcile_customer("RH", [zrec(account="Restoration Hardware", activation="Active", msisdn="7542697860")],
                           t911(name="Restoration Hardware",
                                devices=[{"device_id": "d2", "status": "active", "msisdn": "7542697860"}])),
    ]
    summ = overall_summary(recs)
    assert summ[DEACT_ZOHO_ACTIVE_T911] >= 1
    assert summ[MATCHED_OK] >= 1
    j = tmp_path / "r.json"
    write_json(recs, str(j))
    doc = json.loads(j.read_text(encoding="utf-8"))
    assert doc["read_only"] is True and len(doc["customers"]) == 2
    c = tmp_path / "r.csv"
    n = write_csv(recs, str(c))
    assert n > 0 and "classification" in c.read_text(encoding="utf-8").splitlines()[0]


def test_true911_presents_active_rules():
    assert true911_presents_active(t911(customer_status="active", tenant_active=True)) is True
    assert true911_presents_active(t911(customer_status="active", tenant_active=False)) is False
    assert true911_presents_active(t911(customer_status="inactive",
                                        devices=[{"status": "active"}])) is True
    assert true911_presents_active(t911(customer_status="inactive", devices=[])) is False


# ── customer-scoped ownership (Customer -> Sites -> Devices) ─────────────
def _cust(cid, name, *, tenant="default", status="active"):
    return {"id": cid, "name": name, "tenant_id": tenant, "status": status,
            "zoho_account_id": None, "onboarding_status": None}


def _site(sid, customer_id, *, tenant="default", status="active"):
    return {"site_id": sid, "customer_id": customer_id, "tenant_id": tenant,
            "site_name": sid, "status": status}


def _dvc(did, site_id, *, tenant="default", status="active", msisdn=None):
    return {"device_id": did, "site_id": site_id, "tenant_id": tenant,
            "status": status, "msisdn": msisdn, "model": None, "iccid": None,
            "network_status": None}


def _ln(lid, *, customer_id=None, site_id=None, tenant="default", status="active", did=None):
    return {"line_id": lid, "customer_id": customer_id, "site_id": site_id,
            "tenant_id": tenant, "status": status, "did": did, "sim_iccid": None}


def test_shared_tenant_scopes_only_matched_customer():
    # Two customers in the SHARED 'default' tenant — Webber must not inherit Acme's.
    customers = [_cust(1, "Webber Infra"), _cust(2, "Acme Co")]
    sites = [_site("S1", 1), _site("S2", 2)]
    devices = [_dvc("D1", "S1"), _dvc("D2", "S2"), _dvc("D3", "S2")]
    lines = [_ln("L1", customer_id=1), _ln("L2", customer_id=2)]
    t = scope_true911_by_customer("Webber", customers, sites, devices, lines)
    assert [s["site_id"] for s in t["sites"]] == ["S1"]
    assert [d["device_id"] for d in t["devices"]] == ["D1"]      # NOT D2/D3
    assert [l["line_id"] for l in t["lines"]] == ["L1"]
    assert t["matched_customer_count"] == 1


def test_webber_style_excludes_other_default_tenant_devices():
    # 'default' holds 51 customers; Webber owns just 2 devices. The audit used to
    # report the whole tenant (the 177-device bug) — now it reports only Webber's.
    customers = [_cust(5, "Webber Infra")] + [_cust(i, f"Cust {i}") for i in range(10, 60)]
    sites = [_site("W1", 5)] + [_site(f"O{i}", i) for i in range(10, 60)]
    devices = [_dvc("WD1", "W1"), _dvc("WD2", "W1")] + [_dvc(f"OD{i}", f"O{i}") for i in range(10, 60)]
    t = scope_true911_by_customer("Webber", customers, sites, devices, [])
    assert sorted(d["device_id"] for d in t["devices"]) == ["WD1", "WD2"]
    assert len(t["devices"]) == 2                                # not 52


def test_dedicated_tenant_adopts_unlinked_rows():
    # Webber is the SOLE customer of tenant 'webber'; legacy sites/devices/lines
    # without explicit customer links still belong to it.
    customers = [_cust(9, "Webber Infra", tenant="webber")]
    sites = [_site("WS1", None, tenant="webber"), _site("WS2", 9, tenant="webber")]
    devices = [_dvc("DA", "WS1", tenant="webber"), _dvc("DB", "WS2", tenant="webber"),
               _dvc("DC", None, tenant="webber")]
    lines = [_ln("LA", site_id="WS1", tenant="webber"), _ln("LB", customer_id=9, tenant="webber"),
             _ln("LC", tenant="webber")]
    t = scope_true911_by_customer("Webber", customers, sites, devices, lines)
    assert sorted(s["site_id"] for s in t["sites"]) == ["WS1", "WS2"]
    assert sorted(d["device_id"] for d in t["devices"]) == ["DA", "DB", "DC"]
    assert sorted(l["line_id"] for l in t["lines"]) == ["LA", "LB", "LC"]


def test_unlinked_rows_not_adopted_in_shared_tenant():
    # Contrast: same unlinked site, but the tenant has 2 customers -> NOT adopted.
    customers = [_cust(9, "Webber Infra"), _cust(10, "Other Co")]   # both 'default'
    sites = [_site("WS1", None)]
    devices = [_dvc("DA", "WS1")]
    t = scope_true911_by_customer("Webber", customers, sites, devices, [])
    assert t["sites"] == [] and t["devices"] == []


def test_lines_scoped_by_customer_or_site():
    customers = [_cust(1, "Webber Infra"), _cust(2, "Acme")]
    sites = [_site("S1", 1), _site("S2", 2)]
    lines = [_ln("L1", customer_id=1), _ln("L2", site_id="S1"),
             _ln("L3", customer_id=2), _ln("L4", site_id="S2")]
    t = scope_true911_by_customer("Webber", customers, sites, [], lines)
    assert sorted(l["line_id"] for l in t["lines"]) == ["L1", "L2"]


def test_scope_no_match_returns_empty():
    t = scope_true911_by_customer("Nobody", [_cust(1, "Webber")], [], [], [])
    assert t["sites"] == [] and t["devices"] == [] and t["matched_customer_count"] == 0


def test_scope_then_reconcile_reports_real_device_count():
    # End-to-end: the Webber bug. Whole 'default' tenant = 21 devices; Webber owns 1.
    customers = [_cust(5, "Webber Infra")] + [_cust(i, f"C{i}") for i in range(10, 30)]
    sites = [_site("W1", 5)] + [_site(f"O{i}", i) for i in range(10, 30)]
    devices = [_dvc("WD1", "W1", msisdn="8563081391")] + [_dvc(f"OD{i}", f"O{i}") for i in range(10, 30)]
    t = scope_true911_by_customer("Webber", customers, sites, devices, [])
    rec = reconcile_customer("Webber", [zrec(activation="De-activated", msisdn="8563081391")], t)
    assert rec.true911_device_count == 1                         # was 21 (whole tenant)
    assert DEACT_ZOHO_ACTIVE_T911 in [f.classification for f in rec.findings]


# 8 — no destructive writes
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_zoho_true911_customer_reconciliation.py").read_text(encoding="utf-8")
    lower = src.lower()
    # DB-write primitives only (so Counter.update / sys.path.insert don't false-trip).
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "db.bulk", "add_all"):
        assert forbidden not in lower, f"audit must be read-only; found {forbidden!r}"
    assert "select(" in src
