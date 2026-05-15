#!/usr/bin/env python3
"""Move Restoration Hardware operational data to tenant_id='restoration-hardware'.

DRY-RUN BY DEFAULT.  Writes require BOTH ``--apply`` AND ``DRY_RUN``
env var NOT set to "true".  Anything else (default, ``DRY_RUN=true``,
``--dry-run``, omitting ``--apply``) issues zero UPDATE statements.

What this script does (and ONLY this)
-------------------------------------
For every row matched as Restoration Hardware (see "Matching rules"
below) whose ``tenant_id`` is not already the canonical
``'restoration-hardware'``:

  - sets   customers.tenant_id   = 'restoration-hardware'
  - sets   sites.tenant_id       = 'restoration-hardware'
  - sets   devices.tenant_id     = 'restoration-hardware'

That's it.  No other column on those rows is touched.  No other
table is touched.

Matching rules (mirror api/scripts/audit_rh_data_ownership.py)
--------------------------------------------------------------
A name is treated as Restoration Hardware if any of:
  * starts with (case-insensitive) "restoration hardware"
  * is exactly "rh", or starts with "rh "/"rh-"/"rh,"
  * contains "pleaston" or "pleasanton"

Customers: matched against ``customers.name``.
Sites:     matched against ``site_name`` OR ``customer_name``,
           OR ``customer_id`` -> a matched customer,
           OR ``tenant_id`` ∈ ('rh', 'restoration-hardware').
Devices:   matched if ``site_id`` -> a matched site,
           OR ``tenant_id`` ∈ ('rh', 'restoration-hardware').

Out of scope (intentionally untouched)
--------------------------------------
  * customers.id, sites.id, devices.id, sites.site_id, devices.device_id
  * customers.customer_number / zoho_account_id / billing_*
  * sites.customer_id, sites.site_name, sites.customer_name, sites.e911_*,
    sites.status, sites.notes, sites.lat, sites.lng, sites.last_*,
    sites.reconciliation_status, sites.import_batch_id
  * devices.site_id, devices.serial_number / mac_address / imei /
    iccid / msisdn / firmware_version / container_version / provision_code
  * tenants.* — including the inactive 'rh' tenant
  * users, registrations, registration_locations
  * incidents, events, notifications, command_*, telemetry_*, history
  * service_units, sims, lines, recordings, site_vendors, etc.
  * API credentials, RBAC, auth, schema

Validation (refuses to apply on any failure)
--------------------------------------------
  1. Canonical tenant 'restoration-hardware' must exist.
  2. Canonical tenant must be is_active=True.
  3. Cross-link safety:
       a. Every matched site whose customer_id is set must point at a
          MATCHED RH customer.  A matched RH site that links to a
          non-RH customer is treated as a data anomaly and the script
          aborts.
       b. Every matched device whose site_id is set must point at a
          MATCHED RH site.  A matched RH device on a non-RH site
          aborts the script.

Audit logging
-------------
One ``audit_log_entries`` row is inserted per apply run with:

    entry_id    = 'rh-tenant-remediate-<utc-iso>-<uuid8>'
    tenant_id   = 'restoration-hardware'
    category    = 'security'
    action      = 'remediate_rh_tenant_assignment'
    actor       = 'remediate_script'
    target_type = 'tenant'
    target_id   = 'restoration-hardware'
    summary     = human-readable
    detail_json = {
        "request_id":        ...,
        "canonical_tenant":  "restoration-hardware",
        "customers_moved":   [{id, old_tenant_id, new_tenant_id}, …],
        "sites_moved":       [{site_pk, site_id, old_tenant_id, new_tenant_id}, …],
        "devices_moved":     [{device_pk, device_id, old_tenant_id, new_tenant_id}, …],
        "before_counts":     {customers, sites, devices},
        "after_counts":      {customers, sites, devices},
        "matched_total":     {customers, sites, devices},
    }

Idempotency
-----------
Every UPDATE is guarded by ``WHERE tenant_id != 'restoration-hardware'``.
A re-run of this script (with --apply) is a no-op for any row that
was moved by a prior run.  If nothing is left to move, no audit row
is written.

Rollback
--------
Every move is reversible from the audit row alone.  Find the entry_id
of the run you want to undo, then:

    -- 1. Restore customers
    UPDATE customers c
       SET tenant_id = j.old
      FROM (
        SELECT (elem->>'id')::int       AS id,
               elem->>'old_tenant_id'   AS old
          FROM audit_log_entries,
               jsonb_array_elements(detail_json::jsonb->'customers_moved') elem
         WHERE entry_id = '<entry_id>'
      ) j
     WHERE c.id = j.id
       AND c.tenant_id = 'restoration-hardware';

    -- 2. Restore sites
    UPDATE sites s
       SET tenant_id = j.old
      FROM (
        SELECT (elem->>'site_pk')::int  AS pk,
               elem->>'old_tenant_id'   AS old
          FROM audit_log_entries,
               jsonb_array_elements(detail_json::jsonb->'sites_moved') elem
         WHERE entry_id = '<entry_id>'
      ) j
     WHERE s.id = j.pk
       AND s.tenant_id = 'restoration-hardware';

    -- 3. Restore devices
    UPDATE devices d
       SET tenant_id = j.old
      FROM (
        SELECT (elem->>'device_pk')::int AS pk,
               elem->>'old_tenant_id'    AS old
          FROM audit_log_entries,
               jsonb_array_elements(detail_json::jsonb->'devices_moved') elem
         WHERE entry_id = '<entry_id>'
      ) j
     WHERE d.id = j.pk
       AND d.tenant_id = 'restoration-hardware';

No schema changes.  No deletes.  No tenant rows touched.

Usage on Render shell:

    cd /opt/render/project/src/api
    # 1. Dry-run (default).  Emits the full plan, writes nothing.
    DRY_RUN=true python -m scripts.remediate_rh_tenant_assignment

    # 2. Cap-and-apply (after reviewing the dry-run).  --limit caps
    #    each entity type separately — useful for a small first pass.
    DRY_RUN=false python -m scripts.remediate_rh_tenant_assignment --apply --limit 5

    # 3. Full apply.
    DRY_RUN=false python -m scripts.remediate_rh_tenant_assignment --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Make ``app.*`` importable from either invocation form.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.audit_log_entry import AuditLogEntry  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402


logger = logging.getLogger("remediate_rh_tenant_assignment")


CANONICAL_TENANT_SLUG = "restoration-hardware"
DUPLICATE_TENANT_SLUG = "rh"
RH_TENANT_SLUGS = (DUPLICATE_TENANT_SLUG, CANONICAL_TENANT_SLUG)

ACTION_TYPE = "remediate_rh_tenant_assignment"
SUMMARY_TEMPLATE = (
    "Migrated Restoration Hardware operational data to tenant_id={canonical!r}: "
    "{customers} customer(s), {sites} site(s), {devices} device(s) moved."
)


# ─────────────────────────────────────────────────────────────────────
# Name matching — must match api/scripts/audit_rh_data_ownership.py
# ─────────────────────────────────────────────────────────────────────

_RH_NAME_RE = re.compile(
    r"""
    (^restoration\s+hardware\b)
    | (^rh$)
    | (^rh[\s\-,])
    | (pleaston)
    | (pleasanton)
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


