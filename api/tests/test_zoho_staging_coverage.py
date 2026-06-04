"""Tests for the Zoho staging coverage audit (pure, no DB/Zoho)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from app.audit_zoho_staging_coverage import assess_customer, classify_coverage


def _zr(account="Restoration Hardware", acc_id="ACC1"):
    return {"account_name": account, "external_account_id": acc_id}


def _sr(account="Webber Infrastructure", first=None, upd=None):
    return {"account_name": account, "first_seen_at": first, "updated_at": upd}


# ── classification ───────────────────────────────────────────────────────
def test_classify_missing_backfill():
    assert classify_coverage(34, 0) == "missing_backfill_required"


def test_classify_partial():
    assert classify_coverage(7, 3) == "partial_backfill_required"


def test_classify_complete():
    assert classify_coverage(7, 7) == "complete"
    assert classify_coverage(7, 9) == "complete"


def test_classify_none_either_side():
    assert classify_coverage(0, 0) == "none_either_side"


def test_classify_staged_no_zoho():
    assert classify_coverage(0, 5) == "staged_no_zoho"


def test_classify_zoho_unavailable():
    assert classify_coverage(None, 4) == "zoho_unavailable"


# ── assess_customer (the Restoration Hardware / Webber scenarios) ────────
def test_rh_missing_from_staging():
    # RH: 34 in Zoho, 0 staged -> missing, backfill required.
    row = assess_customer("Restoration Hardware",
                          zoho_records=[_zr() for _ in range(34)],
                          staged_records=[], map_count=0)
    assert row["zoho_count"] == 34 and row["staged_count"] == 0
    assert row["coverage"] == "missing_backfill_required"
    assert row["backfill_required"] is True
    assert "never backfilled" in row["reason"]
    assert "backfill_zoho_subscription_staging --customer 'Restoration Hardware'" in row["recommended_fix"]
    assert row["account_ids"] == ["ACC1"]


def test_webber_complete():
    now = _dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc)
    row = assess_customer("Webber Infra",
                          zoho_records=[_zr("Webber Infrastructure") for _ in range(7)],
                          staged_records=[_sr("Webber Infrastructure", first=now, upd=now)
                                          for _ in range(7)], map_count=7)
    assert row["coverage"] == "complete"
    assert row["backfill_required"] is False
    assert row["staging_first_seen"] == now and row["staging_last_updated"] == now


def test_zoho_unavailable_still_reports_staging():
    row = assess_customer("Integrity", zoho_records=None,
                          staged_records=[_sr("Integrity LLC")], map_count=1)
    assert row["zoho_count"] is None
    assert row["coverage"] == "zoho_unavailable"
    assert row["backfill_required"] is False
    assert row["staged_count"] == 1


def test_staged_no_zoho_flags_name_mismatch():
    row = assess_customer("R&R Realty", zoho_records=[],
                          staged_records=[_sr("R and R Realty")], map_count=0)
    assert row["coverage"] == "staged_no_zoho"
    assert "mismatch" in row["reason"]


# ── read-only / no writes ────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_zoho_staging_coverage.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "add_all", "insert into", "delete from"):
        assert forbidden not in lower, f"audit must be read-only; found {forbidden!r}"
    assert "select(" in src
