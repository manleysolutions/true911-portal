"""Generic, hardware-agnostic device-health sync.

For every device (optionally scoped to a tenant / site), classify it, ask each
applicable vendor adapter for live status, persist the normalized enrichment to
the Device/SIM rows, archive the raw vendor payload, and write an audit log.

    # dry run — prints the plan, writes nothing (default)
    python -m app.sync_device_health

    # apply for real
    DRY_RUN=false python -m app.sync_device_health

    # scope to one tenant / site
    DRY_RUN=false DEVICE_HEALTH_TENANT=integrity-pm DEVICE_HEALTH_SITE=IPM-BELLE-TERRE \
        python -m app.sync_device_health

Idempotency / safety:
  * Only UPDATES existing Device/SIM health fields — never creates devices,
    SIMs, or service units, so it cannot duplicate them.
  * Each vendor adapter self-guards on missing credentials (returns
    MISSING_CREDENTIALS instead of raising), so a partially-configured fleet
    syncs what it can and logs the rest.
  * DRY_RUN defaults to true.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger("true911.sync_device_health")

# Opt-in operator debug: print the SAFE named Vola payload fields per device so
# the real lastUpdateTime format can be confirmed.  Console-only (this is a CLI)
# — never a customer surface.  Enable with DEVICE_HEALTH_DEBUG=true.
_DEBUG = os.environ.get("DEVICE_HEALTH_DEBUG", "").strip().lower() in ("1", "true", "yes")

# Map a T-Mobile subscriber status string to a True911 Sim.status value.
_SIM_STATUS_MAP = {
    "active": "active",
    "suspended": "suspended",
    "deactivated": "deactivated",
    "cancelled": "deactivated",
    "canceled": "deactivated",
    "inactive": "suspended",
}


def compute_device_updates(vendor_statuses, *, now):
    """Pure: given a device's VendorStatus list, return the field changes.

    Returns ``{"device": {...}, "sim": {...}}``.  No I/O — unit-testable.
    """
    from app.services.device_health.status import NormalizedStatus

    device: dict = {}
    sim: dict = {}
    for vs in vendor_statuses:
        if not vs.available:
            continue
        if vs.vendor == "vola":
            # Always record that we synced; only refresh the liveness channel
            # (vola_last_sync) when the device is actually ONLINE, so an OFFLINE
            # device is not kept "fresh" and correctly ages to Offline.
            if vs.normalized_status == NormalizedStatus.ONLINE:
                device["vola_last_sync"] = now
                device["network_status"] = "online"
            elif vs.normalized_status == NormalizedStatus.OFFLINE:
                device["network_status"] = "offline"
            if vs.firmware:
                device["firmware_version"] = vs.firmware
            if vs.static_ip:
                device["wan_ip"] = vs.static_ip
            # Surface the vendor's last heartbeat onto the Device when parsed.
            if vs.last_seen is not None:
                device["last_heartbeat"] = vs.last_seen
        elif vs.vendor == "tmobile":
            device["last_network_event"] = now
            if vs.sim_status:
                sim["status"] = _SIM_STATUS_MAP.get(vs.sim_status.lower().strip(),
                                                    sim.get("status"))
                sim["network_status"] = vs.sim_status
            if vs.static_ip:
                device["wan_ip"] = vs.static_ip
    # Drop a None status we may have set via .get fallback.
    if sim.get("status") is None:
        sim.pop("status", None)
    return {"device": device, "sim": sim}


def _device_identifiers(d):
    return {
        "serial": d.serial_number,
        "imei": d.imei,
        "iccid": d.iccid,
        "msisdn": d.msisdn,
    }


async def _probe_device(d):
    """Run every applicable vendor adapter for one device. Returns list[VendorStatus]."""
    from app.services.device_health.classifier import classify
    from app.services.device_health.adapters import get_status_adapter

    cls = classify(model=d.model, device_type=d.device_type,
                   hardware_model_id=d.hardware_model_id,
                   manufacturer=d.manufacturer, carrier=d.carrier)
    ids = _device_identifiers(d)
    out = []
    for vendor in cls.probe_vendors:
        adapter = get_status_adapter(vendor)
        try:
            vs = await adapter.probe(**ids)
        except Exception as exc:  # adapters shouldn't raise, but be safe
            from app.services.device_health.models import VendorStatus
            from app.services.device_health.reason_codes import ReasonCode
            from app.services.device_health.status import NormalizedStatus
            vs = VendorStatus(vendor=vendor, device_identifier=ids.get("serial") or "",
                              normalized_status=NormalizedStatus.UNKNOWN,
                              available=False, error=f"{type(exc).__name__}: {exc}",
                              reason_codes=[ReasonCode.VENDOR_API_UNAVAILABLE])
        out.append(vs)
    return out


async def run(*, dry_run: bool = True, tenant_id=None, site_id=None) -> dict:
    import uuid

    from sqlalchemy import distinct, select

    from app.database import AsyncSessionLocal
    from app.models.device import Device
    from app.models.sim import Sim
    from app.models.integration_payload import IntegrationPayload
    from app.services.audit_logger import log_audit

    now = _dt.datetime.now(_dt.timezone.utc)
    summary = {"devices": 0, "probed": 0, "updated": 0, "skipped_no_vendor": 0,
               "vendor_calls": [], "notes": []}

    async with AsyncSessionLocal() as db:
        q = select(Device)
        if tenant_id:
            q = q.where(Device.tenant_id == tenant_id)
        if site_id:
            q = q.where(Device.site_id == site_id)
        devices = (await db.execute(q)).scalars().all()
        summary["devices"] = len(devices)

        for d in devices:
            statuses = await _probe_device(d)
            if not statuses:
                summary["skipped_no_vendor"] += 1
                continue
            summary["probed"] += 1

            for vs in statuses:
                summary["vendor_calls"].append({
                    "device_id": d.device_id, "vendor": vs.vendor,
                    "available": vs.available,
                    "status": vs.normalized_status.value,
                    "reasons": [r.value for r in vs.reason_codes],
                    "error": vs.error,
                })
                print(f"  {d.device_id:24} {vs.vendor:9} "
                      f"available={vs.available} status={vs.normalized_status.value} "
                      f"last_seen={vs.last_seen.isoformat() if vs.last_seen else None} "
                      f"reasons={[r.value for r in vs.reason_codes]}"
                      + (f" err={vs.error}" if vs.error else ""))
                # Opt-in: dump the SAFE named Vola payload fields so an operator
                # can confirm the real lastUpdateTime format. Never prints the
                # whole payload and never reaches a customer surface.
                if _DEBUG and vs.vendor == "vola" and vs.raw_payload:
                    from app.services.device_health.adapters.vola import heartbeat_debug_fields
                    print(f"    [DEBUG vola fields] {heartbeat_debug_fields(vs.raw_payload)}")

            changes = compute_device_updates(statuses, now=now)
            dev_changes, sim_changes = changes["device"], changes["sim"]

            if dry_run:
                if dev_changes or sim_changes:
                    print(f"    would update device={dev_changes} sim={sim_changes}")
                continue

            # Apply device changes.
            applied = False
            for field, value in dev_changes.items():
                setattr(d, field, value)
                applied = True

            # Apply SIM changes (linked by device_id or iccid), tenant-scoped.
            if sim_changes:
                sim = (await db.execute(
                    select(Sim).where(Sim.tenant_id == d.tenant_id)
                    .where(Sim.device_id == d.device_id))).scalar_one_or_none()
                if sim is None and d.iccid:
                    sim = (await db.execute(
                        select(Sim).where(Sim.tenant_id == d.tenant_id)
                        .where(Sim.iccid == d.iccid))).scalar_one_or_none()
                if sim is not None:
                    for field, value in sim_changes.items():
                        setattr(sim, field, value)
                    sim.last_synced_at = now
                    applied = True

            # Archive raw vendor payloads (append-only audit trail).
            for vs in statuses:
                if vs.raw_payload:
                    db.add(IntegrationPayload(
                        payload_id=f"dh-{uuid.uuid4().hex[:12]}",
                        source=vs.vendor, direction="outbound",
                        body=vs.raw_payload, processed=True))

            if applied:
                summary["updated"] += 1
                await log_audit(
                    db, d.tenant_id, "device_health", "sync",
                    f"Device health sync for {d.device_id}",
                    actor="sync_device_health", target_type="device",
                    target_id=d.device_id, site_id=d.site_id, device_id=d.device_id,
                    detail={"device_changes": {k: str(v) for k, v in dev_changes.items()},
                            "sim_changes": sim_changes,
                            "vendors": [vs.vendor for vs in statuses]})

        if dry_run:
            await db.rollback()
            print("\nDRY RUN — no changes committed.")
        else:
            await db.commit()
            print("\nCommitted.")

    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    tenant_id = os.environ.get("DEVICE_HEALTH_TENANT") or None
    site_id = os.environ.get("DEVICE_HEALTH_SITE") or None

    print("=" * 60)
    print("Device Health Sync (hardware-agnostic)")
    print("=" * 60)
    print(f"  mode   : {'DRY RUN (no writes)' if dry_run else 'APPLY (writing)'}")
    print(f"  tenant : {tenant_id or '(all tenants)'}")
    print(f"  site   : {site_id or '(all sites)'}")
    print()
    try:
        summary = asyncio.run(run(dry_run=dry_run, tenant_id=tenant_id, site_id=site_id))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: sync aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for k in ("devices", "probed", "updated", "skipped_no_vendor"):
        print(f"  {k:18}: {summary[k]}")


if __name__ == "__main__":
    main()
