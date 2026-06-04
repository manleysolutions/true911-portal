"""Tests for the gated customer retirement planner (pure, no DB)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from app.plan_customer_retirement import (
    RETIRE_CUSTOMER, RETIRE_DEVICE, RETIRE_LINE, RETIRE_MAP, RETIRE_SITE,
    build_retirement_plan,
    feature_enabled,
    should_apply,
    write_csv,
    write_json,
)

UTC = _dt.timezone.utc
NOW = _dt.datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def _cust(status="active", cid=5):
    return {"id": cid, "name": "Webber Infra", "status": status, "tenant_id": "default"}


def _z(activation="De-activated"):
    return {"subscription_mgmt_id": "SM-1", "account_name": "Webber Infrastructure",
            "device_activation_status": activation, "lifecycle_state": None}


def _webber_plan(*, customer=None, devices=None, lines=None, zoho=None, now=NOW):
    return build_retirement_plan(
        customer=customer or _cust(),
        sites=[{"site_id": "S1", "status": "Not Connected"}],
        devices=devices if devices is not None else [{"device_id": "D1", "status": "provisioning"}],
        lines=lines if lines is not None else [{"line_id": "L1", "status": "provisioning"}],
        record_maps=[{"id": 9, "map_status": "unmapped"}],
        zoho_records=zoho if zoho is not None else [_z(), _z()],
        now=now)


# ── proposed changes ─────────────────────────────────────────────────────
def test_plan_proposes_expected_status_changes():
    plan = _webber_plan()
    by = {(c["entity_type"], c["entity_id"]): c for c in plan["changes"]}
    assert by[("customer", 5)]["proposed"] == RETIRE_CUSTOMER
    assert by[("site", "S1")]["proposed"] == RETIRE_SITE
    assert by[("device", "D1")]["proposed"] == RETIRE_DEVICE
    assert by[("line", "L1")]["proposed"] == RETIRE_LINE
    assert by[("external_record_map", 9)]["proposed"] == RETIRE_MAP
    # current values preserved for the audit trail
    assert by[("customer", 5)]["current"] == "active"


def test_no_change_proposed_when_already_retired():
    plan = build_retirement_plan(
        customer=_cust(status="inactive"), sites=[{"site_id": "S1", "status": "decommissioned"}],
        devices=[{"device_id": "D1", "status": "decommissioned"}],
        lines=[{"line_id": "L1", "status": "disconnected"}],
        record_maps=[{"id": 9, "map_status": "retired"}], zoho_records=[_z()], now=NOW)
    assert plan["changes"] == []


# ── gate: Zoho must be deactivated ───────────────────────────────────────
def test_refuses_when_zoho_active():
    plan = _webber_plan(zoho=[_z("De-activated"), _z("Active")])
    assert plan["gates"]["zoho_deactivated"] is False
    assert plan["safe_to_apply"] is False
    assert any("Zoho lifecycle not all deactivated" in b for b in plan["blockers"])


def test_refuses_when_no_zoho_records():
    plan = _webber_plan(zoho=[])
    assert plan["safe_to_apply"] is False     # can't confirm deactivation


# ── gate: no recent liveness ─────────────────────────────────────────────
def test_refuses_when_asset_has_recent_liveness():
    live = [{"device_id": "D1", "status": "provisioning",
             "last_heartbeat": NOW - _dt.timedelta(days=2)}]
    plan = _webber_plan(devices=live)
    assert plan["gates"]["no_active_liveness"] is False
    assert plan["safe_to_apply"] is False
    assert any("recent liveness" in b for b in plan["blockers"])


def test_safe_when_all_stale_and_deactivated():
    plan = _webber_plan(
        devices=[{"device_id": "D1", "status": "provisioning",
                  "last_heartbeat": NOW - _dt.timedelta(days=200)}])
    assert plan["gates"]["zoho_deactivated"] is True
    assert plan["gates"]["no_active_liveness"] is True
    assert plan["safe_to_apply"] is True


# ── apply gating (flag + gates) ──────────────────────────────────────────
def test_apply_gated_by_feature_flag(monkeypatch):
    safe = _webber_plan(devices=[{"device_id": "D1", "status": "provisioning"}])
    assert safe["safe_to_apply"] is True
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_RETIREMENT", "false")
    assert feature_enabled() is False
    assert should_apply(True, safe) is False          # flag off -> no apply
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_RETIREMENT", "true")
    assert should_apply(True, safe) is True
    assert should_apply(False, safe) is False         # not requested -> no apply


def test_apply_refused_when_unsafe_even_with_flag(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_RETIREMENT", "true")
    unsafe = _webber_plan(zoho=[_z("Active")])         # zoho active -> unsafe
    assert should_apply(True, unsafe) is False


# ── customer-scoped only ─────────────────────────────────────────────────
def test_changes_reference_only_given_customer_entities():
    plan = _webber_plan()
    ids = {(c["entity_type"], c["entity_id"]) for c in plan["changes"]}
    # exactly the customer/site/device/line/map we passed — nothing else.
    assert ids == {("customer", 5), ("site", "S1"), ("device", "D1"),
                   ("line", "L1"), ("external_record_map", 9)}


def test_unresolved_customer_blocks_apply():
    plan = build_retirement_plan(customer={}, sites=[], devices=[], lines=[],
                                 record_maps=[], zoho_records=[_z()], now=NOW)
    assert plan["safe_to_apply"] is False
    assert any("customer not resolved" in b for b in plan["blockers"])


# ── export ───────────────────────────────────────────────────────────────
def test_exports(tmp_path):
    plan = _webber_plan()
    j = tmp_path / "p.json"
    write_json(plan, applied=False, path=str(j))
    import json
    doc = json.loads(j.read_text(encoding="utf-8"))
    assert doc["applied"] is False and len(doc["changes"]) == 5
    c = tmp_path / "p.csv"
    n = write_csv(plan, str(c))
    assert n == 5 and "entity_type" in c.read_text(encoding="utf-8").splitlines()[0]


# ── no deletes / dry-run-first (source guarantees) ───────────────────────
def test_never_deletes_and_apply_is_gated():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "plan_customer_retirement.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in (".delete(", "db.delete", "delete from", "drop ", "truncate"):
        assert forbidden not in lower, f"retirement must never delete; found {forbidden!r}"
    # The only write path (commit) is reached via _apply_changes, which is only
    # called under should_apply (flag + gates). Apply is opt-in.
    assert "should_apply(apply_requested, plan)" in src
    assert "await db.commit()" in src and "_apply_changes" in src
