"""Zoho CRM integration service — OAuth2, account sync, status push-back.

Phase 1:
  - Pull Accounts → upsert as Customer records
  - Pull Contacts → store primary contact on Customer
  - Pull closed-won Deals → trigger onboarding status
  - Push site/service status back to Zoho Account custom fields

Authentication: OAuth2 refresh_token grant (server-to-server).
All operations are idempotent via zoho_account_id matching.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.customer import Customer
from app.models.device import Device
from app.models.line import Line
from app.models.sim import Sim
from app.models.site import Site
from app.models.tenant import Tenant

logger = logging.getLogger("true911.zoho_crm")


class ZohoCRMError(Exception):
    pass


# ── OAuth2 Token Management ─────────────────────────────────────

_cached_token: dict | None = None


async def _get_access_token() -> str:
    """Exchange refresh_token for a short-lived access_token."""
    global _cached_token

    if not settings.ZOHO_CRM_CLIENT_ID or not settings.ZOHO_CRM_REFRESH_TOKEN:
        raise ZohoCRMError("Zoho CRM not configured. Set ZOHO_CRM_CLIENT_ID, ZOHO_CRM_CLIENT_SECRET, ZOHO_CRM_REFRESH_TOKEN.")

    # Reuse cached token if not expired (with 60s buffer)
    if _cached_token:
        expires = _cached_token.get("expires_at", 0)
        if datetime.now(timezone.utc).timestamp() < expires - 60:
            return _cached_token["access_token"]

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.ZOHO_CRM_ACCOUNTS_DOMAIN}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.ZOHO_CRM_CLIENT_ID,
                "client_secret": settings.ZOHO_CRM_CLIENT_SECRET,
                "refresh_token": settings.ZOHO_CRM_REFRESH_TOKEN,
            },
        )
        if resp.status_code != 200:
            raise ZohoCRMError(f"Zoho OAuth failed: {resp.status_code} {resp.text[:200]}")

        data = resp.json()
        if "access_token" not in data:
            raise ZohoCRMError(f"Zoho OAuth response missing access_token: {data}")

        _cached_token = {
            "access_token": data["access_token"],
            "expires_at": datetime.now(timezone.utc).timestamp() + data.get("expires_in", 3600),
        }
        return _cached_token["access_token"]


async def _zoho_get(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to Zoho CRM API."""
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{settings.ZOHO_CRM_API_DOMAIN}/crm/v5{path}",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
            params=params,
        )
        if resp.status_code != 200:
            raise ZohoCRMError(f"Zoho API {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json()


async def _zoho_put(path: str, data: dict) -> dict:
    """Make an authenticated PUT request to Zoho CRM API."""
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.put(
            f"{settings.ZOHO_CRM_API_DOMAIN}/crm/v5{path}",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
            json=data,
        )
        if resp.status_code not in (200, 201, 202):
            raise ZohoCRMError(f"Zoho API PUT {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json()


def is_configured() -> bool:
    return bool(settings.ZOHO_CRM_CLIENT_ID and settings.ZOHO_CRM_REFRESH_TOKEN)


def config_summary() -> dict:
    return {
        "configured": is_configured(),
        "api_domain": settings.ZOHO_CRM_API_DOMAIN,
        "org_id": settings.ZOHO_CRM_ORG_ID or "not set",
        "has_client_id": bool(settings.ZOHO_CRM_CLIENT_ID),
        "has_refresh_token": bool(settings.ZOHO_CRM_REFRESH_TOKEN),
    }


# ── Sync: Zoho Accounts → True911 Customers ─────────────────────

async def sync_accounts(db: AsyncSession, tenant_id: str) -> dict:
    """Pull Zoho CRM Accounts and upsert as True911 Customer records."""
    if not is_configured():
        raise ZohoCRMError("Zoho CRM not configured")

    created = 0
    updated = 0
    skipped = 0
    page = 1
    now = datetime.now(timezone.utc)

    while True:
        try:
            data = await _zoho_get("/Accounts", params={"page": page, "per_page": 200})
        except ZohoCRMError:
            break

        records = data.get("data") or []
        if not records:
            break

        for acct in records:
            zoho_id = str(acct.get("id", ""))
            if not zoho_id:
                skipped += 1
                continue

            name = acct.get("Account_Name") or "Unknown"
            email = acct.get("Email") or acct.get("email")
            phone = acct.get("Phone") or acct.get("phone")

            # Upsert by zoho_account_id
            result = await db.execute(
                select(Customer).where(Customer.zoho_account_id == zoho_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                changed = False
                if existing.name != name:
                    existing.name = name
                    changed = True
                if email and existing.billing_email != email:
                    existing.billing_email = email
                    changed = True
                if phone and existing.billing_phone != phone:
                    existing.billing_phone = phone
                    changed = True
                existing.zoho_sync_status = "synced"
                existing.zoho_last_synced_at = now
                if changed:
                    updated += 1
                else:
                    skipped += 1
            else:
                customer = Customer(
                    tenant_id=tenant_id,
                    name=name,
                    billing_email=email,
                    billing_phone=phone,
                    zoho_account_id=zoho_id,
                    zoho_sync_status="synced",
                    zoho_last_synced_at=now,
                    onboarding_status="pending",
                )
                db.add(customer)
                created += 1

        if not data.get("info", {}).get("more_records"):
            break
        page += 1

    await db.commit()
    logger.info("Zoho account sync: created=%d updated=%d skipped=%d", created, updated, skipped)
    return {"created": created, "updated": updated, "skipped": skipped}


# ── Sync: Zoho Contacts → Customer contact fields ───────────────

async def sync_contacts(db: AsyncSession) -> dict:
    """Pull Zoho CRM Contacts and update primary contact on linked Customers."""
    if not is_configured():
        raise ZohoCRMError("Zoho CRM not configured")

    updated = 0
    skipped = 0
    page = 1

    while True:
        try:
            data = await _zoho_get("/Contacts", params={"page": page, "per_page": 200})
        except ZohoCRMError:
            break

        records = data.get("data") or []
        if not records:
            break

        for contact in records:
            account_id = None
            account_ref = contact.get("Account_Name")
            if isinstance(account_ref, dict):
                account_id = str(account_ref.get("id", ""))
            elif isinstance(account_ref, str):
                # Try to find customer by name
                pass

            if not account_id:
                skipped += 1
                continue

            result = await db.execute(
                select(Customer).where(Customer.zoho_account_id == account_id)
            )
            customer = result.scalar_one_or_none()
            if not customer:
                skipped += 1
                continue

            name = f"{contact.get('First_Name', '')} {contact.get('Last_Name', '')}".strip()
            email = contact.get("Email")
            phone = contact.get("Phone") or contact.get("Mobile")
            zoho_contact_id = str(contact.get("id", ""))

            if not customer.zoho_contact_id:
                customer.zoho_contact_id = zoho_contact_id
            if email and not customer.billing_email:
                customer.billing_email = email
            if phone and not customer.billing_phone:
                customer.billing_phone = phone
            updated += 1

        if not data.get("info", {}).get("more_records"):
            break
        page += 1

    await db.commit()
    logger.info("Zoho contact sync: updated=%d skipped=%d", updated, skipped)
    return {"updated": updated, "skipped": skipped}


# ── Push: True911 status → Zoho CRM Account ─────────────────────

async def push_status_to_zoho(db: AsyncSession, customer_id: int) -> dict:
    """Push operational status from True911 back to a Zoho CRM Account."""
    if not is_configured():
        raise ZohoCRMError("Zoho CRM not configured")

    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer or not customer.zoho_account_id:
        raise ZohoCRMError("Customer not found or not linked to Zoho")

    # Gather operational stats
    site_count = await db.scalar(
        select(func.count()).select_from(Site).where(Site.tenant_id == customer.tenant_id)
    ) or 0
    device_count = await db.scalar(
        select(func.count()).select_from(Device).where(Device.tenant_id == customer.tenant_id, Device.status == "active")
    ) or 0
    sim_count = await db.scalar(
        select(func.count()).select_from(Sim).where(Sim.tenant_id == customer.tenant_id, Sim.status == "active")
    ) or 0
    line_count = await db.scalar(
        select(func.count()).select_from(Line).where(Line.tenant_id == customer.tenant_id, Line.status == "active")
    ) or 0

    # Check E911 completeness
    sites_with_e911 = await db.scalar(
        select(func.count()).select_from(Site).where(
            Site.tenant_id == customer.tenant_id,
            Site.e911_street.isnot(None),
            Site.e911_city.isnot(None),
        )
    ) or 0
    e911_status = "complete" if site_count > 0 and sites_with_e911 == site_count else (
        "partial" if sites_with_e911 > 0 else "missing"
    )

    # Push to Zoho as custom fields on the Account
    update_data = {
        "data": [{
            "id": customer.zoho_account_id,
            "True911_Sites": site_count,
            "True911_Active_Devices": device_count,
            "True911_Active_SIMs": sim_count,
            "True911_Active_Lines": line_count,
            "True911_E911_Status": e911_status,
            "True911_Onboarding_Status": customer.onboarding_status or "pending",
            "True911_Last_Sync": datetime.now(timezone.utc).isoformat(),
        }]
    }

    try:
        result = await _zoho_put(f"/Accounts", update_data)
        customer.zoho_sync_status = "synced"
        customer.zoho_last_synced_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "pushed", "zoho_account_id": customer.zoho_account_id,
                "sites": site_count, "devices": device_count, "e911": e911_status}
    except ZohoCRMError as e:
        customer.zoho_sync_status = "error"
        await db.commit()
        raise
