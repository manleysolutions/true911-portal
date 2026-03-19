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
from sqlalchemy.exc import IntegrityError
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
        ).limit(1)
        existing_result = await db.execute(existing_q)
        existing = existing_result.scalar_one_or_none()  # limit(1) ensures at most one

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
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                logger.warning("Skipping duplicate device_id=%s (SN=%s MAC=%s)", device_id, sn, mac)
                skipped += 1
                result_devices.append({
                    "device_id": device_id,
                    "id": None,
                    "action": "skipped_duplicate",
                    "serial_number": sn,
                    "mac_address": mac,
                })
                continue

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


async def ensure_device_exists(
    db: AsyncSession,
    tenant_id: str,
    device_sn: str,
    mac: str = "",
    model: str = "",
    firmware_version: str = "",
) -> Device:
    """Find or create a device record for the given VOLA serial number.

    Returns the Device ORM object (flushed but not committed).
    """
    from sqlalchemy.exc import IntegrityError as _IE

    # Look up by SN first
    result = await db.execute(
        select(Device).where(
            Device.tenant_id == tenant_id,
            Device.serial_number == device_sn,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Also check by MAC
    if mac:
        result2 = await db.execute(
            select(Device).where(
                Device.tenant_id == tenant_id,
                Device.mac_address == mac,
            ).limit(1)
        )
        existing2 = result2.scalar_one_or_none()
        if existing2:
            if not existing2.serial_number:
                existing2.serial_number = device_sn
            return existing2

    device_id = f"VOLA-{device_sn}"
    new_device = Device(
        device_id=device_id,
        tenant_id=tenant_id,
        status="provisioning",
        device_type="PR12",
        model=model or "FlyingVoice PR12",
        manufacturer="FlyingVoice",
        serial_number=device_sn,
        mac_address=mac or None,
        firmware_version=firmware_version or None,
        identifier_type="ata",
        notes="Created via Quick Deploy",
    )
    db.add(new_device)
    try:
        await db.flush()
    except _IE:
        await db.rollback()
        # Race condition — re-fetch
        result3 = await db.execute(
            select(Device).where(
                Device.tenant_id == tenant_id,
                Device.serial_number == device_sn,
            ).limit(1)
        )
        found = result3.scalar_one_or_none()
        if found:
            return found
        raise

    db.add(Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        event_type="device.vola_sync",
        device_id=device_id,
        severity="info",
        message=f"Device {device_id} created via Quick Deploy (SN={device_sn})",
    ))
    return new_device


async def deploy_device(
    db: AsyncSession,
    tenant_id: str,
    client: VolaClient,
    device_sn: str,
    site_id: str,
    site_code: str,
    inform_interval: int = 300,
) -> dict[str, Any]:
    """Run the full deploy sequence for a single device.

    Steps: ensure exists -> bind to site -> provision -> reboot.
    Returns a result dict with status per step.
    """
    result: dict[str, Any] = {
        "device_sn": device_sn,
        "steps": {},
        "status": "success",
        "error": None,
    }

    # Step 1: Ensure device exists
    try:
        device = await ensure_device_exists(db, tenant_id, device_sn)
        result["device_id"] = device.device_id
        result["device_pk"] = device.id
        result["steps"]["ensure_device"] = "ok"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Failed to ensure device: {exc}"
        result["steps"]["ensure_device"] = f"error: {exc}"
        return result

    # Step 2: Bind to site
    try:
        device.site_id = site_id
        if device.status == "provisioning":
            device.status = "active"
        await db.flush()
        result["steps"]["bind_to_site"] = "ok"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Failed to bind to site: {exc}"
        result["steps"]["bind_to_site"] = f"error: {exc}"
        return result

    # Step 3: Provision
    try:
        params = build_provision_payload(site_code, inform_interval)
        err = client.validate_set_param_values(params)
        if err:
            result["steps"]["provision"] = f"validation_error: {err}"
            result["status"] = "failed"
            result["error"] = err
            return result

        data = await client.create_set_parameter_values_task(device_sn, params)
        task_id = data.get("taskId", data.get("id", ""))
        if not task_id:
            result["steps"]["provision"] = "error: no taskId returned"
            result["status"] = "failed"
            result["error"] = "VOLA did not return a taskId for provisioning"
            return result

        poll = await client.poll_task_sync(task_id, timeout_seconds=25, poll_interval=1.0)
        result["steps"]["provision"] = poll["status"]
        result["provision_task_id"] = task_id
        result["applied"] = {p[0]: p[1] for p in params}

        if poll["status"] != "success":
            result["status"] = "partial"
            result["error"] = f"Provision {poll['status']}"
    except Exception as exc:
        result["steps"]["provision"] = f"error: {exc}"
        result["status"] = "failed"
        result["error"] = f"Provision failed: {exc}"
        return result

    # Step 4: Reboot
    try:
        rdata = await client.create_reboot_task(device_sn)
        reboot_tid = rdata.get("taskId", rdata.get("id", ""))
        result["steps"]["reboot"] = "ok" if reboot_tid else "no_task_id"
        result["reboot_task_id"] = reboot_tid
    except Exception as exc:
        # Reboot failure is non-fatal — device was provisioned
        result["steps"]["reboot"] = f"error: {exc}"
        if result["status"] == "success":
            result["status"] = "partial"
            result["error"] = f"Provisioned but reboot failed: {exc}"

    # Commit the DB changes (device create/bind)
    try:
        await db.commit()
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"DB commit failed: {exc}"

    return result


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
