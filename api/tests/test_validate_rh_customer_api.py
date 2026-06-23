"""P4 — RH customer-API render validation tests (pure check surface).

Exercises every check, the sentinel-leak and no-false-green guards, the
PASS/CONDITIONAL PASS/FAIL verdict, and the JSON + CSV report writers — over
RH-shaped synthetic views. No DB, no writes, no flag.
"""

from __future__ import annotations

import csv
import json

from app import validate_rh_customer_api as v


# ── RH-shaped fixture ────────────────────────────────────────────────
def _prot(status="Protected", reason="E911 not verified"):
    if status == "Protected":
        return {"status": "Protected", "as_of": "t",
                "evidence": {"last_checked": "t", "signals": ["device online"], "source": "monitoring"}}
    return {"status": status, "as_of": "t", "reason": reason}


def _rh_view(**kw):
    locs = [
        {"location": "RH Boston", "location_ref": "loc_a", "protection": _prot(), "emergency_address_state": "Verified"},
        {"location": "RH Yountville", "location_ref": "loc_b", "protection": _prot(), "emergency_address_state": "Verified"},
        {"location": "RH Chicago", "location_ref": "loc_c", "protection": _prot(), "emergency_address_state": "Verified"},
    ]
    svcs = [
        {"service": "Elevator emergency phone", "service_ref": "svc_1", "protection": _prot()},
        {"service": "Fire alarm line", "service_ref": "svc_2", "protection": _prot()},
        {"service": "Emergency call station", "service_ref": "svc_3", "protection": _prot()},
    ]
    e911 = [
        {"location": loc["location"], "active": True, "verification": {"state": "Verified", "is_critical": False}}
        for loc in locs
    ]
    prots = [x["protection"] for x in locs] + [x["protection"] for x in svcs]
    pf = {"total": 3, "protected": 3, "attention_needed": 0, "critical": 0,
          "pending_install": 0, "inactive": 0, "unknown": 0}
    dash = {"company": "Restoration Hardware", "portfolio": pf,
            "headline": "3 of 3 locations Protected", "attention_feed": [], "recent_manley_activity": []}
    view = {"dashboard": dash, "locations": locs, "services": svcs, "e911": e911,
            "all_protections": prots, "expected_sites": 3, "expected_services": 3,
            "max_unknown": 0, "forbidden_values": set()}
    view.update(kw)
    if "blob" not in kw:
        view["blob"] = json.dumps({k: view[k] for k in ("dashboard", "locations", "services", "e911")}, default=str)
    return view


# ── Clean RH view: all checks PASS ───────────────────────────────────
def test_clean_rh_view_all_pass():
    checks = v.run_checks(_rh_view())
    assert all(c.passed for c in checks)
    assert v.verdict(checks) == ("PASS", "GO")


# ── Per-check failures ───────────────────────────────────────────────
def test_dashboard_count_mismatch_fails():
    view = _rh_view()
    view["dashboard"]["portfolio"]["total"] = 99
    assert not v.check_dashboard(view).passed


def test_dashboard_activity_must_be_empty():
    view = _rh_view()
    view["dashboard"]["recent_manley_activity"] = [{"x": 1}]
    assert not v.check_dashboard(view).passed


def test_locations_count_mismatch_fails():
    assert not v.check_locations(_rh_view(expected_sites=5)).passed


def test_services_count_mismatch_fails():
    assert not v.check_services(_rh_view(expected_services=10)).passed


def test_e911_active_unverified_must_be_critical():
    view = _rh_view()
    view["e911"][0]["verification"] = {"state": "Not yet verified", "is_critical": False}
    assert not v.check_e911(view).passed


def test_e911_verified_must_not_be_critical():
    view = _rh_view()
    view["e911"][0]["verification"] = {"state": "Verified", "is_critical": True}
    assert not v.check_e911(view).passed


# ── HARD: no false green ─────────────────────────────────────────────
def test_no_false_green_is_hard_and_catches_missing_evidence():
    bad = {"status": "Protected", "as_of": "t", "evidence": None}
    c = v.check_no_false_green(_rh_view(all_protections=[bad]))
    assert c.hard and not c.passed


