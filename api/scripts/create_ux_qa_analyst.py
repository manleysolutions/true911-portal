#!/usr/bin/env python3
"""Create (or update) a UX & QA Analyst user — e.g. Sivmey.

This is a *deliberate, operator-run* provisioning helper.  It is NOT a
seed and is never auto-run by the app; nothing imports it.  Run it by
hand in the Render shell when you want to grant someone the
``UX_QA_ANALYST`` role.

    cd api
    python -m scripts.create_ux_qa_analyst \
        --email sivmey@manleysolutions.com \
        --name "Sivmey" \
        --tenant default \
        --password 'ChangeMeNow123'

Behavior (idempotent upsert, keyed by email — case-insensitive):
  * If the user does NOT exist  -> create with role UX_QA_ANALYST,
    is_active=True, must_change_password=True.
  * If the user DOES exist       -> set role=UX_QA_ANALYST and
    is_active=True only.  An existing password is left untouched unless
    --password is supplied.  No other field is modified.

Safety:
  * Refuses if the target tenant row does not exist (no orphan users).
  * Validates password strength in production mode.
  * Prints exactly what it changed.  Writes ONE user row + one audit
    entry; never deletes, never touches any other table.

Rollback:
  * Deactivate:  PATCH the user is_active=false via the Admin UI, or set
    role back to "User".  To remove entirely, delete the single user row.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid

_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.audit_log_entry import AuditLogEntry  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import hash_password, validate_password_strength  # noqa: E402

ROLE = "UX_QA_ANALYST"


async def _tenant_exists(db: AsyncSession, slug: str) -> bool:
    row = await db.execute(select(Tenant).where(Tenant.tenant_id == slug))
    return row.scalar_one_or_none() is not None


async def _run(email: str, name: str, tenant: str, password: str | None) -> int:
    needle = (email or "").strip().lower()
    if not needle:
        print("ERROR: --email is required")
        return 2

    if password is not None:
        err = validate_password_strength(password)
        if err:
            print(f"ERROR: weak password — {err}")
            return 2

    async with AsyncSessionLocal() as db:
        if not await _tenant_exists(db, tenant):
            print(f"ERROR: tenant {tenant!r} does not exist — refusing to "
                  "create an orphan user. Create the tenant first.")
            return 2

        existing = (
            await db.execute(select(User).where(func.lower(User.email) == needle))
        ).scalar_one_or_none()

        if existing:
            before = {"role": existing.role, "is_active": existing.is_active}
            existing.role = ROLE
            existing.is_active = True
            if password is not None:
                existing.password_hash = hash_password(password)
                existing.must_change_password = True
            action = "update_ux_qa_analyst"
            summary = (f"Set role={ROLE} on existing user {existing.email} "
                       f"(was {before['role']!r}, active={before['is_active']})")
            target_id = str(existing.id)
            actor_email = existing.email
        else:
            if password is None:
                print("ERROR: --password is required when creating a new user")
                return 2
            user = User(
                id=uuid.uuid4(),
                email=needle,
                name=name or "UX & QA Analyst",
                password_hash=hash_password(password),
                role=ROLE,
                tenant_id=tenant,
                is_active=True,
                must_change_password=True,
            )
            db.add(user)
            await db.flush()  # assign user.id for the audit row
            action = "create_ux_qa_analyst"
            summary = f"Created user {needle} with role {ROLE} on tenant {tenant!r}"
            target_id = str(user.id)
            actor_email = needle

        db.add(AuditLogEntry(
            entry_id=f"ux-qa-role-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant,
            category="security",
            action=action,
            actor=actor_email,
            target_type="user",
            target_id=target_id,
            summary=summary,
            detail_json=json.dumps({"email": needle, "role": ROLE, "tenant": tenant}),
        ))
        await db.commit()

    print(summary)
    print("must_change_password is set — the user must set a new password on first login.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Sivmey")
    p.add_argument("--tenant", default="default",
                   help="tenant_id to attach the user to (must already exist)")
    p.add_argument("--password", default=None,
                   help="required when creating; optional when updating an existing user")
    args = p.parse_args()
    return asyncio.run(_run(args.email, args.name, args.tenant, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
