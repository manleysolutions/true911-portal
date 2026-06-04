"""Tests for the R&R device→site assignment diagnostic (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.audit_rr_site_assignment import (
    build_report,
    classify_device,
    write_csv,
    write_json,
)


def _d(did, msisdn, site):
    return {"device_id": did, "msisdn": msisdn, "site_id": site, "status": "active"}


def _l(lid, did, site):
    return {"line_id": lid, "did": did, "site_id": site, "status": "active"}


def _sites(*pairs):
    return [{"site_id": sid, "site_name": name, "customer_id": 7} for sid, name in pairs]


# ── classify_device ──────────────────────────────────────────────────────
def test_likely_correct_same_site():
    cls, prop = classify_device(_d("D1", "3055551234", "S1"),
                                _l("L1", "3055551234", "S1"), 1)
    assert cls == "likely_correct" and prop is None


def test_likely_wrong_site_different_site():
    cls, prop = classify_device(_d("D1", "3055551234", "SITE-BULK"),
                                _l("L1", "3055551234", "SITE-REAL"), 1)
    assert cls == "likely_wrong_site" and prop == "SITE-REAL"


def test_unassigned_when_device_has_no_site():
    cls, prop = classify_device(_d("D1", "3055551234", None),
                                _l("L1", "3055551234", "S1"), 1)
    assert cls == "unassigned" and prop is None


def test_ambiguous_when_no_line():
    assert classify_device(_d("D1", "3055551234", "S1"), None, 0)[0] == "ambiguous"


def test_ambiguous_when_multiple_lines():
    assert classify_device(_d("D1", "3055551234", "S1"),
                           _l("L1", "3055551234", "S1"), 2)[0] == "ambiguous"


# ── aggregates: the R&R bulk-import pattern ──────────────────────────────
def test_bulk_import_pattern_detected():
    # 3 devices ALL on the placeholder site; their lines on 3 distinct real sites.
    BULK = "SITE-1776963371486"
    devices = [_d(f"D{i}", f"30555000{i}", BULK) for i in range(3)]
    lines = [_l(f"L{i}", f"30555000{i}", f"SITE-REAL{i}") for i in range(3)]
    sites = _sites((BULK, "Imported Placeholder"),
                   *[(f"SITE-REAL{i}", f"Real Site {i}") for i in range(3)])
    rep = build_report(devices, lines, sites, customer_id=7, customer_name="R&R Realty Group")
    assert rep["summary"]["likely_wrong_site"] == 3
    assert rep["dominant_site"]["site_id"] == BULK
    assert rep["dominant_site"]["pct"] == 100.0
    assert rep["dominant_site"]["single_site_dominates"] is True
    assert rep["device_distinct_sites"] == 1 and rep["line_distinct_sites"] == 3
    assert rep["lines_more_realistic"] is True
    # every wrong-site row proposes the matching line's site
    wrong = [r for r in rep["rows"] if r["classification"] == "likely_wrong_site"]
    assert all(r["proposed_site_id"] == r["line_site_id"] for r in wrong)


def test_correct_assignments_not_flagged():
    devices = [_d("D1", "3055550001", "S1"), _d("D2", "3055550002", "S2")]
    lines = [_l("L1", "3055550001", "S1"), _l("L2", "3055550002", "S2")]
    rep = build_report(devices, lines, _sites(("S1", "A"), ("S2", "B")),
                       customer_id=7, customer_name="R&R")
    assert rep["summary"]["likely_correct"] == 2
    assert rep["summary"]["likely_wrong_site"] == 0
    assert rep["lines_more_realistic"] is False


def test_devices_sharing_site_and_counts():
    devices = [_d("D1", "30555001", "S1"), _d("D2", "30555002", "S1"), _d("D3", "30555003", "S2")]
    rep = build_report(devices, [], _sites(("S1", "A"), ("S2", "B")),
                       customer_id=7, customer_name="R&R")
    assert rep["device_count_by_site"]["S1"] == 2
    assert rep["devices_sharing_site"] == {"S1": 2}
    assert rep["summary"]["ambiguous"] == 3   # no lines -> all ambiguous


# ── exports ──────────────────────────────────────────────────────────────
def test_exports(tmp_path):
    rep = build_report([_d("D1", "30555001", "SITE-BULK")],
                       [_l("L1", "30555001", "SITE-REAL")],
                       _sites(("SITE-BULK", "Bulk"), ("SITE-REAL", "Real")),
                       customer_id=7, customer_name="R&R")
    j = tmp_path / "r.json"
    write_json(rep, str(j))
    import json
    assert json.loads(j.read_text(encoding="utf-8"))["read_only"] is True
    c = tmp_path / "r.csv"
    assert write_csv(rep["rows"], str(c)) == 1
    assert "device_site_id" in c.read_text(encoding="utf-8").splitlines()[0]


# ── read-only ────────────────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_rr_site_assignment.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "add_all", "insert into", "delete from"):
        assert forbidden not in lower, f"diagnostic must be read-only; found {forbidden!r}"
