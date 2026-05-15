#!/usr/bin/env python3
"""Read-only audit of the two duplicate "Restoration Hardware" tenants.

We discovered that production has both:

    tenant_id = 'rh'
    tenant_id = 'restoration-hardware'

…both labelled "Restoration Hardware".  Before any consolidation, this
script produces a complete side-by-side picture of what lives in each
tenant and where the two are entangled.

100% READ-ONLY.  No INSERT, UPDATE, DELETE, or DDL is issued.  No
recommendations are written to the database.  This script does not
decide which tenant should survive — it surfaces the facts so an
operator can decide with their eyes open.

What it reports
---------------
For each target tenant (default: 'rh' and 'restoration-hardware'):

  1. Tenant metadata:
       tenants.id, tenant_id slug, name, display_name, org_type,
       parent_tenant_id, is_active, contact_email, zoho_account_id,
       created_at, presence of settings_json

  2. Row counts per table:
       users, customers, sites, devices, lines, sims, service_units,
       registrations, action_audits

  3. Onboarding-status distribution:
       customers.onboarding_status, sites.onboarding_status,
       sites.status (looking for 'merged' from the recent remediation)

  4. Recent-activity signals (newest-first across each table):
       max(created_at) per table
       max(devices.last_heartbeat)
       max(sites.last_checkin)

  5. User roster (email, role, is_active) — operator needs this to
     judge whether each tenant has real humans behind it.

  6. Customer roster: id, name, customer_number, zoho_account_id,
     onboarding_status, created_at, site/device counts.

  7. Cross-link analysis (the dangerous part):

     a. Sites with customer_id set, where sites.tenant_id !=
        customers.tenant_id.  This means a site in tenant A claims
        a customer that lives in tenant B.

     b. Devices whose site_id points to a Site row in a DIFFERENT
        tenant_id than the Device row itself.

     c. Users whose email matches a user in the other RH tenant
        (User.email is unique globally, so this should be empty —
        but we check anyway to catch any data inconsistency).

  8. Orphan check: rows in users / customers / sites / devices /
     lines whose tenant_id is one of the RH slugs but no row exists
     in the tenants table for that slug.

  9. Sites both tenants claim — duplicate sites.site_id values
     across the two tenants.

Outputs
-------
* Pretty-printed report on stdout (everything above).
* JSON dump at api/reports/rh_tenant_audit.json with the same data
  in a structured form for archival / further analysis.

Usage on Render shell:

    cd /opt/render/project/src/api
    python -m scripts.audit_rh_tenants

Optional overrides:

    python -m scripts.audit_rh_tenants --slug rh --slug restoration-hardware
    python -m scripts.audit_rh_tenants --json-only

Read-only.  Safe to re-run.  Safe under live traffic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Make ``app.*`` importable from either invocation form.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import and_, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.action_audit import ActionAudit  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.line import Line  # noqa: E402
from app.models.registration import Registration  # noqa: E402
from app.models.service_unit import ServiceUnit  # noqa: E402
from app.models.sim import Sim  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402


DEFAULT_SLUGS = ["rh", "restoration-hardware"]

REPORTS_DIR = Path(_API_DIR) / "reports"
JSON_OUT = REPORTS_DIR / "rh_tenant_audit.json"

# Per-tenant per-table counting models — every model below has a
# String tenant_id column (or, in Registration's case, may have one
# under a different attribute; handled below).
_COUNT_TABLES: list[tuple[str, type]] = [
    ("users",         User),
    ("customers",     Customer),
    ("sites",         Site),
    ("devices",       Device),
    ("lines",         Line),
    ("sims",          Sim),
    ("service_units", ServiceUnit),
    ("registrations", Registration),
    ("action_audits", ActionAudit),
]


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def _section(text: str) -> None:
    print()
    print(f"── {text} " + "─" * max(1, 70 - len(text)))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return None


def _has_tenant_id_attr(model: type) -> bool:
    """Some ORM models don't have a tenant_id column; skip those gracefully."""
    return hasattr(model, "tenant_id")


# ─────────────────────────────────────────────────────────────────────
# Per-tenant collection
# ─────────────────────────────────────────────────────────────────────

