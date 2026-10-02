"""Read-only registration-conversion audit: classification from evidence, never
from status strings; the audit itself never writes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests._customer_db  # noqa: F401  (JSONB -> JSON shim for SQLite)
from app import audit_registration_conversions as audit
from app.database import Base
from app.models.action_audit import ActionAudit
from app.models.audit_log_entry import AuditLogEntry
from app.models.device import Device
from app.models.e911_change_log import E911ChangeLog
from app.models.line import Line
from app.models.provisioning_queue import ProvisioningQueueItem
from app.models.registration import Registration
from app.models.registration_location import RegistrationLocation
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.telemetry_event import TelemetryEvent
from app.models.user import User

TABLES = [m.__table__ for m in (Registration, RegistrationLocation, Site, Line, Device, ServiceUnit,
                                TelemetryEvent, ProvisioningQueueItem, AuditLogEntry, ActionAudit,
                                E911ChangeLog, User)]
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def run(c):
    return asyncio.run(c)


async def _db():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                              connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
    return eng, async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)


async def _converted(s, n, *, updated=T0, status="Connected", onboarding="active"):
    reg = Registration(registration_id=f"REG-{n}", tenant_id="ops", status="internal_review",
                       resume_token_hash=f"h{n}", resume_token_expires_at=T0 + timedelta(days=30),
                       submitter_email=f"owner{n}@example.com", target_tenant_id="acme")
    s.add(reg)
    await s.flush()
    site = Site(site_id=f"acme-store-{n}", tenant_id="acme", site_name=f"Store {n}", customer_name="Acme", status=status,
                onboarding_status=onboarding, e911_street="1 Main St", e911_city="Tampa",
                e911_state="FL", e911_zip="33602", created_at=T0, updated_at=updated)
    s.add(site)
    await s.flush()
    s.add(RegistrationLocation(registration_id=reg.id, location_label=f"Store {n}",
                               materialized_site_id=site.id))
    s.add(ServiceUnit(tenant_id="acme", site_id=site.site_id, unit_id=f"{site.site_id}-U01",
                      unit_name="Elevator", unit_type="elevator_phone", status="pending_install"))
    await s.flush()
    return site


def test_classifies_planned_deployed_and_ambiguous():
    async def go():
        _, sm = await _db()
        async with sm() as s:
            await _converted(s, 1)                                        # A: untouched, nothing
            b = await _converted(s, 2)                                    # B: device beating + active
            s.add(Device(tenant_id="acme", site_id=b.site_id, device_id="D-2", status="active",
                         last_heartbeat=T0 + timedelta(days=3)))
            c = await _converted(s, 3, updated=T0 + timedelta(days=9))    # C: line, no telemetry
            s.add(Line(tenant_id="acme", site_id=c.site_id, line_id="L-3", provider="other", status="provisioning"))
            s.add(User(email="owner1@example.com", name="Owner", password_hash="x", role="User",
                       tenant_id="acme", is_active=False))
            await s.commit()
        async with sm() as s:
            evs = {e.registration_id: e for e in await audit.collect(s)}
        assert [evs[f"REG-{i}"].classification for i in (1, 2, 3)] == ["A", "B", "C"]
        a = evs["REG-1"]
        assert a.status == "Connected" and a.onboarding_status == "active"   # reported, not trusted
        assert a.service_unit_statuses == {"pending_install": 1}
        assert a.invite_issued and a.invite_role == "User" and a.invite_email_masked == "o***@example.com"
        assert evs["REG-2"].devices_with_heartbeat == 1
        assert evs["REG-3"].edited_after_conversion and "site edited after conversion" in evs["REG-3"].reasons
    run(go())


def test_status_strings_alone_never_make_a_site_deployed():
    ev = audit.SiteEvidence(registration_id="R", registration_status="active", tenant_id="t", site_pk=1,
                            site_id="s", site_name=None, address=None, created_at=None, updated_at=None,
                            edited_after_conversion=False, status="Connected", onboarding_status="active",
                            e911_status="validated", e911_confirmation_required=False,
                            address_source=None, devices_total=1, devices_active=1)
    cls, reasons = audit.classify(ev)
    assert cls == "C"           # an "active" device with no heartbeat/telemetry is not deployment proof


def test_audit_never_writes():
    async def go():
        eng, sm = await _db()
        async with sm() as s:
            await _converted(s, 1)
            await s.commit()
        writes = []

        @event.listens_for(eng.sync_engine, "before_cursor_execute")
        def _spy(conn, cursor, statement, *a):
            if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"}:
                writes.append(statement)
        async with sm() as s:
            await audit.collect(s)
            await s.rollback()
        assert writes == []
        async with sm() as s:
            assert (await s.execute(select(func.count()).select_from(Site))).scalar() == 1
    run(go())


def test_simulated_ping_telemetry_is_never_deployment_evidence():
    async def go():
        _, sm = await _db()
        async with sm() as s:
            site = await _converted(s, 4)
            # what POST /api/actions/ping writes on a never-installed site
            s.add(TelemetryEvent(event_id="EVT-1", site_id=site.site_id, tenant_id="acme", timestamp=T0,
                                 category="network", severity="info", message="Ping from Ops: OK"))
            s.add(Device(tenant_id="acme", site_id=site.site_id, device_id="D-4", status="active"))
            await s.commit()
        async with sm() as s:
            (ev,) = await audit.collect(s)
        assert (ev.telemetry_events, ev.simulated_action_events) == (0, 1)
        assert ev.classification == "C"          # not B: an operator click is not a device report
    run(go())


def test_email_masking():
    assert audit.mask_email("judy@rh.example") == "j***@rh.example"
    assert audit.mask_email(None) is None
