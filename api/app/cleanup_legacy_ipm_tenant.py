"""Retire the duplicate legacy Integrity tenant (ipm) — dry-run-first, refusal-gated.

Runs AFTER consolidation (PR #76 moved the useful records into integrity-pm).
This pass SOFT-ARCHIVES the leftover duplicates and RETIRES the tenant — it never
hard-deletes, so the full audit trail is preserved and every change is reversible:

  * duplicate customers  → Customer.status = "archived"
  * duplicate sites      → Site.status = "archived", onboarding_status = "retired"
  * tenant slug ``ipm``  → Tenant.is_active = False  (hidden from active dropdowns,
                           still present for audit)

REFUSES (writes nothing) when any safety check fails:
  * ipm still has ANY operational records (service_units / devices / sims / users /
    registrations / subscriptions > 0);
  * ipm contains an UNEXPECTED site (not the two known Tiffany duplicates) or a
    customer that looks real (has a Zoho id, or a name that isn't the known dup);
  * a duplicate customer is still REFERENCED by a record outside the archive set
    (a site in another tenant, a line, or a subscription).

Never touches: integrity-pm, customer#83, Belle Terre, Vola devices, SIMs, the
already-moved service units, Assurance data, or T-Mobile/Vola integrations.

Run:
    python -m app.cleanup_legacy_ipm_tenant                 # dry run (default)
    DRY_RUN=false python -m app.cleanup_legacy_ipm_tenant   # APPLY (do not run yet)
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

LEGACY_TENANT = os.environ.get("CLEANUP_LEGACY_TENANT", "ipm")
SURVIVOR_TENANT = os.environ.get("CLEANUP_SURVIVOR_TENANT", "integrity-pm")
EXPECTED_SITE_IDS = {"TIFFANY-GARDENS-EAST", "TIFFANY-GARDENS-NORTH"}
CANONICAL_CUSTOMER_NAME = "Integrity Property Management"
ZERO_RECORD_KINDS = ("service_units", "devices", "sims", "users", "registrations", "subscriptions")

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _norm(s: str | None) -> str:
    return _NON_ALNUM.sub("", (s or "").lower())


@dataclass
class CleanupPlan:
    safe: bool = False
    refusals: list = field(default_factory=list)
    archive_customers: list = field(default_factory=list)   # {id, name}
    archive_sites: list = field(default_factory=list)        # {site_id, name}
    retire_tenant: str | None = None


def plan_cleanup(
    *,
    tenant_id: str,
    customers: list[dict],
    sites: list[dict],
    counts: dict[str, int],
    external_references: dict[int, list[str]],
    expected_site_ids: set = EXPECTED_SITE_IDS,
) -> CleanupPlan:
    """Pure: decide whether it is safe to retire ``tenant_id`` and what to archive."""
    refusals: list[str] = []

    # 1. No operational records may remain.
    for kind in ZERO_RECORD_KINDS:
        n = int(counts.get(kind, 0))
        if n != 0:
            refusals.append(f"{tenant_id} still has {n} {kind} (expected 0) — refusing cleanup.")

    # 2. Every site must be a known duplicate; anything else is unexpected.
    for s in sites:
        if s["site_id"] not in expected_site_ids:
            refusals.append(f"unexpected site '{s['site_id']}' under {tenant_id} — refusing (may be operational).")

    # 3. Every customer must look like a duplicate (no Zoho id; known name).
    canon = _norm(CANONICAL_CUSTOMER_NAME)
    for c in customers:
        if c.get("zoho"):
            refusals.append(f"customer#{c['id']} has Zoho id {c['zoho']} — looks real; refusing.")
        elif _norm(c.get("name")) != canon:
            refusals.append(f"customer#{c['id']} name {c.get('name')!r} is not a known duplicate — refusing.")

    # 4. No duplicate customer may still be referenced outside the archive set.
    for c in customers:
        refs = external_references.get(c["id"], [])
        if refs:
            refusals.append(f"customer#{c['id']} still referenced by {refs} — refusing (would orphan a live record).")

    if refusals:
        return CleanupPlan(safe=False, refusals=refusals)

    return CleanupPlan(
        safe=True,
        archive_customers=[{"id": c["id"], "name": c.get("name")} for c in customers],
        archive_sites=[{"site_id": s["site_id"], "name": s.get("site_name")} for s in sites],
        retire_tenant=tenant_id,
    )


# ── DB load + apply (apply soft-archives + retires; never deletes) ───
async def _load(db, tenant_id):
    from sqlalchemy import func, select
    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.models.device import Device
    from app.models.sim import Sim
    from app.models.user import User
    from app.models.registration import Registration
    from app.models.subscription import Subscription

    async def count(model):
        return int((await db.execute(
            select(func.count()).select_from(model).where(model.tenant_id == tenant_id))).scalar() or 0)

    customers = (await db.execute(select(Customer).where(Customer.tenant_id == tenant_id))).scalars().all()
    sites = (await db.execute(select(Site).where(Site.tenant_id == tenant_id))).scalars().all()
    counts = {
        "service_units": await count(ServiceUnit), "devices": await count(Device),
        "sims": await count(Sim), "users": await count(User),
        "registrations": await count(Registration), "subscriptions": await count(Subscription),
    }
    return customers, sites, counts


async def _external_references(db, customer_ids: list[int], archived_site_ids: set) -> dict[int, list[str]]:
    """For each customer, list references OUTSIDE the archive set (would orphan)."""
    from sqlalchemy import select
    from app.models.site import Site
    from app.models.line import Line
    from app.models.subscription import Subscription

    refs: dict[int, list[str]] = {cid: [] for cid in customer_ids}
    if not customer_ids:
        return refs

    for s in (await db.execute(select(Site).where(Site.customer_id.in_(customer_ids)))).scalars().all():
        if s.site_id not in archived_site_ids:
            refs.setdefault(s.customer_id, []).append(f"site:{s.site_id}(tenant {s.tenant_id})")
    for ln in (await db.execute(select(Line).where(Line.customer_id.in_(customer_ids)))).scalars().all():
        refs.setdefault(ln.customer_id, []).append(f"line:{ln.line_id}")
    for sub in (await db.execute(select(Subscription).where(Subscription.customer_id.in_(customer_ids)))).scalars().all():
        refs.setdefault(sub.customer_id, []).append(f"subscription:{sub.id}")
    return refs


async def run(dry_run: bool = True) -> CleanupPlan:
    from app.database import AsyncSessionLocal
    from app.services.audit_logger import log_audit

    print("=" * 68)
    print(f"Legacy tenant cleanup: retire '{LEGACY_TENANT}' (survivor '{SURVIVOR_TENANT}')")
    print(f"  mode: {'DRY RUN (no writes)' if dry_run else 'APPLY (soft-archive + retire; never deletes)'}")
    print("=" * 68)

    async with AsyncSessionLocal() as db:
        customers, sites, counts = await _load(db, LEGACY_TENANT)
        cust_ids = [c.id for c in customers]
        site_ids = {s.site_id for s in sites}
        ext_refs = await _external_references(db, cust_ids, site_ids)

        plan = plan_cleanup(
            tenant_id=LEGACY_TENANT,
            customers=[{"id": c.id, "name": c.name, "zoho": c.zoho_account_id} for c in customers],
            sites=[{"site_id": s.site_id, "site_name": s.site_name} for s in sites],
            counts=counts,
            external_references=ext_refs,
        )

        _print_plan(plan, counts)

        if not plan.safe:
            await db.rollback()
            print("\nREFUSED — preconditions not met. Nothing written.")
            return plan
        if dry_run:
            await db.rollback()
            print("\nDRY RUN — safe to proceed, but nothing written. Re-run with DRY_RUN=false to apply.")
            return plan

        # ── APPLY (soft-archive + retire — no deletes) ──
        from app.models.tenant import Tenant
        from sqlalchemy import select

        for c in customers:
            c.status = "archived"
            await log_audit(db, SURVIVOR_TENANT, "tenant_cleanup", "archive_customer",
                            f"Archived duplicate customer #{c.id} ({c.name}) from legacy {LEGACY_TENANT}",
                            actor="cleanup_legacy_ipm_tenant", target_type="customer", target_id=str(c.id),
                            detail={"legacy_tenant": LEGACY_TENANT})
        for s in sites:
            s.status = "archived"
            s.onboarding_status = "retired"
            await log_audit(db, SURVIVOR_TENANT, "tenant_cleanup", "archive_site",
                            f"Archived duplicate site {s.site_id} from legacy {LEGACY_TENANT}",
                            actor="cleanup_legacy_ipm_tenant", target_type="site", target_id=s.site_id,
                            site_id=s.site_id, detail={"legacy_tenant": LEGACY_TENANT})
        tenant = (await db.execute(select(Tenant).where(Tenant.tenant_id == LEGACY_TENANT))).scalar_one_or_none()
        if tenant is not None:
            tenant.is_active = False
            await log_audit(db, SURVIVOR_TENANT, "tenant_cleanup", "retire_tenant",
                            f"Retired legacy tenant {LEGACY_TENANT} (is_active=False)",
                            actor="cleanup_legacy_ipm_tenant", target_type="tenant", target_id=LEGACY_TENANT,
                            detail={"survivor": SURVIVOR_TENANT})

        await db.commit()
        print(f"\nCOMMITTED — {LEGACY_TENANT} retired; duplicates archived (no deletes). "
              "Rows remain for audit; tenant is hidden from active dropdowns.")
        return plan


def _print_plan(plan: CleanupPlan, counts: dict) -> None:
    print("\nPre-flight counts (must all be 0):")
    for k in ZERO_RECORD_KINDS:
        print(f"    {k:14}: {counts.get(k, 0)}")
    if not plan.safe:
        print("\nREFUSALS:")
        for r in plan.refusals:
            print(f"    ✗ {r}")
        return
    print("\nARCHIVE customers:")
    for c in plan.archive_customers:
        print(f"    - customer#{c['id']} {c['name']!r} → status=archived")
    print("ARCHIVE sites:")
    for s in plan.archive_sites:
        print(f"    - {s['site_id']} {s['name']!r} → status=archived, onboarding_status=retired")
    print(f"RETIRE tenant:\n    - {plan.retire_tenant} → is_active=False (hidden from active dropdowns, kept for audit)")


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    try:
        asyncio.run(run(dry_run=dry_run))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: cleanup aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
