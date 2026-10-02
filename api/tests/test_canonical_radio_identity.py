"""Canonical engine - radio identity, NAPCO provenance and FACP evidence.

Regression tests for the defects the 2026-10-02 RH dry-run exposed (a device
serial counted as a NAPCO radio and an FACP service; one radio projected as two
services; Zoho-only ids presented as NAPCO; SKU / telephone-line records taken
as FACP evidence).  The building SHAPES mirror Houston, Jacksonville, Princeton
and Roseville; every identifier is SYNTHETIC (555-01xx numbers, 2099... serials,
86000... IMEIs, 89010000... SIMs, 77... radio ids).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.source_snapshot import SourceSnapshot, SourceSnapshotRecord
from app.services.canonical import engine, loader, report
from app.services.canonical import vocab as V
from app.services.canonical.normalize import is_sku_label, radio_id
from tests.test_canonical_engine import _facp_device, conns, device, site, snap, svc, zrow

SERIAL = "209901010000027"            # 15-char MS130-style device serial
OLD_SERIAL = "209904030000068"        # an older device's serial (Jacksonville shape)
IMEI = "860000000000017"
ICCID = "8901000000000000017"
PHONE = "2025550170"


def z(facility, ctype=None, *, msisdn=None, starlink=None, sub=None, status="Activated",
      sim=None, imei=None, serial=None):
    r = zrow(facility, msisdn, ctype, status=status, starlink=starlink, sim=sim)
    r.update(subscription_type=sub, imei=imei, serial=serial)
    return r


def reg(mid, bid, value, kind="napco_radio"):
    return {"id": mid, "building_id": bid, "kind": kind, "value": value}


def facps(res, bid):
    return [s for s in res["services"] if s["building_id"] == bid and s["service_type"] == V.FACP]


def codes(res, code):
    return [f for f in res["findings"] if f["code"] == code]


# ── normalisation rules (generic, not per-customer) ───────────────────

@pytest.mark.parametrize("value", [SERIAL, OLD_SERIAL, IMEI, ICCID, PHONE, "1" + PHONE,
                                   "(202) 555-0170", "123", ""])
def test_serial_imei_iccid_and_phone_shapes_are_never_radio_ids(value):
    assert radio_id(value) is None


@pytest.mark.parametrize("value,expected", [("77187020", "77187020"), ("7187020", "7187020"),
                                            ("NAP-0001", "NAP0001"), (" 7700523 ", "7700523")])
def test_radio_shaped_values_are_kept_exactly(value, expected):
    assert radio_id(value) == expected


@pytest.mark.parametrize("label,sku", [
    ("SLELTE - Fire (Dual Line)", True), ("SLE-LTEVI-FIRE (Comm Dual Path)", True),
    ("SLEMAXVI-FIRE (Dual Line 5G)", True), ("MS130v4", True),
    ("Verizon LTE Unlimited Service Pack 3", True),
    ("Fire Alarm", False), ("Alarm Panel", False), ("Elevator", False), ("Voice", False),
    ("Sleep room elevator", False)])
def test_sku_and_plan_labels_are_recognised(label, sku):
    assert is_sku_label(label) is sku


def test_loader_reads_radio_only_from_radio_named_fields():
    assert loader.radio_field_names(["Starlink_Serial_Number", "Radio_Plan", "Starlink_ID",
                                     "Starlink_Status", "Serial_Number", "RadioNumber"]) \
        == ["Starlink_ID", "RadioNumber"]
    assert loader.zoho_radio({"Starlink_Serial_Number": SERIAL, "Starlink_ID": "7700021"}) \
        == "7700021"
    assert loader.zoho_radio({"Serial_Number": SERIAL, "Device_IMEI": IMEI}) is None
    # a serial typed into the radio field itself is passed on - and refused by the engine
    assert loader.zoho_radio({"Starlink_ID": SERIAL}) == SERIAL


# ── 1-3: serials / telephone devices never create an FACP ─────────────

def test_1_telephone_device_serial_cannot_create_an_facp():
    rows = [z("RH Houston #130", "Alarm Panel", msisdn=PHONE, sim=ICCID, imei=IMEI,
              serial=SERIAL, sub="MS130v4")]
    devs = [device("D1", "S-130", model="MS130v4", msisdn=PHONE, starlink_id=SERIAL)]
    res = engine.project(snap(zoho_rows=rows, devices=devs,
                              sites=[site("S-130", "RH Houston #130")],
                              mappings=[reg(1, 4, SERIAL)]))
    assert facps(res, 4) == []
    assert not [a for a in res["assets"].values() if a["asset_type"] == V.NAPCO_RADIO]
    # the line is FACP equipment, not an FACP service
    assert res["assets"]["TELEPHONE_NUMBER:%s" % PHONE]["classification"] == V.FACP_ASSET
    assert len(codes(res, "RADIO_ID_REJECTED")) == 2          # True911 column + registry value
    assert res["connections"] == []


def test_2_jacksonville_old_device_serial_cannot_create_an_facp():
    rows = [z("RH Jacksonville", "Elevator", msisdn="2025550171", serial=OLD_SERIAL, imei=IMEI)]
    res = engine.project(snap(zoho_rows=rows, mappings=[reg(1, 5, OLD_SERIAL)]))
    assert facps(res, 5) == []
    assert not [f for f in codes(res, "FACP_UNRESOLVED") if f["building_id"] == 5]


def test_3_houston_ms130_serial_cannot_create_an_facp_but_the_real_radio_still_can():
    rows = [z("RH Houston #130", "Alarm Panel", msisdn=PHONE, starlink=SERIAL, sub="MS130v4",
              imei=IMEI, serial=SERIAL),                         # serial in the radio field
            z("RH Houston #130", "Alarm Panel", starlink="7700021",
              sub="SLELTE - Fire (Dual Line)")]
    res = engine.project(snap(zoho_rows=rows, mappings=[reg(1, 4, "7700021")]))
    assert [s["service_key"] for s in facps(res, 4)] == ["FACP:radio:7700021"]
    assert all(SERIAL not in s["service_key"] for s in res["services"])


# ── 4-8: one radio = one service; provenance; no fuzzy merge ──────────

def test_4_zoho_record_and_matching_napco_radio_are_one_service():
    rows = [z("RH Princeton", "Fire Alarm", starlink="77187020")]
    res = engine.project(snap(zoho_rows=rows, mappings=[reg(1, 7, "77187020")],
                              napco_radios=["77187020"]))
    f = facps(res, 7)
    assert [s["service_key"] for s in f] == ["FACP:radio:77187020"]
    assert f[0]["confidence"] == V.CONFIRMED and f[0]["provenance"]["napco_backed"] is True
    assert not [s for s in res["services"] if s["service_key"].startswith("FACP:zoho:")]


def test_5_zoho_only_radio_id_is_not_napco_provenance():
    res = engine.project(snap(zoho_rows=[z("RH Princeton", "Fire Alarm", starlink="77187020")]))
    (s,) = facps(res, 7)
    assert s["service_key"] == "FACP:radio:77187020"
    assert s["provenance"] == {"radio_ids": ["77187020"], "sources": [V.SRC_ZOHO],
                               "napco_evidence": "NOT_LOADED", "napco_backed": False}
    assert s["confidence"] == V.PROBABLE and not s["counts"]
    assert codes(res, "FACP_RADIO_SINGLE_SOURCE") and codes(res, "NAPCO_EVIDENCE_NOT_LOADED")
    assert not [x for x in res["services"] if "napco" in x["service_key"].lower()]


def test_6_roseville_pattern_is_not_napco_backed_merely_from_zoho():
    # one hand-entered value copied into the radio, SIM, IMEI and serial fields
    rows = [z("RH Austin #149", "Alarm Panel", starlink="7700523", sim="7700523",
              imei="7700523", serial="7700523")]
    res = engine.project(snap(zoho_rows=rows, mappings=[reg(1, 8, "7700523")],
                              napco_radios=["77187020"]))         # loaded, radio absent
    (s,) = facps(res, 8)
    assert s["provenance"]["napco_backed"] is False
    assert s["provenance"]["napco_evidence"] == "ABSENT"
    assert V.SRC_NAPCO not in s["provenance"]["sources"]
    assert s["confidence"] == V.PROBABLE and not s["counts"]
    assert s["lifecycle"] == V.CURRENT                            # absence != decommissioned
    assert [f["building_id"] for f in codes(res, "RADIO_NOT_IN_NAPCO")] == [8]


def test_7_fuzzy_or_dropped_digit_radio_ids_never_merge():
    rows = [z("RH Princeton", "Fire Alarm", starlink="77187020"),
            z("RH Princeton", "Fire Alarm", starlink="7187020")]   # dropped digit
    res = engine.project(snap(zoho_rows=rows, mappings=[reg(1, 7, "77187020")],
                              napco_radios=["77187020"]))
    by_key = {s["service_key"]: s for s in facps(res, 7)}
    assert sorted(by_key) == ["FACP:radio:7187020", "FACP:radio:77187020"]
    assert by_key["FACP:radio:77187020"]["confidence"] == V.CONFIRMED
    assert by_key["FACP:radio:7187020"]["confidence"] == V.PROBABLE
    assert by_key["FACP:radio:7187020"]["provenance"]["napco_evidence"] == "ABSENT"
    assert len(conns(res, 7)) == 2                                 # only the real radio counts


def test_8_provenance_from_every_source_survives_the_merge():
    rows = [z("RH Chicago #147", "Fire Alarm", starlink="NAP-0001")]
    res = engine.project(snap(zoho_rows=rows, sites=[site("S-147", "RH Chicago #147")],
                              devices=[_facp_device("F1", "S-147", "NAP-0001")],
                              napco_radios=["NAP0001"]))
    (s,) = facps(res, 1)
    assert s["provenance"]["sources"] == sorted([V.SRC_NAPCO, V.SRC_TRUE911, V.SRC_ZOHO])
    assert "device:F1" in s["evidence"][0] and "zoho:" in s["evidence"][0]
    assert ("NAPCO_RADIO:NAP0001", V.REL_SERVICE_EQUIPMENT) in s["assets"]
    text = report.render(res)
    assert "provenance: sources=NAPCO,TRUE911,ZOHO napco=PRESENT" in text


# ── 9-10: lifecycle independence and FACP cardinality ─────────────────

def test_9_lifecycle_is_independent_of_identity_and_confidence():
    # PROBABLE (Zoho only) but Zoho says Activated -> CURRENT lifecycle, still not counted
    a = facps(engine.project(snap(zoho_rows=[z("RH Princeton", "Fire Alarm",
                                                 starlink="77187020")])), 7)[0]
    assert (a["confidence"], a["lifecycle"], a["counts"]) == (V.PROBABLE, V.CURRENT, False)
    # absent from a loaded NAPCO snapshot -> never DECOMMISSIONED by that absence
    b = facps(engine.project(snap(zoho_rows=[z("RH Princeton", "Fire Alarm", starlink="7700099",
                                                 status="Suspended")],
                                  mappings=[reg(1, 7, "7700099")], napco_radios=[])), 7)[0]
    assert b["lifecycle"] != V.DECOMMISSIONED and b["lifecycle_reason"] is None
    # NAPCO-backed + registry, but no source states a lifecycle -> UNKNOWN, not counted
    c = facps(engine.project(snap(zoho_rows=[z("RH Princeton", "Fire Alarm", starlink="77187020",
                                                 status=None)],
                                  mappings=[reg(1, 7, "77187020")],
                                  napco_radios=["77187020"])), 7)[0]
    assert (c["confidence"], c["lifecycle"], c["counts"]) == (V.CONFIRMED, V.UNKNOWN, False)


def test_10_facp_has_two_connections_only_once_the_service_is_established():
    rows = [z("RH Princeton", "Fire Alarm", starlink="77187020")]
    before = engine.project(snap(zoho_rows=rows))                  # Zoho only
    assert conns(before, 7) == []
    b = next(b for b in before["building_summaries"] if b["building_id"] == 7)
    assert b["probable_additional_connections"] == 2
    after = engine.project(snap(zoho_rows=rows, napco_radios=["77187020"]))
    c = conns(after, 7)
    assert [x["ordinal"] for x in c] == [1, 2]
    assert all(x["connection_type"] == "FACP_PATH" for x in c)


# ── FACP evidence: what is NOT evidence ───────────────────────────────

@pytest.mark.parametrize("ctype,sub", [(None, "SLELTE - Fire (Dual Line)"), ("Voice", None),
                                       ("Voice 1", "SLEMAXVI-FIRE (Dual Line 5G)"),
                                       (None, None)])
def test_sku_voice_and_blank_labels_are_not_facp_evidence(ctype, sub):
    res = engine.project(snap(zoho_rows=[z("RH Princeton", ctype, starlink="77187020", sub=sub)],
                              napco_radios=["77187020"]))
    (s,) = facps(res, 7)
    assert s["confidence"] == V.UNRESOLVED and not s["counts"]    # a radio, no FACP evidence


def test_alarm_panel_telephone_line_is_never_an_facp_service():
    res = engine.project(snap(zoho_rows=[z("RH Houston #130", "Alarm Panel", msisdn=PHONE)]))
    assert facps(res, 4) == []
    assert res["assets"]["TELEPHONE_NUMBER:%s" % PHONE]["classification"] == V.FACP_ASSET


# ── loader: NAPCO snapshot evidence ───────────────────────────────────

def _napco_db(radios):
    async def go():
        eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                  connect_args={"check_same_thread": False})
        async with eng.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(
                c, tables=[SourceSnapshot.__table__, SourceSnapshotRecord.__table__]))
        Session = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
        now = datetime(2026, 9, 30, tzinfo=timezone.utc)
        async with Session() as db:
            if radios is not None:
                db.add(SourceSnapshot(
                    id=1, tenant_id="tenant-test", source_system="NAPCO", source_label="radiolist",
                    file_sha256="0" * 64, original_basename="radiolist.csv", file_size=1,
                    parser_name="test", parser_version="1", status_map_version="1",
                    attribution_rule_version="1", source_effective_at=now,
                    effective_at_basis="OPERATOR", imported_at=now, imported_by="test",
                    row_count_total=len(radios), row_count_attributed=len(radios),
                    row_count_excluded=0, row_count_ambiguous=0, row_count_invalid=0))
                for i, r in enumerate(radios, 1):
                    db.add(SourceSnapshotRecord(
                        snapshot_id=1, tenant_id="tenant-test", source_system="NAPCO",
                        row_number=i, source_record_key=r, identifier_type="NAPCO_RADIO",
                        normalized_identifier=r, napco_radio=r,
                        lifecycle_interpretation="UNKNOWN", interpretation_rule="test",
                        attribution_basis="test", attribution_confidence="HIGH",
                        row_hash=str(i)))
                await db.commit()
            out = await loader.load_napco_radios(db, "tenant-test")
            other = await loader.load_napco_radios(db, "another-tenant")
        await eng.dispose()
        return out, other
    return asyncio.run(go())


def test_loader_reads_latest_tenant_napco_snapshot_radios():
    (radios, info), (other, oinfo) = _napco_db(["77187020", "NAP-0001", SERIAL])
    assert radios == ["77187020", "NAP0001"]                       # a serial is never a radio
    assert (info["status"], info["required"], info["radios"]) == ("ok", False, 2)
    assert other is None and oinfo["status"] == "none loaded"      # tenant-scoped


def test_loader_reports_absent_napco_evidence_instead_of_assuming_it():
    (radios, info), _ = _napco_db(None)
    assert radios is None and info["status"] == "none loaded"