def _env_dry_run_default_true() -> bool:
    raw = os.getenv("DRY_RUN")
    if raw is None:
        return True
    return raw.strip().lower() not in {"false", "0", "no", "off"}


# ─────────────────────────────────────────────────────────────────────
# Pre-flight validation
# ─────────────────────────────────────────────────────────────────────

async def _resolve_canonical(db: AsyncSession) -> Optional[Tenant]:
    r = await db.execute(select(Tenant).where(Tenant.tenant_id == CANONICAL_TENANT_SLUG))
    return r.scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────
# Scope collection (mirrors audit_rh_data_ownership.py)
# ─────────────────────────────────────────────────────────────────────

async def _collect_scope(db: AsyncSession) -> dict[str, Any]:
    """Returns plain snapshots (lists of dicts) — no ORM access after this."""
    # Customers
    cust_r = await db.execute(select(Customer))
    matched_customers = [c for c in cust_r.scalars().all() if is_rh_name(c.name)]
    cust_snaps = [
        {
            "pk":        c.id,
            "name":      c.name,
            "tenant_id": c.tenant_id,
        }
        for c in matched_customers
    ]
    rh_customer_ids = {c.id for c in matched_customers}

    # Sites
    site_r = await db.execute(select(Site))
    matched_sites = []
    for s in site_r.scalars().all():
        if (
            is_rh_name(s.site_name)
            or is_rh_name(s.customer_name)
            or s.customer_id in rh_customer_ids
            or s.tenant_id in RH_TENANT_SLUGS
        ):
            matched_sites.append(s)
    site_snaps = [
        {
            "pk":            s.id,
            "site_id":       s.site_id,
            "site_name":     s.site_name,
            "customer_id":   s.customer_id,
            "customer_name": s.customer_name,
            "tenant_id":     s.tenant_id,
        }
        for s in matched_sites
    ]
    rh_site_id_slugs = {s.site_id for s in matched_sites if s.site_id}

    # Devices
    dev_r = await db.execute(select(Device))
    matched_devices = []
    for d in dev_r.scalars().all():
        if d.site_id in rh_site_id_slugs:
            matched_devices.append(d)
        elif d.tenant_id in RH_TENANT_SLUGS:
            matched_devices.append(d)
    dev_snaps = [
        {
            "pk":         d.id,
            "device_id":  d.device_id,
            "site_id":    d.site_id,
            "tenant_id":  d.tenant_id,
        }
        for d in matched_devices
    ]

    return {
        "customers":         cust_snaps,
        "sites":             site_snaps,
        "devices":           dev_snaps,
        "rh_customer_ids":   rh_customer_ids,
        "rh_site_id_slugs":  rh_site_id_slugs,
    }


