#!/usr/bin/env python3
"""Reset (or create) the superadmin user: smanley@manleysolutions.com.

Usage (Render shell — production):
    cd api/
    python scripts/reset_superadmin_password.py

Usage (local dev — requires running Postgres):
    cd api/
    python scripts/reset_superadmin_password.py
"""

import asyncio
import os
import sys
from urllib.parse import urlparse

from app.config import settings


def print_db_info() -> None:
    """Print full database target summary and abort if it looks wrong."""
    raw_url = settings.DATABASE_URL
    parsed = urlparse(raw_url)

    host = parsed.hostname or "unknown"
    port = parsed.port or 5432
    db_name = (parsed.path or "").lstrip("/") or "unknown"
    user = parsed.username or "unknown"

    # Determine environment tier
    env_var_present = bool(os.environ.get("DATABASE_URL"))
    is_localhost = host in ("localhost", "127.0.0.1", "::1")

    if "render.com" in host or "dpg-" in host:
        tier = "RENDER PRODUCTION"
    elif is_localhost:
        tier = "LOCAL DEV"
    else:
        tier = "EXTERNAL"

    print()
    print("=" * 56)
    print("  TRUE911 — Superadmin Password Reset")
    print("=" * 56)
    print()
    print(f"  Host:        {host}:{port}")
    print(f"  Database:    {db_name}")
    print(f"  DB User:     {user}")
    print(f"  APP_MODE:    {settings.APP_MODE}")
    print(f"  Tier:        {tier}")
    print(f"  DATABASE_URL env var set: {'YES' if env_var_present else 'NO (using default from config.py)'}")
    print()

    if is_localhost:
        print("  *** WARNING: Target is localhost. ***")
        print("  This will NOT affect your Render/production database.")
        print("  If you meant to reset the prod password, run this")
        print("  in the Render Shell where DATABASE_URL points to the")
        print("  production Postgres instance.")
        print()
        resp = input("  Continue with localhost? [y/N] ").strip().lower()
        if resp != "y":
            print("\n  Aborted.")
            sys.exit(0)

    print("-" * 56)


async def reset() -> None:
    # Lazy imports — only after the user has confirmed the target
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services.auth import hash_password

    EMAIL = "smanley@manleysolutions.com"
    NAME = "Scott Manley"
    PASSWORD = "Getsolutions#111"
    ROLE = "SuperAdmin"
    TENANT_ID = "default"

    async with AsyncSessionLocal() as db:
        # Ensure tenant
        result = await db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_ID))
        if not result.scalar_one_or_none():
            db.add(Tenant(tenant_id=TENANT_ID, name=TENANT_ID.title()))
            await db.flush()

        result = await db.execute(select(User).where(User.email == EMAIL))
        user = result.scalar_one_or_none()

        if user:
            user.password_hash = hash_password(PASSWORD)
            user.role = ROLE
            user.is_active = True
            await db.commit()
            print(f"\n  Superadmin password reset successfully.")
            print(f"  Email: {EMAIL}")
            print(f"  Role:  {ROLE}")
        else:
            user = User(
                email=EMAIL,
                name=NAME,
                password_hash=hash_password(PASSWORD),
                role=ROLE,
                tenant_id=TENANT_ID,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            print(f"\n  Superadmin user created and password set.")
            print(f"  Email: {EMAIL}")
            print(f"  Role:  {ROLE}")
            print(f"  Tenant: {TENANT_ID}")

    print()


if __name__ == "__main__":
    print_db_info()
    asyncio.run(reset())
