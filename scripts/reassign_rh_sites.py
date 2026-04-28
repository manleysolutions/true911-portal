#!/usr/bin/env python3
"""Bulk-reassign Restoration Hardware sites from tenant_id='default' to
tenant_id='restoration-hardware', along with their linked devices,
service units, SIMs, and voice lines.

Defaults to DRY_RUN — no writes occur unless DRY_RUN=false is set.

Run:
    python -m scripts.reassign_rh_sites                  # dry run
    DRY_RUN=false python -m scripts.reassign_rh_sites    # apply

Matching rules
--------------
Two patterns are accepted, both restricted to ``site.tenant_id =
'default'``:

  Pattern A — strong: ``site_name ILIKE 'Restoration Hardware%'``
  Pattern B — prefix: ``site_name ILIKE 'RH %'`` AND the
              ``customer_name`` clearly identifies Restoration Hardware
              (contains "restoration hardware" or starts with "RH ").

Per rule 15, any pattern-matched site whose ``customer_name`` is set
but does not pass the customer ownership check is treated as
**ambiguous** and the script refuses to run.  Sites with empty
``customer_name`` are allowed and flagged in the report.

Updates applied
---------------
Per rule 9, ``tenant_id`` is moved from 'default' to
'restoration-hardware' on:

  - sites (the matched set itself)
  - devices where ``device.site_id`` ∈ moved_site_ids AND
    ``device.tenant_id == 'default'``
  - service_units where ``service_unit.site_id`` ∈ moved_site_ids AND
    ``service_unit.tenant_id == 'default'``
  - sims where ``sim.site_id`` ∈ moved_site_ids AND
    ``sim.tenant_id == 'default'``
  - lines where ``line.site_id`` ∈ moved_site_ids AND
    ``line.tenant_id == 'default'``

Per rule 8, linked **incidents**, **events**, and **notifications**
are *detected and counted* but not moved (per the explicit "Proposed
changes" list in rule 9).  After-summary lists how many of each
remain on the FROM tenant so the operator can decide whether a
follow-up move is needed.
"""

import asyncio
import json
import os
import sys
from typing import Optional

# Make app.* importable when run as `python -m scripts.reassign_rh_sites`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from sqlalchemy import func, or_, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.audit_log_entry import AuditLogEntry  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.event import Event  # noqa: E402
from app.models.incident import Incident  # noqa: E402
from app.models.line import Line  # noqa: E402
from app.models.notification import CommandNotification  # noqa: E402
from app.models.service_unit import ServiceUnit  # noqa: E402
from app.models.sim import Sim  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────
FROM_TENANT = "default"
TO_TENANT = "restoration-hardware"
PROTECTED_TENANTS = {"default"}  # never used as TO_TENANT, even if edited

_DRY_ENV = os.environ.get("DRY_RUN", "true").strip().lower()
DRY_RUN = _DRY_ENV not in ("0", "false", "no", "off")

# Models whose tenant_id we move when their site_id is in the matched set.
LINKED_MOVE_MODELS: list[tuple[str, type]] = [
    ("devices", Device),
    ("service_units", ServiceUnit),
    ("sims", Sim),
    ("lines", Line),
]

# Models we count but do not move (per the "Proposed changes" list).
LINKED_DETECT_MODELS: list[tuple[str, type]] = [
    ("incidents", Incident),
    ("events", Event),
    ("notifications", CommandNotification),
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


def _is_rh_customer(name: Optional[str]) -> bool:
    """Strong check that a customer_name refers to Restoration Hardware."""
    if not name:
        return False
    n = name.strip().lower()
    if "restoration hardware" in n:
        return True
    if n == "rh" or n.startswith("rh ") or n.startswith("rh-") or n.startswith("rh,"):
        return True
    return False


async def _count_for_site_ids(
    db: AsyncSession,
    model: type,
    site_ids: list[str],
    tenant_id: Optional[str] = None,
) -> int:
    if not site_ids:
        return 0
    q = select(func.count()).select_from(model).where(model.site_id.in_(site_ids))
    if tenant_id is not None:
        q = q.where(model.tenant_id == tenant_id)
    result = await db.execute(q)
    return int(result.scalar_one() or 0)


async def _resolve_to_tenant(db: AsyncSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == TO_TENANT))
    tenant = result.scalar_one_or_none()
    if not tenant:
        print(f"ERROR: TO_TENANT {TO_TENANT!r} does not exist. Refusing.")
        sys.exit(2)
    if not tenant.is_active:
        print(
            f"ERROR: TO_TENANT {TO_TENANT!r} ({tenant.name!r}) is inactive. "
            "Refusing to reassign into an inactive tenant."
        )
        sys.exit(2)
    return tenant


