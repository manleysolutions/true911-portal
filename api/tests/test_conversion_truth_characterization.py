"""CT-1 / CT-2 regression: conversion creates a PLANNED customer portfolio, and the
self-service invite is a customer-plane role.

    ASSESSMENT ≠ DEPLOYMENT · CUSTOMER CREATED ≠ CONNECTED
    ADDRESS PROVIDED ≠ E911 VERIFIED · SERVICE REQUESTED ≠ INSTALLED
    PHONE PROVIDED ≠ VERIFIED CONNECTION · DEVICE REQUESTED ≠ DEVICE PRESENT

(This file previously pinned the old behaviour — Site.status "Connected",
onboarding "active", e911_status NULL — as a characterization awaiting CT-1.)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests._customer_db  # noqa: F401  (JSONB -> JSON shim for SQLite)
from app.database import Base
from app.models.acquisition import AcquisitionRecord
from app.models.action_audit import ActionAudit
from app.models.audit_log_entry import AuditLogEntry
from app.models.customer import Customer
from app.models.device import Device
from app.models.line import Line
from app.models.registration import Registration
from app.models.registration_location import RegistrationLocation
from app.models.registration_service_unit import RegistrationServiceUnit
from app.models.registration_status_event import RegistrationStatusEvent
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.subscription import Subscription
from app.models.telemetry_event import TelemetryEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.services import registration_activation as activation
from app.services import registration_conversion as conv
from app.services import site_lifecycle as lifecycle

TABLES = [m.__table__ for m in (
    Tenant, Customer, Site, ServiceUnit, Subscription, Registration, RegistrationLocation,
    RegistrationServiceUnit, RegistrationStatusEvent, AuditLogEntry, AcquisitionRecord, User,
    Line, Device, TelemetryEvent, ActionAudit)]
PERMS = json.loads((Path(__file__).resolve().parents[2] / "permissions.json").read_text())
PERMS = PERMS.get("permissions", PERMS)


def run(c):
    return asyncio.run(c)


async def _db():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                              connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
    return async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)


async def _registration(s):
    reg = Registration(registration_id="REG-CT1", tenant_id="ops", status="internal_review",
                       resume_token_hash="h", resume_token_expires_at=datetime.now(timezone.utc) + timedelta(days=9),
                       submitter_email="owner@portfolio.example", submitter_name="Owner",
                       customer_name="Portfolio Co")
    s.add(reg)
    await s.flush()
    loc = RegistrationLocation(registration_id=reg.id, location_label="Store 12", street="1 Main St",
                               city="Tampa", state="FL", zip="33602", poc_name="Facilities Lead",
                               poc_phone="555-0100", poc_email="fac@portfolio.example",
                               dispatchable_description="Elevator bank B, 2nd floor", access_notes="Loading dock")
    s.add(loc)
    await s.flush()
    s.add(RegistrationServiceUnit(registration_id=reg.id, registration_location_id=loc.id,
                                  unit_label="Elevator 1", unit_type="elevator_phone",
                                  phone_number_existing="8135550123", hardware_model_request="MS130",
                                  carrier_request="T-Mobile", quantity=2))
    s.add(AcquisitionRecord(record_ref="ACQ-CT1", kind="assessment", status="assessment_submitted",
                            entry_point="registration_wizard", email="owner@portfolio.example",
                            idempotency_key="reg-REG-CT1", registration_ref="REG-CT1",
                            notification_status="sent", notification_attempts=1))
    await s.commit()
    return reg


async def _convert(s, reg, *, dry_run=False):
    return await conv.convert_registration(
        s, reg, tenant_choice="create_new", existing_tenant_id=None, new_tenant_id="portfolio-co",
        new_tenant_name="Portfolio Co", customer_choice="create_new", existing_customer_id=None,
        create_subscription=False, dry_run=dry_run, actor_user_id=None, actor_email="ops@true911.example")


async def _converted_db():
    sm = await _db()
    async with sm() as s:
        reg = await _registration(s)
        await _convert(s, reg)
    return sm


# ── CT-1: the materialized site is planned ───────────────────────────
def test_conversion_creates_a_planned_site_never_an_operational_one():
    async def go():
        sm = await _converted_db()
        async with sm() as s:
            (site,) = (await s.execute(select(Site))).scalars().all()
        assert site.status == lifecycle.SITE_STATUS_PENDING_INSTALL != "Connected"
        assert site.onboarding_status == "pending"
        assert site.onboarding_status not in {"active", "complete", "completed", "operational", "live"}
        # address preserved as an unverified address on file
        assert (site.e911_street, site.e911_city, site.e911_state, site.e911_zip) == ("1 Main St", "Tampa", "FL", "33602")
        assert site.e911_status == "unverified" and site.e911_confirmation_required is True
        assert site.address_source == "registration"
        assert site.address_notes.startswith("Customer-provided location detail (not verified):")
        assert (site.poc_name, site.poc_phone) == ("Facilities Lead", "555-0100")
    run(go())


def test_requested_phone_and_hardware_never_become_lines_or_devices():
    async def go():
        sm = await _converted_db()
        async with sm() as s:
            assert (await s.execute(select(func.count()).select_from(Line))).scalar() == 0
            assert (await s.execute(select(func.count()).select_from(Device))).scalar() == 0
            (unit,) = (await s.execute(select(ServiceUnit))).scalars().all()
        assert unit.status == "pending_install"
        req = unit.meta["requested"]
        assert req["phone_number_existing"] == "8135550123" and req["hardware_model_request"] == "MS130"
        assert req["carrier_request"] == "T-Mobile" and req["quantity"] == 2 and req["source"] == "registration"
    run(go())


def test_acquisition_converted_commits_with_the_conversion_and_not_on_dry_run():
    async def go():
        sm = await _db()
        async with sm() as s:
            reg = await _registration(s)
            await _convert(s, reg, dry_run=True)
        async with sm() as s:
            assert (await s.execute(select(AcquisitionRecord.status))).scalar() == "assessment_submitted"
            assert (await s.execute(select(func.count()).select_from(Site))).scalar() == 0
            reg = (await s.execute(select(Registration))).scalars().first()
            await _convert(s, reg)
        async with sm() as s:
            assert (await s.execute(select(AcquisitionRecord.status))).scalar() == "converted"
    run(go())


def test_planned_site_is_pending_install_not_critical_in_the_assurance_engine():
    from app.services.assurance import engine
    from app.services.assurance.signals import AssuranceLabel, AssuranceSignals
    planned = AssuranceSignals(tenant_id="t", site_id="s", e911_address_present=True,
                               e911_status="unverified", e911_confirmation_required=True,
                               onboarding_status="pending")
    result = engine.compute_site_assurance(planned)
    assert result.label == AssuranceLabel.PENDING_INSTALL
    assert not any("E911" in c or "NO_ACTIVE_DEVICE" in c for c in result.reason_codes)


def test_e911_only_becomes_verified_through_the_official_evidence_path():
    from app.services.assurance.engine import _e911_verified
    base = dict(tenant_id="t", site_id="s", e911_address_present=True, onboarding_status="active")
    from app.services.assurance.signals import AssuranceSignals
    assert not _e911_verified(AssuranceSignals(e911_status="unverified", e911_confirmation_required=True, **base))
    # what verify_rh_e911 / record_verification_test do with provider evidence:
    assert _e911_verified(AssuranceSignals(e911_status="validated", e911_confirmation_required=False, **base))


def test_operator_promotion_path_exists_and_is_restricted_to_known_values():
    from pydantic import ValidationError
    from app.schemas.site import SiteUpdate
    assert SiteUpdate(onboarding_status="active").onboarding_status == "active"
    for bad in ("Connected", "live", "verified"):
        with pytest.raises(ValidationError):
            SiteUpdate(onboarding_status=bad)
    assert "onboarding_status" not in __import__("app.routers.sites", fromlist=["x"])._DATAENTRY_ALLOWED_FIELDS


# ── readers stay neutral for a planned site ───────────────────────────
def test_planned_site_readers_are_neutral():
    from app.services.customer import serialize
    assert lifecycle.is_planned_site("Pending Install") and not lifecycle.is_planned_site("Connected")
    assert "being set up" in serialize._STATUS_MESSAGES["Pending Install"].lower() \
        if hasattr(serialize, "_STATUS_MESSAGES") else True
    import inspect
    from app.routers import command
    from app.services import digest_engine
    assert '"pending" if is_planned_site(site.status)' in inspect.getsource(command)
    assert "not is_planned_site(s.status)" in inspect.getsource(digest_engine)


def _client(sm, user):
    from tests._customer_db import client_for
    from app.routers import actions
    return client_for([(actions.router, "/api")], sm, {"user": user})


def test_ping_and_reboot_never_simulate_equipment_on_a_planned_site():
    async def go():
        sm = await _converted_db()
        async with sm() as s:
            site = (await s.execute(select(Site))).scalars().first()
        admin = SimpleNamespace(role="Admin", tenant_id=site.tenant_id, email="ops@x", name="Ops", id=1,
                                is_active=True, is_platform_user=False)
        async with _client(sm, admin) as c:
            ping = await c.post("/api/actions/ping", json={"site_id": site.site_id})
            reboot = await c.post("/api/actions/reboot", json={"site_id": site.site_id})
        assert ping.status_code == 200 and ping.json()["success"] is False
        assert "No equipment is installed" in ping.json()["message"]
        assert reboot.status_code == 409
        async with sm() as s:
            assert (await s.execute(select(func.count()).select_from(TelemetryEvent))).scalar() == 0
            again = (await s.execute(select(Site))).scalars().first()
        assert again.status == "Pending Install" and again.last_checkin is None
    run(go())


# ── CT-2: the self-service invite is CUSTOMER_ADMIN, no INTERNAL_OPS ──
def test_self_service_invite_is_customer_admin_without_internal_ops():
    async def go():
        sm = await _converted_db()
        async with sm() as s:
            reg = (await s.execute(select(Registration))).scalars().first()
            outcome = await activation.issue_invite(s, reg, actor_user_id=None, actor_email="ops@x")
            await s.commit()
            user = (await s.execute(select(User))).scalars().first()
        assert outcome.action == "created"
        assert user.role == "CUSTOMER_ADMIN" and user.tenant_id == "portfolio-co" and not user.is_active
        assert "CUSTOMER_ADMIN" not in PERMS["INTERNAL_OPS"]
        assert "CUSTOMER_ADMIN" in PERMS["CUSTOMER_VIEW_DASHBOARD"]
    run(go())


def test_a_pending_legacy_user_invite_is_moved_to_customer_admin_but_accepted_users_are_untouched():
    async def go():
        sm = await _converted_db()
        async with sm() as s:
            reg = (await s.execute(select(Registration))).scalars().first()
            s.add(User(email="owner@portfolio.example", name="Owner", password_hash="x", role="User",
                       tenant_id="portfolio-co", is_active=False))
            await s.commit()
            await activation.issue_invite(s, reg, actor_user_id=None, actor_email="ops@x")
            await s.commit()
            assert (await s.execute(select(User.role))).scalar() == "CUSTOMER_ADMIN"
        sm2 = await _converted_db()
        async with sm2() as s:
            reg = (await s.execute(select(Registration))).scalars().first()
            s.add(User(email="owner@portfolio.example", name="Owner", password_hash="x", role="User",
                       tenant_id="portfolio-co", is_active=True))
            await s.commit()
            out = await activation.issue_invite(s, reg, actor_user_id=None, actor_email="ops@x")
            await s.commit()
            assert out.action == "skipped_active"
            assert (await s.execute(select(User.role))).scalar() == "User"   # user-management is out of scope
    run(go())
