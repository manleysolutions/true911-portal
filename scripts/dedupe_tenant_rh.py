#!/usr/bin/env python3
"""Non-destructive merge of duplicate tenant ``rh`` into canonical
``restoration-hardware``.

This script does NOT delete the ``rh`` row.  It re-points every record that
references ``tenant_id='rh'`` to ``tenant_id='restoration-hardware'``,
then marks the duplicate tenant inactive with a renamed display_name.

Defaults to DRY_RUN — no writes occur unless DRY_RUN=false is set.

Run:
    python -m scripts.dedupe_tenant_rh                       # dry run
    DRY_RUN=false python -m scripts.dedupe_tenant_rh         # apply

Refuses to run if either tenant is missing.  Never touches the ``default``
tenant or any other tenant.

Pre-flight collision check
--------------------------
The only known per-tenant unique constraint that could collide on merge is
``uq_lines_did_tenant`` on ``lines(did, tenant_id)``.  If a DID exists on
both sides, the script aborts before any write.
"""

import asyncio
import json
import os
import sys
from typing import Optional

# Make app.* importable when run as `python -m scripts.dedupe_tenant_rh`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from sqlalchemy import func, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.audit_log_entry import AuditLogEntry  # noqa: E402
from app.models.line import Line  # noqa: E402  — used by DID collision check
from app.models.tenant import Tenant  # noqa: E402
from app.services.tenant_registry import tenant_models  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────
FROM_TENANT = "rh"
TO_TENANT = "restoration-hardware"
DUPLICATE_DISPLAY_NAME = "Restoration Hardware (duplicate - inactive)"
PROTECTED_TENANTS = {"default"}  # never touched even if listed accidentally

_DRY_ENV = os.environ.get("DRY_RUN", "true").strip().lower()
DRY_RUN = _DRY_ENV not in ("0", "false", "no", "off")

# Tables we deliberately leave alone.  ``audit_log_entries`` records
# historical actor/tenant context — rewriting it would falsify audit
# history.  Every other tenant_id-bearing model gets moved.
_EXCLUDE_TABLES = {"audit_log_entries"}

# Auto-discovered list of (table_name, mapped_class) for every model
# with a ``tenant_id`` column, minus our explicit exclusions.  See
# app.services.tenant_registry for how discovery works.
TENANT_TABLES: list[tuple[str, type]] = [
    (name, cls) for (name, cls) in tenant_models()
    if name not in _EXCLUDE_TABLES
]


# ── Helpers ───────────────────────────────────────────────────────────
def _banner(text: str) -> None:
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def _section(text: str) -> None:
    print()
    print(f"── {text} " + "─" * max(1, 68 - len(text)))


async def _count(db: AsyncSession, model: type, slug: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(model.tenant_id == slug)
    )
    return int(result.scalar_one() or 0)


async def _resolve_tenant(db: AsyncSession, slug: str) -> Optional[Tenant]:
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == slug))
    return result.scalar_one_or_none()


async def _check_did_collisions(db: AsyncSession) -> list[str]:
    """Return DIDs that exist on both tenants — would violate
    uq_lines_did_tenant after the merge.
    """
    sub_from = (
        select(Line.did)
        .where(Line.tenant_id == FROM_TENANT, Line.did.isnot(None))
        .subquery()
    )
    sub_to = (
        select(Line.did)
        .where(Line.tenant_id == TO_TENANT, Line.did.isnot(None))
        .subquery()
    )
    result = await db.execute(
        select(sub_from.c.did).where(sub_from.c.did.in_(select(sub_to.c.did)))
    )
    return [row[0] for row in result.all()]


async def _table_counts(db: AsyncSession, slug: str) -> dict[str, int]:
    """Per-table count of records with tenant_id = slug.  Skips zero rows
    in the printed output, but the dict always contains every table for
    the audit detail.
    """
    return {
        label: await _count(db, model, slug)
        for label, model in TENANT_TABLES
    }


def _print_counts(label: str, counts: dict[str, int]) -> None:
    nonzero = {k: v for k, v in counts.items() if v}
    total = sum(counts.values())
    print(f"  [{label}] total rows: {total}")
    if not nonzero:
        print("    (no records)")
        return
    width = max(len(k) for k in nonzero)
    for table in sorted(nonzero):
        print(f"    {table:<{width}}  {nonzero[table]:>6}")


