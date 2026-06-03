"""Read-only assembly of AssuranceSignals from existing tables.

NEVER writes. Tenant isolation is the first clause on every query — an
attacker-controlled ``site_id`` from another tenant returns ``None`` (not an
error, not cross-tenant data), matching the contract in
``services.health.signals_loader``.

Operational state is consumed from ``services.health`` (the existing, validated
normalizer). Lifecycle columns that may not exist on a given deployment
(``sites.lifecycle_status``) are read with ``getattr`` so the loader survives a
pre-migration / pre-PR#70 environment without crashing — absent lifecycle is
left ``None`` and the engine treats it conservatively.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.infra_test_result import InfraTestResult
from app.models.line import Line
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.verification_task import VerificationTask
from app.services.assurance.signals import (
    AssuranceSignals,
    DeviceSignal,
    LineSignal,
    ServiceUnitSignal,
    TestRecord,
)
from app.services.health import compute_device_state, load_signals_for_site

_INACTIVE_DEVICE_STATUSES = frozenset({
    "inactive", "decommissioned", "retired", "deactivated", "suspended", "cancelled", "canceled",
})


def _e911_present(site: Site, lines: list[Line]) -> bool:
    if (getattr(site, "e911_street", None) or "").strip():
        return True
    return any((getattr(ln, "e911_street", None) or "").strip() for ln in lines)


async def load_site_assurance_signals(
    db: AsyncSession, tenant_id: str, site_id: str
) -> Optional[AssuranceSignals]:
    """Assemble one site's AssuranceSignals. Returns ``None`` if the site does
    not exist in this tenant. Read-only."""
    site = (
        await db.execute(
            select(Site).where(Site.tenant_id == tenant_id, Site.site_id == site_id)
        )
    ).scalar_one_or_none()
    if site is None:
        return None

    # Operational state per device (reuse the validated health normalizer).
    health_by_device = await load_signals_for_site(db, tenant_id, site_id)
    devices = (
        await db.execute(
            select(Device).where(Device.tenant_id == tenant_id, Device.site_id == site_id)
        )
    ).scalars().all()

    device_signals = []
    active_device_ids: set[str] = set()
    for d in devices:
        hs = health_by_device.get(d.device_id)
        op = compute_device_state(hs).value if hs is not None else "provisioning"
        device_signals.append(DeviceSignal(
            device_id=d.device_id,
            operational_state=op,
            device_lifecycle=(d.status or "active"),
            model=d.model,
            device_type=d.device_type,
            carrier=getattr(d, "carrier", None),
            last_heartbeat_at=d.last_heartbeat,
            last_observed_at=hs.last_observed_at() if hs is not None else None,
        ))
        if (d.status or "active").strip().lower() not in _INACTIVE_DEVICE_STATUSES:
            active_device_ids.add(d.device_id)

    # Service units.
    units = (
        await db.execute(
            select(ServiceUnit).where(
                ServiceUnit.tenant_id == tenant_id, ServiceUnit.site_id == site_id
            )
        )
    ).scalars().all()
    unit_signals = tuple(
        ServiceUnitSignal(
            unit_id=u.unit_id, unit_name=u.unit_name, unit_type=u.unit_type,
            status=(u.status or "active"), device_id=u.device_id,
            has_active_device=bool(u.device_id and u.device_id in active_device_ids),
        )
        for u in units
    )

    # Lines.
    lines = (
        await db.execute(
            select(Line).where(Line.tenant_id == tenant_id, Line.site_id == site_id)
        )
    ).scalars().all()
    line_signals = tuple(
        LineSignal(line_id=ln.line_id, status=(ln.status or "active"), e911_status=ln.e911_status)
        for ln in lines
    )

    last_test = await _load_last_test(db, tenant_id, site_id)

    return AssuranceSignals(
        tenant_id=tenant_id,
        site_id=site_id,
        site_name=site.site_name,
        customer_name=site.customer_name,
        site_lifecycle_status=getattr(site, "lifecycle_status", None),  # defensive (pre-PR#70)
        onboarding_status=getattr(site, "onboarding_status", None),
        reconciliation_status=getattr(site, "reconciliation_status", None),
        e911_address_present=_e911_present(site, list(lines)),
        e911_status=getattr(site, "e911_status", None),
        e911_confirmation_required=bool(getattr(site, "e911_confirmation_required", False)),
        devices=tuple(device_signals),
        service_units=unit_signals,
        lines=line_signals,
        last_test=last_test,
    )


async def _load_last_test(
    db: AsyncSession, tenant_id: str, site_id: str
) -> Optional[TestRecord]:
    """Most recent life-safety-relevant test for the site.

    Source priority: ``verification_tasks`` first, then ``command_testing``
    (``infra_test_results``). The most recent pass/fail wins; on an exact tie,
    verification_tasks wins (collected first).
    """
    candidates: list[TestRecord] = []

    # verification_tasks (result "pass"/"fail", completed_at set).
    vt = (
        await db.execute(
            select(VerificationTask)
            .where(
                VerificationTask.tenant_id == tenant_id,
                VerificationTask.site_id == site_id,
                VerificationTask.result.in_(("pass", "fail")),
                VerificationTask.completed_at.is_not(None),
            )
            .order_by(VerificationTask.completed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if vt is not None and vt.completed_at is not None:
        candidates.append(TestRecord(at=vt.completed_at, result=vt.result, source="verification_tasks"))

    # infra_test_results (status "pass"/"fail", completed_at set).
    itr = (
        await db.execute(
            select(InfraTestResult)
            .where(
                InfraTestResult.tenant_id == tenant_id,
                InfraTestResult.site_id == site_id,
                InfraTestResult.status.in_(("pass", "fail")),
                InfraTestResult.completed_at.is_not(None),
            )
            .order_by(InfraTestResult.completed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if itr is not None and itr.completed_at is not None:
        candidates.append(TestRecord(at=itr.completed_at, result=itr.status, source="command_testing"))

    if not candidates:
        return None
    # Most recent wins; stable sort keeps verification_tasks ahead of command_testing on a tie.
    return max(candidates, key=lambda t: t.at)
