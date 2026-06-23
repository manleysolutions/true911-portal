"""Tests for the RH ICCID Coverage / NAPCO match-readiness audit (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.services.device_health.classifier import classify
from app.audit_rh_iccid_coverage import (
    build_records,
    categorize_device,
    cross_reference,
    duplicate_iccid_set,
    iccid_invalid_reason,
    is_napco_candidate,
    is_valid_iccid,
    looks_like_iccid,
    normalize_iccid,
    summarize,
    write_csv,
    REPORT_FIELDS,
)

# A well-formed 20-digit ICCID (NAPCO export shape; fabricated value).
GOOD = "89000000000000000001"
GOOD2 = "89000000000000000002"


def _dev(device_id, *, iccid=None, serial=None, model="SLE-LTEVI-FIRE",
         manufacturer=None, carrier=None, site_id="rh-site-1", msisdn=None, imei=None):
    return {
        "device_id": device_id, "site_id": site_id, "model": model,
        "device_type": None, "hardware_model_id": None, "manufacturer": manufacturer,
        "carrier": carrier, "serial_number": serial, "iccid": iccid,
        "msisdn": msisdn, "imei": imei,
    }


# ── ICCID validity / normalization ───────────────────────────────────────
def test_valid_iccid():
    assert is_valid_iccid(GOOD)
    assert is_valid_iccid("8900 0000 0000 0000 0001")     # spaces tolerated
    assert is_valid_iccid("89000000000000000001F")        # trailing F pad
    assert iccid_invalid_reason(GOOD) is None


def test_normalize_iccid():
    assert normalize_iccid("8900-0000-0001") == "890000000001"
    assert normalize_iccid("89000000000000000001F") == "89000000000000000001"
    assert normalize_iccid(None) == "" and normalize_iccid("  ") == ""


def test_malformed_iccid():
    assert not is_valid_iccid("123")                      # too short
    assert not is_valid_iccid("12340000000000000001")     # wrong prefix
    assert not is_valid_iccid("abcd")                     # non-numeric
    assert "too short" in iccid_invalid_reason("8900")
    assert "!= '89'" in iccid_invalid_reason("12340000000000000001")


# ── NAPCO candidate classification ───────────────────────────────────────
def test_napco_candidate_classification():
    assert is_napco_candidate(classify(model="SLE-LTEVI-FIRE")) is True
    assert is_napco_candidate(classify(model="StarLink Communicator")) is True
    assert is_napco_candidate(classify(model="LM150")) is False        # VOLA, not NAPCO
    assert is_napco_candidate(classify(model="Cisco ATA 191")) is False


# ── per-device categorization ────────────────────────────────────────────
def test_ready_for_napco_import():
    assert categorize_device(_dev("d1", iccid=GOOD), is_napco=True, dup_iccids=set()) \
        == "ready_for_napco_import"


def test_missing_iccid_napco_candidate():
    assert categorize_device(_dev("d1", iccid=None), is_napco=True, dup_iccids=set()) \
        == "napco_candidate_no_iccid"


def test_invalid_iccid():
    assert categorize_device(_dev("d1", iccid="12345"), is_napco=True, dup_iccids=set()) \
        == "invalid_iccid"


def test_duplicate_iccid():
    devs = [_dev("d1", iccid=GOOD), _dev("d2", iccid=GOOD)]
    dup = duplicate_iccid_set(devs)
    assert normalize_iccid(GOOD) in dup
    assert categorize_device(devs[0], is_napco=True, dup_iccids=dup) == "duplicate_iccid"
    assert categorize_device(devs[1], is_napco=True, dup_iccids=dup) == "duplicate_iccid"


def test_conflicting_identity_iccid_in_serial_column():
    # No ICCID field, but the SERIAL column holds a valid ICCID → conflict.
    d = _dev("d1", iccid=None, serial=GOOD)
    assert categorize_device(d, is_napco=True, dup_iccids=set()) == "conflicting_identity"


def test_non_napco_device():
    d = _dev("d1", iccid=GOOD, model="LM150")
    assert categorize_device(d, is_napco=False, dup_iccids=set()) == "non_napco_device"


# ── build_records + summary math ─────────────────────────────────────────
def _records():
    devices = [
        _dev("ready-1", iccid=GOOD),                       # ready_for_napco_import
        _dev("dup-a", iccid=GOOD2),                        # duplicate (with dup-b)
        _dev("dup-b", iccid=GOOD2),                        # duplicate
        _dev("noicc", iccid=None),                         # napco_candidate_no_iccid
        _dev("bad", iccid="123"),                          # invalid_iccid
        _dev("vola", iccid="89111111111111111111", model="LM150"),  # non_napco_device
    ]
    sites = {"rh-site-1": {"site_id": "rh-site-1", "site_name": "RH Beverly"}}
    return build_records(devices, sites, classify)


def test_build_records_fields_and_site_join():
    recs = _records()
    r = recs[0]
    assert set(REPORT_FIELDS) <= set(r)               # every report field present
    assert r["site_name"] == "RH Beverly"
    assert r["classifier_family"] == "napco_starlink"
    assert r["category"] == "ready_for_napco_import"


def test_summary_math_and_coverage():
    s = summarize(_records())
    assert s["total_devices"] == 6
    assert s["devices_with_iccid"] == 5            # all but 'noicc'
    assert s["devices_missing_iccid"] == 1
    assert s["napco_candidates"] == 5              # all except the LM150
    assert s["import_ready"] == 1                  # only ready-1
    assert s["duplicate_iccid_values"] == 1        # GOOD2 shared
    assert s["duplicate_iccid_devices"] == 2
    assert s["invalid_iccids"] == 1
    assert s["napco_candidate_no_iccid"] == 1
    assert s["by_category"]["non_napco_device"] == 1
    # coverage = import_ready / napco_candidates = 1/5 = 20.0%
    assert s["estimated_match_coverage_pct"] == 20.0


def test_coverage_zero_when_no_candidates():
    sites = {}
    recs = build_records([_dev("x", iccid=GOOD, model="LM150")], sites, classify)
    assert summarize(recs)["estimated_match_coverage_pct"] == 0.0


# ── cross-reference vs export ────────────────────────────────────────────
def test_cross_reference_counts():
    recs = _records()
    export_iccids = {normalize_iccid(GOOD), normalize_iccid("89000000000000009999")}
    cross = cross_reference(recs, export_iccids, export_radio_numbers=set())
    assert cross["match_today_by_iccid"] == 1            # only GOOD is ready + in export
    assert cross["need_iccid_backfill"] == 1             # 'noicc'
    assert cross["need_manual_review"] == 3              # dup-a, dup-b, bad
    assert cross["export_iccids_with_no_rh_device"] == 1  # the 9999 one


# ── CSV export generation ────────────────────────────────────────────────
def test_export_generation(tmp_path):
    recs = _records()
    out = tmp_path / "rh_iccid_audit.csv"
    n = write_csv(recs, str(out))
    assert n == len(recs)
    text = out.read_text(encoding="utf-8")
    assert "device_id,device_name,site_id" in text.splitlines()[0]
    assert "ready-1" in text and "ready_for_napco_import" in text
    # one header + 6 device rows
    assert len([ln for ln in text.splitlines() if ln.strip()]) == 1 + len(recs)


# ── read-only guarantee ──────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_rh_iccid_coverage.py").read_text(encoding="utf-8")
    lower = src.lower()
    # No DB mutation primitives anywhere in the audit. (Tokens are specific to
    # ORM/session writes so list.insert / set.add / dict.update don't false-trip.)
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "db.bulk"):
        assert forbidden not in lower, f"audit must be read-only; found {forbidden!r}"
    # It does query (SELECT only).
    assert "select(" in src
