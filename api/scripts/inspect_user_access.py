#!/usr/bin/env python3
"""Read-only one-time diagnostic for the inactive-user / malformed-role
investigation.  Prints the auth-relevant fields of a single user plus
whether the referenced tenant row exists.

Run on Render shell from the api/ directory:

    cd api
    python -m scripts.inspect_user_access --email sivmey@example.com

Or with the script form:

    cd api
    python scripts/inspect_user_access.py --email sivmey@example.com

Read-only.  Does not write to any table.  Does not change auth behavior.
"""

import argparse
import asyncio
import os
import sys

# When invoked as ``python -m scripts.inspect_user_access`` from inside
# ``api/``, the cwd is on sys.path and ``app`` is importable.  When
# invoked as ``python scripts/inspect_user_access.py`` from ``api/``,
# ``__file__`` is in ``api/scripts``; ``api/`` itself is one level up
# and we add it explicitly so ``import app.*`` works either way.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.rbac import normalize_role  # noqa: E402


def _banner(text: str) -> None:
    print()
    print("=" * 64)
    print(text)
    print("=" * 64)


async def _resolve_user(db: AsyncSession, email: str) -> User | None:
    needle = (email or "").strip().lower()
    if not needle:
        return None
    result = await db.execute(
        select(User).where(func.lower(User.email) == needle)
    )
    return result.scalar_one_or_none()


async def _tenant_exists(db: AsyncSession, slug: str | None) -> tuple[bool, bool]:
    """Return (exists, is_active).  (False, False) when slug is missing."""
    if not slug:
        return (False, False)
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_id == slug)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return (False, False)
    return (True, bool(tenant.is_active))


async def _run(email: str) -> int:
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(db, email)
        if not user:
            _banner(f"NO USER FOUND for email {email!r}")
            return 1

        raw_role = user.role
        normalized = normalize_role(raw_role or "")
        tenant_exists, tenant_active = await _tenant_exists(db, user.tenant_id)

        _banner(f"User: {user.email}")
        rows = [
            ("email",                user.email),
            ("name",                 getattr(user, "name", None)),
            ("raw role",             repr(raw_role)),
            ("normalized role",      repr(normalized)),
            ("is_active",            user.is_active),
            ("tenant_id",            repr(user.tenant_id)),
            ("tenant exists",        "yes" if tenant_exists else "no"),
            ("tenant is_active",     "yes" if tenant_active else ("no" if tenant_exists else "n/a")),
            ("must_change_password", getattr(user, "must_change_password", None)),
            ("created_at",           getattr(user, "created_at", None)),
            ("updated_at",           getattr(user, "updated_at", None)),
        ]
        width = max(len(label) for label, _ in rows)
        for label, value in rows:
            print(f"  {label:<{width}}  {value}")

        # Inline interpretation hints so the operator can see at a glance
        # which 401/403 path get_current_user would take for this user.
        print()
        print("interpretation:")
        if not user.is_active:
            print("  → get_current_user would 401 with 'User not found or inactive'")
            print("    (this is the 'Unauthorized' string the frontend shows).")
        elif normalized not in {"SuperAdmin", "Admin", "Manager", "User", "DataEntry"}:
            print(f"  → role would silently fall through normalize_role as {normalized!r}.")
            print("    rbac.can() returns False for every action → 403 on protected routes.")
        elif not tenant_exists:
            print(f"  → tenant {user.tenant_id!r} is missing.  Tenant-scoped queries")
            print("    return empty arrays (not 401).  Impersonation as this user fails.")
        elif tenant_exists and not tenant_active:
            print(f"  → tenant {user.tenant_id!r} exists but is inactive.")
        else:
            print("  → user looks healthy on the auth path; 401 unlikely from this row.")

        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", required=True, help="Email to inspect (case-insensitive)")
    args = p.parse_args()
    return asyncio.run(_run(args.email))


if __name__ == "__main__":
    raise SystemExit(main())
