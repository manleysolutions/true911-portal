"""Tests for the portfolio reconciliation rollup (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.audit_customer_portfolio_reconciliation import (
    build_row,
    classify_customer,
    remediation_order,
    write_csv,
    write_json,
)


def _row(**over):
    base = dict(zoho_subscription_count=10, device_count=5, line_count=5, site_count=5,
                matched_ok=5, needs_mapping=10, missing_in_true911=0, missing_in_zoho=0,
                duplicate_candidate=0, status_mismatch=0, historical_subscription=0,
                replacement_subscription=0, missing_iccid=0, missing_site=0, missing_device=0)
    base.update(over)
    return base


# ── classify_customer ────────────────────────────────────────────────────
def test_clean_when_matched_no_issues():
    assert classify_customer(_row(needs_mapping=0)) == "clean"


def test_needs_mapping_when_only_unconfirmed():
    # needs_mapping alone (baseline) -> mapping confirmation, not a structural class
    assert classify_customer(_row(needs_mapping=10)) == "needs_mapping_confirmation"


def test_needs_retirement_when_historical_dominant():
    assert classify_customer(_row(historical_subscription=30, duplicate_candidate=1)) == "needs_retirement_review"


def test_needs_site_alignment_when_duplicates_dominant():
    assert classify_customer(_row(duplicate_candidate=54, historical_subscription=2)) == "needs_site_alignment"


def test_needs_iccid_backfill():
    assert classify_customer(_row(missing_iccid=20, duplicate_candidate=1)) == "needs_iccid_backfill"


def test_needs_import_backfill():
    assert classify_customer(_row(missing_device=15, missing_in_true911=5)) == "needs_import_backfill"


def test_needs_manual_review_when_no_data():
    assert classify_customer(_row(zoho_subscription_count=0, device_count=0,
                                  needs_mapping=0)) == "needs_manual_review"


def test_priority_tiebreak_low_risk_first():
    # equal counts -> retirement (priority 0) beats site (priority 1)
    r = _row(historical_subscription=5, duplicate_candidate=5)
    assert classify_customer(r) == "needs_retirement_review"


# ── build_row wires reconciliation + classifier summaries ────────────────
def test_build_row_assembles_counts_and_classifies():
    recon = {"matched_ok": 51, "needs_mapping": 91, "duplicate_candidate": 0,
             "missing_in_true911": 0, "missing_in_zoho": 0, "status_mismatch": 0}
    cls = {"historical_subscription": 30, "missing_iccid": 7, "missing_site": 0,
           "missing_device": 0, "replacement_subscription": 0}
    row = build_row("Restoration Hardware", "default", recon, cls,
                    zoho_count=91, device_count=51, line_count=40, site_count=50)
    assert row["zoho_subscription_count"] == 91 and row["device_count"] == 51
    assert row["historical_subscription"] == 30 and row["missing_iccid"] == 7
    assert row["classification"] == "needs_retirement_review"   # 30 historical dominates
    assert row["recommended_action"].startswith("Run gated retirement")


# ── remediation_order ────────────────────────────────────────────────────
def test_remediation_order_low_risk_first():
    rows = [
        build_row("Clean Co", "t", {"matched_ok": 3, "needs_mapping": 0}, {}, zoho_count=3, device_count=3, line_count=3, site_count=1),
        build_row("Webber", "default", {"matched_ok": 0, "needs_mapping": 7}, {"historical_subscription": 7}, zoho_count=7, device_count=4, line_count=4, site_count=2),
        build_row("R&R", "default", {"matched_ok": 0, "needs_mapping": 5, "duplicate_candidate": 54}, {}, zoho_count=119, device_count=55, line_count=55, site_count=55),
    ]
    ordered = [r["customer"] for r in remediation_order(rows)]
    assert ordered[0] == "Webber"      # retirement (rank 0)
    assert ordered[1] == "R&R"         # site alignment (rank 1)
    assert ordered[-1] == "Clean Co"   # clean last


# ── exports ──────────────────────────────────────────────────────────────
def test_exports(tmp_path):
    rows = [build_row("RH", "default", {"matched_ok": 51, "needs_mapping": 91},
                      {"historical_subscription": 30, "missing_iccid": 7},
                      zoho_count=91, device_count=51, line_count=40, site_count=50)]
    j = tmp_path / "p.json"
    write_json(rows, str(j))
    import json
    doc = json.loads(j.read_text(encoding="utf-8"))
    assert doc["read_only"] is True and "by_class" in doc
    c = tmp_path / "p.csv"
    assert write_csv(rows, str(c)) == 1
    assert "recommended_action" in c.read_text(encoding="utf-8").splitlines()[0]


# ── read-only ────────────────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_customer_portfolio_reconciliation.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "add_all", "insert into", "delete from"):
        assert forbidden not in lower, f"audit must be read-only; found {forbidden!r}"
