#!/usr/bin/env python3
"""Non-destructive tenant/site/device relationship repair.

Targets a single, known data mismatch where a device + site are attached to
the wrong tenant slug.  Defaults to DRY_RUN — no writes happen unless
DRY_RUN=false is explicitly passed.

Run:
    python -m scripts.repair_device_tenant                       # dry run
    DRY_RUN=false python -m scripts.repair_device_tenant         # apply
    DRY_RUN=false TENANT_SLUG=<slug> python -m scripts.repair_device_tenant

Notes
-----
* This codebase joins by the **slug** column ``Tenant.tenant_id`` (not the
  numeric ``Tenant.id``).  ``Site.tenant_id`` and ``Device.tenant_id`` are
  string slugs that must equal ``Tenant.tenant_id``.
* ``Device.site_id`` is the **site slug** (``Site.site_id``), not the
  numeric ``Site.id``.  The original task spec wrote
  ``device.site_id != site.id`` — that's a slug field on both sides, so the
  comparison this script performs is ``device.site_id != site.site_id``.
* The script only updates fields that are *currently* mismatched.  No
  records are deleted or recreated.  Incidents, audits, compliance,
  service units, SIMs, and voice lines are not touched.
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

# Make app.* importable when run as `python -m scripts.repair_device_tenant`
# from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from sqlalchemy import or_, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.audit_log_entry import AuditLogEntry  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────
DEVICE_ID = "13864"
STARLINK_ID = "10719648"
SITE_ID = "SITE-1776962330831"
SITE_NAME_HINT = "Vero Beach"
TENANT_NAME_HINT = "Restoration Hardware"

# Optional override; if set, exact tenant_id slug match is used and the
# fuzzy display_name/name lookup is skipped.
TENANT_SLUG: Optional[str] = os.environ.get("TENANT_SLUG") or None

# DRY_RUN=true (default) | DRY_RUN=false
_DRY_ENV = os.environ.get("DRY_RUN", "true").strip().lower()
DRY_RUN = _DRY_ENV not in ("0", "false", "no", "off")


# ── Helpers ───────────────────────────────────────────────────────────
def _banner(text: str) -> None:
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def _section(text: str) -> None:
    print()
    print(f"── {text} " + "─" * (68 - len(text)))


@dataclass
class Snapshot:
    """Compact view of the three records before/after."""
    tenant_slug: Optional[str] = None
    tenant_name: Optional[str] = None
    site_slug: Optional[str] = None
    site_name: Optional[str] = None
    site_tenant_id: Optional[str] = None
    device_id: Optional[str] = None
    device_tenant_id: Optional[str] = None
    device_site_id: Optional[str] = None
    device_starlink_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _print_state(label: str, snap: Snapshot) -> None:
    print(f"  [{label}]")
    print(f"    tenant.slug          = {snap.tenant_slug!r}  ({snap.tenant_name})")
    print(f"    site.site_id         = {snap.site_slug!r}  ({snap.site_name})")
    print(f"    site.tenant_id       = {snap.site_tenant_id!r}")
    print(f"    device.device_id     = {snap.device_id!r}")
    print(f"    device.starlink_id   = {snap.device_starlink_id!r}")
    print(f"    device.tenant_id     = {snap.device_tenant_id!r}")
    print(f"    device.site_id       = {snap.device_site_id!r}")


# ── Lookups ───────────────────────────────────────────────────────────
async def _resolve_tenant(db: AsyncSession) -> Tenant:
    """Resolve the target tenant.

    Priority:
      1. If TENANT_SLUG is set, exact match on tenant_id.
      2. Else fuzzy match on display_name OR name (ILIKE '%hint%')
         restricted to is_active = true.
      Exits if 0 or >1 candidates remain.
    """
    if TENANT_SLUG:
        result = await db.execute(
            select(Tenant).where(Tenant.tenant_id == TENANT_SLUG)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            print(f"ERROR: TENANT_SLUG={TENANT_SLUG!r} not found.")
            sys.exit(2)
        if not tenant.is_active:
            print(
                f"ERROR: Tenant {tenant.tenant_id!r} ({tenant.name!r}) is inactive. "
                "Refusing to repair against an inactive tenant."
            )
            sys.exit(2)
        return tenant

    pattern = f"%{TENANT_NAME_HINT}%"
    result = await db.execute(
        select(Tenant).where(
            or_(
                Tenant.display_name.ilike(pattern),
                Tenant.name.ilike(pattern),
            ),
            Tenant.is_active == True,  # noqa: E712  (SQLAlchemy idiom)
        )
    )
    tenants = result.scalars().all()
    if not tenants:
        print(
            f"ERROR: No active tenant matches "
            f"(display_name OR name) ILIKE {pattern!r}.\n"
            "Hint: pass an explicit slug via TENANT_SLUG=<slug>."
        )
        sys.exit(2)
    if len(tenants) > 1:
        print(
            f"ERROR: {len(tenants)} active tenants match {pattern!r}. "
            "Refusing to guess. Re-run with TENANT_SLUG=<slug>:"
        )
        for t in tenants:
            print(
                f"   tenant_id={t.tenant_id!r}  "
                f"name={t.name!r}  display_name={t.display_name!r}"
            )
        sys.exit(2)
    return tenants[0]


async def _resolve_site(db: AsyncSession) -> Site:
    pattern = f"%{SITE_NAME_HINT}%"
    result = await db.execute(
        select(Site).where(
            or_(
                Site.site_id == SITE_ID,
                Site.site_name.ilike(pattern),
            )
        )
    )
    sites = result.scalars().all()
    if not sites:
        print(
            f"ERROR: No site matches site_id={SITE_ID!r} or "
            f"site_name ILIKE {pattern!r}."
        )
        sys.exit(2)
    if len(sites) > 1:
        # Try to disambiguate by exact site_id slug match.
        exact = [s for s in sites if s.site_id == SITE_ID]
        if len(exact) == 1:
            return exact[0]
        print(
            f"ERROR: {len(sites)} sites matched the lookup. "
            "Refusing to guess:"
        )
        for s in sites:
            print(
                f"   site_id={s.site_id!r}  site_name={s.site_name!r}  "
                f"tenant_id={s.tenant_id!r}"
            )
        sys.exit(2)
    return sites[0]


async def _resolve_device(db: AsyncSession) -> Device:
    result = await db.execute(
        select(Device).where(
            or_(
                Device.device_id == DEVICE_ID,
                Device.starlink_id == STARLINK_ID,
            )
        )
    )
    devices = result.scalars().all()
    if not devices:
        print(
            f"ERROR: No device matches device_id={DEVICE_ID!r} or "
            f"starlink_id={STARLINK_ID!r}."
        )
        sys.exit(2)
    if len(devices) > 1:
        # Disambiguate by exact device_id slug match.
        exact = [d for d in devices if d.device_id == DEVICE_ID]
        if len(exact) == 1:
            return exact[0]
        print(
            f"ERROR: {len(devices)} devices matched the lookup. "
            "Refusing to guess:"
        )
        for d in devices:
            print(
                f"   device_id={d.device_id!r}  starlink_id={d.starlink_id!r}  "
                f"tenant_id={d.tenant_id!r}  site_id={d.site_id!r}"
            )
        sys.exit(2)
    return devices[0]


def _snapshot(tenant: Tenant, site: Site, device: Device) -> Snapshot:
    return Snapshot(
        tenant_slug=tenant.tenant_id,
        tenant_name=tenant.display_name or tenant.name,
        site_slug=site.site_id,
        site_name=site.site_name,
        site_tenant_id=site.tenant_id,
        device_id=device.device_id,
        device_tenant_id=device.tenant_id,
        device_site_id=device.site_id,
        device_starlink_id=device.starlink_id,
    )


# ── Main ──────────────────────────────────────────────────────────────
async def main() -> int:
    mode = "DRY RUN — no writes will occur" if DRY_RUN else "APPLY MODE — changes WILL be written"
    _banner(mode)
    print(f"  TENANT_NAME_HINT = {TENANT_NAME_HINT!r}")
    print(f"  TENANT_SLUG override = {TENANT_SLUG!r}")
    print(f"  SITE_ID = {SITE_ID!r}, SITE_NAME_HINT = {SITE_NAME_HINT!r}")
    print(f"  DEVICE_ID = {DEVICE_ID!r}, STARLINK_ID = {STARLINK_ID!r}")

    async with AsyncSessionLocal() as db:
        _section("Resolving target records")
        tenant = await _resolve_tenant(db)
        print(
            f"  tenant: tenant_id={tenant.tenant_id!r}  "
            f"name={tenant.name!r}  display_name={tenant.display_name!r}  "
            f"is_active={tenant.is_active}"
        )
        site = await _resolve_site(db)
        print(
            f"  site:   site_id={site.site_id!r}  "
            f"site_name={site.site_name!r}  tenant_id={site.tenant_id!r}"
        )
        device = await _resolve_device(db)
        print(
            f"  device: device_id={device.device_id!r}  "
            f"starlink_id={device.starlink_id!r}  "
            f"tenant_id={device.tenant_id!r}  site_id={device.site_id!r}"
        )

        before = _snapshot(tenant, site, device)
        _section("BEFORE")
        _print_state("before", before)

        # ── Compute proposed changes ────────────────────────────────
        target_tenant = tenant.tenant_id
        target_site_slug = site.site_id

        changes: list[tuple[str, str, str]] = []  # (entity.field, old, new)
        if site.tenant_id != target_tenant:
            changes.append(("site.tenant_id", site.tenant_id, target_tenant))
        if device.tenant_id != target_tenant:
            changes.append(("device.tenant_id", device.tenant_id, target_tenant))
        if device.site_id != target_site_slug:
            changes.append(("device.site_id", device.site_id, target_site_slug))

        _section("Proposed changes")
        if not changes:
            print("  (no changes — all relationships are already correct)")
        else:
            for field, old, new in changes:
                print(f"  {field}: {old!r}  ->  {new!r}")

        if DRY_RUN:
            _banner("DRY RUN complete — no writes were performed")
            print("  Re-run with DRY_RUN=false to apply.")
            return 0

        if not changes:
            _banner("APPLY: nothing to do — exiting cleanly")
            return 0

        # ── Apply (single transaction) ──────────────────────────────
        _section("Applying changes")
        if site.tenant_id != target_tenant:
            site.tenant_id = target_tenant
        if device.tenant_id != target_tenant:
            device.tenant_id = target_tenant
        if device.site_id != target_site_slug:
            device.site_id = target_site_slug

        # Audit log on the target tenant so it's visible in normal scoping.
        audit = AuditLogEntry(
            entry_id=f"manual-tenant-repair-{device.device_id}",
            tenant_id=target_tenant,
            category="security",
            action="manual_tenant_repair",
            actor="repair_script",
            target_type="device",
            target_id=DEVICE_ID,
            site_id=site.site_id,
            device_id=device.device_id,
            summary=(
                f"Repaired tenant/site linkage for device {device.device_id} "
                f"(starlink_id={device.starlink_id}) to tenant "
                f"{target_tenant!r} / site {site.site_id!r}."
            ),
            detail_json=json.dumps({
                "tenant_slug": target_tenant,
                "tenant_name": tenant.name,
                "site_id": site.site_id,
                "site_name": site.site_name,
                "device_id": device.device_id,
                "starlink_id": device.starlink_id,
                "before": before.to_dict(),
                "changes": [
                    {"field": f, "old": o, "new": n} for f, o, n in changes
                ],
                "dry_run": False,
                "script": "scripts/repair_device_tenant.py",
            }),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(site)
        await db.refresh(device)

        after = _snapshot(tenant, site, device)
        _section("AFTER")
        _print_state("after", after)

        _banner("APPLY complete — audit row written")
        print(f"  audit entry_id: {audit.entry_id}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
