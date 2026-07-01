"""Create / invite a CUSTOMER-plane user (e.g. Judy @ Restoration Hardware).

Safe, idempotent, DRY-RUN by default.  Never hardcodes or prints a password —
the account is created inactive with an invite token; the operator delivers the
invite URL out-of-band and the user sets their own password on first login
(mirrors the /api/admin/users/invite flow, usable when there is no admin UI).

Isolation: only the customer-plane roles are accepted (CUSTOMER_ADMIN / MANAGER /
VIEWER / SUPPORT / USER / BILLING / READONLY).  These roles hold no INTERNAL_OPS /
COMMAND_* grant (see permissions.json), so the user cannot reach internal pages.

Usage:
    # preview only (writes nothing):
    python -m scripts.create_customer_user --email judy@rh.example --name "Judy" \
        --role CUSTOMER_ADMIN --tenant restoration-hardware

    # actually create the invite:
    python -m scripts.create_customer_user --email judy@rh.example --name "Judy" \
        --role CUSTOMER_ADMIN --tenant restoration-hardware --apply

Exit codes: 0 ok (created or already-present) · 1 refused (bad role/tenant) · 2 error.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CUSTOMER_ROLES = {
    "CUSTOMER_ADMIN", "CUSTOMER_MANAGER", "CUSTOMER_SUPPORT", "CUSTOMER_VIEWER",
    "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY",
}
DEFAULT_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")
INVITE_TTL_DAYS = 7


async def _run(email: str, name: str, role: str, tenant_id: str, apply: bool) -> int:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services.auth import generate_invite_token, hash_password

    email = email.strip().lower()

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id))).scalar_one_or_none()
        if tenant is None:
            print(f"REFUSED: tenant '{tenant_id}' does not exist. Create it first "
                  "(Admin → Tenants) and re-run.")
            return 1

        existing = (await db.execute(
            select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
        if existing is not None:
            print(f"ALREADY EXISTS: {email} (role={existing.role}, tenant={existing.tenant_id}, "
                  f"active={existing.is_active}). No change made.")
            if existing.tenant_id != tenant_id or existing.role != role:
                print("  NOTE: existing role/tenant differ from requested — review manually; "
                      "this script will not mutate an existing user.")
            return 0

        print("Plan:")
        print(f"  email     : {email}")
        print(f"  name      : {name}")
        print(f"  role      : {role}")
        print(f"  tenant_id : {tenant_id}  (exists: yes, active: {bool(tenant.is_active)})")
        print(f"  is_active : False (invite-pending; user sets own password)")

        if not apply:
            print("\nDRY RUN — nothing written. Re-run with --apply to create the invite.")
            return 0

        token = generate_invite_token()
        user = User(
            email=email,
            name=name,
            # throwaway hash — never shared; the real password is set by the user
            # when they accept the invite.  Not printed.
            password_hash=hash_password(secrets.token_urlsafe(48)),
            role=role,
            tenant_id=tenant_id,
            is_active=False,
            invite_token=token,
            invite_expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
            must_change_password=True,
        )
        db.add(user)
        await db.commit()

        base = os.environ.get("PUBLIC_APP_URL", "").rstrip("/")
        invite_path = f"/AuthGate?invite={token}"
        print("\nCREATED (invite-pending).")
        print(f"  Invite link (deliver OUT-OF-BAND to the user; treat as sensitive):")
        print(f"    {base + invite_path if base else invite_path}")
        print(f"  Expires in {INVITE_TTL_DAYS} days. The user sets their own password on accept.")
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Create/invite a customer-plane user (dry-run by default).")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default="Customer Admin")
    ap.add_argument("--role", default="CUSTOMER_ADMIN")
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    args = ap.parse_args()

    role = args.role.strip().upper()
    if role not in CUSTOMER_ROLES:
        print(f"REFUSED: role '{args.role}' is not a customer-plane role. "
              f"Allowed: {', '.join(sorted(CUSTOMER_ROLES))}")
        raise SystemExit(1)

    try:
        code = asyncio.run(_run(args.email, args.name, role, args.tenant, args.apply))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"ERROR: {type(exc).__name__}: {exc}")
        raise SystemExit(2)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
