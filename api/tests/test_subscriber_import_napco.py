"""Tests for Napco / SLELTE / StarLink fire-alarm communicator support
in the subscriber import validation path.

Pure-function tests against the importer's classifier and validator —
no DB required.
"""

from types import SimpleNamespace

from app.services.subscriber_import_engine import (
    PROTOCOL_MAX_LEN,
    _canonical_protocol,
    _extract_row,
    _is_napco_starlink_row,
    _validate_row,
)


def _empty_seen() -> dict:
    return {"device_ids": {}, "msisdns": {}, "iccids": {}, "serials": {}, "starlinks": {}}


def _row(**overrides) -> dict:
    """Build a CSV-style row dict (post-header-normalization) with sane defaults."""
    base = {
        "customer_name": "Acme Hospital",
        "customer_account_number": "ACCT-1",
        "site_name": "Main Campus",
        "street_address": "1 Main St",
        "city": "Dallas",
        "state": "TX",
        "zip": "75201",
        "country": "US",
        "endpoint_type": "",
        "service_class": "",
        "transport": "",
        "carrier": "",
        "voice_provider": "",
        "device_id": "",
        "hardware_model": "",
        "serial_number": "",
        "imei": "",
        "iccid": "",
        "msisdn": "",
        "did": "",
        "notes": "",
    }
    base.update(overrides)
    return base


# ── Classifier ────────────────────────────────────────────────────

def test_classifier_carrier_napco():
    row = _extract_row(_row(carrier="Napco"), 1)
    assert _is_napco_starlink_row(row) is True


def test_classifier_vendor_napco():
    # vendor_name lookup falls back through manufacturer
    row = _extract_row(_row(vendor_name="Napco Security Technologies"), 1)
    assert _is_napco_starlink_row(row) is True


def test_classifier_model_starlink():
    row = _extract_row(_row(hardware_model="Napco StarLink"), 1)
    assert _is_napco_starlink_row(row) is True


def test_classifier_endpoint_fire_alarm():
    row = _extract_row(_row(endpoint_type="Fire Alarm Control Panel"), 1)
    assert _is_napco_starlink_row(row) is True


def test_classifier_does_not_match_regular_elevator():
    row = _extract_row(
        _row(endpoint_type="Elevator", carrier="T-Mobile", hardware_model="MS130v4"),
        1,
    )
    assert _is_napco_starlink_row(row) is False


def test_classifier_does_not_match_voip_emergency_phone():
    row = _extract_row(
        _row(endpoint_type="Emergency Phone", carrier="", voice_provider="Telnyx"),
        1,
    )
    assert _is_napco_starlink_row(row) is False


# ── Validation: Napco rows accept alternate identifiers ───────────

def test_napco_row_with_serial_only_passes():
    row = _extract_row(
        _row(carrier="Napco", endpoint_type="Fire Alarm", serial_number="SL-SN-001"),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen())
    assert errors == []


def test_napco_row_with_starlink_id_only_passes():
    raw = _row(endpoint_type="Fire Alarm Control Panel", hardware_model="Napco StarLink")
    raw["starlink_id"] = "SL-001"
    row = _extract_row(raw, 1)
    errors, _ = _validate_row(row, _empty_seen())
    assert errors == []


def test_napco_row_with_device_id_only_passes():
    row = _extract_row(
        _row(endpoint_type="Fire Alarm", device_id="DEV-FACP-001"),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen())
    assert errors == []


def test_napco_row_with_no_identifiers_fails_with_napco_message():
    row = _extract_row(
        _row(carrier="Napco", endpoint_type="Fire Alarm"),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen())
    assert any("Napco/SLELTE" in e for e in errors)


# ── Validation: non-Napco rows still require msisdn or iccid ──────

def test_non_napco_row_without_msisdn_or_iccid_still_fails():
    row = _extract_row(
        _row(endpoint_type="Elevator", carrier="T-Mobile", serial_number="MS130-SN-001"),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen())
    assert any("Missing both msisdn and sim_iccid" in e for e in errors)


def test_regular_cellular_voice_row_unchanged():
    row = _extract_row(
        _row(
            endpoint_type="Elevator",
            carrier="T-Mobile",
            msisdn="+12145551001",
            iccid="89012608822800000010",
        ),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen())
    assert errors == []


# ── Intra-CSV duplicate detection ─────────────────────────────────

def test_duplicate_serial_number_in_csv_warns():
    seen = _empty_seen()
    row1 = _extract_row(
        _row(carrier="Napco", endpoint_type="Fire Alarm", serial_number="DUP-SERIAL"),
        1,
    )
    _validate_row(row1, seen)
    seen["serials"]["dup-serial"] = {"row": 1}

    row2 = _extract_row(
        _row(carrier="Napco", endpoint_type="Fire Alarm", serial_number="DUP-SERIAL"),
        2,
    )
    _, warnings = _validate_row(row2, seen)
    assert any("serial_number 'DUP-SERIAL' also on row 1" in w for w in warnings)