# ── Main ──────────────────────────────────────────────────────────────
async def main() -> int:
    if FROM_TENANT in PROTECTED_TENANTS or TO_TENANT in PROTECTED_TENANTS:
        print(
            f"ERROR: refusing to operate on protected tenant "
            f"({PROTECTED_TENANTS})."
        )
        return 2

    if FROM_TENANT == TO_TENANT:
        print("ERROR: FROM_TENANT and TO_TENANT are the same. Refusing.")
        return 2

    mode = "DRY RUN — no writes will occur" if DRY_RUN else "APPLY MODE — changes WILL be written"
    _banner(mode)
    print(f"  FROM_TENANT (duplicate)  = {FROM_TENANT!r}")
    print(f"  TO_TENANT   (canonical)  = {TO_TENANT!r}")
    print(f"  PROTECTED                = {sorted(PROTECTED_TENANTS)}")
    print(f"  movable tables           = {len(TENANT_TABLES)}  "
          f"(auto-discovered; excluded={sorted(_EXCLUDE_TABLES)})")

    async with AsyncSessionLocal() as db:
        _section("Resolving tenants")
        from_t = await _resolve_tenant(db, FROM_TENANT)
        to_t = await _resolve_tenant(db, TO_TENANT)

        missing = []
        if not from_t:
            missing.append(FROM_TENANT)
        if not to_t:
            missing.append(TO_TENANT)
        if missing:
            print(
                f"ERROR: tenant(s) not found: {missing}. "
                "Refusing to run."
            )
            return 2

        print(
            f"  duplicate: tenant_id={from_t.tenant_id!r}  "
            f"name={from_t.name!r}  display_name={from_t.display_name!r}  "
            f"is_active={from_t.is_active}"
        )
        print(
            f"  canonical: tenant_id={to_t.tenant_id!r}  "
            f"name={to_t.name!r}  display_name={to_t.display_name!r}  "
            f"is_active={to_t.is_active}"
        )

        _section("BEFORE — record counts on each tenant")
        before_from = await _table_counts(db, FROM_TENANT)
        before_to = await _table_counts(db, TO_TENANT)
        _print_counts(f"tenant {FROM_TENANT!r} (duplicate)", before_from)
        _print_counts(f"tenant {TO_TENANT!r} (canonical)", before_to)

        # ── Pre-flight: per-tenant unique-constraint collisions ──────
        _section("Pre-flight collision check")
        did_collisions = await _check_did_collisions(db)
        if did_collisions:
            print(
                f"ERROR: {len(did_collisions)} DID(s) exist on both tenants. "
                "Merging would violate uq_lines_did_tenant. "
                "Refusing to apply:"
            )
            for d in did_collisions:
                print(f"   did={d!r}")
            return 2
        print("  no DID collisions detected")

        # ── Compute proposed updates ────────────────────────────────
        nonzero_tables = {k: v for k, v in before_from.items() if v}
        total_rows_to_move = sum(nonzero_tables.values())

        _section("Proposed changes")
        print(
            f"  Move {total_rows_to_move} row(s) across "
            f"{len(nonzero_tables)} table(s):"
        )
        if nonzero_tables:
            width = max(len(k) for k in nonzero_tables)
            for table in sorted(nonzero_tables):
                print(
                    f"    {table:<{width}}  {nonzero_tables[table]:>6}  "
                    f"tenant_id {FROM_TENANT!r} -> {TO_TENANT!r}"
                )
        else:
            print("    (no row updates needed)")

        if from_t.is_active or from_t.display_name != DUPLICATE_DISPLAY_NAME:
            print(
                "  Mark duplicate tenant inactive:"
                f"\n    tenants.is_active     : {from_t.is_active} -> False"
                f"\n    tenants.display_name  : {from_t.display_name!r} -> {DUPLICATE_DISPLAY_NAME!r}"
            )
        else:
            print("  Duplicate tenant already marked inactive — no tenant-row change.")

        if DRY_RUN:
            _banner("DRY RUN complete — no writes were performed")
            print("  Re-run with DRY_RUN=false to apply.")
            return 0

        if total_rows_to_move == 0 and not from_t.is_active and from_t.display_name == DUPLICATE_DISPLAY_NAME:
            _banner("APPLY: nothing to do — exiting cleanly")
            return 0

        # ── Apply (single transaction) ──────────────────────────────
        _section("Applying changes")
        moved: dict[str, int] = {}
        for label, model in TENANT_TABLES:
            if before_from.get(label, 0) == 0:
                continue
            result = await db.execute(
                update(model)
                .where(model.tenant_id == FROM_TENANT)
                .values(tenant_id=TO_TENANT)
            )
            moved[label] = result.rowcount or 0
            print(f"  updated {label:<24}  rows={moved[label]}")

        # Mark duplicate tenant inactive
        from_t.is_active = False
        from_t.display_name = DUPLICATE_DISPLAY_NAME

        # Audit row, scoped to canonical tenant so it appears in normal scoping.
        audit = AuditLogEntry(
            entry_id=f"tenant-dedupe-{FROM_TENANT}-{TO_TENANT}",
            tenant_id=TO_TENANT,
            category="security",
            action="tenant_dedupe",
            actor="dedupe_script",
            target_type="tenant",
            target_id=TO_TENANT,
            summary=(
                f"Merged duplicate tenant {FROM_TENANT!r} into "
                f"{TO_TENANT!r}; marked duplicate inactive."
            ),
            detail_json=json.dumps({
                "from_tenant": FROM_TENANT,
                "to_tenant": TO_TENANT,
                "duplicate_display_name": DUPLICATE_DISPLAY_NAME,
                "before_from_counts": before_from,
                "before_to_counts": before_to,
                "moved": moved,
                "did_collisions": did_collisions,
                "script": "scripts/dedupe_tenant_rh.py",
            }),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(from_t)
        await db.refresh(to_t)

        # ── After ────────────────────────────────────────────────────
        _section("AFTER — record counts on each tenant")
        after_from = await _table_counts(db, FROM_TENANT)
        after_to = await _table_counts(db, TO_TENANT)
        _print_counts(f"tenant {FROM_TENANT!r} (duplicate)", after_from)
        _print_counts(f"tenant {TO_TENANT!r} (canonical)", after_to)

        print(
            f"  duplicate tenant: is_active={from_t.is_active}  "
            f"display_name={from_t.display_name!r}"
        )

        _banner("APPLY complete — audit row written")
        print(f"  audit entry_id: {audit.entry_id}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
