#!/usr/bin/env python3
"""One-time script to reset the password for smanley@manleysolutions.com.

Usage:
    cd api/
    python scripts/reset_admin_password.py "YourNewPassword123"

The password is passed as a CLI argument. The script does NOT log the
password or the resulting hash.
"""

import asyncio
import sys

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.auth import hash_password, validate_password_strength

TARGET_EMAIL = "smanley@manleysolutions.com"


async def reset(new_password: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email == TARGET_EMAIL)
        )
        user = result.scalar_one_or_none()

        if not user:
            print(f"[!!] User {TARGET_EMAIL} not found in database.")
            print("     Check DATABASE_URL in your .env and ensure migrations have run.")
            sys.exit(1)

        print(f"[OK] Found user: {user.name} ({user.email})")
        print(f"     Role: {user.role}  Tenant: {user.tenant_id}  Active: {user.is_active}")

        # Hash and update
        user.password_hash = hash_password(new_password)
        user.is_active = True
        user.must_change_password = False
        await db.commit()

        print(f"[OK] Password updated successfully.")
        print(f"     You can now log in with: {TARGET_EMAIL}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/reset_admin_password.py \"YourNewPassword123\"")
        sys.exit(1)

    new_password = sys.argv[1]

    # Validate strength (respects APP_MODE — demo skips validation)
    err = validate_password_strength(new_password)
    if err:
        print(f"[!!] Password too weak: {err}")
        sys.exit(1)

    asyncio.run(reset(new_password))


if __name__ == "__main__":
    main()
