"""Tests for the RH device-identity backfill planner (pure, no DB)."""

from __future__ import annotations

from app.backfill_rh_device_identity import plan_device_mapping


def _dev(did, **kw):
    base = {f: None for f in (
        "model", "device_type", "manufacturer", "carrier", "hardware_model_id",
        "serial_number", "imei", "iccid", "msisdn", "vola_org_id", "sim_id",
        "imsi", "starlink_id")}
    base.update(device_id=did, site_id="RH-S1", last_heartbeat=None)
    base.update(kw)
    return base


# ── happy path / monitorability ──────────────────────────────────────────
def test_backfill_empty_fields_makes_cellular_monitorable():
    # Carrier T-Mobile → probe 'tmobile'; imei provides the identifier.
    devs = [_dev("RH-1")]
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "carrier": "T-Mobile", "imei": "354000000000001"}], devs)
    assert plan.safe is True and len(plan.changes) == 1
    ch = plan.changes[0]
    assert "tmobile" in ch["probe_vendors"]
    assert ch["becomes_monitorable"] is True
    assert ch["set_fields"]["carrier"][1] == "T-Mobile"


def test_vola_model_with_org_id_is_monitorable():
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "model": "LM150", "vola_org_id": "rh-org-1"}], [_dev("RH-1")])
    ch = plan.changes[0]
    assert "vola" in ch["probe_vendors"] and ch["becomes_monitorable"] is True


def test_adapter_without_identifier_is_not_monitorable():
    # Recognised model (probe vola) but no identifier → not monitorable yet.
    plan = plan_device_mapping([{"device_id": "RH-1", "model": "LM150"}], [_dev("RH-1")])
    ch = plan.changes[0]
    assert ch["probe_vendors"] == ["vola"]
    assert ch["becomes_monitorable"] is False


# ── refusals (batch all-or-nothing) ──────────────────────────────────────
def test_invalid_imei_refuses_batch():
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "imei": "123"}], [_dev("RH-1")])
    assert plan.safe is False and plan.changes == []
    assert any("invalid imei" in r for r in plan.refusals)


def test_invalid_iccid_and_msisdn():
    p1 = plan_device_mapping([{"device_id": "RH-1", "iccid": "89001"}], [_dev("RH-1")])
    assert any("invalid iccid" in r for r in p1.refusals)
    p2 = plan_device_mapping([{"device_id": "RH-1", "msisdn": "abc"}], [_dev("RH-1")])
    assert any("invalid msisdn" in r for r in p2.refusals)


def test_unknown_field_refuses():
    plan = plan_device_mapping([{"device_id": "RH-1", "color": "red"}], [_dev("RH-1")])
    assert plan.safe is False and any("unknown field" in r for r in plan.refusals)


def test_unknown_device_refuses():
    plan = plan_device_mapping([{"device_id": "NOPE", "carrier": "T-Mobile"}], [_dev("RH-1")])
    assert any("NOPE" in r and "not found" in r for r in plan.refusals)


def test_duplicate_device_id_refuses():
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "carrier": "T-Mobile"}, {"device_id": "RH-1", "model": "LM150"}],
        [_dev("RH-1")])
    assert any("duplicate device_id" in r for r in plan.refusals)


# ── conflict / overwrite semantics ───────────────────────────────────────
def test_conflict_refuses_without_overwrite():
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "carrier": "Verizon"}], [_dev("RH-1", carrier="T-Mobile")])
    assert plan.safe is False
    assert any("refusing to overwrite" in r for r in plan.refusals)


def test_conflict_allowed_with_overwrite():
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "carrier": "Verizon"}], [_dev("RH-1", carrier="T-Mobile")],
        allow_overwrite=True)
    assert plan.safe is True
    assert plan.changes[0]["set_fields"]["carrier"] == ("T-Mobile", "Verizon")


def test_matching_existing_value_is_noop():
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "carrier": "t-mobile"}], [_dev("RH-1", carrier="T-Mobile")])
    assert plan.safe is True and plan.changes == []
    assert plan.noops == ["RH-1"]


def test_partial_existing_only_backfills_empty():
    # carrier already set, imei empty → only imei is written.
    plan = plan_device_mapping(
        [{"device_id": "RH-1", "carrier": "T-Mobile", "imei": "354000000000001"}],
        [_dev("RH-1", carrier="T-Mobile")])
    ch = plan.changes[0]
    assert set(ch["set_fields"]) == {"imei"}
    assert ch["becomes_monitorable"] is True
