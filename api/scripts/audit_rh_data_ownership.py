#!/usr/bin/env python3
"""Read-only audit of Restoration Hardware customer/site/device ownership.

Context
-------
We have two RH tenants:
    rh                       — inactive duplicate (deduped by
                                scripts/dedupe_tenant_rh.py)
    restoration-hardware     — active, canonical target

But operational data is currently scattered.  A prior pass
(``scripts/consolidate_rh_to_default.py``) moved most operational
rows from ``restoration-hardware`` into ``default``.  A follow-on
script (``scripts/reassign_rh_sites.py``) was written to reverse that
for SITES + their linked devices/service_units/sims/lines, but
deliberately excluded customers.

This audit answers: where do RH customers / sites / devices actually
live today, and what is the gap to "everything under
``restoration-hardware``"?

Matching rules (lift-and-shift from reassign_rh_sites.py, extended)
------------------------------------------------------------------
A name is treated as Restoration Hardware if any of:
  * starts with (case-insensitive) "restoration hardware"
  * is exactly "rh" or starts with "rh "/"rh-"/"rh,"
  * contains "pleaston" or "pleasanton"  (typo + correct spelling
    are both common in current RH site labels)

Customers:   matched against ``customers.name``
Sites:       matched against ``sites.site_name``  OR  ``sites.customer_name``
             OR ``sites.customer_id`` -> a matched customer
Devices:     a device is considered "RH" if its ``site_id`` points at
             a matched site, OR its ``tenant_id`` is one of the RH
             tenants (``rh`` / ``restoration-hardware``).

100% READ-ONLY.  No INSERT, UPDATE, DELETE, or DDL is issued.

What the audit reports
----------------------
  1. RH customer roster (id, name, tenant_id, customer_number, zoho)
  2. RH site roster (site_id, site_name, customer_name, customer_id,
     tenant_id, status, device_count)
  3. RH device roster (device_id, tenant_id, site_id, status)
  4. Tenant-distribution table (customers / sites / devices × tenant_id)
  5. Split-ownership findings:
        - RH sites whose tenant_id != restoration-hardware
        - RH devices whose tenant_id != restoration-hardware
        - RH devices attached to a non-RH site
        - RH sites with zero devices
        - RH sites whose customer_id points at a non-RH customer
        - RH customers whose tenant_id != restoration-hardware
  6. Concrete remediation recommendation (text only — no code generated)

Outputs
-------
* Pretty-printed report on stdout.
* JSON dump at api/reports/rh_data_ownership_audit.json with the
  same findings in structured form.

Usage on Render shell:

    cd /opt/render/project/src/api
    python -m scripts.audit_rh_data_ownership

Read-only.  Safe to re-run.  Safe under live traffic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Make ``app.*`` importable from either invocation form.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402


RH_TENANT_SLUGS = ("rh", "restoration-hardware")
CANONICAL_TENANT_SLUG = "restoration-hardware"
DUPLICATE_TENANT_SLUG = "rh"

REPORTS_DIR = Path(_API_DIR) / "reports"
JSON_OUT = REPORTS_DIR / "rh_data_ownership_audit.json"


# ─────────────────────────────────────────────────────────────────────
# Name matching — mirrors scripts/reassign_rh_sites.py::_is_rh_customer
# with the extra Pleaston/Pleasanton patterns the operator requested.
# ─────────────────────────────────────────────────────────────────────

_RH_NAME_RE = re.compile(
    r"""
    (^restoration\s+hardware\b)        # starts with "Restoration Hardware"
    | (^rh$)                            # exactly "RH"
    | (^rh[\s\-,])                      # "RH " / "RH-" / "RH,"
    | (pleaston)                        # typo variant
    | (pleasanton)                      # correct spelling
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_rh_name(name: Optional[str]) -> bool:
    if not name:
        return False
    return bool(_RH_NAME_RE.search(name.strip()))


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


# ─────────────────────────────────────────────────────────────────────
# Audit phases
# ─────────────────────────────────────────────────────────────────────

