"""Admin-only endpoints for Verizon ThingSpace carrier integration.

Provides:
    POST /test-connection   — verify credentials work
    GET  /config            — safe diagnostic view of current config
    GET  /devices           — fetch & normalize device inventory (preview)
    GET  /devices/{kind}/{identifier} — look up single device
    POST /sync              — import Verizon lines into SIM inventory
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.device import Device
from app.models.device_sim import DeviceSim
from app.models.event import Event
from app.models.sim import Sim
from app.models.user import User
from app.services.verizon_thingspace import (
    VerizonThingSpaceError,
    get_verizon_client,
    normalize_verizon_device,
)

logger = logging.getLogger("true911.carrier_verizon")

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
    auth_mode: Optional[str] = None
    m2m_auth_mode: Optional[str] = None
    token_type: Optional[str] = None
    request_headers_sent: Optional[list[str]] = None
    oauth_token_url: Optional[str] = None
    oauth_token_obtained: Optional[bool] = None
    oauth_token_status: Optional[int] = None
    oauth_token_body: Optional[str] = None
    m2m_session_login_url: Optional[str] = None
    m2m_session_token_obtained: Optional[bool] = None
    m2m_session_login_status: Optional[int] = None
    m2m_session_login_body: Optional[str] = None
    account_name: Optional[str] = None
    m2m_account_id: Optional[str] = None
    account_info: Optional[dict] = None
    account_info_endpoint: Optional[str] = None
    account_info_status: Optional[int] = None
    account_info_body: Optional[str] = None
    m2m_request_method: Optional[str] = None
    m2m_request_url: Optional[str] = None
    m2m_request_headers: Optional[list[str]] = None
    m2m_actual_headers_sent: Optional[list[str]] = None
    m2m_request_params: Optional[list[str]] = None
    m2m_request_body_keys: Optional[list[str]] = None
    note: Optional[str] = None


class NormalizedDevice(BaseModel):
    carrier: str = "verizon"
    external_id: Optional[str] = None
    imei: Optional[str] = None
    iccid: Optional[str] = None
    msisdn: Optional[str] = None
    sim_status: Optional[str] = None
    line_status: Optional[str] = None
    activation_status: Optional[str] = None
    usage_data_mb: Optional[float] = None
    last_seen_at: Optional[str] = None
    raw_payload: Optional[dict] = None


class DeviceListResult(BaseModel):
    total: int
    devices: list[NormalizedDevice]


class SyncResult(BaseModel):
    dry_run: bool
    created: int
    updated: int
    unchanged: int
    skipped: int
    conflicts: list[dict]
    total_fetched: int
    tenant_id: str
    details: list[dict]
    devices_created: int = 0
    devices_linked: int = 0
    carrier_set: int = 0


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/config",
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def verizon_config_summary(
    current_user: User = Depends(get_current_user),
):
    """Return a safe (no secrets) diagnostic view of the Verizon config. Admin only."""
    client = get_verizon_client()
    return client.config_summary()


@router.post(
    "/test-connection",
    response_model=ConnectionTestResult,
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def test_verizon_connection(
    current_user: User = Depends(get_current_user),
):
    """Test connectivity to Verizon ThingSpace. Admin only."""
    client = get_verizon_client()

    if not client.is_configured:
        summary = client.config_summary()
        detail = summary.get("error") or f"Missing: {', '.join(summary.get('missing_vars', []))}"
        return ConnectionTestResult(
            ok=False,
            auth_mode=client.auth_mode,
            message=f"Verizon ThingSpace not configured. {detail}",
        )

    try:
        result = await client.test_connection()

        # test_connection now returns authenticated=False on auth failure
        # instead of raising, so we get rich diagnostics either way.
        authenticated = result.get("authenticated", False)

        # Determine overall OK status:
        # - Must be authenticated
        # - If session token mode, session token must be obtained
        # - If account_info was fetched, that's a bonus success indicator
        m2m_session_ok = result.get("m2m_session_token_obtained")
        ok = authenticated and (m2m_session_ok is not False)

        return ConnectionTestResult(
            ok=ok,
            auth_mode=result.get("auth_mode"),
            m2m_auth_mode=result.get("m2m_auth_mode"),
            token_type=result.get("token_type"),
            request_headers_sent=result.get("request_headers_sent"),
            oauth_token_url=result.get("oauth_token_url"),
            oauth_token_obtained=result.get("oauth_token_obtained"),
            oauth_token_status=result.get("oauth_token_status"),
            oauth_token_body=result.get("oauth_token_body"),
            m2m_session_login_url=result.get("m2m_session_login_url"),
            m2m_session_token_obtained=result.get("m2m_session_token_obtained"),
            m2m_session_login_status=result.get("m2m_session_login_status"),
            m2m_session_login_body=result.get("m2m_session_login_body"),
            message=(
                "Successfully authenticated to Verizon ThingSpace"
                if ok
                else result.get("note") or "Authentication failed"
            ),
            account_name=result.get("account_name"),
            m2m_account_id=result.get("m2m_account_id"),
            account_info=result.get("account_info"),
            account_info_endpoint=result.get("account_info_endpoint"),
            account_info_status=result.get("account_info_status"),
            account_info_body=result.get("account_info_body"),
            m2m_request_method=result.get("m2m_request_method"),
            m2m_request_url=result.get("m2m_request_url"),
            m2m_request_headers=result.get("m2m_request_headers"),
            m2m_actual_headers_sent=result.get("m2m_actual_headers_sent"),
            m2m_request_params=result.get("m2m_request_params"),
            m2m_request_body_keys=result.get("m2m_request_body_keys"),
            note=result.get("note"),
        )
    except VerizonThingSpaceError as e:
        logger.warning("Verizon connection test failed: %s", e)
        return ConnectionTestResult(
            ok=False,
            auth_mode=client.auth_mode,
            message=f"Connection failed: {e}",
        )
    except Exception as e:
        logger.exception("Unexpected error testing Verizon connection")
        return ConnectionTestResult(
            ok=False,
            auth_mode=client.auth_mode,
            message=f"Unexpected error: {type(e).__name__}",
        )


@router.get(
    "/devices",
    response_model=DeviceListResult,
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def list_verizon_devices(
    max_results: int = Query(500, ge=1, le=2000, description=(
        "How many normalized devices to return.  Verizon requires fetching "
        "500–2000 per page, so the API may request more from Verizon than "
        "it returns to you."
    )),
    current_user: User = Depends(get_current_user),
):
    """Fetch Verizon device inventory and return normalized results. Admin only.

    This is a preview/read-only call — nothing is persisted.
    """
    client = get_verizon_client()
    _require_client_configured(client)

    try:
        raw_devices = await client.fetch_devices(display_count=max_results)
    except VerizonThingSpaceError as e:
        detail = {
            "error": str(e),
            "status_code": e.status_code,
            "body": e.body,
            "request_method": e.request_method,
            "request_url": e.request_url,
            "request_headers": e.request_headers,
            "actual_headers_sent": e.actual_headers_sent,
            "request_body_keys": e.request_body_keys,
        }
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    normalized = [normalize_verizon_device(d) for d in raw_devices]
    return DeviceListResult(
        total=len(normalized),
        devices=[NormalizedDevice(**d) for d in normalized],
    )


@router.get(
    "/devices/{kind}/{identifier}",
    response_model=NormalizedDevice,
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def get_verizon_device(
    kind: str,
    identifier: str,
    current_user: User = Depends(get_current_user),
):
    """Look up a single Verizon device by ICCID, IMEI, MDN, or MSISDN. Admin only."""
    allowed_kinds = {"iccid", "imei", "mdn", "msisdn"}
    if kind.lower() not in allowed_kinds:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"kind must be one of: {', '.join(sorted(allowed_kinds))}",
        )

    client = get_verizon_client()
    _require_client_configured(client)

    try:
        raw = await client.fetch_device_by_identifier(
            kind=kind.upper(), identifier=identifier
        )
    except VerizonThingSpaceError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"ThingSpace API error: {e}")

    if not raw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found on ThingSpace")

    return NormalizedDevice(**normalize_verizon_device(raw))


@router.post(
    "/sync",
    response_model=SyncResult,
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def sync_verizon_devices(
    dry_run: bool = Query(True, description="Preview only — set false to persist"),
    max_results: int = Query(500, ge=500, le=2000, description=(
        "How many devices to fetch from Verizon (500–2000, per Verizon API limits)."
    )),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync Verizon lines into the SIM inventory table.

    - dry_run=true (default): preview what would be created/updated
    - dry_run=false: actually persist to the sims table

    Matching is done by ICCID (globally unique).  The sync checks for:
    - ICCIDs that already exist under a *different* tenant (conflict)
    - MSISDNs that already exist on another SIM row (unique-index conflict)
    - Duplicate MSISDNs within the incoming Verizon batch

    Lines are not auto-attached to customers or devices — that requires a
    separate manual mapping step.
    """
    client = get_verizon_client()
    _require_client_configured(client)

    try:
        raw_devices = await client.fetch_devices(display_count=max_results)
    except VerizonThingSpaceError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"ThingSpace API error: {e}")

    normalized = [normalize_verizon_device(d) for d in raw_devices]
    tenant_id = current_user.tenant_id

    # ── Pre-flight: load ALL existing SIMs whose ICCID or MSISDN appears
    #    in the incoming batch, regardless of tenant.  This lets us detect
    #    cross-tenant ICCID conflicts and MSISDN unique-index violations
    #    *before* they would crash a live sync.
    incoming_iccids = {d["iccid"] for d in normalized if d.get("iccid")}
    incoming_msisdns = {d["msisdn"] for d in normalized if d.get("msisdn")}

    filters = []
    if incoming_iccids:
        filters.append(Sim.iccid.in_(incoming_iccids))
    if incoming_msisdns:
        filters.append(Sim.msisdn.in_(incoming_msisdns))

    existing_by_iccid: dict[str, Sim] = {}
    existing_by_msisdn: dict[str, Sim] = {}
    if filters:
        existing_result = await db.execute(select(Sim).where(or_(*filters)))
        for sim in existing_result.scalars().all():
            if sim.iccid:
                existing_by_iccid[sim.iccid] = sim
            if sim.msisdn:
                existing_by_msisdn[sim.msisdn] = sim

    # Track MSISDNs we plan to insert in this batch to catch intra-batch dupes
    batch_msisdns: dict[str, str] = {}  # msisdn → iccid that claimed it first

    created = 0
    updated = 0
    unchanged = 0
    skipped = 0
    conflicts: list[dict] = []
    details: list[dict] = []

    for device in normalized:
        iccid = device.get("iccid")
        msisdn = device.get("msisdn")

        if not iccid:
            skipped += 1
            details.append({"action": "skip", "reason": "no_iccid",
                            "external_id": device.get("external_id")})
            continue

        # ── Conflict check: ICCID exists under a different tenant ────
        existing_sim = existing_by_iccid.get(iccid)
        if existing_sim and existing_sim.tenant_id != tenant_id:
            skipped += 1
            conflicts.append({
                "type": "iccid_cross_tenant",
                "iccid": iccid,
                "existing_tenant_id": existing_sim.tenant_id,
                "your_tenant_id": tenant_id,
            })
            details.append({"action": "skip", "reason": "iccid_owned_by_other_tenant",
                            "iccid": iccid})
            continue

        # ── Conflict check: MSISDN already on a *different* SIM row ──
        if msisdn:
            msisdn_owner = existing_by_msisdn.get(msisdn)
            if msisdn_owner and msisdn_owner.iccid != iccid:
                skipped += 1
                conflicts.append({
                    "type": "msisdn_collision",
                    "msisdn": msisdn,
                    "iccid": iccid,
                    "existing_iccid": msisdn_owner.iccid,
                })
                details.append({"action": "skip", "reason": "msisdn_on_other_sim",
                                "iccid": iccid, "msisdn": msisdn})
                continue

            # Intra-batch duplicate MSISDN
            if msisdn in batch_msisdns and batch_msisdns[msisdn] != iccid:
                skipped += 1
                conflicts.append({
                    "type": "msisdn_batch_duplicate",
                    "msisdn": msisdn,
                    "iccid": iccid,
                    "first_iccid": batch_msisdns[msisdn],
                })
                details.append({"action": "skip", "reason": "msisdn_duplicate_in_batch",
                                "iccid": iccid, "msisdn": msisdn})
                continue

            batch_msisdns[msisdn] = iccid

        # ── Update existing SIM (same tenant) ────────────────────────
        if existing_sim:
            changed = False
            changes: dict[str, list] = {}
            if msisdn and existing_sim.msisdn != msisdn:
                changes["msisdn"] = [existing_sim.msisdn, msisdn]
                if not dry_run:
                    existing_sim.msisdn = msisdn
                changed = True
            new_status = _map_verizon_status(device.get("activation_status"))
            if new_status and existing_sim.status != new_status:
                changes["status"] = [existing_sim.status, new_status]
                if not dry_run:
                    existing_sim.status = new_status
                changed = True

            if changed:
                updated += 1
                details.append({"action": "update", "iccid": iccid,
                                "msisdn": msisdn, "changes": changes})
            else:
                unchanged += 1
        else:
            # ── Create new SIM ────────────────────────────────────────
            created += 1
            mapped_status = _map_verizon_status(device.get("activation_status")) or "inventory"
            details.append({"action": "create", "iccid": iccid,
                            "msisdn": msisdn, "status": mapped_status})
            if not dry_run:
                new_sim = Sim(
                    tenant_id=tenant_id,
                    iccid=iccid,
                    msisdn=msisdn,
                    carrier="verizon",
                    status=mapped_status,
                    provider_sim_id=device.get("external_id"),
                    meta={"raw_payload": device.get("raw_payload")},
                )
                db.add(new_sim)

    # ── Phase 2: Auto-create devices and link DeviceSim records ──────
    devices_created = 0
    devices_linked = 0
    carrier_set = 0

    if not dry_run:
        # Flush SIM inserts so we can reference their .id values
        await db.flush()

        # Reload all SIMs for this tenant that have an ICCID in this batch
        sim_result = await db.execute(
            select(Sim).where(
                Sim.tenant_id == tenant_id,
                Sim.iccid.in_(incoming_iccids),
            )
        )
        sims_by_iccid: dict[str, Sim] = {
            s.iccid: s for s in sim_result.scalars().all()
        }

        # Build a lookup of normalized data keyed by ICCID for IMEI access
        norm_by_iccid: dict[str, dict] = {
            d["iccid"]: d for d in normalized if d.get("iccid")
        }

        # Pre-load existing devices by IMEI for this tenant
        incoming_imeis = {
            d["imei"] for d in normalized if d.get("imei")
        }
        existing_devices_by_imei: dict[str, Device] = {}
        if incoming_imeis:
            dev_result = await db.execute(
                select(Device).where(
                    Device.tenant_id == tenant_id,
                    Device.imei.in_(incoming_imeis),
                )
            )
            for dev in dev_result.scalars().all():
                if dev.imei:
                    existing_devices_by_imei[dev.imei] = dev

        # Pre-load existing active DeviceSim links for the SIMs in this batch
        sim_ids_in_batch = [s.id for s in sims_by_iccid.values()]
        existing_links: set[tuple[int, int]] = set()  # (device.id, sim.id)
        if sim_ids_in_batch:
            link_result = await db.execute(
                select(DeviceSim).where(
                    DeviceSim.sim_id.in_(sim_ids_in_batch),
                    DeviceSim.active == True,
                )
            )
            for link in link_result.scalars().all():
                existing_links.add((link.device_id, link.sim_id))

        for iccid, sim in sims_by_iccid.items():
            norm = norm_by_iccid.get(iccid)
            if not norm:
                continue
            imei = norm.get("imei")
            if not imei:
                continue

            # Find or create Device
            device = existing_devices_by_imei.get(imei)
            if not device:
                device_id = f"VZ-{uuid.uuid4().hex[:8].upper()}"
                device = Device(
                    device_id=device_id,
                    tenant_id=tenant_id,
                    status="provisioning",
                    device_type="Cellular Gateway",
                    identifier_type="cellular",
                    imei=imei,
                    iccid=sim.iccid,
                    msisdn=sim.msisdn,
                    carrier="verizon",
                )
                db.add(device)
                await db.flush()  # get device.id
                existing_devices_by_imei[imei] = device
                devices_created += 1
            else:
                # Set carrier if empty
                if not device.carrier:
                    device.carrier = "verizon"
                    carrier_set += 1
                elif device.carrier.lower() != "verizon":
                    # Don't overwrite existing non-verizon carrier; report it
                    details.append({
                        "action": "carrier_mismatch",
                        "device_id": device.device_id,
                        "imei": imei,
                        "existing_carrier": device.carrier,
                        "verizon_iccid": iccid,
                    })

            # Create DeviceSim link if not already linked
            if (device.id, sim.id) not in existing_links:
                link = DeviceSim(
                    device_id=device.id,
                    sim_id=sim.id,
                    slot=1,
                    active=True,
                    assigned_by="verizon-sync",
                )
                db.add(link)
                existing_links.add((device.id, sim.id))
                devices_linked += 1

        await db.commit()
    else:
        # Dry-run: estimate device creation / linking
        for device_data in normalized:
            imei = device_data.get("imei")
            iccid = device_data.get("iccid")
            if not imei or not iccid:
                continue
            # Check if device with this IMEI exists
            dev_result = await db.execute(
                select(Device.id, Device.carrier).where(
                    Device.tenant_id == tenant_id,
                    Device.imei == imei,
                )
            )
            row = dev_result.first()
            if not row:
                devices_created += 1
                devices_linked += 1
            else:
                if not row.carrier:
                    carrier_set += 1
                # Check if link already exists
                sim_result = await db.execute(
                    select(Sim.id).where(
                        Sim.tenant_id == tenant_id,
                        Sim.iccid == iccid,
                    )
                )
                sim_row = sim_result.first()
                if sim_row:
                    link_result = await db.execute(
                        select(DeviceSim.id).where(
                            DeviceSim.device_id == row.id,
                            DeviceSim.sim_id == sim_row.id,
                            DeviceSim.active == True,
                        )
                    )
                    if not link_result.first():
                        devices_linked += 1

    logger.info(
        "Verizon sync %s: tenant=%s fetched=%d created=%d updated=%d "
        "unchanged=%d skipped=%d conflicts=%d devices_created=%d "
        "devices_linked=%d carrier_set=%d",
        "DRY-RUN" if dry_run else "LIVE",
        tenant_id, len(normalized), created, updated, unchanged,
        skipped, len(conflicts), devices_created, devices_linked,
        carrier_set,
    )

    # Emit audit event for sync run
    sync_event = Event(
        event_id=f"evt-vzsync-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        event_type="integration.verizon_sync",
        severity="info",
        message=(
            f"Verizon sync {'preview' if dry_run else 'live'}: "
            f"{created} created, {updated} updated, {skipped} skipped"
        ),
        metadata_json={
            "mode": "preview" if dry_run else "live",
            "total_fetched": len(normalized),
            "sims_created": created,
            "sims_updated": updated,
            "unchanged": unchanged,
            "skipped": skipped,
            "conflicts": len(conflicts),
            "devices_created": devices_created,
            "devices_linked": devices_linked,
            "carrier_set": carrier_set,
            "initiated_by": current_user.email,
        },
    )
    db.add(sync_event)
    await db.commit()

    return SyncResult(
        dry_run=dry_run,
        created=created,
        updated=updated,
        unchanged=unchanged,
        skipped=skipped,
        conflicts=conflicts,
        total_fetched=len(normalized),
        tenant_id=tenant_id,
        details=details[:100],
        devices_created=devices_created,
        devices_linked=devices_linked,
        carrier_set=carrier_set,
    )


