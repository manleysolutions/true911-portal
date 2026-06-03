"""Consolidate the duplicate Integrity tenant (ipm) into the survivor (integrity-pm).

DRY_RUN defaults to **true** — prints the plan and writes nothing.  Even in APPLY
mode this script NEVER deletes: it MOVES the genuinely-useful records (service
units), MERGES blank-only data (E911 address) into the survivor, and RE-POINTS
the inactive subscription to the canonical customer.  Duplicate customers and
duplicate Tiffany sites are FLAGGED as archive candidates for a SEPARATE,
reviewed purge PR once this pass is confirmed — they are not touched here.

Hard guards (never modified):
  * Belle Terre (IPM-BELLE-TERRE) and its devices / SIMs / service units.
  * Vola devices (ipm has 0 devices; the script also never updates any device).
  * Assurance / lifecycle / E911 *status* fields (only blank E911 *address*
    fields are filled on the survivor; e911_status is left to the audited E911
    flow).

Run:
    python -m app.consolidate_integrity_tenants                 # dry run (default)
    DRY_RUN=false python -m app.consolidate_integrity_tenants   # APPLY (do not run yet)
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SOURCE_TENANT = os.environ.get("CONSOLIDATE_SOURCE", "ipm")
SURVIVOR_TENANT = os.environ.get("CONSOLIDATE_SURVIVOR", "integrity-pm")
PROTECTED_SITE_IDS = {"IPM-BELLE-TERRE"}
E911_ADDRESS_FIELDS = ("e911_street", "e911_city", "e911_state", "e911_zip")

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def normalize_name(s: str | None) -> str:
    return _NON_ALNUM.sub("", (s or "").lower())


# ── Plan model (pure) ────────────────────────────────────────────────
@dataclass
class Plan:
    move_units: list = field(default_factory=list)          # {unit_id, unit_name, from_site, to_site, to_tenant}
    merge_site_e911: list = field(default_factory=list)     # {survivor_site_id, from_site_id, fields:{...}}
    move_sites: list = field(default_factory=list)          # {site_id, to_tenant, to_customer_id} (no survivor match)
    repoint_subscriptions: list = field(default_factory=list)  # {sub_id, to_customer_id, to_tenant}
    archive_customers: list = field(default_factory=list)   # {id, name, reason} (DEFERRED)
    archive_sites: list = field(default_factory=list)       # {site_id, merged_into, reason} (DEFERRED)
    discard_units: list = field(default_factory=list)       # {unit_id, reason} (duplicate at survivor)
    skipped: list = field(default_factory=list)             # {kind, id, reason}
    warnings: list = field(default_factory=list)


def plan_consolidation(
    *,
    source_sites: list[dict],
    survivor_sites: list[dict],
    source_units_by_site: dict[str, list[dict]],
    survivor_unit_types_by_site: dict[str, set],
    source_customers: list[dict],
    survivor_customers: list[dict],
    source_subscriptions: list[dict],
    protected_site_ids: set = PROTECTED_SITE_IDS,
) -> Plan:
    """Pure: compute the consolidation plan. No I/O."""
    plan = Plan()

    canonical = next((c for c in survivor_customers if c.get("zoho")), None)
    if canonical is None and survivor_customers:
        canonical = survivor_customers[0]
        plan.warnings.append("Survivor has no Zoho-linked customer; using first customer as canonical.")
    if canonical is None:
        plan.warnings.append("Survivor has NO customers — cannot re-point references; aborting plan.")
        return plan

    survivor_by_name = {normalize_name(s["site_name"]): s for s in survivor_sites}

    for ss in source_sites:
        if ss["site_id"] in protected_site_ids:
            plan.skipped.append({"kind": "site", "id": ss["site_id"], "reason": "protected — never touched"})
            continue

        match = survivor_by_name.get(normalize_name(ss.get("site_name")))
        units = source_units_by_site.get(ss["site_id"], [])

        if match:
            # Duplicate site → fill blank E911 address fields on survivor, move
            # units, flag the source site for archive (deferred).
            fills = {
                f: ss[f] for f in E911_ADDRESS_FIELDS
                if (ss.get(f) or "").strip() and not (match.get(f) or "").strip()
            }
            if fills:
                plan.merge_site_e911.append({
                    "survivor_site_id": match["site_id"], "from_site_id": ss["site_id"], "fields": fills,
                })
            survivor_unit_types = survivor_unit_types_by_site.get(match["site_id"], set())
            for u in units:
                if u.get("unit_type") in survivor_unit_types:
                    plan.discard_units.append({
                        "unit_id": u["unit_id"],
                        "reason": f"duplicate unit_type '{u.get('unit_type')}' already on survivor site {match['site_id']}",
                    })
                else:
                    plan.move_units.append({
                        "unit_id": u["unit_id"], "unit_name": u.get("unit_name"),
                        "from_site": ss["site_id"], "to_site": match["site_id"], "to_tenant": SURVIVOR_TENANT,
                    })
            plan.archive_sites.append({
                "site_id": ss["site_id"], "merged_into": match["site_id"],
                "reason": "duplicate of survivor site (same name) — archive after units moved (deferred to purge PR)",
            })
        else:
            # Unique source site → MOVE to survivor (re-tenant + re-point customer).
            plan.move_sites.append({
                "site_id": ss["site_id"], "to_tenant": SURVIVOR_TENANT, "to_customer_id": canonical["id"],
            })
            for u in units:
                plan.move_units.append({
                    "unit_id": u["unit_id"], "unit_name": u.get("unit_name"),
                    "from_site": ss["site_id"], "to_site": ss["site_id"], "to_tenant": SURVIVOR_TENANT,
                })

    # Duplicate customers under the source tenant → archive candidates; their
    # references (subscriptions) are re-pointed to the canonical customer.
    canon_name = normalize_name(canonical.get("name"))
    for c in source_customers:
        dup = normalize_name(c.get("name")) == canon_name or (c.get("zoho") and c.get("zoho") == canonical.get("zoho"))
        plan.archive_customers.append({
            "id": c["id"], "name": c.get("name"),
            "reason": (f"duplicate of canonical customer id={canonical['id']} "
                       f"(Zoho {canonical.get('zoho')})") if dup else "source-tenant customer (review)",
        })

    for sub in source_subscriptions:
        plan.repoint_subscriptions.append({
            "sub_id": sub["id"], "status": sub.get("status"),
            "to_customer_id": canonical["id"], "to_tenant": SURVIVOR_TENANT,
        })

    return plan


# ── DB load + apply (apply never deletes) ────────────────────────────
async def _load(db, tenant_id):
    from sqlalchemy import select
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.models.customer import Customer
    from app.models.subscription import Subscription

    sites = (await db.execute(select(Site).where(Site.tenant_id == tenant_id))).scalars().all()
    units = (await db.execute(select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all()
    customers = (await db.execute(select(Customer).where(Customer.tenant_id == tenant_id))).scalars().all()
    subs = (await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))).scalars().all()
    return sites, units, customers, subs


def _site_dict(s):
    return {"site_id": s.site_id, "site_name": s.site_name, "status": s.status,
            "customer_id": s.customer_id,
            **{f: getattr(s, f, None) for f in E911_ADDRESS_FIELDS}}


async def run(dry_run: bool = True) -> Plan:
    from app.database import AsyncSessionLocal
    from app.services.audit_logger import log_audit

    print("=" * 68)
    print(f"Integrity tenant consolidation: {SOURCE_TENANT} → {SURVIVOR_TENANT}")
    print(f"  mode: {'DRY RUN (no writes)' if dry_run else 'APPLY (writing; never deletes)'}")
    print("=" * 68)

    async with AsyncSessionLocal() as db:
        src_sites, src_units, src_customers, src_subs = await _load(db, SOURCE_TENANT)
        sur_sites, sur_units, sur_customers, _ = await _load(db, SURVIVOR_TENANT)

        source_units_by_site: dict[str, list[dict]] = {}
        for u in src_units:
            source_units_by_site.setdefault(u.site_id, []).append(
                {"unit_id": u.unit_id, "unit_name": u.unit_name, "unit_type": u.unit_type})
        survivor_unit_types_by_site: dict[str, set] = {}
        for u in sur_units:
            survivor_unit_types_by_site.setdefault(u.site_id, set()).add(u.unit_type)

        plan = plan_consolidation(
            source_sites=[_site_dict(s) for s in src_sites],
            survivor_sites=[_site_dict(s) for s in sur_sites],
            source_units_by_site=source_units_by_site,
            survivor_unit_types_by_site=survivor_unit_types_by_site,
            source_customers=[{"id": c.id, "name": c.name, "zoho": c.zoho_account_id} for c in src_customers],
            survivor_customers=[{"id": c.id, "name": c.name, "zoho": c.zoho_account_id} for c in sur_customers],
            source_subscriptions=[{"id": s.id, "status": s.status} for s in src_subs],
        )

        _print_plan(plan)

        if dry_run:
            await db.rollback()
            print("\nDRY RUN — nothing written. Re-run with DRY_RUN=false to apply (move/merge/repoint only).")
            return plan

        # ── APPLY (move/merge/repoint only — never deletes) ──
        now = _dt.datetime.now(_dt.timezone.utc)
        unit_by_id = {u.unit_id: u for u in src_units}
        site_by_id = {s.site_id: s for s in (src_sites + sur_sites)}
        sub_by_id = {s.id: s for s in src_subs}

        for mv in plan.move_units:
            u = unit_by_id.get(mv["unit_id"])
            if u:
                u.site_id, u.tenant_id = mv["to_site"], mv["to_tenant"]
                await log_audit(db, SURVIVOR_TENANT, "tenant_consolidation", "move_service_unit",
                                f"Moved service unit {u.unit_id} {mv['from_site']}→{mv['to_site']}",
                                actor="consolidate_integrity_tenants", target_type="service_unit",
                                target_id=u.unit_id, site_id=mv["to_site"], detail=mv)
        for mg in plan.merge_site_e911:
            site = site_by_id.get(mg["survivor_site_id"])
            if site:
                for f, v in mg["fields"].items():
                    setattr(site, f, v)
                await log_audit(db, SURVIVOR_TENANT, "tenant_consolidation", "merge_site_e911",
                                f"Filled blank E911 fields on {site.site_id} from {mg['from_site_id']}",
                                actor="consolidate_integrity_tenants", target_type="site",
                                target_id=site.site_id, site_id=site.site_id, detail=mg)
        for mvs in plan.move_sites:
            site = site_by_id.get(mvs["site_id"])
            if site:
                site.tenant_id, site.customer_id = mvs["to_tenant"], mvs["to_customer_id"]
                await log_audit(db, SURVIVOR_TENANT, "tenant_consolidation", "move_site",
                                f"Moved site {site.site_id} → {mvs['to_tenant']}",
                                actor="consolidate_integrity_tenants", target_type="site",
                                target_id=site.site_id, site_id=site.site_id, detail=mvs)
        for rp in plan.repoint_subscriptions:
            sub = sub_by_id.get(rp["sub_id"])
            if sub:
                sub.customer_id, sub.tenant_id = rp["to_customer_id"], rp["to_tenant"]
                await log_audit(db, SURVIVOR_TENANT, "tenant_consolidation", "repoint_subscription",
                                f"Re-pointed subscription {sub.id} → customer {rp['to_customer_id']}",
                                actor="consolidate_integrity_tenants", target_type="subscription",
                                target_id=str(sub.id), detail=rp)

        await db.commit()
        print("\nCOMMITTED move/merge/repoint changes (no deletes). Archive candidates "
              "were NOT touched — handle them in the follow-up purge PR.")
        return plan


def _print_plan(plan: Plan) -> None:
    def section(title, items, fmt):
        print(f"\n{title}: {len(items)}")
        for it in items:
            print(f"    - {fmt(it)}")

    section("MOVE service units", plan.move_units,
            lambda m: f"{m['unit_id']} ({m.get('unit_name')}) {m['from_site']}→{m['to_site']} @ {m['to_tenant']}")
    section("MERGE site E911 (fill blanks only)", plan.merge_site_e911,
            lambda m: f"{m['survivor_site_id']} ⟵ {m['from_site_id']} fields={list(m['fields'])}")
    section("MOVE sites (no survivor match)", plan.move_sites,
            lambda m: f"{m['site_id']} → {m['to_tenant']} customer={m['to_customer_id']}")
    section("RE-POINT subscriptions", plan.repoint_subscriptions,
            lambda m: f"sub#{m['sub_id']} (status={m.get('status')}) → customer {m['to_customer_id']} @ {m['to_tenant']}")
    section("ARCHIVE candidates — customers (DEFERRED)", plan.archive_customers,
            lambda m: f"customer#{m['id']} {m['name']!r} — {m['reason']}")
    section("ARCHIVE candidates — sites (DEFERRED)", plan.archive_sites,
            lambda m: f"{m['site_id']} (merged into {m['merged_into']}) — {m['reason']}")
    section("DISCARD duplicate units", plan.discard_units, lambda m: f"{m['unit_id']} — {m['reason']}")
    section("SKIPPED / untouched", plan.skipped, lambda m: f"{m['kind']} {m['id']} — {m['reason']}")
    if plan.warnings:
        print("\nWARNINGS:")
        for w in plan.warnings:
            print(f"    ! {w}")


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    try:
        asyncio.run(run(dry_run=dry_run))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: consolidation aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
