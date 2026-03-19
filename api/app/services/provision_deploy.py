"""Zero-Touch Provisioning — full deployment orchestration.

Creates tenant/customer/site/device/user in one atomic flow,
then provisions PR12 devices via VOLA.
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.event import Event
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth import hash_password, generate_invite_token
from app.services.vola_service import (
    deploy_device,
    get_tenant_vola_client,
)

logger = logging.getLogger("true911.services.provision_deploy")


def _slugify(name: str) -> str:
    """Convert a name to a URL/ID-safe slug."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] if s else "site"


def _generate_temp_password() -> str:
    """Generate a secure temporary password (meets production rules)."""
    # 16 chars, guaranteed upper + lower + digit
    base = secrets.token_urlsafe(12)  # ~16 chars
    return f"T{base}1a"  # prefix T (upper), suffix 1 (digit) a (lower)


async def _ensure_tenant(db: AsyncSession, tenant_id: str, name: str) -> Tenant:
    """Find or create a tenant."""
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant

    tenant = Tenant(tenant_id=tenant_id, name=name, org_type="customer")
    db.add(tenant)
    await db.flush()
    logger.info("Created tenant: %s", tenant_id)
    return tenant


async def _ensure_customer(
    db: AsyncSession, tenant_id: str, name: str, email: str | None = None
) -> Customer:
    """Find customer by name within tenant, or create."""
    result = await db.execute(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.name == name,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    customer = Customer(
        tenant_id=tenant_id,
        name=name,
        billing_email=email,
        status="active",
        onboarding_status="in_progress",
    )
    db.add(customer)
    await db.flush()
    logger.info("Created customer: %s (tenant=%s)", name, tenant_id)
    return customer


async def _ensure_site(
    db: AsyncSession,
    tenant_id: str,
    customer_name: str,
    site_name: str,
    site_id: str | None = None,
    address: str | None = None,
    carrier: str | None = None,
    contact_email: str | None = None,
) -> Site:
    """Find site by site_id within tenant, or create."""
    sid = site_id or _slugify(site_name)

    # Check for existing
    result = await db.execute(
        select(Site).where(Site.site_id == sid).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Parse address if provided (simple: "street, city, state zip")
    e911_street = e911_city = e911_state = e911_zip = None
    if address:
        parts = [p.strip() for p in address.split(",")]
        if len(parts) >= 1:
            e911_street = parts[0]
        if len(parts) >= 2:
            e911_city = parts[1]
        if len(parts) >= 3:
            state_zip = parts[2].strip().split()
            e911_state = state_zip[0] if state_zip else None
            e911_zip = state_zip[1] if len(state_zip) > 1 else None

    site = Site(
        site_id=sid,
        tenant_id=tenant_id,
        site_name=site_name,
        customer_name=customer_name,
        status="Provisioning",
        carrier=carrier,
        e911_street=e911_street,
        e911_city=e911_city,
        e911_state=e911_state,
        e911_zip=e911_zip,
        poc_email=contact_email,
    )
    db.add(site)
    await db.flush()
    logger.info("Created site: %s (tenant=%s)", sid, tenant_id)
    return site


async def _create_invite_user(
    db: AsyncSession,
    tenant_id: str,
    email: str,
    name: str,
) -> dict[str, Any]:
    """Create a user account with invite token. Returns user info + invite link."""
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == email)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {
            "user_id": str(existing.id),
            "email": existing.email,
            "status": "already_exists",
            "invite_token": None,
            "temp_password": None,
        }

    temp_password = _generate_temp_password()
    invite_token = generate_invite_token()
    user = User(
        email=email,
        name=name,
        password_hash=hash_password(temp_password),
        role="User",
        tenant_id=tenant_id,
        invite_token=invite_token,
        invite_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        must_change_password=True,
    )
    db.add(user)
    await db.flush()
    logger.info("Created invite user: %s (tenant=%s)", email, tenant_id)

    return {
        "user_id": str(user.id),
        "email": email,
        "status": "created",
        "invite_token": invite_token,
        "temp_password": temp_password,
    }


async def run_provision_deployment(
    db: AsyncSession,
    operator_tenant_id: str,
    *,
    customer_name: str,
    site_name: str,
    device_sns: list[str],
    address: str | None = None,
    contact_email: str | None = None,
    contact_name: str | None = None,
    site_code: str | None = None,
    site_id: str | None = None,
    carrier: str | None = None,
    inform_interval: int = 300,
) -> dict[str, Any]:
    """Execute the full zero-touch provisioning deployment.

    Steps:
    1. Ensure tenant exists
    2. Create customer
    3. Create site
    4. For each device: ensure + bind + provision + reboot
    5. Create user account if contact_email provided
    6. Return comprehensive result
    """
    result: dict[str, Any] = {
        "status": "success",
        "steps": {},
        "customer": None,
        "site": None,
        "devices": [],
        "user_invite": None,
        "error": None,
    }

    tenant_id = operator_tenant_id

    # Step 1: Ensure tenant
    try:
        tenant = await _ensure_tenant(db, tenant_id, customer_name)
        result["steps"]["tenant"] = "ok"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Tenant creation failed: {exc}"
        result["steps"]["tenant"] = f"error: {exc}"
        return result

    # Step 2: Create customer
    try:
        customer = await _ensure_customer(db, tenant_id, customer_name, contact_email)
        result["steps"]["customer"] = "ok"
        result["customer"] = {"id": customer.id, "name": customer.name}
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Customer creation failed: {exc}"
        result["steps"]["customer"] = f"error: {exc}"
        return result

    # Step 3: Create site
    try:
        site = await _ensure_site(
            db, tenant_id, customer_name, site_name,
            site_id=site_id, address=address, carrier=carrier,
            contact_email=contact_email,
        )
        result["steps"]["site"] = "ok"
        result["site"] = {
            "id": site.id,
            "site_id": site.site_id,
            "site_name": site.site_name,
        }
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Site creation failed: {exc}"
        result["steps"]["site"] = f"error: {exc}"
        return result

    # Commit customer/site before device operations
    await db.commit()

    # Step 4: Deploy devices
    effective_site_code = site_code or site.site_id

    if device_sns:
        try:
            client = await get_tenant_vola_client(db, tenant_id)
        except Exception as exc:
            result["status"] = "partial"
            result["error"] = f"VOLA client failed: {exc}"
            result["steps"]["vola_connect"] = f"error: {exc}"
            # Still return customer/site info
            await _maybe_create_user(db, result, tenant_id, contact_email, contact_name, customer_name)
            return result

        result["steps"]["vola_connect"] = "ok"

        for sn in device_sns:
            dev_result = await deploy_device(
                db, tenant_id, client,
                device_sn=sn,
                site_id=site.site_id,
                site_code=effective_site_code,
                inform_interval=inform_interval,
            )
            result["devices"].append(dev_result)

        all_ok = all(d["status"] == "success" for d in result["devices"])
        any_ok = any(d["status"] == "success" for d in result["devices"])
        if not all_ok:
            result["status"] = "partial" if any_ok else "failed"
            if not any_ok:
                result["error"] = "All device deployments failed"
        result["steps"]["devices"] = f"{sum(1 for d in result['devices'] if d['status'] == 'success')}/{len(device_sns)} succeeded"
    else:
        result["steps"]["devices"] = "skipped (no devices)"

    # Step 5: Create user account
    await _maybe_create_user(db, result, tenant_id, contact_email, contact_name, customer_name)

    # Update site status
    try:
        site.status = "Active" if result["status"] == "success" else "Provisioning"
        if customer.onboarding_status == "in_progress" and result["status"] == "success":
            customer.onboarding_status = "complete"
        await db.commit()
    except Exception:
        pass  # Non-fatal

    # Emit event
    try:
        db.add(Event(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            event_type="deployment.provision",
            site_id=site.site_id,
            severity="info",
            message=f"Provision deployment: {customer_name} / {site_name} — {len(device_sns)} device(s), status={result['status']}",
        ))
        await db.commit()
    except Exception:
        pass

    return result


async def _maybe_create_user(
    db: AsyncSession,
    result: dict[str, Any],
    tenant_id: str,
    contact_email: str | None,
    contact_name: str | None,
    customer_name: str,
) -> None:
    """Create invite user if contact_email provided. Mutates result dict."""
    if not contact_email:
        result["steps"]["user_invite"] = "skipped (no email)"
        return

    try:
        user_info = await _create_invite_user(
            db, tenant_id, contact_email,
            name=contact_name or customer_name,
        )
        await db.commit()
        result["user_invite"] = user_info
        result["steps"]["user_invite"] = user_info["status"]
    except Exception as exc:
        result["steps"]["user_invite"] = f"error: {exc}"
        # Non-fatal — deployment still succeeded
        logger.warning("Failed to create invite user: %s", exc)