async def _tenant_metadata(db: AsyncSession, slugs: list[str]) -> dict[str, Any]:
    r = await db.execute(select(Tenant).where(Tenant.tenant_id.in_(slugs)))
    rows = list(r.scalars().all())
    out: dict[str, Any] = {}
    for t in rows:
        out[t.tenant_id] = {
            "pk":               t.id,
            "tenant_id":        t.tenant_id,
            "name":             t.name,
            "display_name":     t.display_name,
            "org_type":         t.org_type,
            "parent_tenant_id": t.parent_tenant_id,
            "is_active":        bool(t.is_active),
            "contact_email":    t.contact_email,
            "contact_phone":    t.contact_phone,
            "zoho_account_id":  t.zoho_account_id,
            "has_settings_json": bool(t.settings_json),
            "created_at":       _iso(t.created_at),
        }
    return out


async def _row_counts(db: AsyncSession, slugs: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {s: {label: 0 for label, _ in _COUNT_TABLES} for s in slugs}
    for label, model in _COUNT_TABLES:
        if not _has_tenant_id_attr(model):
            continue
        r = await db.execute(
            select(model.tenant_id, func.count())
            .where(model.tenant_id.in_(slugs))
            .group_by(model.tenant_id)
        )
        for slug, n in r.all():
            if slug in out:
                out[slug][label] = int(n)
    return out


async def _onboarding_status_distribution(
    db: AsyncSession, slugs: list[str]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {s: {} for s in slugs}
    # customers.onboarding_status
    r = await db.execute(
        select(Customer.tenant_id, Customer.onboarding_status, func.count())
        .where(Customer.tenant_id.in_(slugs))
        .group_by(Customer.tenant_id, Customer.onboarding_status)
    )
    for slug, status, n in r.all():
        if slug in out:
            out[slug].setdefault("customers_onboarding_status", {})[status or "<null>"] = int(n)
    # sites.onboarding_status
    r = await db.execute(
        select(Site.tenant_id, Site.onboarding_status, func.count())
        .where(Site.tenant_id.in_(slugs))
        .group_by(Site.tenant_id, Site.onboarding_status)
    )
    for slug, status, n in r.all():
        if slug in out:
            out[slug].setdefault("sites_onboarding_status", {})[status or "<null>"] = int(n)
    # sites.status (looking for 'merged' from remediation)
    r = await db.execute(
        select(Site.tenant_id, Site.status, func.count())
        .where(Site.tenant_id.in_(slugs))
        .group_by(Site.tenant_id, Site.status)
    )
    for slug, status, n in r.all():
        if slug in out:
            out[slug].setdefault("sites_status", {})[status or "<null>"] = int(n)
    return out


async def _recent_activity(db: AsyncSession, slugs: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {s: {} for s in slugs}
    # max(created_at) per table
    for label, model in _COUNT_TABLES:
        if not _has_tenant_id_attr(model) or not hasattr(model, "created_at"):
            continue
        r = await db.execute(
            select(model.tenant_id, func.max(model.created_at))
            .where(model.tenant_id.in_(slugs))
            .group_by(model.tenant_id)
        )
        for slug, ts in r.all():
            if slug in out:
                out[slug].setdefault("max_created_at", {})[label] = _iso(ts)
    # devices.last_heartbeat
    r = await db.execute(
        select(Device.tenant_id, func.max(Device.last_heartbeat))
        .where(Device.tenant_id.in_(slugs))
        .group_by(Device.tenant_id)
    )
    for slug, ts in r.all():
        if slug in out:
            out[slug]["max_device_last_heartbeat"] = _iso(ts)
    # sites.last_checkin
    r = await db.execute(
        select(Site.tenant_id, func.max(Site.last_checkin))
        .where(Site.tenant_id.in_(slugs))
        .group_by(Site.tenant_id)
    )
    for slug, ts in r.all():
        if slug in out:
            out[slug]["max_site_last_checkin"] = _iso(ts)
    return out


async def _user_roster(db: AsyncSession, slugs: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in slugs}
    r = await db.execute(
        select(User.email, User.name, User.role, User.is_active, User.tenant_id, User.created_at)
        .where(User.tenant_id.in_(slugs))
        .order_by(User.tenant_id, User.created_at)
    )
    for email, name, role, is_active, tid, created in r.all():
        if tid in out:
            out[tid].append({
                "email":      email,
                "name":       name,
                "role":       role,
                "is_active":  bool(is_active),
                "created_at": _iso(created),
            })
    return out


async def _customer_roster(db: AsyncSession, slugs: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in slugs}
    r = await db.execute(
        select(Customer).where(Customer.tenant_id.in_(slugs)).order_by(Customer.tenant_id, Customer.id)
    )
    customers = list(r.scalars().all())

    cust_ids = [c.id for c in customers]
    site_counts: dict[int, int] = {}
    if cust_ids:
        sc = await db.execute(
            select(Site.customer_id, func.count())
            .where(Site.customer_id.in_(cust_ids))
            .group_by(Site.customer_id)
        )
        site_counts = {cid: int(n) for cid, n in sc.all() if cid is not None}

    for c in customers:
        if c.tenant_id in out:
            out[c.tenant_id].append({
                "id":                  c.id,
                "name":                c.name,
                "customer_number":     c.customer_number,
                "zoho_account_id":     c.zoho_account_id,
                "status":              c.status,
                "onboarding_status":   c.onboarding_status,
                "created_at":          _iso(c.created_at),
                "site_count":          site_counts.get(c.id, 0),
            })
    return out


async def _cross_links(db: AsyncSession, slugs: list[str]) -> dict[str, Any]:
    """Find rows that span the two tenants.

    Three checks:
      a. Site.tenant_id != Customer.tenant_id (where Site.customer_id is set)
      b. Device.tenant_id != Site.tenant_id  (joined on site_id slug)
      c. Users with the same email in different tenants (should be 0)
    """
    findings: dict[str, Any] = {
        "site_customer_tenant_mismatch": [],
        "device_site_tenant_mismatch":   [],
        "user_email_collision":          [],
    }

    # a. Site vs Customer
    r = await db.execute(
        select(
            Site.id, Site.site_id, Site.tenant_id, Site.customer_id,
            Customer.id, Customer.name, Customer.tenant_id,
        )
        .join(Customer, Customer.id == Site.customer_id)
        .where(
            and_(
                Site.customer_id.isnot(None),
                Site.tenant_id != Customer.tenant_id,
                Site.tenant_id.in_(slugs) | Customer.tenant_id.in_(slugs),
            )
        )
    )
    for site_pk, site_id, site_tenant, customer_id, cust_pk, cust_name, cust_tenant in r.all():
        findings["site_customer_tenant_mismatch"].append({
            "site_pk":         site_pk,
            "site_id":         site_id,
            "site_tenant_id":  site_tenant,
            "customer_pk":     cust_pk,
            "customer_name":   cust_name,
            "customer_tenant_id": cust_tenant,
        })

    # b. Device vs Site
    r = await db.execute(
        select(
            Device.id, Device.device_id, Device.tenant_id, Device.site_id,
            Site.id, Site.tenant_id,
        )
        .join(Site, Site.site_id == Device.site_id)
        .where(
            and_(
                Device.site_id.isnot(None),
                Device.tenant_id != Site.tenant_id,
                Device.tenant_id.in_(slugs) | Site.tenant_id.in_(slugs),
            )
        )
    )
    for dev_pk, dev_id, dev_tenant, site_id, site_pk, site_tenant in r.all():
        findings["device_site_tenant_mismatch"].append({
            "device_pk":      dev_pk,
            "device_id":      dev_id,
            "device_tenant_id": dev_tenant,
            "site_id":        site_id,
            "site_pk":        site_pk,
            "site_tenant_id": site_tenant,
        })

    # c. User email collisions across the two RH tenants.  User.email
    # is globally unique, so we shouldn't find any — but if a prior
    # consolidation attempt failed mid-flight we'd see ghosts here.
    r = await db.execute(
        select(User.email, func.count(), func.array_agg(User.tenant_id))
        .where(User.tenant_id.in_(slugs))
        .group_by(User.email)
        .having(func.count() > 1)
    )
    for email, n, tenants in r.all():
        findings["user_email_collision"].append({
            "email": email,
            "count": int(n),
            "tenant_ids": list(tenants) if tenants else [],
        })
    return findings


async def _site_id_collisions(db: AsyncSession, slugs: list[str]) -> list[dict[str, Any]]:
    """sites.site_id is globally unique by schema (unique index).  If the
    two RH tenants somehow claim the same site_id slug, surface it."""
    r = await db.execute(
        select(Site.site_id, func.count(), func.array_agg(Site.tenant_id))
        .where(Site.tenant_id.in_(slugs))
        .group_by(Site.site_id)
        .having(func.count() > 1)
    )
    out: list[dict[str, Any]] = []
    for site_id, n, tenants in r.all():
        out.append({"site_id": site_id, "count": int(n), "tenant_ids": list(tenants) if tenants else []})
    return out


async def _orphan_check(db: AsyncSession, slugs: list[str], present: set[str]) -> dict[str, list[str]]:
    """Detect rows whose tenant_id is one of the RH slugs but the
    tenant row doesn't exist in ``tenants``.  Should be empty in a
    healthy system; non-empty means a slug was deleted from the
    tenants table while child rows survived."""
    missing = [s for s in slugs if s not in present]
    out: dict[str, list[str]] = {}
    if not missing:
        return out
    for label, model in _COUNT_TABLES:
        if not _has_tenant_id_attr(model):
            continue
        r = await db.execute(
            select(model.tenant_id, func.count())
            .where(model.tenant_id.in_(missing))
            .group_by(model.tenant_id)
        )
        for slug, n in r.all():
            if int(n) > 0:
                out.setdefault(slug, []).append(f"{label}={n}")
    return out


# ─────────────────────────────────────────────────────────────────────
# Pretty-print
# ─────────────────────────────────────────────────────────────────────

def _print_report(report: dict[str, Any]) -> None:
    slugs: list[str] = report["target_slugs"]
    meta: dict[str, Any] = report["tenant_metadata"]
    counts: dict[str, dict[str, int]] = report["row_counts"]
    onboarding: dict[str, dict[str, Any]] = report["onboarding_status_distribution"]
    recent: dict[str, dict[str, Any]] = report["recent_activity"]
    users: dict[str, list[dict[str, Any]]] = report["user_roster"]
    customers: dict[str, list[dict[str, Any]]] = report["customer_roster"]
    crosslinks: dict[str, Any] = report["cross_links"]
    site_collisions: list[dict[str, Any]] = report["site_id_collisions"]
    orphans: dict[str, list[str]] = report["orphans"]

    _banner(f"RH tenant duplicate audit  (read-only; ran at {report['ran_at']})")
    print(f"  target slugs: {', '.join(slugs)}")

    # 1. Tenant metadata
    _section("1. Tenant metadata")
    for s in slugs:
        m = meta.get(s)
        if not m:
            print(f"  {s!r}: NOT PRESENT in tenants table")
            continue
        print(f"  [{s}]")
        for k, v in m.items():
            print(f"    {k:<20} : {v}")

    # 2. Row counts
    _section("2. Row counts per tenant")
    labels = [lbl for lbl, _ in _COUNT_TABLES]
    header = f"  {'table':<16} " + "  ".join(f"{s:>22}" for s in slugs)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for lbl in labels:
        row = f"  {lbl:<16} "
        row += "  ".join(f"{counts.get(s, {}).get(lbl, 0):>22}" for s in slugs)
        print(row)

    # 3. Onboarding-status distribution
    _section("3. Onboarding-status distribution")
    for s in slugs:
        print(f"  [{s}]")
        sub = onboarding.get(s, {})
        if not sub:
            print("    (no data)")
            continue
        for category, dist in sub.items():
            print(f"    {category}:")
            for status, n in sorted(dist.items()):
                print(f"      {status:<20} : {n}")

    # 4. Recent activity
    _section("4. Recent activity (most recent timestamp per source)")
    for s in slugs:
        print(f"  [{s}]")
        sub = recent.get(s, {})
        if not sub:
            print("    (no data)")
            continue
        for k in ("max_device_last_heartbeat", "max_site_last_checkin"):
            print(f"    {k:<28} : {sub.get(k)}")
        mc = sub.get("max_created_at", {})
        for lbl in labels:
            if lbl in mc:
                print(f"    max(created_at) {lbl:<14} : {mc[lbl]}")

    # 5. Users
    _section("5. User roster")
    for s in slugs:
        rs = users.get(s, [])
        print(f"  [{s}]  {len(rs)} user(s)")
        for u in rs[:50]:
            print(
                f"    {u['email']:<40} {u['role']:<10} "
                f"active={u['is_active']}  created={u['created_at']}"
            )
        if len(rs) > 50:
            print(f"    … {len(rs) - 50} more (see JSON)")

    # 6. Customers
    _section("6. Customer roster")
    for s in slugs:
        rs = customers.get(s, [])
        print(f"  [{s}]  {len(rs)} customer(s)")
        for c in rs[:50]:
            print(
                f"    id={c['id']:<6} sites={c['site_count']:<4}  "
                f"zoho_acct={c['zoho_account_id'] or '-':<20}  "
                f"onboarding={c['onboarding_status'] or '-':<12}  "
                f"{c['name']}"
            )
        if len(rs) > 50:
            print(f"    … {len(rs) - 50} more (see JSON)")

    # 7. Cross-links
    _section("7. Cross-tenant linkage (dangerous if non-empty)")
    a = crosslinks["site_customer_tenant_mismatch"]
    b = crosslinks["device_site_tenant_mismatch"]
    c = crosslinks["user_email_collision"]
    print(f"  a) sites whose customer is in a different tenant : {len(a)}")
    for row in a[:25]:
        print(
            f"     site_id={row['site_id']:<24} tenant={row['site_tenant_id']:<22} "
            f"→ customer_id={row['customer_pk']} (tenant={row['customer_tenant_id']}, "
            f"name={row['customer_name']!r})"
        )
    if len(a) > 25:
        print(f"     … {len(a) - 25} more (see JSON)")
    print(f"  b) devices whose site is in a different tenant   : {len(b)}")
    for row in b[:25]:
        print(
            f"     device_id={row['device_id']:<24} tenant={row['device_tenant_id']:<22} "
            f"→ site_id={row['site_id']} (tenant={row['site_tenant_id']})"
        )
    if len(b) > 25:
        print(f"     … {len(b) - 25} more (see JSON)")
    print(f"  c) users with duplicate emails across RH tenants : {len(c)}")
    for row in c:
        print(f"     email={row['email']}  count={row['count']}  tenants={row['tenant_ids']}")

    # 8. Site-ID collisions
    _section("8. site_id values claimed by both tenants")
    if not site_collisions:
        print("  none (sites.site_id is globally unique by schema — expected)")
    else:
        for row in site_collisions:
            print(f"  site_id={row['site_id']}  appears {row['count']}× in tenants={row['tenant_ids']}")

    # 9. Orphans
    _section("9. Orphan check (rows in RH slug whose tenant row is missing)")
    if not orphans:
        print("  none — both slugs are present in the tenants table")
    else:
        for slug, rows in orphans.items():
            print(f"  {slug}:  " + "; ".join(rows))

    _banner("End of audit  (READ-ONLY — no rows were modified)")


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--slug",
        action="append",
        default=None,
        help="Tenant slug to audit.  Pass twice for two slugs.  "
             "Default: --slug rh --slug restoration-hardware",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Write the JSON file and skip the pretty-printed report.",
    )
    args = parser.parse_args()

    slugs = list(args.slug) if args.slug else list(DEFAULT_SLUGS)
    if len(slugs) < 2:
        print(
            "Note: this script is designed to compare two tenants; "
            f"running with {len(slugs)} slug(s).",
            file=sys.stderr,
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ran_at = datetime.now(timezone.utc).isoformat()

    async with AsyncSessionLocal() as db:
        meta = await _tenant_metadata(db, slugs)
        counts = await _row_counts(db, slugs)
        onboarding = await _onboarding_status_distribution(db, slugs)
        recent = await _recent_activity(db, slugs)
        users = await _user_roster(db, slugs)
        customers = await _customer_roster(db, slugs)
        crosslinks = await _cross_links(db, slugs)
        site_collisions = await _site_id_collisions(db, slugs)
        orphans = await _orphan_check(db, slugs, set(meta.keys()))

    report = {
        "ran_at":                        ran_at,
        "target_slugs":                  slugs,
        "tenant_metadata":               meta,
        "row_counts":                    counts,
        "onboarding_status_distribution": onboarding,
        "recent_activity":               recent,
        "user_roster":                   users,
        "customer_roster":               customers,
        "cross_links":                   crosslinks,
        "site_id_collisions":            site_collisions,
        "orphans":                       orphans,
    }

    JSON_OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    if not args.json_only:
        _print_report(report)

    print()
    print(f"  wrote {JSON_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
