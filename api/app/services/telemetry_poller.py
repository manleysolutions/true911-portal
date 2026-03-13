"""Telemetry poller — fetches latest device state from carrier APIs.

Phase 2 supports Verizon ThingSpace carrier polling.  Device-side telemetry
(from PR12 heartbeats, Inseego heartbeats) flows through the heartbeat
endpoint instead — see routers/heartbeat.py.

Telemetry source hierarchy (documented in PART 4 — Precedence Rule):
    1. Device heartbeat (PR12/Inseego) — primary for signal + online status
    2. Carrier API (Verizon/T-Mobile)   — supplements with SIM/account/usage
    Both write CommandTelemetry records; health scoring uses the latest.

Inseego: No API client exists.  FW3100 routers report telemetry via device
heartbeats (POST /api/heartbeat).  NOT polled here.

Flying Voice PR12: Device-side telemetry comes via heartbeats.  VolaCloud
(api/app/integrations/vola.py) could be used for polling in a future phase,
but no API keys are currently configured.

What Verizon actually provides (from device inventory records):
    - activation_status / connection_status  → maps to network_status
    - usage_data_mb                          → maps to data_usage_mb
    - last_seen_at                           → maps to last_network_event
    - sim_status                             → informational

What Verizon does NOT provide (honestly reported):
    - signal_dbm (no signal strength in inventory API)
    - roaming state
    - network_tech (LTE/5G)
    - real-time telemetry stream
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.sim import Sim
from app.services.carrier_adapter import (
    CarrierTelemetry,
    ingest_carrier_telemetry,
)
from app.services.verizon_thingspace import (
    VerizonThingSpaceError,
    get_verizon_client,
    normalize_verizon_device,
)

logger = logging.getLogger("true911.telemetry_poller")


def _map_vz_network_status(activation_status: str | None) -> str | None:
    """Map Verizon activation/connection status to a network_status value."""
    if not activation_status:
        return None
    s = activation_status.lower()
    if s in ("active", "connected", "activated"):
        return "connected"
    if s in ("suspended",):
        return "suspended"
    if s in ("deactivated", "deactive", "terminated", "disconnected"):
        return "disconnected"
    if s in ("ready", "preactive", "inventory"):
        return "not_registered"
    return None


async def poll_verizon_telemetry(
    db: AsyncSession,
    tenant_id: str,
    initiated_by: str,
    max_results: int = 500,
) -> dict:
    """Fetch Verizon inventory and push telemetry for tenant devices.

    Returns a summary dict with counts.
    """
    client = get_verizon_client()
    if not client.is_configured:
        return {
            "source": "verizon",
            "ok": False,
            "error": "Verizon ThingSpace not configured",
            "total_fetched": 0,
            "checked": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }

    # Fetch from Verizon
    try:
        raw_devices = await client.fetch_devices(display_count=max_results)
    except VerizonThingSpaceError as e:
        logger.warning("Verizon telemetry poll failed: %s", e)
        return {
            "source": "verizon",
            "ok": False,
            "error": str(e),
            "total_fetched": 0,
            "checked": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 1,
        }

    normalized = [normalize_verizon_device(d) for d in raw_devices]

    # Load tenant devices by ICCID for matching
    dev_result = await db.execute(
        select(Device).where(
            Device.tenant_id == tenant_id,
            Device.carrier == "verizon",
        )
    )
    tenant_devices = {
        d.iccid.lower(): d
        for d in dev_result.scalars().all()
        if d.iccid
    }

    checked = 0
    updated = 0
    skipped = 0
    errors = 0
    error_details = []

    for vz in normalized:
        iccid = vz.get("iccid")
        if not iccid or iccid.lower() not in tenant_devices:
            skipped += 1
            continue

        device = tenant_devices[iccid.lower()]
        checked += 1

        try:
            # Build CarrierTelemetry from Verizon data
            network_status = _map_vz_network_status(
                vz.get("activation_status") or vz.get("line_status")
            )

            telemetry = CarrierTelemetry(
                device_id=device.device_id,
                carrier="verizon",
                signal_dbm=None,  # Verizon inventory API does not provide signal
                network_status=network_status,
                roaming=None,     # Not available from inventory
                data_usage_mb=vz.get("usage_data_mb"),
                network_tech=None,  # Not available from inventory
            )

            await ingest_carrier_telemetry(db, tenant_id, telemetry)
            updated += 1
        except Exception as e:
            logger.exception("Error ingesting telemetry for device %s", device.device_id)
            errors += 1
            error_details.append(f"{device.device_id}: {e}")

    await db.commit()

    logger.info(
        "Verizon telemetry poll: tenant=%s fetched=%d checked=%d "
        "updated=%d skipped=%d errors=%d",
        tenant_id, len(normalized), checked, updated, skipped, errors,
    )

    return {
        "source": "verizon",
        "ok": errors == 0,
        "total_fetched": len(normalized),
        "checked": checked,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details[:10] if error_details else [],
        "fields_available": [
            "network_status (from activation_status)",
            "data_usage_mb (from usage field, if present)",
        ],
        "fields_not_available": [
            "signal_dbm (not in Verizon inventory API)",
            "roaming (not in Verizon inventory API)",
            "network_tech (not in Verizon inventory API)",
        ],
    }
