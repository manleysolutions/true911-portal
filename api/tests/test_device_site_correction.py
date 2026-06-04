"""Tests for the gated device→site correction planner (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.plan_device_site_correction import (
    build_correction_plan,
    feature_enabled,
    should_apply,
    write_csv,
    write_json,
)


def _row(device_id, *, classification="likely_wrong_site", proposed="SITE-REAL",
         current="SITE-BULK", msisdn="3055551234"):
    return {"device_id": device_id, "msisdn": msisdn,
            "device_site_id": current, "device_site_name": "Bulk",
            "line_site_id": proposed, "line_site_name": "Real",
            "classification": classification, "proposed_site_id": proposed}


VALID = {"SITE-REAL", "SITE-BULK", "SITE-OTHER"}


# ── plan building / refusals (req. 7) ────────────────────────────────────
def test_likely_wrong_site_becomes_a_correction():
    plan = build_correction_plan([_row("D1")], VALID)
    assert plan["summary"]["to_correct"] == 1
    c = plan["changes"][0]
    assert c["current_site_id"] == "SITE-BULK" and c["proposed_site_id"] == "SITE-REAL"
    assert c["device_id"] == "D1" and c["msisdn"] == "3055551234"


def test_refuse_ambiguous():
    plan = build_correction_plan([_row("D1", classification="ambiguous")], VALID)
    assert plan["summary"]["to_correct"] == 0
    assert "ambiguous" in plan["skipped"][0]["skip_reason"]


def test_refuse_unassigned_and_already_correct():
    plan = build_correction_plan(
        [_row("D1", classification="unassigned"),
         _row("D2", classification="likely_correct")], VALID)
    assert plan["summary"]["to_correct"] == 0 and plan["summary"]["skipped"] == 2


def test_refuse_no_proposed_site():
    plan = build_correction_plan([_row("D1", proposed=None)], VALID)
    assert plan["summary"]["to_correct"] == 0
    assert plan["skipped"][0]["skip_reason"] == "no proposed site"


def test_refuse_customer_mismatch_proposed_site_not_owned():
    # proposed site is NOT among this customer's sites -> refuse.
    plan = build_correction_plan([_row("D1", proposed="SITE-FOREIGN")], VALID)
    assert plan["summary"]["to_correct"] == 0
    assert "customer mismatch" in plan["skipped"][0]["skip_reason"]


def test_mixed_fleet_summary():
    rows = [_row(f"W{i}") for i in range(54)]          # 54 wrong-site -> correct
    rows.append(_row("C1", classification="likely_correct"))
    plan = build_correction_plan(rows, VALID)
    assert plan["summary"]["to_correct"] == 54
    assert plan["summary"]["skipped"] == 1


# ── apply gating (flag + --apply) ────────────────────────────────────────
def test_apply_gated_by_flag(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_DEVICE_SITE_CORRECTION", "false")
    assert feature_enabled() is False
    assert should_apply(True) is False               # requested but flag off
    monkeypatch.setattr("app.config.settings.FEATURE_DEVICE_SITE_CORRECTION", "true")
    assert should_apply(True) is True
    assert should_apply(False) is False              # not requested -> never writes


# ── exports ──────────────────────────────────────────────────────────────
def test_exports(tmp_path):
    plan = build_correction_plan([_row("D1"), _row("D2", current="SITE-OTHER")], VALID)
    j = tmp_path / "p.json"
    write_json(plan, applied=None, path=str(j))
    import json
    doc = json.loads(j.read_text(encoding="utf-8"))
    assert doc["applied"] is False and len(doc["changes"]) == 2
    c = tmp_path / "p.csv"
    assert write_csv(plan, str(c)) == 2
    assert "proposed_site_id" in c.read_text(encoding="utf-8").splitlines()[0]


# ── safety: site_id-only write, no deletes, no line/customer changes ─────
def test_writes_only_site_id_no_deletes_no_line_customer():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "plan_device_site_correction.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in (".delete(", "db.delete", "delete from", "drop ", "truncate"):
        assert forbidden not in lower, f"must never delete; found {forbidden!r}"
    # Only devices.site_id is assigned; no Line/Customer model is imported or mutated.
    assert "d.site_id = ch[" in src
    for not_imported in ("from app.models.line", "from app.models.customer"):
        assert not_imported not in src, f"must not touch {not_imported}"
    # Apply is gated and audited.
    assert "should_apply(apply_requested)" in src
    assert "await db.commit()" in src and "log_audit" in src
