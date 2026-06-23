"""Tests for the RH NAPCO RadioNumber match + dry-run ICCID backfill plan (pure, no DB)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.device_health.classifier import classify
from app.backfill_rh_device_identity import ALLOWED_FIELDS
from app.audit_rh_napco_radio_match import (
    build_records,
    build_plan_document,
    importer_mapping,
    summarize,
    write_plan,
)

GOOD = "89000000000000000001"   # valid 20-digit ICCID
GOOD2 = "89000000000000000002"
RH = "Restoration Hardware #999 Test Store"


def _dev(device_id, *, serial_number=None, iccid=None, model="SLELTE - Fire",
         manufacturer="NAPCO", carrier=None, site_id="rh-1"):
    return {"device_id": device_id, "site_id": site_id, "site_name": "RH Beverly",
            "model": model, "device_type": None, "hardware_model_id": None,
            "manufacturer": manufacturer, "carrier": carrier,
            "serial_number": serial_number, "iccid": iccid}


def _exp(radio, iccid, *, subscriber=RH, sim="Active",
         last="2026-06-03T07:19:47", plan="SLF-SVC-10-LSVI", gentech="4G:LTE"):
    return {"radio_number": radio, "iccid": iccid, "sim_status": sim,
            "last_signal": last, "subscriber_name": subscriber,
            "plan": plan, "gen_tech": gentech}


def _one(devices, export):
    """Build records and return the single record for the first device."""
    recs = build_records(devices, export, classify)
    return recs[0], recs


# 1 — device_id matches RadioNumber
def test_device_id_matches_radionumber():
    rec, _ = _one([_dev("10000004")], [_exp("10000004", GOOD)])
    assert rec["match_status"] == "exact_device_id_match"
    assert rec["backfill_decision"] == "backfill_ready"
    assert rec["matched_radio_number"] == "10000004"


# 2 — serial_number matches RadioNumber
def test_serial_matches_radionumber():
    rec, _ = _one([_dev("dev-x", serial_number="10000005")], [_exp("10000005", GOOD)])
    assert rec["match_status"] == "exact_serial_match"
    assert rec["backfill_decision"] == "backfill_ready"


# 3 — ICCID proposed when Device.iccid empty
def test_iccid_proposed_when_empty():
    rec, _ = _one([_dev("13864")], [_exp("13864", GOOD)])
    assert rec["proposed_update"]["iccid"] == GOOD
    assert rec["proposed_update"]["device_id"] == "13864"
    # serial backfilled with the RadioNumber (was empty).
    assert rec["proposed_update"]["serial_number"] == "13864"


# 4 — existing different ICCID refuses proposal
def test_existing_different_iccid_review_required():
    rec, _ = _one([_dev("10000004", iccid=GOOD2)], [_exp("10000004", GOOD)])
    assert rec["match_status"] == "data_conflict"
    assert rec["backfill_decision"] == "review_required"
    assert rec["proposed_update"] is None


# 5 — duplicate RadioNumber in export refuses proposal
def test_duplicate_radionumber_refused():
    rec, _ = _one([_dev("10000004")], [_exp("10000004", GOOD), _exp("10000004", GOOD2)])
    assert rec["match_status"] == "duplicate_radio_number"
    assert rec["backfill_decision"] == "refused"


# 6 — multiple RH devices match same RadioNumber refuses proposal
def test_ambiguous_multiple_rh_devices_refused():
    recs = build_records(
        [_dev("10000004"), _dev("other", serial_number="10000004")],
        [_exp("10000004", GOOD)], classify)
    assert all(r["match_status"] == "ambiguous_match" for r in recs)
    assert all(r["backfill_decision"] == "refused" for r in recs)


# 7 — SubscriberName unrelated to RH becomes review_required
def test_unrelated_subscriber_review_required():
    rec, _ = _one([_dev("10000004")],
                  [_exp("10000004", GOOD, subscriber="Acme Plumbing LLC")])
    assert rec["backfill_decision"] == "review_required"
    assert "not clearly Restoration Hardware" in rec["reason"]


# 8 — non-NAPCO device skipped
def test_non_napco_device_skipped():
    rec, _ = _one([_dev("10000004", model="LM150", manufacturer="FlyingVoice")],
                  [_exp("10000004", GOOD)])
    assert rec["match_status"] == "non_napco_device"
    assert rec["backfill_decision"] == "skipped_non_napco"


# 9 — export JSON plan importer rows contain only whitelisted fields
def test_export_plan_only_whitelisted_fields():
    recs = build_records([_dev("10000004"), _dev("10000005")],
                         [_exp("10000004", GOOD), _exp("10000005", GOOD2)], classify)
    allowed = set(ALLOWED_FIELDS) | {"device_id"}
    for row in importer_mapping(recs):
        assert set(row).issubset(allowed), f"non-whitelisted field in {row}"
        assert row["device_id"] and row["iccid"]


# 10 — command is read-only
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_rh_napco_radio_match.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge"):
        assert forbidden not in lower, f"audit must be read-only; found {forbidden!r}"
    assert "select(" in src


# 11 — malformed ICCID refuses proposal
def test_malformed_iccid_refused():
    rec, _ = _one([_dev("10000004")], [_exp("10000004", "12345")])
    assert rec["backfill_decision"] == "refused"
    assert "malformed" in rec["reason"]


# 12 — summary math correct
def test_summary_math():
    devices = [
        _dev("10000004"),                       # backfill_ready
        _dev("10000005"),                       # backfill_ready
        _dev("13864", iccid=GOOD2),            # review_required (diff iccid) — uses GOOD on export
        _dev("10000002"),                      # refused (malformed export iccid)
        _dev("nomatch-1"),                     # unmatched
        _dev("vola-1", model="LM150", manufacturer="FlyingVoice"),  # non_napco
    ]
    export = [
        _exp("10000004", GOOD), _exp("10000005", GOOD2),
        _exp("13864", GOOD), _exp("10000002", "bad"),
    ]
    recs = build_records(devices, export, classify)
    s = summarize(recs, export)
    assert s["rh_devices_total"] == 6
    assert s["napco_candidates"] == 5          # all but the LM150
    assert s["napco_export_rows"] == 4
    assert s["matched_by_device_id"] == 3      # 10000004, 10000005, 13864 (conflict still matched)
    assert s["backfill_ready"] == 2
    assert s["review_required"] == 1
    assert s["refused"] == 1
    assert s["unmatched_napco_candidates"] == 1
    assert s["estimated_backfill_ready_over_candidates"] == "2/5"


# ── plan document + file export ──────────────────────────────────────────
def test_plan_document_and_write(tmp_path):
    recs = build_records([_dev("10000004"), _dev("10000005")],
                         [_exp("10000004", GOOD), _exp("10000005", GOOD2)], classify)
    doc = build_plan_document(recs, summarize(recs, []), "restoration-hardware")
    assert doc["apply"] is False and doc["read_only"] is True
    assert len(doc["importer_mapping"]) == 2
    # review_plan carries the rich NAPCO metadata (separate from importer rows).
    rp = doc["review_plan"][0]
    assert rp["napco_radio_number"] in ("10000004", "10000005")
    assert rp["suggested_vendor"] == "napco"
    out = tmp_path / "plan.json"
    n = write_plan(doc, str(out))
    assert n == 2
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["importer_mapping"][0]["iccid"] in (GOOD, GOOD2)