def _detect_cross_links(scope: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Returns lists of cross-link findings.  Empty == safe to apply."""
    rh_customer_ids: set[int] = scope["rh_customer_ids"]
    rh_site_id_slugs: set[str] = scope["rh_site_id_slugs"]

    sites_on_non_rh_customer = [
        s for s in scope["sites"]
        if s["customer_id"] is not None and s["customer_id"] not in rh_customer_ids
    ]
    devices_on_non_rh_site = [
        d for d in scope["devices"]
        if d["site_id"] is not None and d["site_id"] not in rh_site_id_slugs
    ]
    return {
        "sites_on_non_rh_customer": sites_on_non_rh_customer,
        "devices_on_non_rh_site":   devices_on_non_rh_site,
    }


def _movable(scope_list: list[dict[str, Any]], canonical: str) -> list[dict[str, Any]]:
    return [r for r in scope_list if r.get("tenant_id") != canonical]


# ─────────────────────────────────────────────────────────────────────
# Pretty-print
# ─────────────────────────────────────────────────────────────────────

def _print_counts_table(title: str, rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.get("tenant_id") or "<null>"] = counts.get(r.get("tenant_id") or "<null>", 0) + 1
    print(f"  {title}:")
    if not counts:
        print("    (none)")
        return
    for tid, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        tag = "  ← CANONICAL" if tid == CANONICAL_TENANT_SLUG else (
            "  ← duplicate (inactive)" if tid == DUPLICATE_TENANT_SLUG else ""
        )
        print(f"    {tid:<24}: {n}{tag}")


# ─────────────────────────────────────────────────────────────────────
# Apply
# ─────────────────────────────────────────────────────────────────────

async def _apply(
    db: AsyncSession,
    customers_to_move: list[dict[str, Any]],
    sites_to_move: list[dict[str, Any]],
    devices_to_move: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Perform the UPDATE statements, return per-row move logs."""
    moved_customers: list[dict[str, Any]] = []
    moved_sites: list[dict[str, Any]] = []
    moved_devices: list[dict[str, Any]] = []

    for c in customers_to_move:
        res = await db.execute(
            update(Customer)
            .where(Customer.id == c["pk"])
            .where(Customer.tenant_id != CANONICAL_TENANT_SLUG)
            .values(tenant_id=CANONICAL_TENANT_SLUG)
        )
        if res.rowcount == 1:
            moved_customers.append({
                "id":             c["pk"],
                "name":           c["name"],
                "old_tenant_id":  c["tenant_id"],
                "new_tenant_id":  CANONICAL_TENANT_SLUG,
            })
        else:
            logger.info(
                "customer move skipped (already canonical or concurrent move)  pk=%s",
                c["pk"],
            )

    for s in sites_to_move:
        res = await db.execute(
            update(Site)
            .where(Site.id == s["pk"])
            .where(Site.tenant_id != CANONICAL_TENANT_SLUG)
            .values(tenant_id=CANONICAL_TENANT_SLUG)
        )
        if res.rowcount == 1:
            moved_sites.append({
                "site_pk":        s["pk"],
                "site_id":        s["site_id"],
                "old_tenant_id":  s["tenant_id"],
                "new_tenant_id":  CANONICAL_TENANT_SLUG,
            })
        else:
            logger.info(
                "site move skipped (already canonical or concurrent move)  pk=%s",
                s["pk"],
            )

    for d in devices_to_move:
        res = await db.execute(
            update(Device)
            .where(Device.id == d["pk"])
            .where(Device.tenant_id != CANONICAL_TENANT_SLUG)
            .values(tenant_id=CANONICAL_TENANT_SLUG)
        )
        if res.rowcount == 1:
            moved_devices.append({
                "device_pk":      d["pk"],
                "device_id":      d["device_id"],
                "old_tenant_id":  d["tenant_id"],
                "new_tenant_id":  CANONICAL_TENANT_SLUG,
            })
        else:
            logger.info(
                "device move skipped (already canonical or concurrent move)  pk=%s",
                d["pk"],
            )

    return moved_customers, moved_sites, moved_devices


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply writes.  Without --apply (or with DRY_RUN!=false or "
             "--dry-run), no UPDATEs are issued.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run even if --apply is also passed.  Belt-and-braces.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap each entity type independently (customers/sites/devices) "
             "to N rows.  Useful for a small first apply.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    env_dry = _env_dry_run_default_true()
    apply_writes = args.apply and not env_dry and not args.dry_run

    started = datetime.now(timezone.utc)
    request_id = f"rh-tenant-remediate-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    mode_str = "APPLY (writes will occur)" if apply_writes else "DRY-RUN (no writes)"
    if args.apply and not apply_writes:
        if env_dry:
            mode_str += "  [--apply was passed but DRY_RUN env forced dry-run]"
        elif args.dry_run:
            mode_str += "  [--apply was passed but --dry-run forced dry-run]"

    _banner(f"remediate_rh_tenant_assignment  [{mode_str}]")
    print(f"  request_id       : {request_id}")
    print(f"  canonical_tenant : {CANONICAL_TENANT_SLUG!r}")
    print(f"  duplicate_tenant : {DUPLICATE_TENANT_SLUG!r}  (left untouched)")
    print(f"  limit            : {args.limit if args.limit is not None else 'none'}")
    print(f"  DRY_RUN env      : {os.getenv('DRY_RUN', '<unset, treated as true>')}")

    async with AsyncSessionLocal() as db:
        # 1. Validate canonical tenant ────────────────────────────
        _section("1. Canonical tenant validation")
        canonical = await _resolve_canonical(db)
        if canonical is None:
            print(f"  FATAL: tenant {CANONICAL_TENANT_SLUG!r} is NOT PRESENT in tenants table.")
            print("         Refusing to proceed.  Create the tenant before re-running.")
            return 2
        if not canonical.is_active:
            print(
                f"  FATAL: tenant {CANONICAL_TENANT_SLUG!r} is is_active=False.  "
                "Refusing to migrate data into an inactive tenant."
            )
            return 2
        print(
            f"  ✓ tenant {CANONICAL_TENANT_SLUG!r} pk={canonical.id} "
            f"name={canonical.name!r} is_active=True"
        )

        # 2. Collect scope ─────────────────────────────────────────
        _section("2. Collecting RH scope (matches audit_rh_data_ownership.py)")
        scope = await _collect_scope(db)
        print(f"  RH customers matched : {len(scope['customers'])}")
        print(f"  RH sites matched     : {len(scope['sites'])}")
        print(f"  RH devices matched   : {len(scope['devices'])}")

        # 3. Cross-link safety ─────────────────────────────────────
        _section("3. Cross-link safety check")
        cross = _detect_cross_links(scope)
        n_a = len(cross["sites_on_non_rh_customer"])
        n_b = len(cross["devices_on_non_rh_site"])
        print(f"  matched sites pointing at non-RH customer : {n_a}")
        print(f"  matched devices on non-RH site            : {n_b}")
        if n_a or n_b:
            print()
            print("  FATAL: cross-link anomalies detected.  Refusing to apply.")
            if n_a:
                print(f"  ─ {n_a} matched site(s) point at customer_id NOT in matched RH customers:")
                for r in cross["sites_on_non_rh_customer"][:10]:
                    print(
                        f"      site_pk={r['pk']:<6} site_id={r['site_id']!r:<22} "
                        f"tenant={r['tenant_id']!r:<22} customer_id={r['customer_id']}"
                    )
                if len(cross["sites_on_non_rh_customer"]) > 10:
                    print(f"      … {len(cross['sites_on_non_rh_customer']) - 10} more")
            if n_b:
                print(f"  ─ {n_b} matched device(s) attached to site_id NOT in matched RH sites:")
                for r in cross["devices_on_non_rh_site"][:10]:
                    print(
                        f"      device_pk={r['pk']:<6} device_id={r['device_id']!r:<22} "
                        f"tenant={r['tenant_id']!r:<22} site_id={r['site_id']!r}"
                    )
                if len(cross["devices_on_non_rh_site"]) > 10:
                    print(f"      … {len(cross['devices_on_non_rh_site']) - 10} more")
            print()
            print("  Resolve the anomalies first (rename customers, re-link sites, "
                  "or remove the bad rows from RH scope) and re-run the audit + "
                  "this script.")
            return 2
        print("  ✓ no cross-link anomalies")

        # 4. Before counts ─────────────────────────────────────────
        _section("4. BEFORE — tenant distribution of matched RH data")
        _print_counts_table("customers", scope["customers"])
        _print_counts_table("sites",     scope["sites"])
        _print_counts_table("devices",   scope["devices"])

        # 5. Movable set (idempotent) ──────────────────────────────
        _section("5. Movable rows (not already in canonical)")
        movable_customers = _movable(scope["customers"], CANONICAL_TENANT_SLUG)
        movable_sites     = _movable(scope["sites"],     CANONICAL_TENANT_SLUG)
        movable_devices   = _movable(scope["devices"],   CANONICAL_TENANT_SLUG)
        if args.limit is not None:
            movable_customers = movable_customers[: args.limit]
            movable_sites     = movable_sites[: args.limit]
            movable_devices   = movable_devices[: args.limit]
        print(f"  customers to move : {len(movable_customers)}")
        print(f"  sites to move     : {len(movable_sites)}")
        print(f"  devices to move   : {len(movable_devices)}")

        if not (movable_customers or movable_sites or movable_devices):
            _banner("Nothing to do — every matched RH row is already in canonical")
            return 0

        # 6. Dry-run or apply ─────────────────────────────────────
        if not apply_writes:
            _section("6. Proposed changes (DRY-RUN)")
            print(f"  would set customers.tenant_id = {CANONICAL_TENANT_SLUG!r} on {len(movable_customers)} row(s)")
            print(f"  would set sites.tenant_id     = {CANONICAL_TENANT_SLUG!r} on {len(movable_sites)} row(s)")
            print(f"  would set devices.tenant_id   = {CANONICAL_TENANT_SLUG!r} on {len(movable_devices)} row(s)")
            print()
            print("  Sample (first 5 of each):")
            for r in movable_customers[:5]:
                print(f"    customer  pk={r['pk']:<6} tenant {r['tenant_id']!r:<22} → {CANONICAL_TENANT_SLUG!r}  name={r['name']!r}")
            for r in movable_sites[:5]:
                print(f"    site      pk={r['pk']:<6} tenant {r['tenant_id']!r:<22} → {CANONICAL_TENANT_SLUG!r}  site_id={r['site_id']!r}")
            for r in movable_devices[:5]:
                print(f"    device    pk={r['pk']:<6} tenant {r['tenant_id']!r:<22} → {CANONICAL_TENANT_SLUG!r}  device_id={r['device_id']!r}")
            _banner("DRY-RUN complete — no rows were modified")
            print("  Re-run with --apply (and DRY_RUN=false) to write these.")
            return 0

        # ── APPLY (single transaction, single audit row) ─────────
        _section("6. Applying — single transaction")
        try:
            moved_c, moved_s, moved_d = await _apply(
                db, movable_customers, movable_sites, movable_devices,
            )

            total_moved = len(moved_c) + len(moved_s) + len(moved_d)
            if total_moved == 0:
                # All rows raced to canonical between the SELECT and the
                # UPDATE.  Nothing to audit; cleanly roll back the no-op
                # transaction and exit.
                await db.rollback()
                _banner("APPLY: nothing was moved (rows raced to canonical) — no audit row written")
                return 0

            entry_id = request_id  # already includes timestamp + uuid8
            after_counts = {
                "customers": len([c for c in scope["customers"] if c["tenant_id"] == CANONICAL_TENANT_SLUG]) + len(moved_c),
                "sites":     len([s for s in scope["sites"]     if s["tenant_id"] == CANONICAL_TENANT_SLUG]) + len(moved_s),
                "devices":   len([d for d in scope["devices"]   if d["tenant_id"] == CANONICAL_TENANT_SLUG]) + len(moved_d),
            }
            before_counts = {
                "customers": len([c for c in scope["customers"] if c["tenant_id"] == CANONICAL_TENANT_SLUG]),
                "sites":     len([s for s in scope["sites"]     if s["tenant_id"] == CANONICAL_TENANT_SLUG]),
                "devices":   len([d for d in scope["devices"]   if d["tenant_id"] == CANONICAL_TENANT_SLUG]),
            }
            matched_total = {
                "customers": len(scope["customers"]),
                "sites":     len(scope["sites"]),
                "devices":   len(scope["devices"]),
            }
            summary = SUMMARY_TEMPLATE.format(
                canonical=CANONICAL_TENANT_SLUG,
                customers=len(moved_c),
                sites=len(moved_s),
                devices=len(moved_d),
            )
            audit = AuditLogEntry(
                entry_id=entry_id,
                tenant_id=CANONICAL_TENANT_SLUG,
                category="security",
                action=ACTION_TYPE,
                actor="remediate_script",
                target_type="tenant",
                target_id=CANONICAL_TENANT_SLUG,
                summary=summary,
                detail_json=json.dumps({
                    "request_id":       request_id,
                    "canonical_tenant": CANONICAL_TENANT_SLUG,
                    "customers_moved":  moved_c,
                    "sites_moved":      moved_s,
                    "devices_moved":    moved_d,
                    "before_counts":    before_counts,
                    "after_counts":     after_counts,
                    "matched_total":    matched_total,
                    "script":           "api/scripts/remediate_rh_tenant_assignment.py",
                }),
            )
            db.add(audit)
            await db.commit()
        except Exception:
            await db.rollback()
            print()
            print("ERROR: apply failed — rolled back the entire transaction.")
            raise

        # 7. After report ─────────────────────────────────────────
        _section("7. AFTER — moves applied")
        print(f"  customers moved : {len(moved_c)}")
        print(f"  sites moved     : {len(moved_s)}")
        print(f"  devices moved   : {len(moved_d)}")
        print(f"  audit entry_id  : {entry_id}")
        print()
        print("  Verify with:")
        print(f"    SELECT detail_json FROM audit_log_entries WHERE entry_id = '{entry_id}';")
        print()
        print("  Rollback (per category) — see script docstring for full SQL.")
        _banner("APPLY complete — audit row written")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
