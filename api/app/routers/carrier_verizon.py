"""Admin-only endpoints for Verizon ThingSpace carrier integration.

Provides:
    POST /test-connection   — verify credentials work
    GET  /config            — safe diagnostic view of current config
    GET  /devices           — fetch & normalize device inventory (preview)
    GET  /devices/{kind}/{identifier} — look up single device
    POST /sync              — import Verizon lines into SIM inventory
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
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
    created: int
    updated: int
    unchanged: int
    errors: int
    total_fetched: int
    details: list[dict]


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
    max_results: int = Query(200, le=500),
    current_user: User = Depends(get_current_user),
):
    """Fetch Verizon device inventory and return normalized results. Admin only.

    This is a preview/read-only call — nothing is persisted.
    """
    client = get_verizon_client()
    _require_client_configured(client)

    try:
        raw_devices = await client.fetch_devices(max_results=max_results)
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
    max_results: int = Query(500, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync Verizon lines into the SIM inventory table.

    - dry_run=true (default): preview what would be created/updated
    - dry_run=false: actually persist to the sims table

    Matching is done by ICCID. Existing SIMs are updated; new ones are created.
    Lines are not auto-attached to customers or devices — that requires a
    separate manual mapping step.
    """
    client = get_verizon_client()
    _require_client_configured(client)

    try:
        raw_devices = await client.fetch_devices(max_results=max_results)
    except VerizonThingSpaceError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"ThingSpace API error: {e}")

    normalized = [normalize_verizon_device(d) for d in raw_devices]
    tenant_id = current_user.tenant_id

    # Load existing SIMs by ICCID for this tenant
    existing_result = await db.execute(
        select(Sim).where(Sim.tenant_id == tenant_id, Sim.carrier == "verizon")
    )
    existing_sims = {s.iccid: s for s in existing_result.scalars().all()}

    created = 0
    updated = 0
    unchanged = 0
    errors = 0
    details: list[dict] = []

    for device in normalized:
        iccid = device.get("iccid")
        if not iccid:
            errors += 1
            details.append({"action": "skip", "reason": "no_iccid", "external_id": device.get("external_id")})
            continue

        sim = existing_sims.get(iccid)
        if sim:
            changed = False
            if device.get("msisdn") and sim.msisdn != device["msisdn"]:
                if not dry_run:
                    sim.msisdn = device["msisdn"]
                changed = True
            new_status = _map_verizon_status(device.get("activation_status"))
            if new_status and sim.status != new_status:
                if not dry_run:
                    sim.status = new_status
                changed = True

            if changed:
                updated += 1
                details.append({"action": "update", "iccid": iccid, "msisdn": device.get("msisdn")})
            else:
                unchanged += 1
        else:
            created += 1
            details.append({"action": "create", "iccid": iccid, "msisdn": device.get("msisdn")})
            if not dry_run:
                new_sim = Sim(
                    tenant_id=tenant_id,
                    iccid=iccid,
                    msisdn=device.get("msisdn"),
                    carrier="verizon",
                    status=_map_verizon_status(device.get("activation_status")) or "inventory",
                    provider_sim_id=device.get("external_id"),
                    meta={"raw_payload": device.get("raw_payload")},
                )
                db.add(new_sim)

    if not dry_run:
        await db.commit()

    return SyncResult(
        created=created,
        updated=updated,
        unchanged=unchanged,
        errors=errors,
        total_fetched=len(normalized),
        details=details[:50],
    )


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
