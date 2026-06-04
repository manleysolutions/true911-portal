"""Tests for the R&R device↔line pairing diagnostic (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.audit_rr_device_line_pairing import (
    classify_pair,
    pair_and_classify,
    summarize,
    write_csv,
    write_json,
)

# site -> customer mapping for ownership checks
SITES = {"S1": 7, "S2": 7, "S3": 9}   # S1/S2 owned by customer 7, S3 by 9


def _d(did, msisdn, *, site="S1"):
    return {"device_id": did, "msisdn": msisdn, "site_id": site, "status": "active"}


def _l(lid, did, *, device_id=None, site="S1", customer_id=None):
    return {"line_id": lid, "did": did, "device_id": device_id, "site_id": site,
            "customer_id": customer_id, "status": "active"}


def _one(devices, lines, site_customer=SITES):
    return classify_pair("3055551234", devices, lines, site_customer)


# 1 — exact linked pair
def test_exact_linked_pair():
    r = _one([_d("D1", "3055551234")], [_l("L1", "3055551234", device_id="D1")])
    assert r["classification"] == "collapsible_exact"
    assert r["would_collapse_under"] == "exact"
    assert r["device_id_linked"] is True and r["site_match"] is True


# 2 — same MSISDN/site but line.device_id missing  (the R&R case)
def test_same_msisdn_site_but_line_device_id_missing():
    r = _one([_d("D1", "3055551234", site="S1")],
             [_l("L1", "+1 (305) 555-1234", device_id=None, site="S1")])
    assert r["classification"] == "collapsible_by_msisdn_site"
    assert r["would_collapse_under"] == "relaxed"
    assert r["line_device_id"] is None and r["msisdn_equal"] is True


# 3 — device_id mismatch
def test_device_id_mismatch():
    r = _one([_d("D1", "3055551234")], [_l("L1", "3055551234", device_id="D2")])
    assert r["classification"] == "line_device_id_mismatch"
    assert r["would_collapse_under"] == "no"


# 4 — site mismatch
def test_site_mismatch():
    r = _one([_d("D1", "3055551234", site="S1")],
             [_l("L1", "3055551234", device_id=None, site="S2")])
    # S1 and S2 are the SAME customer (7) but different sites -> site_mismatch
    assert r["classification"] == "site_mismatch"


# 5 — true duplicate (two devices)
def test_true_duplicate_two_devices():
    r = _one([_d("D1", "3055551234"), _d("D2", "3055551234")],
             [_l("L1", "3055551234")])
    assert r["classification"] == "true_duplicate"


# 6 — missing line
def test_missing_line():
    r = _one([_d("D1", "3055551234")], [])
    assert r["classification"] == "missing_line"


# 7 — missing device
def test_missing_device():
    r = _one([], [_l("L1", "3055551234")])
    assert r["classification"] == "missing_device"


# extra — customer mismatch (device on a customer-7 site, line carries customer 9)
def test_customer_mismatch():
    r = _one([_d("D1", "3055551234", site="S1")],
             [_l("L1", "3055551234", device_id=None, site="S1", customer_id=9)])
    assert r["classification"] == "customer_mismatch"


def test_line_device_id_missing_unconfirmable():
    # device_id NULL, line on a DIFFERENT customer's site (S3 -> cust 9) AND device on S1 (cust 7)
    r = classify_pair("3055551234",
                      [_d("D1", "3055551234", site="S1")],
                      [_l("L1", "3055551234", device_id=None, site="S3")], SITES)
    # site differs AND customers differ -> caught as site_mismatch (first hard gate)
    assert r["classification"] in ("site_mismatch", "customer_mismatch")


# ── aggregate over a fleet ───────────────────────────────────────────────
def test_pair_and_classify_and_summary():
    devices = [_d("D1", "3050000001"), _d("D2", "3050000002"), _d("D3", "3050000003")]
    lines = [
        _l("L1", "3050000001", device_id="D1"),          # collapsible_exact
        _l("L2", "3050000002", device_id=None),          # collapsible_by_msisdn_site
        # D3 has no line -> missing_line; an orphan line:
        _l("L9", "3059999999", device_id=None),          # missing_device
    ]
    rows = pair_and_classify(devices, lines, [{"site_id": "S1", "customer_id": 7}])
    s = summarize(rows)
    assert s["collapsible_exact"] == 1
    assert s["collapsible_by_msisdn_site"] == 1
    assert s["missing_line"] == 1
    assert s["missing_device"] == 1
    assert s["total_msisdns"] == 4


def test_exports(tmp_path):
    rows = pair_and_classify([_d("D1", "3050000001")],
                             [_l("L1", "3050000001", device_id=None)],
                             [{"site_id": "S1", "customer_id": 7}])
    j = tmp_path / "r.json"
    write_json(rows, summarize(rows), str(j))
    import json
    assert json.loads(j.read_text(encoding="utf-8"))["read_only"] is True
    c = tmp_path / "r.csv"
    assert write_csv(rows, str(c)) == 1
    assert "classification" in c.read_text(encoding="utf-8").splitlines()[0]


# ── read-only ────────────────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_rr_device_line_pairing.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "add_all", "insert into", "delete from"):
        assert forbidden not in lower, f"diagnostic must be read-only; found {forbidden!r}"
    assert "select(" not in src or "_load_true911" in src   # only the shared loader queries
