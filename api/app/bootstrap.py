"""Bootstrap admin creation — runs on app startup."""

import logging

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth import hash_password

logger = logging.getLogger("true911")


async def _ensure_tenant(db, tenant_id: str) -> None:
    """Create the tenant row if it doesn't exist yet (idempotent)."""
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not result.scalar_one_or_none():
        db.add(Tenant(tenant_id=tenant_id, name=tenant_id.title()))
        await db.flush()


async def ensure_bootstrap_admin() -> None:
    """Create initial admin if it doesn't exist. Called on app startup.

    Also upgrades the bootstrap superadmin email to SuperAdmin role if needed.
    """
    password = settings.TRUE911_BOOTSTRAP_ADMIN_PASSWORD
    superadmin_email = settings.TRUE911_BOOTSTRAP_SUPERADMIN_EMAIL

    async with AsyncSessionLocal() as db:
        # --- SuperAdmin upgrade ---
        if superadmin_email:
            result = await db.execute(
                select(User).where(User.email == superadmin_email)
            )
            existing_sa = result.scalar_one_or_none()
            if existing_sa and existing_sa.role != "SuperAdmin":
                existing_sa.role = "SuperAdmin"
                await db.commit()
                logger.info(
                    "Upgraded %s to SuperAdmin", superadmin_email
                )

        # --- Bootstrap admin creation ---
        if not password:
            logger.info("TRUE911_BOOTSTRAP_ADMIN_PASSWORD not set — skipping bootstrap")
            return

        email = superadmin_email or "smanley@manleysolutions.com"

        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            logger.info("Bootstrap admin already exists — not overwriting password")
            return

        # Ensure tenant exists
        await _ensure_tenant(db, "default")

        user = User(
            email=email,
            name="Scott Manley",
            password_hash=hash_password(password),
            role="SuperAdmin",
            tenant_id="default",
        )
        db.add(user)
        await db.commit()
        logger.info("Bootstrap SuperAdmin created: %s", email)
