"""Operational source snapshots (D-024): parsers, status interpretation, tenant
attribution, privacy, immutable apply, SHA dedupe, no side effects, CLI rails.

Fixtures in tests/fixtures/source_snapshots mirror the STRUCTURE of the real
NAPCO / Infatrac / Verizon exports; every identifier in them is SYNTHETIC.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.canonical import CommunicationsAsset, OperatorDecision
from app.models.device import Device
from app.models.e911_change_log import E911ChangeLog
from app.models.line import Line
from app.models.portfolio_registry import PortfolioBuilding, PortfolioDeviceMapping
from app.models.sim import Sim
from app.models.site import Site
from app.models.source_snapshot import SourceSnapshot, SourceSnapshotRecord
from app.services.canonical import vocab as V
from app.services.source_snapshots import adapters as A
from app.services.source_snapshots import attribution as AT
from app.services.source_snapshots import importer, reader
from app.services.source_snapshots import status as ST
from tests import _customer_db  # noqa: F401  (JSONB -> JSON shim for SQLite)

RH = "restoration-hardware"
OTHER = "other-tenant"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "source_snapshots")
NAPCO_FILE = os.path.join(FIX, "Radiolist-20260901120000-synthetic.csv")
TMO_FILE = os.path.join(FIX, "tmobile_infatrac_synthetic.csv")
VZ_FILE = os.path.join(FIX, "verizon_inventory_synthetic.csv")
RP_FILE = os.path.join(FIX, "redpocket_synthetic.csv")

WATCHED = [Device, Line, Sim, Site, PortfolioBuilding, PortfolioDeviceMapping,
           CommunicationsAsset, OperatorDecision, E911ChangeLog]
TABLES = [m.__table__ for m in WATCHED + [SourceSnapshot, SourceSnapshotRecord]]


async def make_db():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                              connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
    S = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    async with S() as db:
        db.add_all([
            Site(site_id="S-1", tenant_id=RH, site_name="RH Chicago #147", customer_name="RH",
                 status="active", e911_status="pending"),
            Device(device_id="RH-D6", tenant_id=RH, site_id="S-1", status="active",
                   starlink_id="99000006"),
            Line(line_id="RH-L6", tenant_id=RH, site_id="S-1", provider="telnyx",
                 did="2025550606", status="active"),
            Device(device_id="OT-D5", tenant_id=OTHER, status="active", starlink_id="99000005",
                   iccid="8901000000000000077"),
        ])
        await db.commit()
    return S


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar()


async def plan(S, source, path, tenant=RH, **kw):
    async with S() as db:
        return await importer.plan_import(db, tenant, source, path, **kw)


def rec(p, key):
    return next(r for r in p["records"] if r["source_record_key"] == key)


# ── status interpretation ────────────────────────────────────────────

@pytest.mark.parametrize("source,raw,expected", [
    (ST.NAPCO, "Active", V.CURRENT), (ST.NAPCO, "Suspend", V.SUSPENDED),
    (ST.NAPCO, "Terminate", V.DECOMMISSIONED), (ST.NAPCO, "Pending Activation", V.UNKNOWN),
    (ST.T_MOBILE, "Active", V.CURRENT), (ST.T_MOBILE, "Deactivated", V.DECOMMISSIONED),
    (ST.T_MOBILE, "Hotlined", V.UNKNOWN), (ST.VERIZON, "active", V.CURRENT),
    (ST.VERIZON, "deactive", V.DECOMMISSIONED), (ST.VERIZON, "pre-active", V.UNKNOWN),
    (ST.VERIZON, "connected", V.UNKNOWN), (ST.RED_POCKET, "Active", V.CURRENT),
    (ST.RED_POCKET, "Expired", V.UNKNOWN),
])
def test_status_maps(source, raw, expected):
    lc, rule = ST.interpret(source, raw)
    assert lc == expected
    assert rule.startswith(ST.map_version(source))


@pytest.mark.parametrize("raw", ["", None, "   ", "ready", "inventory", "online", "OK",
                                 "provisioning", "unknown"])
def test_unknown_or_empty_status_is_never_current(raw):
    for source in ST.SOURCE_SYSTEMS:
        lc, rule = ST.interpret(source, raw)
        assert lc == V.UNKNOWN and "unmapped" in rule


# ── parsers ──────────────────────────────────────────────────────────

NAPCO_HEADERS = [
    "RadioNumber", "ICCID", "DealerId", "SubscriberName", "DealerCompany", "DealerEmail",
    "LastSignalReceived", "OnlineDate", "SIMStatus", "FirmwareVer", "DebounceTime",
    "PollingRate", "AutoEnrollCSTel", "AutoEnrollCSAcct", "PrimaryCSReceiver", "PrimaryCSAcct",
    "PrimaryCSReceiverType", "BackupCSReceiver", "BackupCSAcct", "BackupCSReceiverType",
    "DuplicateCSReceiver", "DuplicateCSAcct", "DuplicateCSReceiverType",
    "DuplicateBackupCSReceiver", "DuplicateBackupCSAcct", "DuplicateBackupCSReceiverType",
    "Plan", "GenTech"]
INFATRAC_HEADERS = [
    "Partner", "MSISDN", "Status", "Package", "Last CDR date", "Idle", "Unbilled Voice, min",
    "Daily Voice, min", "3-Day Voice, min", "7-Day Voice, min", "14-Day Voice, min",
    "30-Day Voice, min", "Label"]
VERIZON_HEADERS = [
    "Unnamed: 0", "Billing account name", "Billing account number", "Cost Center",
    "Mobile number", "Username", "Wireless ID", "Equipment Model", "Upgrade date", "Device ID",
    "SIM ID", "Service status", "Suspended date"]


def test_actual_napco_header_set_parses():
    cmap = A.NAPCO_ADAPTER.column_map(NAPCO_HEADERS)
    assert A.NAPCO_ADAPTER.accepts(NAPCO_HEADERS)
    assert {"napco_radio", "iccid", "status", "activity", "label"} <= set(cmap)
    assert cmap["status"] == NAPCO_HEADERS.index("SIMStatus")
    # dealer + central-station contact / account columns are never mapped
    mapped = {NAPCO_HEADERS[i] for i in cmap.values()}
    assert not mapped & {"DealerId", "DealerEmail", "DealerCompany", "AutoEnrollCSTel",
                         "AutoEnrollCSAcct", "PrimaryCSAcct", "BackupCSAcct"}


def test_actual_infatrac_header_set_parses():
    cmap = A.TMOBILE_ADAPTER.column_map(INFATRAC_HEADERS)
    assert A.TMOBILE_ADAPTER.accepts(INFATRAC_HEADERS)
    assert len(cmap) == 13                       # every actual column is recognised
    assert cmap["msisdn"] == 1 and cmap["status"] == 2 and cmap["activity"] == 4
    assert cmap["label"] == 12


def test_header_whitespace_is_normalised_for_matching_only():
    padded = ["  %s " % h for h in INFATRAC_HEADERS]
    assert A.TMOBILE_ADAPTER.column_map(padded) == A.TMOBILE_ADAPTER.column_map(INFATRAC_HEADERS)
    padded_v = [" %s  " % h for h in VERIZON_HEADERS]
    assert A.VERIZON_ADAPTER.column_map(padded_v) == A.VERIZON_ADAPTER.column_map(VERIZON_HEADERS)


def test_actual_verizon_header_set_parses_and_ignores_index_and_private_columns():
    cmap = A.VERIZON_ADAPTER.column_map(VERIZON_HEADERS)
    assert A.VERIZON_ADAPTER.accepts(VERIZON_HEADERS)
    assert cmap == {"label": 3, "msisdn": 4, "model": 7, "upgrade_date": 8, "imei": 9,
                    "iccid": 10, "status": 11, "suspended_date": 12}
    mapped = {VERIZON_HEADERS[i] for i in cmap.values()}
    assert not mapped & {"Unnamed: 0", "Billing account name", "Billing account number",
                         "Username", "Wireless ID"}


@pytest.mark.parametrize("fixture,owner", [
    (NAPCO_FILE, ST.NAPCO), (TMO_FILE, ST.T_MOBILE), (VZ_FILE, ST.VERIZON),
])
def test_cross_source_header_rejection(fixture, owner):
    for source, adapter in A.ADAPTERS.items():
        if source == owner:
            reader.read_table(fixture, adapter.accepts)
        else:
            with pytest.raises(reader.ReadError):
                reader.read_table(fixture, adapter.accepts)


def test_actual_header_sets_are_accepted_only_by_their_own_adapter():
    for headers, owner in ((NAPCO_HEADERS, ST.NAPCO), (INFATRAC_HEADERS, ST.T_MOBILE),
                           (VERIZON_HEADERS, ST.VERIZON)):
        assert [s for s, a in A.ADAPTERS.items() if a.accepts(headers)] == [owner]


@pytest.mark.parametrize("kind,raw,value,issue", [
    ("msisdn", "(202) 555-0101", "2025550101", None),
    ("msisdn", "555-0101", None, "MSISDN_INVALID"),
    ("imei", "3.59E+14", None, "IMEI_MANGLED"),
    ("imei", "3590000", None, "IMEI_INVALID"),
    ("imei", "A0000000000202", "A0000000000202", "IMEI_NONSTANDARD_MEID"),
    ("iccid", "8901000000000000011", "8901000000000000011", None),
    ("iccid", "A1B2C3D4E5F6A7B8C9D0", "A1B2C3D4E5F6A7B8C9D0", "ICCID_NONSTANDARD"),
    ("iccid", "123", None, "ICCID_INVALID"),
    ("napco_radio", "-", None, None),
])
def test_identifier_validation_never_repairs(kind, raw, value, issue):
    assert A.validate_identifier(kind, raw) == (value, issue)


def test_napco_plan_parses_interprets_and_attributes():
    async def go():
        S = await make_db()
        p = await plan(S, ST.NAPCO, NAPCO_FILE)
        # the RadioList file-name timestamp has no established timezone: it is a
        # recorded candidate only, never the effective time
        assert p["source_effective_at"] is None
        assert p["effective_at_basis"] == importer.EFFECTIVE_UNDATED
        assert p["summary"]["filename_timestamp_candidate"] == "2026-09-01T12:00:00"
        assert p["summary"]["filename_timezone_established"] is False
        assert (p["row_count_total"], p["row_count_invalid"]) == (10, 1)
        keys = {r["source_record_key"] for r in p["records"]}
        assert keys == {"99000001", "99000002", "99000006", "99000008", "99000009"}
        assert rec(p, "99000001")["attribution_basis"] == "LABEL:BRAND_PHRASE"
        assert rec(p, "99000001")["attribution_confidence"] == AT.MEDIUM
        assert rec(p, "99000002")["attribution_basis"] == "LABEL:STORE_CODE"
        assert rec(p, "99000006")["attribution_basis"] == "IDENTIFIER_MATCH:EQUIPMENT"
        assert rec(p, "99000006")["attribution_confidence"] == AT.HIGH
        # raw status is preserved beside the interpretation
        r8 = rec(p, "99000008")
        assert (r8["source_status_raw"], r8["lifecycle_interpretation"]) == \
            ("Pending Activation", V.UNKNOWN)
        assert rec(p, "99000001")["lifecycle_interpretation"] == V.CURRENT
        assert rec(p, "99000002")["lifecycle_interpretation"] == V.SUSPENDED
        r9 = rec(p, "99000009")
        assert r9["lifecycle_interpretation"] == V.DECOMMISSIONED
        assert r9["attributes"]["identifier_issues"] == ["ICCID_NONSTANDARD"]
        assert rec(p, "99000001")["activity_at"] is not None
        assert rec(p, "99000006")["activity_at"] is None
        amb = {a["reason"] for a in p["summary"]["ambiguous"]}
        assert amb == {"LABEL:SHORT_TOKEN_ONLY", "LABEL_VS_OTHER_TENANT_IDENTIFIER"}
        assert p["summary"]["verdicts"]["EXCLUDED"] == 2
    asyncio.run(go())


# ── effective-time precedence ────────────────────────────────────────

def test_operator_effective_at_overrides_a_filename_timestamp():
    async def go():
        S = await make_db()
        op = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)
        p = await plan(S, ST.NAPCO, NAPCO_FILE, effective_at=op)
        assert (p["source_effective_at"], p["effective_at_basis"]) == \
            (op, importer.EFFECTIVE_OPERATOR)
        assert p["summary"]["filename_timestamp_candidate"] == "2026-09-01T12:00:00"
    asyncio.run(go())


def test_effective_time_precedence_rules():
    import dataclasses
    name = "Radiolist-20260901120000.xlsx"
    op = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)
    # 1 operator wins
    assert importer.resolve_effective_at(A.NAPCO_ADAPTER, name, op)[:2] == \
        (op, importer.EFFECTIVE_OPERATOR)
    # 3 a file-name timestamp is used only when its timezone is established
    assert importer.resolve_effective_at(A.NAPCO_ADAPTER, name)[:2] == \
        (None, importer.EFFECTIVE_UNDATED)
    established = dataclasses.replace(A.NAPCO_ADAPTER, filename_timezone_established=True)
    eff, basis, _c = importer.resolve_effective_at(established, name)
    assert (eff, basis) == (datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
                            importer.EFFECTIVE_FILENAME)
    # 4 otherwise UNDATED
    assert importer.resolve_effective_at(A.TMOBILE_ADAPTER, "infatrac.csv") == \
        (None, importer.EFFECTIVE_UNDATED, None)


def test_undated_snapshot_can_be_stored_but_is_never_fresh():
    async def go():
        S = await make_db()
        p = await plan(S, ST.NAPCO, NAPCO_FILE)
        async with S() as db:
            sid, created = await importer.apply_import(db, p, imported_by="op")
            snap = (await db.execute(select(SourceSnapshot).where(
                SourceSnapshot.id == sid))).scalar_one()
        assert created and snap.effective_at_basis == importer.EFFECTIVE_UNDATED
        assert importer.freshness(snap) == importer.UNDATED
    asyncio.run(go())


def test_napco_attributes_are_allow_listed_and_private():
    async def go():
        S = await make_db()
        p = await plan(S, ST.NAPCO, NAPCO_FILE)
        blob = json.dumps(p["records"], default=str)
        for secret in ("5550000000", "dealer@example.com", "CSACCT", "D-0000",
                       "Synthetic Dealer"):
            assert secret not in blob
        a = rec(p, "99000001")["attributes"]
        assert a["primary_cs_configured"] is True and a["backup_cs_configured"] is False
        assert rec(p, "99000009")["attributes"]["primary_cs_configured"] is False
        assert set(a) <= {"online_date", "firmware", "debounce", "polling", "plan", "gen_tech",
                          "primary_cs_type", "backup_cs_type", "primary_cs_configured",
                          "backup_cs_configured", "identifier_issues"}
    asyncio.run(go())


def test_xlsx_sheet_selection(tmp_path):
    import csv

    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Summary"
    wb.active.append(["Report", "generated", "today"])
    ws = wb.create_sheet("RadioList")
    with open(NAPCO_FILE, newline="") as fh:
        for row in csv.reader(fh):
            ws.append(row)
    path = str(tmp_path / "Radiolist-20260902080000.xlsx")
    wb.save(path)

    async def go():
        S = await make_db()
        p = await plan(S, ST.NAPCO, path)
        assert p["summary"]["sheet"] == "RadioList"
        assert p["row_count_total"] == 10 and p["row_count_attributed"] == 5
    asyncio.run(go())


def test_infatrac_plan():
    async def go():
        S = await make_db()
        p = await plan(S, ST.T_MOBILE, TMO_FILE)
        assert p["parser_version"] == "tmobile_infatrac.v2"
        assert len(p["summary"]["recognised_fields"]) == 13
        keys = {r["source_record_key"]: r for r in p["records"]}
        assert set(keys) == {"2025550701", "2025550702", "2025550704", "2025550606",
                             "2025550705"}                      # 703 is another customer
        lc = {k: r["lifecycle_interpretation"] for k, r in keys.items()}
        assert lc == {"2025550701": V.CURRENT, "2025550702": V.SUSPENDED,
                      "2025550704": V.DECOMMISSIONED, "2025550606": V.CURRENT,
                      "2025550705": V.UNKNOWN}                  # "Porting" is unmapped
        assert keys["2025550705"]["source_status_raw"] == "Porting"
        assert keys["2025550606"]["attribution_basis"] == "IDENTIFIER_MATCH:PHONE"
        assert keys["2025550701"]["activity_at"] == datetime(2026, 9, 28, 14, 5,
                                                             tzinfo=timezone.utc)
        a = keys["2025550701"]["attributes"]
        assert (a["package"], a["idle"], a["voice_30day_min"], a["partner"]) == \
            ("IoT Voice 500", "No", "9", "Fictional Partner LLC")
    asyncio.run(go())


def test_infatrac_label_never_assigns_a_service_type():
    async def go():
        S = await make_db()
        p = await plan(S, ST.T_MOBILE, TMO_FILE)
        for r in p["records"]:
            assert not any("service" in k or "classif" in k for k in r)
            assert not any("service" in k or "classif" in k or "type" == k
                           for k in r["attributes"])
            assert r["identifier_type"] == A.MSISDN
        r1 = next(r for r in p["records"] if r["source_record_key"] == "2025550701")
        # "Elevator 1" in the label is location / attribution evidence only
        assert r1["location_hint"] == "Restoration Hardware #147 Elevator 1"
        assert "Elevator" not in json.dumps(r1["attributes"])
        assert r1["lifecycle_interpretation"] == V.CURRENT
    asyncio.run(go())


def test_verizon_plan_drops_private_and_index_columns():
    async def go():
        S = await make_db()
        p = await plan(S, ST.VERIZON, VZ_FILE)
        assert p["parser_version"] == "verizon_inventory.v2"
        lc = {r["source_record_key"]: r["lifecycle_interpretation"] for r in p["records"]}
        assert lc == {"2025550801": V.CURRENT, "2025550802": V.CURRENT,
                      "2025550803": V.SUSPENDED, "2025550804": V.UNKNOWN}
        by = {r["source_record_key"]: r for r in p["records"]}
        assert by["2025550801"]["imei"] == "359000000000201"
        assert by["2025550801"]["iccid"] == "8901000000000000201"
        assert by["2025550802"]["imei"] == "A0000000000202"
        assert by["2025550802"]["attributes"]["identifier_issues"] == ["IMEI_NONSTANDARD_MEID"]
        assert by["2025550803"]["attributes"]["suspended_date"] == "2026-08-15"
        assert by["2025550801"]["attributes"]["model"] == "LM150"
        assert by["2025550801"]["location_hint"] == "Restoration Hardware Dallas #168"
        blob = json.dumps(p["records"], default=str)
        for private in ("BAN-SYNTH", "Pat Example", "Sam Placeholder", "WID-SYNTH",
                        "Fictional Billing Co"):
            assert private not in blob
        for r in p["records"]:
            assert set(r["attributes"]) <= {"model", "upgrade_date", "suspended_date",
                                            "identifier_issues"}
        assert p["effective_at_basis"] == importer.EFFECTIVE_UNDATED
    asyncio.run(go())


def test_verizon_private_columns_are_never_persisted():
    async def go():
        S = await make_db()
        p = await plan(S, ST.VERIZON, VZ_FILE)
        async with S() as db:
            await importer.apply_import(db, p, imported_by="op")
            rows = (await db.execute(select(SourceSnapshotRecord))).scalars().all()
            snap = (await db.execute(select(SourceSnapshot))).scalar_one()
        stored = json.dumps([{c.name: getattr(r, c.name) for c in r.__table__.columns}
                             for r in rows], default=str) + (snap.summary or "")
        for private in ("BAN-SYNTH", "Pat Example", "Sam Placeholder", "Lee Sample",
                        "Kim Dummy", "WID-SYNTH", "Fictional Billing Co"):
            assert private not in stored
    asyncio.run(go())


def test_fixtures_and_tests_contain_only_synthetic_identifiers():
    import re
    allowed = ("990000", "8901000000000000", "359000", "202555", "1202555", "555000",
               "000000", "2024", "2025", "2026", "2027")
    paths = [os.path.join(FIX, f) for f in os.listdir(FIX)] + [__file__]
    for path in paths:
        text = open(path, encoding="utf-8").read()
        for run in re.findall(r"\d{7,}", text):
            assert run.startswith(allowed), (os.path.basename(path), run)


def test_red_pocket_contract_is_provisional():
    async def go():
        S = await make_db()
        p = await plan(S, ST.RED_POCKET, RP_FILE,
                       effective_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
        assert p["summary"]["provisional_adapter"] is True
        assert p["parser_version"].endswith("provisional")
        assert p["effective_at_basis"] == importer.EFFECTIVE_OPERATOR
        lc = sorted(r["lifecycle_interpretation"] for r in p["records"])
        assert lc == [V.CURRENT, V.UNKNOWN]                                   # Expired
    asyncio.run(go())


# ── tenant attribution ───────────────────────────────────────────────

def _ix(**owners):
    ix = AT.IdentifierIndex()
    for tenant, values in owners.items():
        for v in values:
            ix.add(tenant.replace("_", "-"), v, phone=len(v) == 10)
    return ix


def test_identifier_match_is_high_confidence():
    ix = _ix(restoration_hardware=["2025550101"])
    out = AT.attribute(RH, {"msisdn": "2025550101"}, ["Some Label"], ix)
    assert (out["verdict"], out["confidence"]) == (AT.ATTRIBUTED, AT.HIGH)


def test_identifier_held_by_two_tenants_is_ambiguous():
    ix = _ix(restoration_hardware=["2025550101"], other_tenant=["2025550101"])
    assert AT.attribute(RH, {"msisdn": "2025550101"}, [], ix)["verdict"] == AT.AMBIGUOUS


def test_other_tenants_identifier_is_never_attributed_even_with_rh_label():
    ix = _ix(other_tenant=["99000005"])
    out = AT.attribute(RH, {"napco_radio": "99000005"}, ["Restoration Hardware"], ix)
    assert out["verdict"] == AT.AMBIGUOUS
    out = AT.attribute(RH, {"napco_radio": "99000005"}, ["Other Co"], ix)
    assert out["verdict"] == AT.EXCLUDED


@pytest.mark.parametrize("label,verdict", [
    ("Restoration Hardware Memphis", AT.ATTRIBUTED),
    ("RH #147", AT.ATTRIBUTED),
    ("RH Houston #130", AT.ATTRIBUTED),
    ("RH #2", AT.AMBIGUOUS),
    ("RH-506", AT.ATTRIBUTED),
    ("RH Warehouse", AT.AMBIGUOUS),
    ("RH", AT.AMBIGUOUS),
    ("Rhodes Plumbing", AT.EXCLUDED),
    ("Thrive Fitness", AT.EXCLUDED),
    ("RH 5th Avenue Realty", AT.AMBIGUOUS),
])
def test_label_rule_requires_specificity(label, verdict):
    assert AT.attribute(RH, {"msisdn": "2025550999"}, [label], AT.IdentifierIndex())["verdict"] \
        == verdict


def test_tenant_without_profile_uses_identifiers_only():
    out = AT.attribute("some-other-customer", {"msisdn": "2025550999"},
                       ["Restoration Hardware"], AT.IdentifierIndex())
    assert out["verdict"] == AT.EXCLUDED


def test_other_tenants_rows_are_never_stored():
    async def go():
        S = await make_db()
        p = await plan(S, ST.NAPCO, NAPCO_FILE)
        assert "99000005" not in {r["source_record_key"] for r in p["records"]}
        assert "99000004" not in {r["source_record_key"] for r in p["records"]}
        async with S() as db:
            await importer.apply_import(db, p, imported_by="test")
            stored = (await db.execute(select(SourceSnapshotRecord.source_record_key))).scalars().all()
        assert set(stored) == {r["source_record_key"] for r in p["records"]}
    asyncio.run(go())


# ── apply: immutable, deduplicated, no side effects ──────────────────

def test_apply_is_immutable_and_sha_deduplicated(tmp_path):
    async def go():
        S = await make_db()
        p = await plan(S, ST.NAPCO, NAPCO_FILE)
        assert p["duplicate_of"] is None
        async with S() as db:
            sid, created = await importer.apply_import(db, p, imported_by="op@example.com")
        assert created
        again = await plan(S, ST.NAPCO, NAPCO_FILE)
        assert again["duplicate_of"] == sid
        async with S() as db:
            sid2, created2 = await importer.apply_import(db, again, imported_by="op")
            assert (sid2, created2) == (sid, False)
            assert await count(db, SourceSnapshot) == 1
            assert await count(db, SourceSnapshotRecord) == 5
            snap = (await db.execute(select(SourceSnapshot))).scalar_one()
            assert (snap.row_count_total, snap.row_count_attributed, snap.row_count_ambiguous,
                    snap.row_count_invalid) == (10, 5, 2, 1)
            assert snap.file_sha256 == importer.file_sha256(NAPCO_FILE)
            assert snap.parser_version == "napco_radiolist.v1"
            assert snap.status_map_version == "napco.simstatus.v1"
            assert snap.attribution_rule_version == "rh.attribution.v1"
            r = (await db.execute(select(SourceSnapshotRecord).where(
                SourceSnapshotRecord.source_record_key == "99000002"))).scalar_one()
            assert (r.source_status_raw, r.lifecycle_interpretation) == ("Suspend", V.SUSPENDED)
            assert r.interpretation_rule == "napco.simstatus.v1:suspend->SUSPENDED"
            assert len(r.row_hash) == 64
        # a newer export is a NEW snapshot; the old one is kept
        newer = tmp_path / "Radiolist-20260915120000.csv"
        text = open(NAPCO_FILE, encoding="utf-8").read().replace("Suspend", "Active")
        newer.write_text(text, encoding="utf-8")
        p2 = await plan(S, ST.NAPCO, str(newer))
        async with S() as db:
            sid3, _ = await importer.apply_import(db, p2, imported_by="op")
            assert await count(db, SourceSnapshot) == 2
            assert await count(db, SourceSnapshotRecord) == 10
            latest = await importer.latest_snapshot(db, RH, ST.NAPCO)
            assert latest.id == sid3
    asyncio.run(go())


def test_same_file_for_a_different_source_or_tenant_is_separate_evidence():
    async def go():
        S = await make_db()
        p = await plan(S, ST.NAPCO, NAPCO_FILE, tenant=OTHER)
        async with S() as db:
            await importer.apply_import(db, p, imported_by="op")
        p_rh = await plan(S, ST.NAPCO, NAPCO_FILE)
        assert p_rh["duplicate_of"] is None
    asyncio.run(go())


def test_import_writes_nothing_but_snapshot_tables():
    async def go():
        S = await make_db()

        async def state():
            async with S() as db:
                counts = [await count(db, m) for m in WATCHED]
                e911 = (await db.execute(select(Site.e911_status))).scalars().all()
                devs = (await db.execute(select(Device.device_id, Device.status,
                                                Device.last_heartbeat))).all()
                return counts, e911, devs
        before = await state()
        for source, path in ((ST.NAPCO, NAPCO_FILE), (ST.T_MOBILE, TMO_FILE),
                             (ST.VERIZON, VZ_FILE), (ST.RED_POCKET, RP_FILE)):
            p = await plan(S, source, path)
            async with S() as db:
                await importer.apply_import(db, p, imported_by="op")
        assert await state() == before
    asyncio.run(go())


def test_dry_run_plan_writes_nothing():
    async def go():
        S = await make_db()
        await plan(S, ST.NAPCO, NAPCO_FILE)
        async with S() as db:
            assert await count(db, SourceSnapshot) == 0
            assert await count(db, SourceSnapshotRecord) == 0
    asyncio.run(go())


# ── freshness (inventory certification, not monitoring) ──────────────

def test_freshness_uses_source_effective_time_not_import_time():
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    s = SimpleNamespace(source_effective_at=now - timedelta(days=6), imported_at=now)
    assert importer.freshness(s, now, 7) == importer.FRESH
    s.source_effective_at = now - timedelta(days=8)
    assert importer.freshness(s, now, 7) == importer.STALE
    s.source_effective_at = None
    assert importer.freshness(s, now, 7) == importer.UNDATED


def test_default_freshness_window_is_seven_days():
    from app.config import settings
    assert int(settings.SOURCE_SNAPSHOT_FRESHNESS_DAYS) == 7


# ── CLI rails ────────────────────────────────────────────────────────

def _args(**kw):
    base = dict(tenant=RH, source="NAPCO", file=None, effective_at=None, apply=False,
                imported_by=None, list=False, show=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_cli_refuses_a_file_inside_the_repository(monkeypatch, capsys):
    from scripts import source_snapshot_import as cli

    async def go():
        S = await make_db()
        monkeypatch.setattr("app.database.AsyncSessionLocal", S)
        return await cli.run(_args(file=NAPCO_FILE))
    assert asyncio.run(go()) == 3
    assert "OUTSIDE the repository" in capsys.readouterr().out


def test_cli_dry_run_apply_show_and_list(tmp_path, monkeypatch, capsys):
    from scripts import source_snapshot_import as cli
    path = str(tmp_path / os.path.basename(NAPCO_FILE))
    shutil.copy(NAPCO_FILE, path)

    async def go():
        S = await make_db()
        monkeypatch.setattr("app.database.AsyncSessionLocal", S)
        assert await cli.run(_args(file=path)) == 0
        async with S() as db:
            assert await count(db, SourceSnapshot) == 0
        assert await cli.run(_args(file=path, apply=True)) == 3          # needs --imported-by
        assert await cli.run(_args(file=path, apply=True, imported_by="op")) == 0
        async with S() as db:
            sid = (await db.execute(select(SourceSnapshot.id))).scalar_one()
        assert await cli.run(_args(show=sid)) == 0
        assert await cli.run(_args(list=True)) == 0
        assert await cli.run(_args(file=path, apply=True, imported_by="op")) == 0
        async with S() as db:
            assert await count(db, SourceSnapshot) == 1
    asyncio.run(go())
    out = capsys.readouterr().out
    assert "DRY-RUN: nothing was written" in out
    assert "APPLIED: stored snapshot" in out and "UNCHANGED: file already imported" in out
    assert "OK" in out
    # identifiers in the report are masked except telephone numbers
    assert "8901000000000000011" not in out


def test_cli_effective_at_requires_a_timezone():
    from scripts import source_snapshot_import as cli
    with pytest.raises(ValueError, match="timezone"):
        cli._parse_effective("2026-09-30T12:29:03")
    assert cli._parse_effective("2026-09-30T12:29:03-04:00") == \
        datetime(2026, 9, 30, 16, 29, 3, tzinfo=timezone.utc)