async def _find_candidate_sites(db: AsyncSession) -> list[Site]:
    """Return sites on FROM_TENANT whose site_name matches Pattern A or B."""
    result = await db.execute(
        select(Site)
        .where(Site.tenant_id == FROM_TENANT)
        .where(
            or_(
                Site.site_name.ilike("Restoration Hardware%"),
                Site.site_name.ilike("RH %"),
            )
        )
        .order_by(Site.site_name)
    )
    return list(result.scalars().all())


# ── Main ──────────────────────────────────────────────────────────────
async def main() -> int:
    if FROM_TENANT == TO_TENANT:
        print("ERROR: FROM_TENANT and TO_TENANT are the same. Refusing.")
        return 2
    if TO_TENANT in PROTECTED_TENANTS:
        print(f"ERROR: refusing to use protected tenant as TO_TENANT ({TO_TENANT!r}).")
        return 2

    mode = "DRY RUN — no writes will occur" if DRY_RUN else "APPLY MODE — changes WILL be written"
    _banner(mode)
    print(f"  FROM_TENANT = {FROM_TENANT!r}")
    print(f"  TO_TENANT   = {TO_TENANT!r}")

    async with AsyncSessionLocal() as db:
        _section("Resolving target tenant")
        to_tenant = await _resolve_to_tenant(db)
        print(
            f"  TO_TENANT: tenant_id={to_tenant.tenant_id!r}  "
            f"name={to_tenant.name!r}  is_active={to_tenant.is_active}"
        )

        _section("Scanning candidate sites on FROM_TENANT")
        candidates = await _find_candidate_sites(db)
        print(f"  matched {len(candidates)} site(s) on tenant {FROM_TENANT!r}")
        if not candidates:
            _banner("Nothing to do — no candidate sites found")
            return 0

        # ── Per-site report + ambiguity classification ──────────────
        confident: list[Site] = []
        ambiguous: list[tuple[Site, str]] = []
        empty_customer: list[Site] = []

        _section("Per-site report")
        for s in candidates:
            name = s.site_name or ""
            cust = (s.customer_name or "").strip()
            pattern = (
                "A (Restoration Hardware*)"
                if name.lower().startswith("restoration hardware")
                else "B (RH *)"
            )

            dev = await _count_for_site_ids(db, Device, [s.site_id], FROM_TENANT)
            su = await _count_for_site_ids(db, ServiceUnit, [s.site_id], FROM_TENANT)
            sim = await _count_for_site_ids(db, Sim, [s.site_id], FROM_TENANT)
            line = await _count_for_site_ids(db, Line, [s.site_id], FROM_TENANT)

            address_parts = [
                s.e911_street, s.e911_city, s.e911_state, s.e911_zip
            ]
            address = ", ".join(p for p in address_parts if p) or "(no address)"

            print(
                f"  - site_id={s.site_id!r}  pattern={pattern}\n"
                f"    site_name      = {s.site_name!r}\n"
                f"    customer_name  = {s.customer_name!r}\n"
                f"    tenant_id      = {s.tenant_id!r}\n"
                f"    address        = {address}\n"
                f"    devices        = {dev}\n"
                f"    service_units  = {su}\n"
                f"    sims           = {sim}\n"
                f"    voice_lines    = {line}"
            )

            if not cust:
                empty_customer.append(s)
                confident.append(s)
                continue
            if _is_rh_customer(cust):
                confident.append(s)
            else:
                ambiguous.append((s, cust))

        # ── Refuse on ambiguity ─────────────────────────────────────
        if ambiguous:
            _section("Ambiguous customer ownership detected — refusing to apply")
            for s, cust in ambiguous:
                print(
                    f"  - site_id={s.site_id!r}  site_name={s.site_name!r}  "
                    f"customer_name={cust!r}  ← does not look like Restoration Hardware"
                )
            print(
                "\n  Per rule 15, refusing to run.  Resolve the customer_name "
                "field on the listed sites (or remove them from the match by "
                "renaming) and re-run."
            )
            return 2

        if empty_customer:
            _section("Sites with empty customer_name (allowed; no ambiguity)")
            for s in empty_customer:
                print(f"  - site_id={s.site_id!r}  site_name={s.site_name!r}")

        # ── Linked-record snapshot for the confident set ────────────
        moved_site_ids = [s.site_id for s in confident]

        _section("Linked records on FROM_TENANT (across all matched sites)")
        link_counts_from: dict[str, int] = {}
        for label, model in LINKED_MOVE_MODELS + LINKED_DETECT_MODELS:
            n = await _count_for_site_ids(db, model, moved_site_ids, FROM_TENANT)
            link_counts_from[label] = n
            print(f"  {label:<18}  {n:>6}  on tenant_id={FROM_TENANT!r}")

        _section("Proposed changes")
        print(
            f"  sites:           tenant_id {FROM_TENANT!r} -> {TO_TENANT!r}  "
            f"({len(confident)} row(s))"
        )
        for label, _ in LINKED_MOVE_MODELS:
            print(
                f"  {label:<16} tenant_id {FROM_TENANT!r} -> {TO_TENANT!r}  "
                f"({link_counts_from[label]} row(s))"
            )
        for label, _ in LINKED_DETECT_MODELS:
            print(
                f"  {label:<16} (detected only — NOT moved per spec; "
                f"{link_counts_from[label]} row(s) will remain on "
                f"{FROM_TENANT!r})"
            )

        if DRY_RUN:
            _banner("DRY RUN complete — no writes were performed")
            print("  Re-run with DRY_RUN=false to apply.")
            return 0

        if not confident:
            _banner("APPLY: nothing confident to move — exiting cleanly")
            return 0

        # ── Apply (single transaction, single commit) ───────────────
        _section("Applying changes")
        moved_counts: dict[str, int] = {"sites": 0}

        site_result = await db.execute(
            update(Site)
            .where(Site.tenant_id == FROM_TENANT)
            .where(Site.site_id.in_(moved_site_ids))
            .values(tenant_id=TO_TENANT)
        )
        moved_counts["sites"] = site_result.rowcount or 0
        print(f"  updated sites             rows={moved_counts['sites']}")

        for label, model in LINKED_MOVE_MODELS:
            r = await db.execute(
                update(model)
                .where(model.tenant_id == FROM_TENANT)
                .where(model.site_id.in_(moved_site_ids))
                .values(tenant_id=TO_TENANT)
            )
            moved_counts[label] = r.rowcount or 0
            print(f"  updated {label:<18}  rows={moved_counts[label]}")

        # Audit row scoped to canonical tenant for normal scoping visibility.
        audit = AuditLogEntry(
            entry_id=f"bulk-reassign-rh-sites-{len(moved_site_ids)}",
            tenant_id=TO_TENANT,
            category="security",
            action="bulk_reassign_rh_sites",
            actor="reassign_script",
            target_type="tenant",
            target_id=TO_TENANT,
            summary=(
                f"Reassigned {len(moved_site_ids)} Restoration Hardware "
                f"site(s) from tenant {FROM_TENANT!r} to {TO_TENANT!r} "
                f"with linked devices/service_units/sims/lines."
            ),
            detail_json=json.dumps({
                "from_tenant": FROM_TENANT,
                "to_tenant": TO_TENANT,
                "moved_site_ids": moved_site_ids,
                "moved_counts": moved_counts,
                "linked_counts_from_before": link_counts_from,
                "empty_customer_site_ids": [s.site_id for s in empty_customer],
                "script": "scripts/reassign_rh_sites.py",
            }),
        )
        db.add(audit)

        await db.commit()

        # ── After summary ───────────────────────────────────────────
        _section("AFTER — verifying tenant assignments on moved sites")
        # Re-count linked records that did NOT move (incidents/events/notifications).
        leftover: dict[str, int] = {}
        for label, model in LINKED_DETECT_MODELS:
            n = await _count_for_site_ids(db, model, moved_site_ids, FROM_TENANT)
            leftover[label] = n

        for label, _ in LINKED_MOVE_MODELS:
            n_to = await _count_for_site_ids(db, _, moved_site_ids, TO_TENANT)
            n_from = await _count_for_site_ids(db, _, moved_site_ids, FROM_TENANT)
            print(
                f"  {label:<18}  on {TO_TENANT!r}={n_to}  "
                f"on {FROM_TENANT!r}={n_from}"
            )

        if any(leftover.values()):
            _section("Detected linked records left on FROM_TENANT (NOT moved per spec)")
            for label, n in leftover.items():
                if n:
                    print(
                        f"  {label:<18}  {n}  rows still reference moved "
                        f"site_ids on tenant_id={FROM_TENANT!r}"
                    )
            print(
                "\n  These were not moved per the explicit Proposed Changes "
                "list in the spec.  If they should follow their site, run a "
                "follow-up reassign for these tables specifically."
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
