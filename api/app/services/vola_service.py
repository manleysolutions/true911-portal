"""VOLA / PR12 service layer.

Provides tenant-scoped VOLA client creation, device sync/import,
bind-to-site, and provisioning workflows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.vola import VolaClient, normalize_vola_device, extract_parameter_values
from app.models.device import Device
from app.models.event import Event
from app.models.provider import Provider

logger = logging.getLogger("true911.services.vola")


def _parse_csv(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def get_vola_client(
    *,
    provider: Provider | None = None,
) -> VolaClient:
    """Build a VolaClient from provider config_json or fall back to env vars.

    Phase 1 source of truth: provider.config_json overrides env vars.
    """
    base_url = settings.VOLA_BASE_URL
    email = settings.VOLA_EMAIL
    password = settings.VOLA_PASSWORD
    org_id = settings.VOLA_ORG_ID or None

    # Override from provider config_json if available
    if provider and provider.config_json:
        cfg = provider.config_json
        base_url = cfg.get("base_url", base_url)
        email = cfg.get("email", email)
        password = cfg.get("password", password)
        org_id = cfg.get("org_id", org_id)

    allowed_param = _parse_csv(settings.VOLA_ALLOWED_PARAM_PREFIXES) or None
    allowed_set = _parse_csv(settings.VOLA_ALLOWED_SET_PREFIXES) or None
    blocked_set = _parse_csv(settings.VOLA_BLOCKED_SET_PREFIXES) or None
    denylist = set(_parse_csv(settings.VOLA_DENYLIST_EXACT)) or None

    return VolaClient(
        base_url=base_url,
        email=email,
        password=password,
        org_id=org_id,
        allowed_param_prefixes=allowed_param,
        allowed_set_prefixes=allowed_set,
        blocked_set_prefixes=blocked_set,
        denylist_exact=denylist,
    )


async def find_vola_provider(
    db: AsyncSession, tenant_id: str
) -> Provider | None:
    """Find the first enabled VOLA provider for a tenant."""
    result = await db.execute(
        select(Provider).where(
            Provider.tenant_id == tenant_id,
            Provider.provider_type == "vola",
            Provider.enabled == True,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def get_tenant_vola_client(
    db: AsyncSession, tenant_id: str
) -> VolaClient:
    """Get a VolaClient for the given tenant, using provider record if available."""
    provider = await find_vola_provider(db, tenant_id)
    return get_vola_client(provider=provider)


async def sync_vola_devices(
    db: AsyncSession,
    tenant_id: str,
    vola_devices: list[dict[str, Any]],
    *,
    user_email: str = "system",
) -> dict[str, Any]:
    """Import/sync normalized VOLA devices into the devices table.

    Deduplicates by serial_number (device_sn) or mac_address.
    Returns {"imported": N, "updated": N, "skipped": N, "devices": [...]}.
    """
    imported = 0
    updated = 0
    skipped = 0
    result_devices = []

    for vd in vola_devices:
        normalized = normalize_vola_device(vd) if "device_sn" not in vd else vd
        sn = normalized.get("device_sn", "").strip()
        mac = normalized.get("mac", "").strip()

        if not sn and not mac:
            skipped += 1
            continue

        # Look for existing device by SN or MAC
        conditions = []
        if sn:
            conditions.append(Device.serial_number == sn)
        if mac:
            conditions.append(Device.mac_address == mac)

        existing_q = select(Device).where(
            Device.tenant_id == tenant_id,
            or_(*conditions),
        )
        existing_result = await db.execute(existing_q)
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update metadata from VOLA
            changed = False
            if normalized.get("firmware_version") and existing.firmware_version != normalized["firmware_version"]:
                existing.firmware_version = normalized["firmware_version"]
                changed = True
            if mac and not existing.mac_address:
                existing.mac_address = mac
                changed = True
            if sn and not existing.serial_number:
                existing.serial_number = sn
                changed = True
            if normalized.get("model") and not existing.model:
                existing.model = normalized["model"]
                changed = True
            if normalized.get("status") == "online" and existing.status == "provisioning":
                existing.status = "active"
                changed = True

            if changed:
                updated += 1
            else:
                skipped += 1
            result_devices.append({
                "device_id": existing.device_id,
                "id": existing.id,
                "action": "updated" if changed else "skipped",
                "serial_number": existing.serial_number,
                "mac_address": existing.mac_address,
            })
        else:
            # Create new device
            device_id = f"VOLA-{sn}" if sn else f"VOLA-{mac.replace(':', '')}"
            new_device = Device(
                device_id=device_id,
                tenant_id=tenant_id,
                status="provisioning",
                device_type="PR12",
                model=normalized.get("model", "FlyingVoice PR12"),
                manufacturer="FlyingVoice",
                serial_number=sn or None,
                mac_address=mac or None,
                firmware_version=normalized.get("firmware_version") or None,
                identifier_type="ata",
                notes=f"Synced from VOLA org={normalized.get('org_id', '')}",
            )
            db.add(new_device)
            await db.flush()

            # Emit event
            db.add(Event(
                event_id=f"evt-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                event_type="device.vola_sync",
                device_id=device_id,
                severity="info",
                message=f"Device {device_id} imported from VOLA (SN={sn}, MAC={mac})",
            ))

            imported += 1
            result_devices.append({
                "device_id": device_id,
                "id": new_device.id,
                "action": "imported",
                "serial_number": sn,
                "mac_address": mac,
            })

    await db.commit()
    logger.info(
        "VOLA sync complete for tenant %s: imported=%d updated=%d skipped=%d",
        tenant_id, imported, updated, skipped,
    )

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "devices": result_devices,
    }


async def bind_device_to_site(
    db: AsyncSession,
    tenant_id: str,
    device_id: int,
    site_id: str,
) -> Device:
    """Bind a device to a site. Returns the updated device."""
    result = await db.execute(
        select(Device).where(
            Device.id == device_id,
            Device.tenant_id == tenant_id,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise ValueError(f"Device {device_id} not found for tenant {tenant_id}")

    device.site_id = site_id
    if device.status == "provisioning":
        device.status = "active"

    db.add(Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        event_type="device.bound_to_site",
        device_id=device.device_id,
        site_id=site_id,
        severity="info",
        message=f"Device {device.device_id} bound to site {site_id}",
    ))

    await db.commit()
    await db.refresh(device)
    return device


# ── Basic provisioning templates ────────────────────────────────────────────

BASIC_PROVISION_PARAMS: list[list[str]] = [
    # Safe, useful provisioning parameters for PR12
    # ["Device.DeviceInfo.ProvisioningCode", "<site_code>"],
    # ["Device.ManagementServer.PeriodicInformInterval", "300"],
]


def build_provision_payload(
    site_code: str,
    inform_interval: int = 300,
    extra_params: list[list[str]] | None = None,
) -> list[list[str]]:
    """Build a safe provisioning parameter set for a PR12 device."""
    params = [
        ["Device.DeviceInfo.ProvisioningCode", site_code],
        ["Device.ManagementServer.PeriodicInformInterval", str(inform_interval)],
    ]
    if extra_params:
        params.extend(extra_params)
    return params
