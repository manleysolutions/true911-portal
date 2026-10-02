"""Canonical model persistence (D-023): loader -> engine -> writer on a real
(in-memory SQLite) database, the operator-decision ledger, and the scripts'
safety rails.  SYNTHETIC identifiers only.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.canonical import (
    AssetLifecycleEvent,
    CanonicalEvidence,
    CommunicationsAsset,
    ConnectionAssetLink,
    LifeSafetyConnection,
    LifeSafetyService,
    OperatorDecision,
    ProjectionRun,
)
from app.models.device import Device
from app.models.e911_change_log import E911ChangeLog
from app.models.line import Line
from app.models.portfolio_registry import PortfolioBuilding, PortfolioDeviceMapping
from app.models.site import Site
from app.models.source_snapshot import SourceSnapshot, SourceSnapshotRecord
from app.services.canonical import decisions as D
from app.services.canonical import engine, loader, writer
from app.services.canonical import vocab as V
from tests import _customer_db as cdb

T = "tenant-test"
CANONICAL = [m.__table__ for m in (ProjectionRun, CommunicationsAsset, LifeSafetyService,
                                   LifeSafetyConnection, ConnectionAssetLink, AssetLifecycleEvent,
                                   CanonicalEvidence, OperatorDecision,
                                   SourceSnapshot, SourceSnapshotRecord)]
RECENT = datetime.now(timezone.utc) - timedelta(days=1)


async def make_db():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                              connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=cdb.TABLES + CANONICAL))
    return eng, async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)


async def seed(Session):
    async with Session() as db:
        db.add_all([
            PortfolioBuilding(id=1, tenant_id=T, canonical_name="RH Chicago", store_number="147",
                              status="active", address="1 Test St", city="Chicago", state="IL",
                              approved=True, approved_by="ops"),
            PortfolioBuilding(id=5, tenant_id=T, canonical_name="RH Jacksonville",
                              store_number="140", status="active", address="5 Test Way",
                              city="Jacksonville", state="FL", approved=True, approved_by="ops"),
            PortfolioBuilding(id=9, tenant_id=T, canonical_name="Unapproved Candidate",
                              status="active", approved=False),
            Site(site_id="S-147", tenant_id=T, site_name="RH Chicago #147", customer_name="RH",
                 status="active", e911_street="1 Test St", e911_city="Chicago", e911_state="IL",
                 e911_zip="60601", e911_status="pending"),
            Device(device_id="F1", tenant_id=T, site_id="S-147", status="active",
                   device_type="Fire Alarm Control Panel", model="StarLink", manufacturer="Napco",
                   starlink_id="NAP-0001", iccid="8901000000000000009",
                   last_heartbeat=RECENT),
            Device(device_id="E1", tenant_id=T, site_id="S-147", status="active",
                   device_type="elevator", model="LM150", msisdn="2025550101",
                   last_heartbeat=RECENT),
            # an already-imported carrier snapshot: recent activity on the
            # emergency-phone line (deployment evidence; "Active" alone is not)
            SourceSnapshot(id=1, tenant_id=T, source_system="T_MOBILE", source_label="infatrac",
                           file_sha256="1" * 64, original_basename="infatrac.csv", file_size=1,
                           parser_name="tmobile_infatrac", parser_version="tmobile_infatrac.v2",
                           status_map_version="tmobile.infatrac.v1",
                           attribution_rule_version="1", source_effective_at=RECENT,
                           effective_at_basis="OPERATOR", imported_at=RECENT, imported_by="test",
                           row_count_total=1, row_count_attributed=1, row_count_excluded=0,
                           row_count_ambiguous=0, row_count_invalid=0),
            SourceSnapshotRecord(snapshot_id=1, tenant_id=T, source_system="T_MOBILE",
                                 row_number=1, source_record_key="2025550102",
                                 identifier_type="MSISDN", normalized_identifier="2025550102",
                                 msisdn="2025550102", source_status_raw="Active",
                                 lifecycle_interpretation="CURRENT", interpretation_rule="t",
                                 activity_at=RECENT, attribution_basis="test",
                                 attribution_confidence="HIGH", row_hash="h1"),
            Line(line_id="L1", tenant_id=T, site_id="S-147", device_id="E1", provider="telnyx",
                 did="2025550101", status="active", line_type="Elevator"),
            PortfolioDeviceMapping(tenant_id=T, building_id=1, kind="true911_device",
                                   value="S-147", value_normalized="S147", source="test",
                                   active=True),
            # deterministic placement (exact registry identifier / telephone mappings)
            *[PortfolioDeviceMapping(tenant_id=T, building_id=1, kind=k, value=v,
                                     value_normalized=n, source="test", active=True)
              for k, v, n in (("napco_radio", "NAP-0001", "NAP0001"),
                              ("phone", "2025550101", "2025550101"),
                              ("phone", "2025550102", "2025550102"))],
        ])
        await db.commit()


def zrows(extra=()):
    base = [{"zoho_id": "Z1", "facility": "RH Chicago #147", "account": None, "parent": None,
             "msisdn": "2025550102", "connection_type": "Emergency Phone",
             "subscription_type": None, "activation": "Active", "starlink": None, "sim": None,
             "imei": None, "serial": None, "modified": "2026-09-01T00:00:00+00:00"}]
    return base + list(extra)


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar()


async def project(Session, **kw):
    async with Session() as db:
        snap = await loader.build_snapshot(db, T, zoho=kw.pop("zoho", "rows"),
                                           zoho_rows=kw.pop("rows", zrows()), **kw)
    return snap, engine.project(snap)


def test_loader_reads_only_approved_buildings_and_projects():
    async def go():
        _e, S = await make_db()
        await seed(S)
        snap, res = await project(S)
        assert [b["name"] for b in snap["buildings"]] == ["RH Chicago", "RH Jacksonville"]
        counted = sorted(s["service_key"] for s in res["services"] if s["counts"])
        assert counted == ["ELEV:tel:2025550101", "EPH:tel:2025550102", "FACP:radio:NAP0001"]
        assert res["portfolio"]["confirmed_required_connections"] == 4
    asyncio.run(go())


def test_apply_is_idempotent_and_never_deletes():
    async def go():
        _e, S = await make_db()
        await seed(S)
        _s, res = await project(S)
        async with S() as db:
            r1 = await writer.apply_projection(db, res, run_by="test")
        async with S() as db:
            first = [await count(db, m) for m in (CommunicationsAsset, LifeSafetyService,
                                                  LifeSafetyConnection, ConnectionAssetLink)]
        assert first[1] == 3 and first[2] == 4
        _s, res2 = await project(S)
        async with S() as db:
            r2 = await writer.apply_projection(db, res2, run_by="test")
        async with S() as db:
            second = [await count(db, m) for m in (CommunicationsAsset, LifeSafetyService,
                                                   LifeSafetyConnection, ConnectionAssetLink)]
            assert second == first
            assert await count(db, ProjectionRun) == 2 and r2 != r1
            ev = (await db.execute(select(func.count()).select_from(CanonicalEvidence).where(
                CanonicalEvidence.projection_run_id == r2))).scalar()
            assert ev > 0
            svc = (await db.execute(select(LifeSafetyService).where(
                LifeSafetyService.service_key == "FACP:radio:NAP0001"))).scalar_one()
            assert (svc.confidence, svc.lifecycle, svc.last_projection_run_id) == \
                (V.CONFIRMED, V.CURRENT, r2)
            sim = (await db.execute(select(CommunicationsAsset).where(
                CommunicationsAsset.asset_type == V.SIM_ICCID))).scalar_one()
            assert sim.display_value == "***0009"        # masked
    asyncio.run(go())


def test_service_that_stops_qualifying_is_kept_and_its_connections_stop_being_required():
    async def go():
        _e, S = await make_db()
        await seed(S)
        _s, res = await project(S)
        async with S() as db:
            await writer.apply_projection(db, res, run_by="test")
        _s, res2 = await project(S, rows=[])                 # the emergency phone row is gone
        async with S() as db:
            rid = await writer.apply_projection(db, res2, run_by="test")
        async with S() as db:
            eph = (await db.execute(select(LifeSafetyService).where(
                LifeSafetyService.service_key == "EPH:tel:2025550102"))).scalar_one()
            assert eph.last_projection_run_id != rid       # stale, not deleted
            c = (await db.execute(select(LifeSafetyConnection).where(
                LifeSafetyConnection.service_id == eph.id))).scalars().all()
            assert [x.requirement for x in c] == [V.NOT_REQUIRED]
    asyncio.run(go())


def test_degraded_projection_is_refused():
    async def go():
        _e, S = await make_db()
        await seed(S)
        _s, res = await project(S, zoho="skip")
        assert res["degraded"]
        async with S() as db:
            with pytest.raises(writer.DegradedProjectionError):
                await writer.apply_projection(db, res, run_by="test")
            assert await count(db, ProjectionRun) == 0
    asyncio.run(go())


def test_apply_never_touches_e911_registry_or_source_rows():
    async def go():
        _e, S = await make_db()
        await seed(S)

        async def fingerprint():
            async with S() as db:
                sites = [(s.site_id, s.e911_status, s.e911_street) for s in
                         (await db.execute(select(Site))).scalars().all()]
                return (sites, await count(db, Device), await count(db, Line),
                        await count(db, PortfolioBuilding), await count(db, PortfolioDeviceMapping),
                        await count(db, E911ChangeLog))
        before = await fingerprint()
        _s, res = await project(S)
        async with S() as db:
            await writer.apply_projection(db, res, run_by="test")
        assert await fingerprint() == before
        assert before[0][0][1] == "pending"                 # E911 still unverified
    asyncio.run(go())


# ── operator decision ledger ─────────────────────────────────────────

BLD = [{"id": 1, "name": "RH Chicago"}, {"id": 5, "name": "RH Jacksonville"}]


def _suspect(flag):
    return D.normalize_all([{"type": "BUILDING_IDENTITY_SUSPECT",
                             "subject": {"building": "RH Chicago"},
                             "new_state": {"suspect": flag}, "reason": "ops review"}], BLD)[0]


def test_decisions_dry_run_writes_nothing_then_apply_supersedes_without_destroying():
    async def go():
        _e, S = await make_db()
        async with S() as db:
            plan = await D.plan_and_record(db, T, _suspect(True), recorded_by="op", apply=False)
            assert plan[0]["action"] == "NEW" and await count(db, OperatorDecision) == 0
            await D.plan_and_record(db, T, _suspect(True), recorded_by="op", apply=True)
        async with S() as db:
            again = await D.plan_and_record(db, T, _suspect(True), recorded_by="op", apply=True)
            assert again[0]["action"] == "UNCHANGED" and await count(db, OperatorDecision) == 1
        async with S() as db:
            rev = await D.plan_and_record(db, T, _suspect(False), recorded_by="op2", apply=True)
            assert rev[0]["action"] == "SUPERSEDE"
            assert rev[0]["previous_state"] == {"suspect": True}
        async with S() as db:
            hist = await D.load_history(db, T)
            assert len(hist) == 2
            first, second = hist
            assert first["superseded_by_id"] == second["id"]
            assert first["new_state"] == {"suspect": True}          # preserved
            assert second["new_state"] == {"suspect": False}
            row = (await db.execute(select(OperatorDecision).where(
                OperatorDecision.id == second["id"]))).scalar_one()
            assert json.loads(row.previous_state) == {"suspect": True}
            assert (row.source, row.recorded_by) == (V.SRC_OPERATOR, "op2")
            active = await D.load_active(db, T)
            assert [a["id"] for a in active] == [second["id"]]
    asyncio.run(go())


def test_carrier_migration_decision_creates_one_lifecycle_event_across_runs():
    legacy = ["20255502%02d" % i for i in range(1, 7)]
    repl = ["20255503%02d" % i for i in range(1, 8)]
    rows = zrows([{"zoho_id": "J%s" % n, "facility": "RH Jacksonville", "account": None,
                   "parent": None, "msisdn": n, "connection_type": "Voice", "subscription_type": None,
                   "activation": "Active", "starlink": None, "sim": None, "imei": None,
                   "serial": None, "modified": None} for n in legacy + repl])

    async def go():
        _e, S = await make_db()
        await seed(S)
        decs, errs = D.normalize_all([{
            "type": "CARRIER_MIGRATION", "effective_date": "2026-06-01", "reason": "migration",
            "subject": {"building": "RH Jacksonville", "legacy_numbers": legacy,
                        "replacement_numbers": repl},
            "new_state": {"legacy_carrier": "Legacy MVNO", "replacement_carrier": "New Carrier"}}], BLD)
        assert not errs
        async with S() as db:
            await D.plan_and_record(db, T, decs, recorded_by="op", apply=True)
        for _ in range(2):
            _s, res = await project(S, rows=rows)
            async with S() as db:
                await writer.apply_projection(db, res, run_by="test")
        async with S() as db:
            ev = (await db.execute(select(AssetLifecycleEvent))).scalars().all()
            assert len(ev) == 1 and ev[0].operator_decision_id is not None
            old = (await db.execute(select(CommunicationsAsset).where(
                CommunicationsAsset.normalized_value.in_(legacy)))).scalars().all()
            assert len(old) == 6
            assert {(a.lifecycle, a.lifecycle_reason, a.lifecycle_event_id, a.carrier)
                    for a in old} == {(V.DECOMMISSIONED, V.REASON_CARRIER_MIGRATION, ev[0].id,
                                       "Legacy MVNO")}
            assert all(a.effective_to is not None for a in old)
            new = (await db.execute(select(CommunicationsAsset).where(
                CommunicationsAsset.normalized_value.in_(repl)))).scalars().all()
            assert {a.lifecycle for a in new} == {V.CURRENT}
    asyncio.run(go())


# ── scripts ──────────────────────────────────────────────────────────

def test_decision_file_inside_repository_is_refused(tmp_path):
    from scripts import canonical_operator_decisions as cod
    assert cod.inside_repo(os.path.join(cod.REPO_ROOT, "api", "decisions.json"))
    assert not cod.inside_repo(str(tmp_path / "decisions.json"))


def _fixture(tmp_path):
    from tests.test_canonical_engine import BUILDINGS
    snap = {"tenant_id": T, "buildings": BUILDINGS,
            "zoho_rows": [{"zoho_id": "Z1", "facility": "RH Memphis", "msisdn": "2025550400",
                           "connection_type": "Elevator", "activation": "Active"},
                          {"zoho_id": "Z2", "facility": "RH Cleveland", "msisdn": "2025550401",
                           "connection_type": "Elevator", "activation": "Active",
                           "parent": "Restoration Hardware MEMPHIS"}],
            "source_activity": [{"source": "T_MOBILE", "msisdn": n, "lifecycle": "CURRENT",
                                 "activity_at": RECENT.isoformat()}
                                for n in ("2025550400", "2025550401")]}
    p = tmp_path / "fixture.json"
    p.write_text(json.dumps(snap))
    d = tmp_path / "decisions.json"
    d.write_text(json.dumps({"tenant": T, "decisions": [
        {"type": "BUILDING_IDENTITY_SUSPECT", "subject": {"building": "RH Memphis"},
         "new_state": {"suspect": True}, "reason": "historically merged"},
        {"type": "SERVICE_CLASSIFICATION",
         "subject": {"building": "RH Memphis", "number": "2025550400"},
         "new_state": {"service_type": "ELEVATOR"}, "reason": "site visit"},
        {"type": "SERVICE_CLASSIFICATION",
         "subject": {"building": "RH Cleveland", "number": "2025550401"},
         "new_state": {"service_type": "ELEVATOR"}, "reason": "site visit"}]}))
    return str(p), str(d)


def _args(**kw):
    base = dict(tenant=T, zoho="skip", decisions_file=None, fixture=None, json=None, apply=False,
                confirm_tenant=None, run_by="test")
    base.update(kw)
    return SimpleNamespace(**base)


def test_backfill_dry_run_on_fixture(tmp_path, capsys):
    from scripts import canonical_service_backfill as bf
    fx, dec = _fixture(tmp_path)
    out_json = str(tmp_path / "out.json")
    code = asyncio.run(bf.run(_args(fixture=fx, decisions_file=dec, json=out_json)))
    out = capsys.readouterr().out
    assert code == 0
    assert "RH MEMPHIS RECONCILIATION" in out and "nothing was written" in out
    data = json.loads(open(out_json, encoding="utf-8").read())
    assert data["portfolio"]["confirmed_service_total"] == 2


def test_backfill_refuses_apply_on_fixture(tmp_path, capsys):
    from scripts import canonical_service_backfill as bf
    fx, _d = _fixture(tmp_path)
    assert asyncio.run(bf.run(_args(fixture=fx, apply=True))) == 3


# ── degraded projections are never persisted (no override) ───────────

def test_writer_has_no_degraded_override_and_rederives_degradation():
    import inspect
    assert "allow_degraded" not in inspect.signature(writer.apply_projection).parameters

    async def go():
        _e, S = await make_db()
        await seed(S)
        _s, res = await project(S)
        assert not res["degraded"]
        # a caller cannot launder a failed required source by flipping the flag
        res["sources"]["zoho"]["status"] = "unavailable: timeout"
        async with S() as db:
            with pytest.raises(writer.DegradedProjectionError):
                await writer.apply_projection(db, res, run_by="test")
            assert await count(db, ProjectionRun) == 0
    asyncio.run(go())


def test_cli_rejects_allow_degraded_flag(monkeypatch):
    from scripts import canonical_service_backfill as bf
    monkeypatch.setattr("sys.argv", ["canonical_service_backfill", "--allow-degraded"])
    with pytest.raises(SystemExit) as exc:
        bf.main()
    assert exc.value.code == 2                       # argparse: unrecognized argument


def test_degraded_dry_run_prints_reconciliation_and_exits_2(tmp_path, capsys):
    from scripts import canonical_service_backfill as bf
    fx, _d = _fixture(tmp_path)
    data = json.loads(open(fx, encoding="utf-8").read())
    data["sources"] = {"zoho": {"status": "unavailable: timeout", "required": True}}
    open(fx, "w", encoding="utf-8").write(json.dumps(data))
    code = asyncio.run(bf.run(_args(fixture=fx)))
    out = capsys.readouterr().out
    assert code == 2
    assert "DEGRADED" in out and "=== PER BUILDING ===" in out and "nothing was written" in out


def test_degraded_cli_apply_is_refused_and_writes_nothing(monkeypatch, capsys):
    from scripts import canonical_service_backfill as bf

    async def go():
        _e, S = await make_db()
        await seed(S)
        monkeypatch.setattr("app.database.AsyncSessionLocal", S)
        code = await bf.run(_args(zoho="skip", apply=True, confirm_tenant=T))
        async with S() as db:
            return code, await count(db, ProjectionRun), await count(db, LifeSafetyService)
    code, runs, services = asyncio.run(go())
    out = capsys.readouterr().out
    assert (code, runs, services) == (2, 0, 0)
    assert "refusing to apply" in out and "=== PER BUILDING ===" in out