def test_no_false_green_missing_signals():
    bad = {"status": "Protected", "as_of": "t", "evidence": {"signals": []}}
    assert not v.check_no_false_green(_rh_view(all_protections=[bad])).passed


# ── HARD: unexplained red ────────────────────────────────────────────
def test_reasons_is_hard_and_catches_blank_reason():
    bad = {"status": "Critical", "as_of": "t", "reason": ""}
    c = v.check_reasons(_rh_view(all_protections=[bad]))
    assert c.hard and not c.passed


def test_reasons_pass_when_reason_present():
    ok = {"status": "Critical", "as_of": "t", "reason": "Emergency address not verified"}
    assert v.check_reasons(_rh_view(all_protections=[ok])).passed


# ── Unknown minimization (default max 0) ─────────────────────────────
def test_unknown_over_threshold_fails():
    unk = {"status": "Unknown", "as_of": "t", "reason": "setting up"}
    assert not v.check_unknown(_rh_view(all_protections=[unk], max_unknown=0)).passed


def test_unknown_within_threshold_passes():
    unk = {"status": "Unknown", "as_of": "t", "reason": "setting up"}
    assert v.check_unknown(_rh_view(all_protections=[unk], max_unknown=1)).passed


# ── HARD: sentinel leak ──────────────────────────────────────────────
def test_leak_value_from_real_row_is_hard_fail():
    iccid = "8901240204219434247"
    view = _rh_view(forbidden_values={iccid},
                    blob=json.dumps({"services": [{"equipment": iccid}]}))
    c = v.check_no_leak(view)
    assert c.hard and not c.passed


def test_leak_forbidden_key_fails():
    view = _rh_view(blob=json.dumps({"x": {"iccid": "hidden"}}))
    assert not v.check_no_leak(view).passed


def test_clean_blob_no_leak():
    assert v.check_no_leak(_rh_view()).passed


# ── Billing / support deferred ───────────────────────────────────────
def test_billing_keys_must_not_appear():
    view = _rh_view(blob=json.dumps({"d": {"monthly_cost": "$120"}}))
    assert not v.check_billing_deferred(view).passed
    assert v.check_billing_deferred(_rh_view()).passed


def test_support_internal_must_not_appear():
    view = _rh_view(blob=json.dumps({"s": {"internal_summary": "secret"}}))
    assert not v.check_support_deferred(view).passed
    assert v.check_support_deferred(_rh_view()).passed


# ── Verdict mapping ──────────────────────────────────────────────────
def test_verdict_conditional_pass_on_soft_only():
    # Force a SOFT failure (unknown) with all hard checks passing.
    unk = {"status": "Unknown", "as_of": "t", "reason": "x"}
    checks = v.run_checks(_rh_view(all_protections=_rh_view()["all_protections"] + [unk], max_unknown=0))
    status, rec = v.verdict(checks)
    assert status == "CONDITIONAL PASS" and rec.startswith("CONDITIONAL GO")


def test_verdict_fail_on_hard():
    bad = {"status": "Protected", "as_of": "t", "evidence": None}
    checks = v.run_checks(_rh_view(all_protections=[bad]))
    assert v.verdict(checks) == ("FAIL", "NO-GO")


# ── --only selection ─────────────────────────────────────────────────
def test_only_runs_single_check():
    checks = v.run_checks(_rh_view(), only="leaks")
    assert len(checks) == 1 and checks[0].name == "leaks"


# ── JSON artifact + CSV summary ──────────────────────────────────────
def test_reports_written(tmp_path):
    checks = v.run_checks(_rh_view())
    base = str(tmp_path / "rh_p4.json")
    jp, cp = v._write_reports(base, checks, _rh_view())
    assert jp.endswith(".json") and cp.endswith(".csv")

    data = json.loads(open(jp, encoding="utf-8").read())
    assert data["result"] == "PASS" and data["recommendation"] == "GO"
    assert len(data["checks"]) == len(checks)

    rows = list(csv.DictReader(open(cp, encoding="utf-8")))
    assert [f for f in rows[0].keys()] == ["name", "status", "hard", "summary"]
    assert len(rows) == len(checks) and all(r["status"] == "PASS" for r in rows)