async def _tenant_metadata(db: AsyncSession) -> dict[str, dict[str, Any]]:
    r = await db.execute(select(Tenant).where(Tenant.tenant_id.in_(RH_TENANT_SLUGS)))
    out: dict[str, dict[str, Any]] = {}
    for t in r.scalars().all():
        out[t.tenant_id] = {
            "pk":              t.id,
            "tenant_id":       t.tenant_id,
            "name":            t.name,
            "display_name":    t.display_name,
            "is_active":       bool(t.is_active),
            "org_type":        t.org_type,
            "zoho_account_id": t.zoho_account_id,
        }
    return out


async def _rh_customers(db: AsyncSession) -> list[Customer]:
    """All customers whose name matches the RH pattern, across all tenants."""
    r = await db.execute(select(Customer).order_by(Customer.tenant_id, Customer.id))
    return [c for c in r.scalars().all() if is_rh_name(c.name)]


async def _rh_sites(
    db: AsyncSession, rh_customer_ids: set[int]
) -> list[Site]:
    """Sites where site_name OR customer_name matches, OR whose customer_id
    points at a matched customer, OR tenant_id is one of the RH slugs."""
    r = await db.execute(select(Site).order_by(Site.tenant_id, Site.id))
    out: list[Site] = []
    for s in r.scalars().all():
        if is_rh_name(s.site_name):
            out.append(s)
            continue
        if is_rh_name(s.customer_name):
            out.append(s)
            continue
        if s.customer_id in rh_customer_ids:
            out.append(s)
            continue
        if s.tenant_id in RH_TENANT_SLUGS:
            out.append(s)
            continue
    return out


async def _rh_devices(
    db: AsyncSession, rh_site_id_slugs: set[str]
) -> list[Device]:
    """Devices that are either attached to an RH site OR live in an RH tenant."""
    r = await db.execute(select(Device).order_by(Device.tenant_id, Device.id))
    out: list[Device] = []
    for d in r.scalars().all():
        if d.site_id in rh_site_id_slugs:
            out.append(d)
        elif d.tenant_id in RH_TENANT_SLUGS:
            out.append(d)
    return out


async def _device_counts_per_site(
    db: AsyncSession, site_id_slugs: list[str]
) -> dict[str, int]:
    if not site_id_slugs:
        return {}
    r = await db.execute(
        select(Device.site_id, func.count())
        .where(Device.site_id.in_(site_id_slugs))
        .group_by(Device.site_id)
    )
    return {sid: int(n) for sid, n in r.all()}


# ─────────────────────────────────────────────────────────────────────
# Report builder
# ─────────────────────────────────────────────────────────────────────

def _build_findings(
    customers: list[Customer],
    sites: list[Site],
    devices: list[Device],
    device_counts: dict[str, int],
    rh_customer_ids: set[int],
    rh_site_id_slugs: set[str],
) -> dict[str, Any]:
    findings: dict[str, Any] = {}

    findings["sites_not_in_canonical"] = [
        {
            "site_pk":      s.id,
            "site_id":      s.site_id,
            "site_name":    s.site_name,
            "customer_id":  s.customer_id,
            "customer_name": s.customer_name,
            "tenant_id":    s.tenant_id,
            "status":       s.status,
            "device_count": device_counts.get(s.site_id, 0),
        }
        for s in sites if s.tenant_id != CANONICAL_TENANT_SLUG
    ]

    findings["devices_not_in_canonical"] = [
        {
            "device_pk":  d.id,
            "device_id":  d.device_id,
            "tenant_id":  d.tenant_id,
            "site_id":    d.site_id,
            "status":     d.status,
        }
        for d in devices if d.tenant_id != CANONICAL_TENANT_SLUG
    ]

    findings["devices_on_non_rh_site"] = [
        {
            "device_pk": d.id,
            "device_id": d.device_id,
            "tenant_id": d.tenant_id,
            "site_id":   d.site_id,
            "status":    d.status,
        }
        for d in devices
        if d.site_id is not None and d.site_id not in rh_site_id_slugs
    ]

    findings["sites_with_no_devices"] = [
        {
            "site_pk":     s.id,
            "site_id":     s.site_id,
            "site_name":   s.site_name,
            "tenant_id":   s.tenant_id,
            "customer_id": s.customer_id,
        }
        for s in sites if device_counts.get(s.site_id, 0) == 0
    ]

    findings["sites_pointing_at_non_rh_customer"] = [
        {
            "site_pk":     s.id,
            "site_id":     s.site_id,
            "site_name":   s.site_name,
            "tenant_id":   s.tenant_id,
            "customer_id": s.customer_id,
            "customer_name_on_site": s.customer_name,
        }
        for s in sites
        if s.customer_id is not None and s.customer_id not in rh_customer_ids
    ]

    findings["customers_not_in_canonical"] = [
        {
            "customer_pk":      c.id,
            "name":             c.name,
            "customer_number":  c.customer_number,
            "tenant_id":        c.tenant_id,
            "zoho_account_id":  c.zoho_account_id,
            "status":           c.status,
        }
        for c in customers if c.tenant_id != CANONICAL_TENANT_SLUG
    ]

    return findings


