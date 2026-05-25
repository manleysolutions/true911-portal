"""Read-only signal loader — builds HealthSignals from existing tables.

Issues a small fixed number of bulk queries per call (no per-device
queries) so the cost is O(1) round-trips regardless of fleet size.
Every query is scoped by ``tenant_id`` — the single tenancy guarantee
of this module.

Never writes.  Never updates ``Device.last_heartbeat`` from
provider data — that would be a field-overloading bug per
``docs/HEALTH_NORMALIZER_MVP.md`` 'What is intentionally not done'.
Provider signals contribute to the COMPUTED state at read time;
the underlying column stays the source-of-truth for its own writer.

Fields read off Device:
  * device_id, site_id, status (lifecycle), heartbeat_interval
  * last_heartbeat                (CSAS edge channel)
  * network_status                (degradation indicator)
  * last_network_event            (Verizon poll channel)
  * vola_last_sync                (Inseego TR-069 channel)

External sources read:
  * MAX(call_records.started_at) per device  (Telnyx CDR channel)

Defensive getattr is used for ``last_network_event`` and
``vola_last_sync`` so an older deployment without those columns
(pre-migration 032) does not crash — the loader returns ``None`` on
that channel instead.
"""

from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord
from app.models.device import Device
from app.services.health.signals import HealthSignals


async def load_signals_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> Dict[str, HealthSignals]:
    """Return a ``{device_id: HealthSignals}`` map for every device in ``tenant_id``.

    Two queries total — one for devices, one aggregate for the most
    recent Telnyx CDR per device.  Returns an empty dict when the
    tenant has no devices.

    Tenant isolation is enforced by every ``where(... == tenant_id)``
    clause in this function.  Callers MUST NOT pass a tenant_id from
    anywhere other than the authenticated user's effective tenant
    (i.e. ``current_user.tenant_id`` post-impersonation).  This
    contract is identical to the one ``LLLMContext`` already enforces.
    """
    # 1) Load all devices for the tenant in one query.
    devices_q = select(Device).where(Device.tenant_id == tenant_id)
    devices = (await db.execute(devices_q)).scalars().all()
    if not devices:
        return {}

    device_ids = [d.device_id for d in devices]

    # 2) MAX(call_records.started_at) per device, scoped by tenant.
    #    Only call records that successfully matched a device on
    #    ingestion are counted — unmatched CDRs have device_id NULL
    #    and are correctly ignored.  The join key is the string
    #    device business-id, matching how Telnyx ingestion populates
    #    call_records.device_id.
    last_call_q = (
        select(
            CallRecord.device_id,
            func.max(CallRecord.started_at).label("last_call"),
        )
        .where(CallRecord.tenant_id == tenant_id)
        .where(CallRecord.device_id.in_(device_ids))
        .where(CallRecord.started_at.is_not(None))
        .group_by(CallRecord.device_id)
    )
    last_call_rows = (await db.execute(last_call_q)).all()
    last_call_by_device = {row.device_id: row.last_call for row in last_call_rows}

    # 3) Compose HealthSignals per device.  Defensive getattr for
    #    columns added in later migrations so the loader survives
    #    a partially-migrated environment.
    result: Dict[str, HealthSignals] = {}
    for d in devices:
        result[d.device_id] = HealthSignals(
            last_heartbeat_at=d.last_heartbeat,
            last_carrier_event_at=getattr(d, "last_network_event", None),
            last_call_event_at=last_call_by_device.get(d.device_id),
            last_vola_sync_at=getattr(d, "vola_last_sync", None),
            network_status=d.network_status,
            # MVP: signal_dbm and sip_status live on CommandTelemetry,
            # not Device.  Left None here and filled in a follow-up
            # commit when the soak validates the core algorithm.
            signal_dbm=None,
            sip_status=None,
            heartbeat_interval_seconds=d.heartbeat_interval,
            device_lifecycle=d.status or "active",
        )
    return result


async def load_signals_for_site(
    db: AsyncSession,
    tenant_id: str,
    site_id: str,
) -> Dict[str, HealthSignals]:
    """Same shape as :func:`load_signals_for_tenant`, scoped to one site.

    Used by the AI Health Summary's site scope.  Tenant isolation is
    the FIRST clause on every query so an attacker-controlled
    ``site_id`` belonging to another tenant simply returns an empty
    map (not an error, not cross-tenant data).
    """
    devices_q = (
        select(Device)
        .where(Device.tenant_id == tenant_id)
        .where(Device.site_id == site_id)
    )
    devices = (await db.execute(devices_q)).scalars().all()
    if not devices:
        return {}

    device_ids = [d.device_id for d in devices]

    last_call_q = (
        select(
            CallRecord.device_id,
            func.max(CallRecord.started_at).label("last_call"),
        )
        .where(CallRecord.tenant_id == tenant_id)
        .where(CallRecord.site_id == site_id)
        .where(CallRecord.device_id.in_(device_ids))
        .where(CallRecord.started_at.is_not(None))
        .group_by(CallRecord.device_id)
    )
    last_call_rows = (await db.execute(last_call_q)).all()
    last_call_by_device = {row.device_id: row.last_call for row in last_call_rows}

    result: Dict[str, HealthSignals] = {}
    for d in devices:
        result[d.device_id] = HealthSignals(
            last_heartbeat_at=d.last_heartbeat,
            last_carrier_event_at=getattr(d, "last_network_event", None),
            last_call_event_at=last_call_by_device.get(d.device_id),
            last_vola_sync_at=getattr(d, "vola_last_sync", None),
            network_status=d.network_status,
            signal_dbm=None,
            sip_status=None,
            heartbeat_interval_seconds=d.heartbeat_interval,
            device_lifecycle=d.status or "active",
        )
    return result
