#!/usr/bin/env python3
"""Consolidate operational data from ``tenant_id='restoration-hardware'``
into ``tenant_id='default'`` so the default tenant becomes the single
operational workspace for the onboarding team.

Defaults to DRY_RUN — no writes occur unless DRY_RUN=false is set.

Run:
    python -m scripts.consolidate_rh_to_default                # dry run
    DRY_RUN=false python -m scripts.consolidate_rh_to_default  # apply

Scope (per the approved Option-B plan)
--------------------------------------
* Direction: restoration-hardware → default (one-way).
* Moves the named operational entities and their tenant_id-bearing
  child records:

    sites, devices, sims, lines, service_units,
    incidents, events, notifications, notification_rules,
    escalation_rules, automation_rule, autonomous_action,
    command_activity, command_telemetry, e911_change_log,
    import_batch, infra_test, infra_test_result, job,
    line_intelligence_event, network_event, operational_digest,
    outbound_webhook, port_state, provider, provisioning_queue,
    recording, service_contract, site_template,
    site_vendor_assignments, subscription, support_sessions,
    support_diagnostics, support_escalations,
    support_remediation_actions, telemetry_event, vendor,
    verification_task

* **Does NOT move**:
    users           — explicit carve-out per spec.  Sivmey is already
                       on default; other RH-tenant users (if any) stay.
    audit_log_entries — historical audit records preserve their
                       original tenant context.
    action_audit    — same; this is an audit log of operator actions.
    customers       — customer rows are tenant-tier; default already
                       holds the operational customer set.

* Does NOT delete or deactivate ``restoration-hardware``.
* Single transaction.  On any unexpected error the entire move is
  rolled back and no audit row is written.

Pre-flight collision check
--------------------------
The only known per-tenant unique constraint that could collide on
merge is ``uq_lines_did_tenant`` on ``lines(did, tenant_id)``.  If a
DID exists on both sides, the script aborts before any write.
"""

import asyncio
import json
import os
import sys
from typing import Optional

# Make app.* importable when run as `python -m scripts.consolidate_rh_to_default`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from sqlalchemy import func, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.audit_log_entry import AuditLogEntry  # noqa: E402
from app.models.line import Line  # noqa: E402  — used by DID collision check
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402  — used for the Sivmey row check
from app.services.tenant_registry import tenant_models  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────
FROM_TENANT = "restoration-hardware"
TO_TENANT = "default"
PROTECTED_TENANTS = {"default"}  # never used as FROM, even if edited

_DRY_ENV = os.environ.get("DRY_RUN", "true").strip().lower()
DRY_RUN = _DRY_ENV not in ("0", "false", "no", "off")

# Tables we deliberately leave alone per the approved Option-B spec.
# Each entry has a one-line rationale so the carve-out can't drift
# into "I forgot why this was excluded" territory.
_HANDS_OFF_RATIONALE: dict[str, str] = {
    "users":             "explicit carve-out — Sivmey already on default",
    "audit_log_entries": "audit history preserves original tenant",
    "action_audits":     "audit family — same reason as audit_log_entries",
    "customers":         "tenant-tier; default already holds the operational set",
}
_EXCLUDE_TABLES: set[str] = set(_HANDS_OFF_RATIONALE)

# Auto-discovered list of (table_name, mapped_class) for every model
# with a ``tenant_id`` column, minus our explicit exclusions.  See
# app.services.tenant_registry for how discovery works.
TENANT_TABLES: list[tuple[str, type]] = [
    (name, cls) for (name, cls) in tenant_models()
    if name not in _EXCLUDE_TABLES
]
_HANDS_OFF_TABLES: list[tuple[str, type, str]] = [
    (name, cls, _HANDS_OFF_RATIONALE[name])
    for (name, cls) in tenant_models()
    if name in _EXCLUDE_TABLES
]