def _tenant_distribution(
    customers: list[Customer],
    sites: list[Site],
    devices: list[Device],
) -> dict[str, dict[str, int]]:
    """{ "customers": {tenant: n}, "sites": {tenant: n}, "devices": {tenant: n} }"""
    out: dict[str, dict[str, int]] = {
        "customers": defaultdict(int),
        "sites":     defaultdict(int),
        "devices":   defaultdict(int),
    }
    for c in customers:
        out["customers"][c.tenant_id or "<null>"] += 1
    for s in sites:
        out["sites"][s.tenant_id or "<null>"] += 1
    for d in devices:
        out["devices"][d.tenant_id or "<null>"] += 1
    return {k: dict(v) for k, v in out.items()}


def _build_remediation_text(
    tenant_meta: dict[str, dict[str, Any]],
    customers: list[Customer],
    sites: list[Site],
    devices: list[Device],
    findings: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    n_cust_to_move = len(findings["customers_not_in_canonical"])
    n_sites_to_move = len(findings["sites_not_in_canonical"])
    n_devs_to_move = len(findings["devices_not_in_canonical"])

    canonical_present = CANONICAL_TENANT_SLUG in tenant_meta
    duplicate_present = DUPLICATE_TENANT_SLUG in tenant_meta
    canonical_active = canonical_present and tenant_meta[CANONICAL_TENANT_SLUG]["is_active"]

    lines.append("Recommended remediation plan  (text only — no code is generated here)")
    lines.append("")
    lines.append(f"Canonical target: tenant_id = {CANONICAL_TENANT_SLUG!r}")
    if not canonical_present:
        lines.append(
            f"  ⚠  Canonical tenant {CANONICAL_TENANT_SLUG!r} is MISSING from the tenants table. "
            "Create it before any move."
        )
    elif not canonical_active:
        lines.append(
            f"  ⚠  Canonical tenant exists but is_active=False. "
            "Reactivate before any move."
        )
    else:
        lines.append(
            f"  ✓ Canonical tenant exists and is_active=True "
            f"(pk={tenant_meta[CANONICAL_TENANT_SLUG]['pk']})."
        )

    lines.append("")
    lines.append("Proposed scope (DRY-RUN-default script — not written yet):")
    lines.append(
        f"  - move {n_cust_to_move} customer row(s) -> tenant_id = {CANONICAL_TENANT_SLUG!r}"
    )
    lines.append(
        f"  - move {n_sites_to_move} site row(s)     -> tenant_id = {CANONICAL_TENANT_SLUG!r}"
    )
    lines.append(
        f"  - move {n_devs_to_move} device row(s)    -> tenant_id = {CANONICAL_TENANT_SLUG!r}"
    )
    lines.append("")
    lines.append("Out of scope (intentionally untouched):")
    lines.append("  - non-RH customers (no name match)")
    lines.append("  - non-RH sites and their devices")
    lines.append(f"  - the inactive duplicate tenant {DUPLICATE_TENANT_SLUG!r} "
                 "(remains as-is for audit history)")
    lines.append("  - any *_audit / audit_log_entries rows (historical context preserved)")
    lines.append("  - schema (no DDL, no new columns)")
    lines.append("  - RBAC, auth, API sync flags")
    lines.append("")
    lines.append("Suggested execution sequence:")
    lines.append("  1. Run this audit; archive the JSON output.")
    lines.append("  2. If any cross-link concerns exist (sites pointing at non-RH")
    lines.append("     customers, devices on non-RH sites), resolve those FIRST.")
    lines.append("  3. Write a dedicated DRY-RUN remediation script that:")
    lines.append("       - moves customers -> restoration-hardware")
    lines.append(f"         (idempotent: WHERE tenant_id != {CANONICAL_TENANT_SLUG!r})")
    lines.append("       - moves sites    -> restoration-hardware (same guard)")
    lines.append("       - moves devices  -> restoration-hardware (same guard)")
    lines.append("       - writes one audit row per category to action_audits")
    lines.append("       - leaves customers.id, customers.zoho_account_id,")
    lines.append("         sites.site_id, devices.device_id unchanged")
    lines.append("  4. Apply only after the dry-run output is reviewed by a human.")
    lines.append("")
    lines.append("Linked-table reminder:")
    lines.append("  Per existing scripts/reassign_rh_sites.py and Phase 2 plan,")
    lines.append("  service_units / sims / lines that share an RH site_id should")
    lines.append("  follow their site.  Incidents / events / notifications were")
    lines.append("  historically left on the FROM tenant — confirm policy before")
    lines.append("  writing the remediation script.")
    return lines


# ─────────────────────────────────────────────────────────────────────
# Pretty-print
# ─────────────────────────────────────────────────────────────────────

def _print_report(report: dict[str, Any]) -> None:
    meta = report["tenant_metadata"]
    distribution = report["tenant_distribution"]
    customers = report["customer_roster"]
    sites = report["site_roster"]
    devices = report["device_roster"]
    findings = report["findings"]
    remediation = report["remediation_recommendation"]

    _banner(f"RH customer/site/device ownership audit  (read-only; ran at {report['ran_at']})")

    # Tenant metadata
    _section("RH tenant metadata")
    for s in RH_TENANT_SLUGS:
        m = meta.get(s)
        if not m:
            print(f"  {s!r}: NOT present in tenants table")
            continue
        print(
            f"  [{s}]  pk={m['pk']}  is_active={m['is_active']}  "
            f"org_type={m['org_type']!r}  name={m['name']!r}  "
            f"display_name={m['display_name']!r}"
        )

    # Headline counts
    _section("Headline counts")
    print(f"  RH customers matched : {len(customers)}")
    print(f"  RH sites matched     : {len(sites)}")
    print(f"  RH devices matched   : {len(devices)}")

    # Tenant distribution
    _section("Current tenant distribution")
    for entity in ("customers", "sites", "devices"):
        dist = distribution[entity]
        print(f"  {entity}:")
        if not dist:
            print("    (none)")
            continue
        for tid, n in sorted(dist.items(), key=lambda kv: (-kv[1], kv[0])):
            tag = "  ← CANONICAL" if tid == CANONICAL_TENANT_SLUG else (
                "  ← duplicate (inactive)" if tid == DUPLICATE_TENANT_SLUG else ""
            )
            print(f"    {tid:<24} : {n:>5}{tag}")

    # Customer roster
    _section(f"Customer roster — {len(customers)} row(s)")
    if not customers:
        print("  (no RH customers found)")
    else:
        print(f"  {'id':>6}  {'tenant_id':<24}  {'cust_number':<14}  {'zoho_account':<22}  name")
        print("  " + "-" * 96)
        for c in customers:
            print(
                f"  {c['customer_pk']:>6}  {c['tenant_id'] or '<null>':<24}  "
                f"{c['customer_number'] or '-':<14}  "
                f"{c['zoho_account_id'] or '-':<22}  {c['name']}"
            )

    # Site roster
    _section(f"Site roster — {len(sites)} row(s)")
    if not sites:
        print("  (no RH sites found)")
    else:
        # Print first 60 only to keep stdout sane; full data is in JSON.
        print(
            f"  {'site_id':<24} {'tenant_id':<22} {'cust_id':<7} "
            f"{'status':<11} {'devs':<4}  site_name"
        )
        print("  " + "-" * 100)
        for s in sites[:60]:
            print(
                f"  {s['site_id']:<24} {s['tenant_id'] or '<null>':<22} "
                f"{str(s['customer_id'] or '-'):<7} "
                f"{s['status'] or '-':<11} {s['device_count']:<4}  "
                f"{s['site_name']}"
            )
        if len(sites) > 60:
            print(f"  … {len(sites) - 60} more (see JSON)")

    # Device roster (short)
    _section(f"Device roster — {len(devices)} row(s)")
    if not devices:
        print("  (no RH devices found)")
    else:
        print(
            f"  {'device_id':<26} {'tenant_id':<22} {'site_id':<22} status"
        )
        print("  " + "-" * 90)
        for d in devices[:60]:
            print(
                f"  {d['device_id']:<26} {d['tenant_id'] or '<null>':<22} "
                f"{d['site_id'] or '<null>':<22} {d['status'] or '-'}"
            )
        if len(devices) > 60:
            print(f"  … {len(devices) - 60} more (see JSON)")

    # Findings
    _section("Split / mismatched-ownership findings")
    for key in (
        "customers_not_in_canonical",
        "sites_not_in_canonical",
        "devices_not_in_canonical",
        "devices_on_non_rh_site",
        "sites_with_no_devices",
        "sites_pointing_at_non_rh_customer",
    ):
        n = len(findings[key])
        print(f"  {key:<38} : {n}")

    # Remediation recommendation
    _section("Remediation recommendation")
    for line in remediation:
        print(f"  {line}")

    _banner("End of audit  (READ-ONLY — no rows were modified)")


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Write the JSON file and skip the pretty-printed report.",
    )
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ran_at = datetime.now(timezone.utc).isoformat()

    async with AsyncSessionLocal() as db:
        tenant_meta = await _tenant_metadata(db)

        customers = await _rh_customers(db)
        rh_customer_ids = {c.id for c in customers}

        sites = await _rh_sites(db, rh_customer_ids)
        rh_site_id_slugs = {s.site_id for s in sites if s.site_id}

        devices = await _rh_devices(db, rh_site_id_slugs)

        device_counts = await _device_counts_per_site(db, list(rh_site_id_slugs))

    # Build structured views
    customer_roster = [
        {
            "customer_pk":      c.id,
            "name":             c.name,
            "customer_number":  c.customer_number,
            "tenant_id":        c.tenant_id,
            "zoho_account_id":  c.zoho_account_id,
            "status":           c.status,
            "onboarding_status": c.onboarding_status,
            "created_at":       _iso(c.created_at),
        }
        for c in customers
    ]
    site_roster = [
        {
            "site_pk":          s.id,
            "site_id":          s.site_id,
            "site_name":        s.site_name,
            "customer_id":      s.customer_id,
            "customer_name":    s.customer_name,
            "tenant_id":        s.tenant_id,
            "status":           s.status,
            "onboarding_status": s.onboarding_status,
            "e911_city":        s.e911_city,
            "e911_state":       s.e911_state,
            "device_count":     device_counts.get(s.site_id, 0),
            "created_at":       _iso(s.created_at),
        }
        for s in sites
    ]
    device_roster = [
        {
            "device_pk":   d.id,
            "device_id":   d.device_id,
            "tenant_id":   d.tenant_id,
            "site_id":     d.site_id,
            "status":      d.status,
            "device_type": d.device_type,
            "model":       d.model,
            "created_at":  _iso(d.created_at),
        }
        for d in devices
    ]

    findings = _build_findings(
        customers, sites, devices, device_counts, rh_customer_ids, rh_site_id_slugs,
    )
    distribution = _tenant_distribution(customers, sites, devices)
    remediation = _build_remediation_text(
        tenant_meta, customers, sites, devices, findings,
    )

    report: dict[str, Any] = {
        "ran_at":                     ran_at,
        "canonical_tenant_slug":      CANONICAL_TENANT_SLUG,
        "duplicate_tenant_slug":      DUPLICATE_TENANT_SLUG,
        "tenant_metadata":            tenant_meta,
        "tenant_distribution":        distribution,
        "customer_roster":            customer_roster,
        "site_roster":                site_roster,
        "device_roster":              device_roster,
        "findings":                   findings,
        "remediation_recommendation": remediation,
    }

    JSON_OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    if not args.json_only:
        _print_report(report)

    print()
    print(f"  wrote {JSON_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
