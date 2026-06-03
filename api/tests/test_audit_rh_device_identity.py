"""Tests for the RH device identity discovery audit (pure, no DB)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from app.audit_rh_device_identity import (
    AFTER_TMOBILE_ACCOUNT,
    DATA_CONFLICT,
    MANUAL_REQUIRED,
    MONITORABLE_NOW,
    NEEDS_CREDENTIALS,
    NEEDS_IDENTITY,
    UNKNOWN_TYPE,
    build_template_row,
    categorize_device,
    detect_data_conflict,
    export_record,
    infer_identity_hints,
    summary_counts,
)


def _dev(**kw):
    base = dict(device_id="RH-1", display_name="RH-1", site_id="S1", site_name="Store 1",
                customer_id=7, tenant_id="restoration-hardware", model=None, device_type=None,
                manufacturer=None, hardware_model_id=None, carrier=None, telemetry_source=None,
                vola_org_id=None, msisdn=None, imei=None, iccid=None, serial_number=None,
                status="active", last_heartbeat=None, network_status=None,
                identifier_type=None, reconciliation_status=None, import_batch_id=None)
    base.update(kw)
    return base


# ── categorization ───────────────────────────────────────────────────────
def test_full_identity_is_monitorable_now():
    d = _dev(model="LM150", serial_number="SN123")
    cat = categorize_device(d, ["vola"], adapter_configured={"vola": True},
                            tmobile_account_available=True)
    assert cat["category"] == MONITORABLE_NOW


def test_tmobile_with_msisdn_no_account_id():
    d = _dev(carrier="T-Mobile", msisdn="8135550100")
    cat = categorize_device(d, ["tmobile"], adapter_configured={"tmobile": True},
                            tmobile_account_available=False)
    assert cat["category"] == AFTER_TMOBILE_ACCOUNT
    assert "TMOBILE_ACCOUNT_ID" in cat["reason"]


def test_manual_only_device():
    d = _dev(model="Cisco-ATA", device_type="analog")
    cat = categorize_device(d, ["cisco_ata", "telnyx"], adapter_configured={"cisco_ata": False, "telnyx": False},
                            tmobile_account_available=True)
    assert cat["category"] == MANUAL_REQUIRED


def test_blank_inventory_needs_identity_mapping():
    cat = categorize_device(_dev(), [], adapter_configured={}, tmobile_account_available=True)
    assert cat["category"] == NEEDS_IDENTITY


def test_unrecognised_model_is_unknown_type():
    d = _dev(model="WidgetPhone 9000")
    cat = categorize_device(d, [], adapter_configured={}, tmobile_account_available=True)
    assert cat["category"] == UNKNOWN_TYPE


def test_vola_configured_missing_credentials_vs_identity():
    # adapter present + identifier present but creds missing → needs_vendor_credentials
    d = _dev(model="LM150", serial_number="SN1")
    cat = categorize_device(d, ["vola"], adapter_configured={"vola": False},
                            tmobile_account_available=True)
    assert cat["category"] == NEEDS_CREDENTIALS
    # adapter present, configured, but no identifier → needs_identity_mapping
    d2 = _dev(model="LM150")
    cat2 = categorize_device(d2, ["vola"], adapter_configured={"vola": True},
                             tmobile_account_available=True)
    assert cat2["category"] == NEEDS_IDENTITY


def test_conflicting_identity_is_data_conflict():
    # vola_org_id set but classifier did not yield vola
    d = _dev(vola_org_id="rh-org-1")
    cat = categorize_device(d, ["tmobile"], adapter_configured={"tmobile": True},
                            tmobile_account_available=True)
    assert cat["category"] == DATA_CONFLICT
    # serial looks like a phone number but differs from msisdn
    d2 = _dev(serial_number="813-555-0100", msisdn="8135559999")
    assert detect_data_conflict(d2, ["tmobile"]) is not None


# ── identity hints ───────────────────────────────────────────────────────
def test_hints_for_vola_model():
    h = infer_identity_hints(_dev(model="LM150"))
    assert h["likely_vendor_candidate"] == "vola"
    assert "vola_org_id" in h["missing_fields"]


def test_hints_for_phone_like_id():
    h = infer_identity_hints(_dev(device_id="8135550123", display_name="8135550123"))
    assert "cellular" in h["likely_device_class"]
    assert "msisdn" in h["missing_fields"]


def test_template_row_shape_matches_spec():
    row = build_template_row(_dev(model="LM150"), infer_identity_hints(_dev(model="LM150")), NEEDS_IDENTITY)
    assert set(row) == {
        "device_id", "site_id", "site_name", "current_name", "suggested_model",
        "suggested_vendor", "required_identifier", "imei", "iccid", "msisdn",
        "serial_number", "manual_verification_only", "operator_notes"}
    assert row["manual_verification_only"] is False


def test_template_marks_manual_only():
    row = build_template_row(_dev(), infer_identity_hints(_dev()), MANUAL_REQUIRED)
    assert row["manual_verification_only"] is True


# ── summary + export ─────────────────────────────────────────────────────
def _report(cat, **cur):
    d = _dev(**cur)
    return {"current": d, "probe_vendors": ([] if cat in (NEEDS_IDENTITY, UNKNOWN_TYPE) else ["vola"]),
            "classifier": {}, "adapter_candidate": None, "category": cat, "reason": "x",
            "hints": infer_identity_hints(d)}


def test_summary_counts():
    reports = [_report(MONITORABLE_NOW, imei="35"), _report(AFTER_TMOBILE_ACCOUNT, msisdn="813"),
               _report(NEEDS_IDENTITY), _report(UNKNOWN_TYPE, model="x"), _report(MANUAL_REQUIRED)]
    s = summary_counts(reports)
    assert s["total_devices"] == 5
    assert s["monitorable_now"] == 1
    assert s["blocked_by_tmobile_account_id"] == 1
    assert s["unmapped"] == 2                       # needs_identity + unknown_type
    assert s["manual_verification_required"] == 1
    assert s["missing_model"] >= 3


def test_export_record_contains_no_secrets():
    r = _report(MONITORABLE_NOW, model="LM150", serial_number="SN1")
    rec = export_record(r)
    blob = repr(rec).lower()
    for secret in ("password", "secret", "private_key", "rsa", "consumer_key", "vola_password", "jwt"):
        assert secret not in blob
    # only whitelisted-ish keys; no raw payload
    assert "raw_payload" not in rec and "device_id" in rec


# ── read-only guard ──────────────────────────────────────────────────────
def test_module_is_read_only():
    src = Path(__file__).resolve().parents[1].joinpath("app", "audit_rh_device_identity.py").read_text(encoding="utf-8")
    for forbidden in ("db.add(", "db.commit(", "db.delete(", "db.flush(", "session.add("):
        assert forbidden not in src, f"read-only audit must not contain {forbidden!r}"


def test_template_file_matches_spec_schema():
    import json
    p = Path(__file__).resolve().parents[2].joinpath(
        "docs", "templates", "rh_device_identity_mapping_template.json")
    rows = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and len(rows) >= 1
    assert set(rows[0]) == {
        "device_id", "site_id", "site_name", "current_name", "suggested_model",
        "suggested_vendor", "required_identifier", "imei", "iccid", "msisdn",
        "serial_number", "manual_verification_only", "operator_notes"}
