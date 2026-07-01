"""Reissue an invite for an existing INACTIVE customer user (safe operator tool).

When a customer's invite link expired (or was lost) before they set a password,
this mints a fresh ``invite_token`` + ``invite_expires_at`` for the SAME user —
without changing their role, tenant, email, name, or activation state.

Strict safety rails:
  * DRY-RUN by default; writes only with ``--apply``.
  * Refuses unless the user is **inactive** (invite-pending).  An already-active
    account is never re-invited (that would be an account-takeover foot-gun).
  * Refuses unless the role is a **CUSTOMER_*** role (this tool is customer-plane
    only; internal users are provisioned differently).
  * Tenant-scoped lookup (email + tenant) — never touches another tenant's user,
    never reveals a user that lives in a different tenant.
  * Prints NO secrets — only the new one-time invite link, and only after --apply.

Usage:
    # preview (writes nothing):
    python -m scripts.reissue_customer_invite --email judy@rh.example --tenant restoration-hardware

    # actually reissue:
    python -m scripts.reissue_customer_invite --email judy@rh.example --tenant restoration-hardware --apply
    # (set PUBLIC_APP_URL to get a full invite link)

Exit codes: 0 ok (dry-run or reissued) · 1 refused (not eligible) · 2 error.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")
INVITE_TTL_DAYS = 7


def eligibility(user) -> str | None:
    """Return a refusal reason, or None when the user may be re-invited.

    Pure + deterministic (no DB) so every branch is unit-testable.  Eligible =
    an existing, INACTIVE, CUSTOMER_* user."""
    if user is None:
        return "no invite-pending customer user with this email in this tenant"
    if getattr(user, "is_active", False):
        return ("user is active — reissue is only for inactive (invite-pending) "
                "users; use a password-reset flow for an active account")
    role = (getattr(user, "role", "") or "")
    if not str(role).upper().startswith("CUSTOMER_"):
        return f"role '{role}' is not a customer-plane role — this tool is customer-only"
    return None


async def reissue(db, *, email: str, tenant: str, apply: bool) -> dict:
    """Look up the user (tenant-scoped), check eligibility, and — only with
    ``apply`` — mint a fresh invite token + expiry.  Never changes role / tenant /
    email / name / is_active.  Returns a structured result (no secrets except the
    new invite_token, which the caller surfaces only as a one-time link)."""
    from sqlalchemy import func, select

    from app.models.user import User
    from app.services.auth import generate_invite_token

    email = email.strip().lower()
    user = (await db.execute(
        select(User).where(func.lower(User.email) == email, User.tenant_id == tenant)
    )).scalar_one_or_none()

    reason = eligibility(user)
    if reason is not None:
        return {"status": "refused", "reason": reason, "email": email, "tenant": tenant}

    info = {"email": user.email, "role": user.role, "tenant": user.tenant_id,
            "is_active": bool(user.is_active)}
    if not apply:
        return {"status": "dry_run", **info}

    # Reissue ONLY the invite token + expiry.  Identity/role/tenant/activation
    # are deliberately left untouched.
    token = generate_invite_token()
    user.invite_token = token
    user.invite_expires_at = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)
    await db.commit()
    return {"status": "reissued", **info, "invite_token": token,
            "invite_expires_days": INVITE_TTL_DAYS}


async def _run(email: str, tenant: str, apply: bool) -> int:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await reissue(db, email=email, tenant=tenant, apply=apply)

    status = result["status"]
    if status == "refused":
        print(f"REFUSED: {result['reason']}")
        return 1

    print("Target (invite-pending customer user):")
    print(f"  email     : {result['email']}")
    print(f"  role      : {result['role']}   (unchanged)")
    print(f"  tenant    : {result['tenant']}   (unchanged)")
    print(f"  is_active : {result['is_active']}   (unchanged)")

    if status == "dry_run":
        print("\nDRY RUN — nothing written. Re-run with --apply to reissue the invite.")
        return 0

    base = os.environ.get("PUBLIC_APP_URL", "").rstrip("/")
    invite_path = f"/AuthGate?invite={result['invite_token']}"
    print("\nREISSUED (new invite minted; role/tenant/identity unchanged).")
    print("  Invite link (deliver OUT-OF-BAND; one-time, treat as sensitive):")
    print(f"    {base + invite_path if base else invite_path}")
    print(f"  Expires in {result['invite_expires_days']} days.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Reissue an invite for an inactive customer user (dry-run by default).")
    ap.add_argument("--email", required=True)
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    args = ap.parse_args()

    try:
        code = asyncio.run(_run(args.email, args.tenant, args.apply))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"ERROR: {type(exc).__name__}: {exc}")
        raise SystemExit(2)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