def test_duplicate_starlink_id_in_csv_warns():
    seen = _empty_seen()
    seen["starlinks"]["sl-dup"] = {"row": 1}

    raw = _row(carrier="Napco", endpoint_type="Fire Alarm")
    raw["starlink_id"] = "SL-DUP"
    row2 = _extract_row(raw, 2)
    _, warnings = _validate_row(row2, seen)
    assert any("starlink_id 'SL-DUP' also on row 1" in w for w in warnings)


# ── Cross-DB collision: serial / starlink owned by a different device ──

def test_serial_collision_with_existing_device_errors():
    existing_devices = {
        "serial:taken-serial": SimpleNamespace(device_id="DEV-EXISTING"),
    }
    row = _extract_row(
        _row(
            carrier="Napco",
            endpoint_type="Fire Alarm",
            device_id="DEV-NEW",
            serial_number="TAKEN-SERIAL",
        ),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen(), existing_devices=existing_devices)
    assert any(
        "TAKEN-SERIAL" in e and "DEV-EXISTING" in e and "DEV-NEW" in e
        for e in errors
    )


def test_starlink_collision_with_existing_device_errors():
    existing_devices = {
        "starlink:sl-taken": SimpleNamespace(device_id="DEV-EXISTING"),
    }
    raw = _row(carrier="Napco", endpoint_type="Fire Alarm", device_id="DEV-NEW")
    raw["starlink_id"] = "SL-TAKEN"
    row = _extract_row(raw, 1)
    errors, _ = _validate_row(row, _empty_seen(), existing_devices=existing_devices)
    assert any("SL-TAKEN" in e and "DEV-EXISTING" in e for e in errors)


# ── Protocol canonicalization (VARCHAR(20) for lines.protocol) ────

def test_canonical_protocol_maps_volte_long_label():
    assert _canonical_protocol("VoLTE (Cellular Voice)") == "VoLTE"


def test_canonical_protocol_maps_analog_pots_long_label():
    assert _canonical_protocol("Analog (POTS Replacement)") == "POTS"


def test_canonical_protocol_maps_voip_sip():
    assert _canonical_protocol("VoIP (SIP)") == "SIP"


def test_canonical_protocol_maps_data_only():
    assert _canonical_protocol("Data Only") == "DATA"


def test_canonical_protocol_maps_ethernet_lan():
    assert _canonical_protocol("Ethernet (LAN)") == "ethernet"


def test_canonical_protocol_empty_defaults_to_cellular():
    assert _canonical_protocol("") == "cellular"
    assert _canonical_protocol(None) == "cellular"


def test_canonical_protocol_passes_short_unknown_through():
    assert _canonical_protocol("DECT") == "DECT"


def test_canonical_protocol_returns_none_for_overlong_unknown():
    overlong = "X" * (PROTOCOL_MAX_LEN + 1)
    assert _canonical_protocol(overlong) is None


def test_canonical_protocol_output_always_fits_column():
    samples = [
        "VoLTE (Cellular Voice)",
        "Analog (POTS Replacement)",
        "VoIP (SIP)",
        "Data Only",
        "Ethernet (LAN)",
        "Cellular",
        "",
        "SIP",
    ]
    for s in samples:
        out = _canonical_protocol(s)
        assert out is not None
        assert len(out) <= PROTOCOL_MAX_LEN


def test_validate_row_template_volte_value_passes():
    """Regression: rows with the project's own template 'service_class'
    values must not be rejected."""
    row = _extract_row(
        _row(
            endpoint_type="Elevator",
            service_class="VoLTE (Cellular Voice)",
            carrier="T-Mobile",
            msisdn="+12145551001",
            iccid="89012608822800000010",
        ),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen())
    assert errors == []


def test_validate_row_overlong_unmappable_protocol_errors_in_preview():
    """Defensive: an unmapped >20-char service_class surfaces in preview
    rather than crashing at commit-time INSERT."""
    overlong = "Frobnicated Hyperbolic Trans-Multi-Carrier"
    row = _extract_row(
        _row(
            endpoint_type="Elevator",
            service_class=overlong,
            carrier="T-Mobile",
            msisdn="+12145551001",
        ),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen())
    assert any("canonical protocol code" in e for e in errors)


def test_serial_match_without_device_id_is_not_a_collision():
    """A row with only serial_number that matches an existing device is a
    normal serial-based match, not a conflict."""
    existing_devices = {
        "serial:owned-serial": SimpleNamespace(device_id="DEV-EXISTING"),
    }
    row = _extract_row(
        _row(carrier="Napco", endpoint_type="Fire Alarm", serial_number="OWNED-SERIAL"),
        1,
    )
    errors, _ = _validate_row(row, _empty_seen(), existing_devices=existing_devices)
    assert errors == []