# ── Helpers ───────────────────────────────────────────────────────────
def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def _section(text: str) -> None:
    print()
    print(f"── {text} " + "─" * max(1, 74 - len(text)))


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
    uq_lines_did_tenant after the merge."""
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


async def _table_counts(db: AsyncSession, slug: str, tables) -> dict[str, int]:
    return {label: await _count(db, model, slug) for label, model in tables}


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
    if FROM_TENANT == TO_TENANT:
        print("ERROR: FROM_TENANT and TO_TENANT are the same. Refusing.")
        return 2
    if FROM_TENANT in PROTECTED_TENANTS:
        print(
            f"ERROR: refusing to use protected tenant as FROM_TENANT "
            f"({FROM_TENANT!r})."
        )
        return 2

    mode = "DRY RUN — no writes will occur" if DRY_RUN else "APPLY MODE — changes WILL be written"
    _banner(mode)
    print(f"  FROM_TENANT  = {FROM_TENANT!r}")
    print(f"  TO_TENANT    = {TO_TENANT!r}")
    print(f"  PROTECTED    = {sorted(PROTECTED_TENANTS)}")
    print(f"  movable      = {len(TENANT_TABLES)} tables (auto-discovered)")
    print(f"  hands-off    = {sorted(_EXCLUDE_TABLES)}")

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
            print(f"ERROR: tenant(s) not found: {missing}. Refusing to run.")
            return 2

        print(
            f"  source: tenant_id={from_t.tenant_id!r}  "
            f"name={from_t.name!r}  display_name={from_t.display_name!r}  "
            f"is_active={from_t.is_active}"
        )
        print(
            f"  target: tenant_id={to_t.tenant_id!r}  "
            f"name={to_t.name!r}  display_name={to_t.display_name!r}  "
            f"is_active={to_t.is_active}"
        )

        # ── BEFORE: counts on each side ─────────────────────────────
        _section("BEFORE — record counts (tables we MOVE)")
        before_from = await _table_counts(db, FROM_TENANT, TENANT_TABLES)
        before_to = await _table_counts(db, TO_TENANT, TENANT_TABLES)
        _print_counts(f"tenant {FROM_TENANT!r} (source)", before_from)
        _print_counts(f"tenant {TO_TENANT!r} (target)", before_to)

        _section("BEFORE — record counts (tables we LEAVE)")
        before_handsoff_from = await _table_counts(
            db, FROM_TENANT, [(lbl, m) for lbl, m, _ in _HANDS_OFF_TABLES],
        )
        for label, _model, reason in _HANDS_OFF_TABLES:
            n = before_handsoff_from.get(label, 0)
            print(f"  [hands-off] {label:<22}  rows on {FROM_TENANT!r}={n:>4}  ({reason})")

        # Sivmey-specific check
        sivmey_q = await db.execute(
            select(User).where(func.lower(User.email) == "sivmey@manleysolutions.com")
        )
        sivmey = sivmey_q.scalar_one_or_none()
        if sivmey:
            print(
                f"  [user-check] sivmey@manleysolutions.com  "
                f"tenant_id={sivmey.tenant_id!r}  is_active={sivmey.is_active}  "
                f"role={sivmey.role!r}"
            )
        else:
            print("  [user-check] sivmey@manleysolutions.com NOT FOUND")

        # ── Pre-flight: per-tenant unique-constraint collisions ──────
        _section("Pre-flight collision check")
        did_collisions = await _check_did_collisions(db)
        if did_collisions:
            print(
                f"ERROR: {len(did_collisions)} DID(s) exist on both tenants. "
                "Merging would violate uq_lines_did_tenant. Refusing to apply:"
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
            f"{len(nonzero_tables)} table(s) from "
            f"tenant_id {FROM_TENANT!r} -> {TO_TENANT!r}:"
        )
        if nonzero_tables:
            width = max(len(k) for k in nonzero_tables)
            for table in sorted(nonzero_tables):
                print(f"    {table:<{width}}  {nonzero_tables[table]:>6}")
        else:
            print("    (no row updates needed — tenant has no movable data)")
        print()
        print("  Tenants are NOT deactivated.  No tenant rows are deleted.")
        print(
            f"  '{FROM_TENANT}' will keep is_active and display_name "
            "exactly as they are now."
        )

        if DRY_RUN:
            _banner("DRY RUN complete — no writes were performed")
            print("  Re-run with DRY_RUN=false to apply.")
            return 0

        if total_rows_to_move == 0:
            _banner("APPLY: nothing to do — exiting cleanly")
            return 0

        # ── Apply (single transaction, single commit) ───────────────
        # Anything that raises inside this block triggers an automatic
        # rollback via SQLAlchemy's session lifecycle — no partial moves.
        try:
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
                print(f"  updated {label:<28}  rows={moved[label]}")

            audit = AuditLogEntry(
                entry_id=f"consolidate-{FROM_TENANT}-to-{TO_TENANT}",
                tenant_id=TO_TENANT,
                category="security",
                action="consolidate_to_operational_tenant",
                actor="consolidate_script",
                target_type="tenant",
                target_id=TO_TENANT,
                summary=(
                    f"Consolidated operational data from tenant {FROM_TENANT!r} "
                    f"into {TO_TENANT!r} ({sum(moved.values())} rows moved across "
                    f"{len(moved)} table(s)).  Source tenant kept active."
                ),
                detail_json=json.dumps({
                    "from_tenant": FROM_TENANT,
                    "to_tenant": TO_TENANT,
                    "before_from_counts": before_from,
                    "before_to_counts": before_to,
                    "before_handsoff_from_counts": before_handsoff_from,
                    "moved": moved,
                    "did_collisions": did_collisions,
                    "users_moved": False,
                    "audit_logs_moved": False,
                    "source_tenant_deactivated": False,
                    "script": "scripts/consolidate_rh_to_default.py",
                }),
            )
            db.add(audit)
            await db.commit()
        except Exception:
            # Roll back the entire apply on any error so we never leave
            # the database in a half-moved state.
            await db.rollback()
            print()
            print("ERROR: apply failed — rolled back.  Re-raising.")
            raise

        # ── AFTER ────────────────────────────────────────────────────
        _section("AFTER — record counts (tables we MOVE)")
        after_from = await _table_counts(db, FROM_TENANT, TENANT_TABLES)
        after_to = await _table_counts(db, TO_TENANT, TENANT_TABLES)
        _print_counts(f"tenant {FROM_TENANT!r} (source)", after_from)
        _print_counts(f"tenant {TO_TENANT!r} (target)", after_to)

        _banner("APPLY complete — audit row written")
        print(f"  audit entry_id: {audit.entry_id}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
