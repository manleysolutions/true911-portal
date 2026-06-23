"""Tests for the RH subscription classification audit (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.audit_rh_subscription_classification import (
    build_classification,
    classify_subscription,
    normalize_iccid,
    write_csv,
    write_json,
)

GOOD_ICCID = "89000000000000000001"


def _kw(**over):
    base = dict(lifecycle="active", has_device_match=False, iccid_present=False,
                msisdn_present=True, site_match="missing", dup_count=1,
                has_active_sibling=False)
    base.update(over)
    return base


# ── classify_subscription (each branch) ──────────────────────────────────
def test_matched_service():
    assert classify_subscription(**_kw(has_device_match=True, lifecycle="active")) == "matched_service"


def test_historical_when_deactivated_with_device():
    assert classify_subscription(**_kw(has_device_match=True, lifecycle="deactivated")) == "historical_subscription"


def test_historical_when_deactivated_no_device():
    assert classify_subscription(**_kw(has_device_match=False, lifecycle="deactivated")) == "historical_subscription"


def test_duplicate_subscription():
    assert classify_subscription(**_kw(dup_count=2, has_active_sibling=False)) == "duplicate_subscription"


def test_replacement_subscription():
    # deactivated member of a group that has an active sibling -> superseded
    assert classify_subscription(**_kw(dup_count=2, lifecycle="deactivated",
                                       has_active_sibling=True)) == "replacement_subscription"


def test_missing_iccid_active_no_device():
    assert classify_subscription(**_kw(iccid_present=False, msisdn_present=True)) == "missing_iccid"


def test_missing_device_active_with_iccid_no_device():
    assert classify_subscription(**_kw(iccid_present=True, msisdn_present=True)) == "missing_device"


def test_missing_site_no_identifiers():
    assert classify_subscription(**_kw(msisdn_present=False, iccid_present=False,
                                       site_match="missing")) == "missing_site"


def test_unresolved():
    assert classify_subscription(**_kw(msisdn_present=False, iccid_present=False,
                                       site_match="exact")) == "unresolved"


# ── normalize_iccid ──────────────────────────────────────────────────────
def test_normalize_iccid():
    assert normalize_iccid("8900 0000 0000 0000 0001") == GOOD_ICCID
    assert normalize_iccid(GOOD_ICCID + "F") == GOOD_ICCID
    assert normalize_iccid(None) == ""


# ── build_classification: the 91-vs-51 story ─────────────────────────────
def _sub(sid, *, account="Restoration Hardware", facility=None, msisdn=None,
         iccid=None, status="Active", lifecycle=None, sub_type="IoT"):
    return {"subscription_mgmt_id": sid, "account_name": account, "facility_name": facility,
            "msisdn": msisdn, "iccid": iccid, "device_activation_status": status,
            "lifecycle_state": lifecycle, "subscription_type": sub_type,
            "connection_type": "cellular", "device_identifier": None}


def _t911(devices=None, lines=None, sites=None):
    return {"customer": {"name": "Restoration Hardware"}, "tenant": {"is_active": True},
            "devices": devices or [], "lines": lines or [], "sites": sites or []}


def test_build_explains_the_gap():
    devices = [{"device_id": "RH-D1", "site_id": "S1", "status": "active",
                "msisdn": "3055550001", "iccid": None, "network_status": "online"}]
    subs = [
        _sub("A1", msisdn="3055550001", status="Active"),            # matched_service
        _sub("H1", msisdn="3055559999", status="De-activated"),      # historical (no device)
        _sub("H2", msisdn="3055558888", status="De-activated"),      # historical
        _sub("M1", msisdn="3055557777", status="Active"),            # missing_iccid (active, no device, no iccid)
        _sub("MD", msisdn="3055556666", iccid=GOOD_ICCID, status="Active"),  # missing_device
        _sub("D1", msisdn="3055555555", status="Active"),            # duplicate (with D2)
        _sub("D2", msisdn="3055555555", status="Active"),            # duplicate
    ]
    rep = build_classification(subs, _t911(devices=devices))
    s = rep["summary"]
    assert s["matched_service"] == 1
    assert s["historical_subscription"] == 2
    assert s["missing_iccid"] == 1
    assert s["missing_device"] == 1
    assert s["duplicate_subscription"] == 2
    assert s["total_subscriptions"] == 7 and s["true911_devices"] == 1
    assert any("historical_subscription" in line for line in rep["recommendation"])


def test_replacement_detected_in_mixed_group():
    subs = [
        _sub("OLD", msisdn="3055551234", status="De-activated"),
        _sub("NEW", msisdn="3055551234", status="Active"),
    ]
    rep = build_classification(subs, _t911())
    cls = {r["subscription_id"]: r["classification"] for r in rep["rows"]}
    assert cls["OLD"] == "replacement_subscription"   # superseded
    assert cls["NEW"] == "duplicate_subscription"     # the live one in the group


# ── exports ──────────────────────────────────────────────────────────────
def test_exports(tmp_path):
    rep = build_classification([_sub("A1", msisdn="3055550001")], _t911())
    j = tmp_path / "r.json"
    write_json(rep, str(j))
    import json
    assert json.loads(j.read_text(encoding="utf-8"))["read_only"] is True
    c = tmp_path / "r.csv"
    assert write_csv(rep["rows"], str(c)) == 1
    assert "subscription_id" in c.read_text(encoding="utf-8").splitlines()[0]


# ── read-only ────────────────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_rh_subscription_classification.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "add_all", "insert into", "delete from"):
        assert forbidden not in lower, f"audit must be read-only; found {forbidden!r}"
