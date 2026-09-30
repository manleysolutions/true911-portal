"""Physical-device counting (the RH "Devices = 0" fix) — pure unit tests.

A physical device is counted once no matter how many identifiers describe it;
identifiers alone (a SIM, a number) are never devices; evidence from one
building never leaks into another.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.customer import physical_devices as pd


def m(kind, value, active=True):
    return {"kind": kind, "value": value, "active": active}


def dev(device_id, **kw):
    base = dict(imei=None, iccid=None, msisdn=None, serial_number=None)
    base.update(kw)
    return SimpleNamespace(device_id=device_id, **base)


def test_napco_radio_is_one_device():
    assert pd.building_physical_devices([m("napco_radio", "R-1")]) == 1


def test_ms130_identifiers_do_not_inflate_count():
    # IMEI + ICCID + MSISDN + phone for ONE MS130v4
    maps = [m("imei", "359000000000001"), m("iccid", "8901000000000000002"),
            m("genesis_msisdn", "5125550149"), m("phone", "5125550149")]
    assert pd.building_physical_devices(maps) == 1


def test_identifiers_alone_are_not_devices():
    assert pd.building_physical_devices([m("iccid", "8901"), m("phone", "5125550149")]) == 0
    assert pd.building_physical_devices([m("true911_device", "RH-147"),
                                         m("zoho_account", "RH Chicago")]) == 0


def test_same_radio_seen_by_three_sources_is_one_device():
    maps = [m("napco_radio", "R-1"), m("iccid", "8901AA"), m("phone", "3125550100")]
    fused = pd.fused_device_groups([{"kind": "napco_radio", "radio_number": "R-1",
                                     "starlink_id": "R-1", "iccid": "8901AA"}])
    site = [dev("D-1", iccid="8901AA", msisdn="3125550100")]
    assert pd.building_physical_devices(maps, site, fused) == 1


def test_two_real_devices_stay_two():
    maps = [m("napco_radio", "R-1"), m("imei", "359000000000009")]
    assert pd.building_physical_devices(maps) == 2
    assert pd.building_physical_devices([], [dev("D-1"), dev("D-2")]) == 2


def test_true911_device_without_identifiers_still_counts_once():
    assert pd.building_physical_devices([], [dev("D-1")]) == 1


def test_fused_payload_from_another_building_does_not_leak():
    fused = pd.fused_device_groups([{"kind": "napco_radio", "radio_number": "R-OTHER"}])
    assert pd.building_physical_devices([m("napco_radio", "R-1")], (), fused) == 1


def test_inactive_mapping_ignored_and_bare_line_not_a_device():
    assert pd.building_physical_devices([m("napco_radio", "R-1", active=False)]) == 0
    fused = pd.fused_device_groups([{"kind": "line", "msisdn": "3125550100"}])
    assert pd.building_physical_devices([m("phone", "3125550100")], (), fused) == 0


def test_phone_numbers_normalized_and_deduplicated():
    maps = [m("phone", "+1 (312) 555-0100"), m("genesis_msisdn", "13125550100"),
            m("iccid", "8901")]
    assert pd.building_phone_numbers(maps, ["312.555.0100", "3125550199"]) == [
        "3125550100", "3125550199"]