@router.get(
    "/sync-history",
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def verizon_sync_history(
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recent Verizon sync events for operational visibility."""
    result = await db.execute(
        select(Event)
        .where(
            Event.tenant_id == current_user.tenant_id,
            Event.event_type == "integration.verizon_sync",
        )
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "event_id": e.event_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "message": e.message,
            "metadata": e.metadata_json,
        }
        for e in events
    ]


# ── Telemetry Poll ──────────────────────────────────────────────────────────

@router.post(
    "/poll-telemetry",
    dependencies=[Depends(require_permission("MANAGE_INTEGRATIONS"))],
)
async def poll_verizon_telemetry_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch latest device state from Verizon and update telemetry.

    This re-reads the Verizon inventory and pushes activation_status,
    usage, and last_seen through the carrier telemetry pipeline for
    every Verizon device belonging to the current tenant.
    """
    from app.services.telemetry_poller import poll_verizon_telemetry

    result = await poll_verizon_telemetry(
        db, current_user.tenant_id, current_user.email,
    )
    return result


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_client_configured(client) -> None:
    """Raise 400 with a helpful message if the client is not configured."""
    if not client.is_configured:
        summary = client.config_summary()
        detail = summary.get("error") or f"Missing: {', '.join(summary.get('missing_vars', []))}"
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Verizon ThingSpace not configured. {detail}",
        )


def _map_verizon_status(raw_status: str | None) -> str | None:
    """Map Verizon activation/connection status to our SIM status enum."""
    if not raw_status:
        return None
    s = raw_status.lower()
    if s in ("active", "connected", "activated"):
        return "active"
    if s in ("suspended", "suspend"):
        return "suspended"
    if s in ("deactivated", "deactive", "terminated", "disconnected"):
        return "terminated"
    if s in ("ready", "preactive", "inventory"):
        return "inventory"
    return "inventory"
