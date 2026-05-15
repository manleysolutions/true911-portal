#!/usr/bin/env python3
"""Safely remediate import-corruption duplicate site rows.

DRY-RUN BY DEFAULT.  Real writes require BOTH ``--apply`` AND
``DRY_RUN`` env var not set to "true".  Nothing else (default,
``DRY_RUN=true``, ``--dry-run``, or omitting ``--apply``) results in
zero UPDATE / INSERT statements.

What this script does (and only this):
  1. For a single ``customer_id``, find groups of sites that look like
     synthetic import duplicates:
         same tenant_id  +  same customer_id
         +  same normalized site_name
         +  same normalized city + state + zip
     (street is intentionally NOT part of the key because the importer
     reportedly fabricates sequential street numbers.)
     Optional narrowing: ``--import-batch-id`` if all bad rows share one.

  2. For each group of >= ``--min-group-size`` sites, pick a canonical
     "master" by ``(created_at ASC, id ASC)`` — earliest first, then
     lowest PK as deterministic tie-break.

  3. For every NON-canonical site in the group:
       a. Re-point every ``devices`` row whose ``devices.site_id`` ==
          duplicate.site_id  →  canonical.site_id.
       b. Set the duplicate site's ``status='merged'``.
       (See "Out of scope" below for what is intentionally NOT touched.)

  4. Write one ``action_audits`` row per device move AND one per site
     marked merged.  ``details`` is JSON capturing every value needed
     to roll back (see "Rollback" below).

Out of scope (intentionally untouched by this script):
  * tenants, customers, registrations, registration_locations
  * Site columns other than ``status`` (e911_*, customer_id,
    customer_name, tenant_id, site_name, notes, reconciliation_status,
    last_portal_sync, import_batch_id, address_*, …  — all preserved
    exactly as they are)
  * Device columns other than ``site_id``
  * All other tables that also reference ``site_id`` (lines,
    recordings, telemetry_events, incidents, command_activity,
    command_telemetry, e911_change_log, notifications,
    verification_tasks, service_contracts, sims, service_units,
    line_intelligence_events, port_states, site_vendors, events,
    import_rows, registration_locations.materialized_site_id).
    These rows continue to point at the duplicate site_id.  That is
    safe because the duplicate row still exists; it is just marked
    ``status='merged'``.  Migrating those rows is a Phase 2 decision
    that should happen separately, with its own audit + rollback.

No schema changes.  No deletes.

Safety guarantees
-----------------
* Dry-run is the default.
* ``--customer-id`` is REQUIRED.  The script will not scan all
  customers in a single invocation — you point it at one at a time.
* Each group is processed inside its own transaction.  A failure on
  group 7 cannot corrupt group 3.
* The site-status UPDATE is guarded by ``WHERE status != 'merged'``,
  so a re-run is a no-op for groups already remediated.
* The device-move UPDATE is a core ``update()`` carrying only the
  ``site_id`` column.  No other device attribute is in the statement.
* In ``--apply``, candidate rows are selected ``FOR UPDATE SKIP
  LOCKED`` to avoid blocking live API traffic.

Rollback strategy
-----------------
Every change is reversible from the audit log alone — no separate
backup needed.

To roll back a run identified by ``request_id``:

    -- 1. Restore device site_ids
    UPDATE devices d
       SET site_id = (a.details::jsonb ->> 'old_site_id')
      FROM action_audits a
     WHERE a.request_id = '<request_id>'
       AND a.action_type = 'remediate_duplicate_site_device_move'
       AND d.id = (a.details::jsonb ->> 'device_pk')::int
       AND d.site_id = (a.details::jsonb ->> 'new_site_id');

    -- 2. Restore site statuses
    UPDATE sites s
       SET status = (a.details::jsonb ->> 'old_status')
      FROM action_audits a
     WHERE a.request_id = '<request_id>'
       AND a.action_type = 'remediate_duplicate_site_mark_merged'
       AND s.id = (a.details::jsonb ->> 'site_pk')::int
       AND s.status = 'merged';

    -- 3. Mark the audit rows as rolled-back (optional, for trail)
    UPDATE action_audits SET result = 'rolled_back'
     WHERE request_id = '<request_id>' AND result = 'applied';

A companion ``rollback_duplicate_sites.py`` script can be added later;
the SQL above is the authoritative behavior.

Run on Render shell from the api/ directory:

    cd api
    # 1. Dry-run (default) — emits CSVs + summary, writes nothing.
    DRY_RUN=true python -m scripts.remediate_duplicate_sites --customer-id 5

    # 2. After reviewing, narrow to the known bad batch:
    DRY_RUN=true python -m scripts.remediate_duplicate_sites \\
        --customer-id 5 --import-batch-id <batch>

    # 3. Apply (only after operator review).
    DRY_RUN=false python -m scripts.remediate_duplicate_sites \\
        --customer-id 5 --import-batch-id <batch> --apply

Outputs (under ``api/reports/``):
    duplicate_remediation_groups.csv
    duplicate_remediation_device_moves.csv
    duplicate_remediation_summary.txt
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Make ``app.*`` importable.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import func, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.action_audit import ActionAudit  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.site import Site  # noqa: E402


logger = logging.getLogger("remediate_duplicate_sites")


REPORTS_DIR = Path(_API_DIR) / "reports"
GROUPS_CSV = REPORTS_DIR / "duplicate_remediation_groups.csv"
MOVES_CSV = REPORTS_DIR / "duplicate_remediation_device_moves.csv"
SUMMARY_TXT = REPORTS_DIR / "duplicate_remediation_summary.txt"

ACTION_DEVICE_MOVE = "remediate_duplicate_site_device_move"
ACTION_MARK_MERGED = "remediate_duplicate_site_mark_merged"

SYSTEM_ACTOR_EMAIL = "system@true911.local"
SYSTEM_ACTOR_ROLE = "system"
MERGED_STATUS = "merged"


# ─────────────────────────────────────────────────────────────────────
# Snapshots — plain dataclasses pre-materialized from ORM rows.
#
# Every per-group transaction issues commit() or rollback().  In async
# SQLAlchemy both can expire the session's ORM-tracked attributes;
# accessing an attribute on an expired instance triggers an implicit
# lazy-load, which from a non-greenlet context raises
# ``sqlalchemy.exc.MissingGreenlet``.  We avoid the whole class of
# bugs by snapshotting Site/Device rows to frozen dataclasses *before*
# the first commit/rollback and operating on those everywhere after.
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _SiteSnap:
    pk: int
    site_id: str
    tenant_id: str
    customer_id: Optional[int]
    site_name: str
    status: Optional[str]
    e911_street: Optional[str]
    e911_city: Optional[str]
    e911_state: Optional[str]
    e911_zip: Optional[str]
    created_at: Optional[datetime]


@dataclass(frozen=True)
class _DeviceSnap:
    pk: int
    device_id: str
    tenant_id: Optional[str]
    site_id: Optional[str]


def _snapshot_site(s: Site) -> _SiteSnap:
    return _SiteSnap(
        pk=s.id,
        site_id=s.site_id,
        tenant_id=s.tenant_id,
        customer_id=s.customer_id,
        site_name=s.site_name or "",
        status=s.status,
        e911_street=s.e911_street,
        e911_city=s.e911_city,
        e911_state=s.e911_state,
        e911_zip=s.e911_zip,
        created_at=s.created_at if isinstance(s.created_at, datetime) else None,
    )


def _snapshot_device(d: Device) -> _DeviceSnap:
    return _DeviceSnap(
        pk=d.id,
        device_id=d.device_id,
        tenant_id=d.tenant_id,
        site_id=d.site_id,
    )


# ─────────────────────────────────────────────────────────────────────
# Normalization (key used for grouping)
# ─────────────────────────────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def norm_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def group_key(site: _SiteSnap) -> tuple[str, str, str, str, str]:
    """The duplicate-detection key.

    Street is intentionally excluded — the importer's bug fabricates
    sequential street numbers, so street is exactly what differs
    between duplicates in this incident.
    """
    return (
        site.tenant_id or "",
        norm_text(site.site_name),
        norm_text(site.e911_city),
        norm_text(site.e911_state),
        norm_text(site.e911_zip),
    )


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def _env_dry_run_default_true() -> bool:
    raw = os.getenv("DRY_RUN")
    if raw is None:
        return True
    return raw.strip().lower() not in {"false", "0", "no", "off"}


def _sort_canonical(sites: list[_SiteSnap]) -> list[_SiteSnap]:
    """Canonical first.  Tie-break: (created_at ASC, pk ASC)."""
    def k(s: _SiteSnap) -> tuple[float, int]:
        ts = s.created_at.timestamp() if s.created_at is not None else float("inf")
        return (ts, s.pk)
    return sorted(sites, key=k)


_GROUPS_HEADER = [
    "group_id",
    "tenant_id",
    "customer_id",
    "norm_site_name",
    "norm_city",
    "norm_state",
    "norm_zip",
    "group_size",
    "canonical_site_pk",
    "canonical_site_id",
    "canonical_created_at",
    "duplicate_site_pks",
    "duplicate_site_ids",
    "devices_to_move_total",
]

_MOVES_HEADER = [
    "mode",                 # dry_run | apply
    "group_id",
    "device_pk",
    "device_id",
    "device_tenant_id",
    "old_site_id",          # duplicate
    "new_site_id",          # canonical
    "old_site_pk",
    "new_site_pk",
    "audit_id",             # blank in dry-run
    "applied_at",
]


# ─────────────────────────────────────────────────────────────────────
# Core processing
# ─────────────────────────────────────────────────────────────────────

async def _load_candidate_sites(
    db: AsyncSession,
    customer_id: int,
    tenant: Optional[str],
    import_batch_id: Optional[str],
    apply_writes: bool,
) -> list[_SiteSnap]:
    """Pull all sites for the customer that are still 'live' (not already merged).

    Returns plain ``_SiteSnap`` dataclasses, not ORM objects, so the
    caller can safely traverse them across commit/rollback boundaries.
    """
    q = (
        select(Site)
        .where(Site.customer_id == customer_id)
        .where((Site.status.is_(None)) | (Site.status != MERGED_STATUS))
        .order_by(Site.id)
    )
    if tenant:
        q = q.where(Site.tenant_id == tenant)
    if import_batch_id:
        q = q.where(Site.import_batch_id == import_batch_id)
    if apply_writes:
        q = q.with_for_update(skip_locked=True)
    r = await db.execute(q)
    return [_snapshot_site(s) for s in r.scalars().all()]


async def _count_lines_incidents(db: AsyncSession, site_id_strs: list[str]) -> dict[str, dict[str, int]]:
    """Read-only impact count for a small, operationally important set
    of tables.  Returns ``{site_id: {table: count}}``.

    Kept intentionally short — full impact across all 15+ tables is a
    Phase 2 concern.  This is just enough so an operator reviewing the
    plan can see whether the duplicates carry attached lines or
    incidents that *don't* move with the device.
    """
    if not site_id_strs:
        return {}
    # Late imports so the file stays light if these aren't used in a run.
    from app.models.line import Line  # noqa: WPS433
    from app.models.incident import Incident  # noqa: WPS433

    out: dict[str, dict[str, int]] = {sid: {"lines": 0, "incidents": 0} for sid in site_id_strs}

    line_r = await db.execute(
        select(Line.site_id, func.count())
        .where(Line.site_id.in_(site_id_strs))
        .group_by(Line.site_id)
    )
    for sid, n in line_r.all():
        out.setdefault(sid, {"lines": 0, "incidents": 0})["lines"] = int(n)

    inc_r = await db.execute(
        select(Incident.site_id, func.count())
        .where(Incident.site_id.in_(site_id_strs))
        .group_by(Incident.site_id)
    )
    for sid, n in inc_r.all():
        out.setdefault(sid, {"lines": 0, "incidents": 0})["incidents"] = int(n)

    return out


async def _process_group(
    db: AsyncSession,
    apply_writes: bool,
    request_id: str,
    group_id: str,
    members: list[_SiteSnap],
    moves_writer: csv.writer,
) -> tuple[int, int, int]:
    """Return (devices_moved, devices_dryrun, sites_marked_merged).

    Operates exclusively on plain ``_SiteSnap`` / ``_DeviceSnap``
    dataclasses.  No ORM-tracked instance is read after this function
    issues its first write — the outer caller's commit/rollback can
    therefore expire the session safely.
    """
    sorted_members = _sort_canonical(members)
    canonical = sorted_members[0]
    duplicates = sorted_members[1:]

    devices_moved = 0
    devices_dryrun = 0
    sites_marked = 0

    duplicate_site_ids = [d.site_id for d in duplicates]
    if not duplicate_site_ids:
        return (0, 0, 0)

    # Load devices and immediately convert to plain snapshots so we
    # never read attributes off an ORM Device after the session emits
    # any UPDATE statements below.
    dev_r = await db.execute(
        select(Device).where(Device.site_id.in_(duplicate_site_ids))
    )
    device_snaps = [_snapshot_device(d) for d in dev_r.scalars().all()]

    devs_by_dup: dict[str, list[_DeviceSnap]] = defaultdict(list)
    for d in device_snaps:
        if d.site_id is not None:
            devs_by_dup[d.site_id].append(d)

    now_iso = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731

    for dup in duplicates:
        dup_devices = devs_by_dup.get(dup.site_id, [])

        # ── (a) re-point devices ──────────────────────────────────
        for d in dup_devices:
            audit_id = ""
            applied_at = ""
            if apply_writes:
                upd = (
                    update(Device)
                    .where(Device.id == d.pk)
                    .where(Device.site_id == dup.site_id)  # idempotency guard
                    .values(site_id=canonical.site_id)
                )
                res = await db.execute(upd)
                if res.rowcount != 1:
                    # Something else moved it first; record + skip.
                    logger.warning(
                        "device move skipped (concurrent or stale)  device_pk=%s",
                        d.pk,
                    )
                    moves_writer.writerow([
                        "apply", group_id, d.pk, d.device_id, d.tenant_id,
                        dup.site_id, canonical.site_id, dup.pk, canonical.pk,
                        "", "skipped_concurrent",
                    ])
                    continue
                audit_id = uuid.uuid4().hex
                applied_at = now_iso()
                db.add(ActionAudit(
                    audit_id=audit_id,
                    request_id=request_id,
                    tenant_id=d.tenant_id or dup.tenant_id,
                    user_email=SYSTEM_ACTOR_EMAIL,
                    requester_name="remediate_duplicate_sites",
                    role=SYSTEM_ACTOR_ROLE,
                    action_type=ACTION_DEVICE_MOVE,
                    site_id=canonical.site_id,
                    timestamp=datetime.now(timezone.utc),
                    result="applied",
                    details=json.dumps({
                        "request_id": request_id,
                        "group_id": group_id,
                        "device_pk": d.pk,
                        "device_id": d.device_id,
                        "old_site_id": dup.site_id,
                        "new_site_id": canonical.site_id,
                        "old_site_pk": dup.pk,
                        "new_site_pk": canonical.pk,
                        "customer_id": dup.customer_id,
                        "rule": "remediate_duplicate_sites:canonical_by_created_at_then_pk",
                    }),
                ))
                devices_moved += 1
            else:
                devices_dryrun += 1

            moves_writer.writerow([
                "apply" if apply_writes else "dry_run",
                group_id, d.pk, d.device_id, d.tenant_id,
                dup.site_id, canonical.site_id, dup.pk, canonical.pk,
                audit_id, applied_at,
            ])

        # ── (b) mark the duplicate site merged ────────────────────
        if apply_writes:
            old_status = dup.status
            upd = (
                update(Site)
                .where(Site.id == dup.pk)
                .where(Site.status != MERGED_STATUS)
                .values(status=MERGED_STATUS)
            )
            res = await db.execute(upd)
            if res.rowcount == 1:
                db.add(ActionAudit(
                    audit_id=uuid.uuid4().hex,
                    request_id=request_id,
                    tenant_id=dup.tenant_id,
                    user_email=SYSTEM_ACTOR_EMAIL,
                    requester_name="remediate_duplicate_sites",
                    role=SYSTEM_ACTOR_ROLE,
                    action_type=ACTION_MARK_MERGED,
                    site_id=dup.site_id,
                    timestamp=datetime.now(timezone.utc),
                    result="applied",
                    details=json.dumps({
                        "request_id": request_id,
                        "group_id": group_id,
                        "site_pk": dup.pk,
                        "site_id": dup.site_id,
                        "old_status": old_status,
                        "new_status": MERGED_STATUS,
                        "canonical_site_pk": canonical.pk,
                        "canonical_site_id": canonical.site_id,
                        "devices_moved_count": len(dup_devices),
                    }),
                ))
                sites_marked += 1
            else:
                logger.info("site %s already merged or status-locked", dup.site_id)
        # In dry-run we deliberately do nothing — but we DO count it
        # as a planned change so the summary is accurate.
        else:
            sites_marked += 1

    return (devices_moved, devices_dryrun, sites_marked)


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--customer-id",
        type=int,
        required=True,
        help="REQUIRED.  Numeric customers.id to remediate (e.g. 5 for R&R REALTY GROUP).",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Optional defense-in-depth filter: only sites in this tenant_id.",
    )
    parser.add_argument(
        "--import-batch-id",
        default=None,
        help="Optional: restrict to sites with this import_batch_id.",
    )
    parser.add_argument(
        "--min-group-size",
        type=int,
        default=2,
        help="Minimum members for a group to be remediated (default 2).",
    )
    parser.add_argument(
        "--limit-groups",
        type=int,
        default=None,
        help="Hard cap on the number of duplicate groups processed.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply writes.  Without --apply (or with DRY_RUN!=false), no DB changes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run even if --apply is also passed.  Belt-and-braces.",
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
    request_id = f"remediate-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    mode_str = "APPLY (writes will occur)" if apply_writes else "DRY-RUN (no writes)"
    if args.apply and not apply_writes:
        if env_dry:
            mode_str += "  [--apply was passed but DRY_RUN env forced dry-run]"
        elif args.dry_run:
            mode_str += "  [--apply was passed but --dry-run forced dry-run]"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    _banner(f"remediate_duplicate_sites  [{mode_str}]")
    print(f"  request_id      : {request_id}")
    print(f"  customer_id     : {args.customer_id}")
    print(f"  tenant filter   : {args.tenant or '(any)'}")
    print(f"  import_batch_id : {args.import_batch_id or '(any)'}")
    print(f"  min_group_size  : {args.min_group_size}")
    print(f"  limit_groups    : {args.limit_groups if args.limit_groups is not None else 'none'}")
    print(f"  DRY_RUN env     : {os.getenv('DRY_RUN', '<unset, treated as true>')}")

    # Open CSVs.
    groups_fh = GROUPS_CSV.open("w", encoding="utf-8", newline="")
    moves_fh = MOVES_CSV.open("w", encoding="utf-8", newline="")
    g_w = csv.writer(groups_fh)
    m_w = csv.writer(moves_fh)
    g_w.writerow(_GROUPS_HEADER)
    m_w.writerow(_MOVES_HEADER)

    totals = {
        "sites_considered": 0,
        "groups_found": 0,
        "groups_processed": 0,
        "duplicates_marked_merged": 0,
        "devices_moved": 0,
        "devices_dryrun_planned": 0,
    }
    per_group_impact: list[dict[str, object]] = []

    try:
        async with AsyncSessionLocal() as db:
            # ── 1. Load candidates ────────────────────────────────
            sites = await _load_candidate_sites(
                db,
                customer_id=args.customer_id,
                tenant=args.tenant,
                import_batch_id=args.import_batch_id,
                apply_writes=apply_writes,
            )
            totals["sites_considered"] = len(sites)
            print(f"  loaded sites    : {len(sites)}")

            # ── 2. Group ──────────────────────────────────────────
            grouped: dict[tuple, list[_SiteSnap]] = defaultdict(list)
            for s in sites:
                if not norm_text(s.site_name):
                    # Don't group sites with no name — too risky.
                    continue
                grouped[group_key(s)].append(s)

            multi = [
                (k, m) for k, m in grouped.items()
                if len(m) >= args.min_group_size
            ]
            multi.sort(key=lambda km: (-len(km[1]), km[0]))  # biggest groups first
            totals["groups_found"] = len(multi)
            print(f"  duplicate groups (>= {args.min_group_size}): {len(multi)}")

            if args.limit_groups is not None:
                multi = multi[: args.limit_groups]
                print(f"  limited to first {len(multi)} group(s)")

            # ── 3. Optional read-only impact counts ───────────────
            all_dup_site_id_strs: list[str] = []
            for _key, members in multi:
                sm = _sort_canonical(members)
                for d in sm[1:]:
                    if d.site_id:
                        all_dup_site_id_strs.append(d.site_id)
            impact = await _count_lines_incidents(db, all_dup_site_id_strs)

            # ── 4. Process each group ─────────────────────────────
            for gi, (key, members) in enumerate(multi, start=1):
                group_id = f"G{gi:04d}"
                sorted_members = _sort_canonical(members)
                canonical = sorted_members[0]
                duplicates = sorted_members[1:]

                # Pre-materialize every value we'll need after the
                # per-group commit/rollback so nothing here ever has
                # to lazy-load an ORM attribute later.
                canonical_pk = canonical.pk
                canonical_site_id_str = canonical.site_id
                canonical_tenant = canonical.tenant_id
                canonical_customer = canonical.customer_id
                canonical_created_iso = (
                    canonical.created_at.isoformat()
                    if canonical.created_at is not None else ""
                )
                members_size = len(members)
                dup_pks_joined = ";".join(str(d.pk) for d in duplicates)
                dup_site_ids = [d.site_id for d in duplicates]
                dup_site_ids_joined = ";".join(dup_site_ids)

                # Count devices currently attached to the duplicates
                # (this is just for the groups CSV — actual move logic
                # re-queries inside _process_group).
                dev_r = await db.execute(
                    select(func.count())
                    .select_from(Device)
                    .where(Device.site_id.in_(dup_site_ids))
                )
                dev_count = int(dev_r.scalar() or 0)

                g_w.writerow([
                    group_id,
                    canonical_tenant,
                    canonical_customer,
                    key[1], key[2], key[3], key[4],
                    members_size,
                    canonical_pk,
                    canonical_site_id_str,
                    canonical_created_iso,
                    dup_pks_joined,
                    dup_site_ids_joined,
                    dev_count,
                ])

                # Per-group transaction
                try:
                    moved, dryrun, marked = await _process_group(
                        db,
                        apply_writes=apply_writes,
                        request_id=request_id,
                        group_id=group_id,
                        members=members,
                        moves_writer=m_w,
                    )
                    if apply_writes:
                        await db.commit()
                    else:
                        await db.rollback()
                    totals["groups_processed"] += 1
                    totals["devices_moved"] += moved
                    totals["devices_dryrun_planned"] += dryrun
                    totals["duplicates_marked_merged"] += marked
                except Exception:
                    await db.rollback()
                    logger.exception("group %s failed; continuing", group_id)
                    continue

                # Collect impact for the summary — uses ONLY the plain
                # strings captured above; no ORM attribute access here.
                group_impact_lines = sum(
                    impact.get(sid, {}).get("lines", 0) for sid in dup_site_ids
                )
                group_impact_incidents = sum(
                    impact.get(sid, {}).get("incidents", 0) for sid in dup_site_ids
                )
                per_group_impact.append({
                    "group_id": group_id,
                    "canonical_site_id": canonical_site_id_str,
                    "size": members_size,
                    "device_count": dev_count,
                    "lines_left_attached_to_duplicates": group_impact_lines,
                    "incidents_left_attached_to_duplicates": group_impact_incidents,
                })

    finally:
        groups_fh.close()
        moves_fh.close()

    finished = datetime.now(timezone.utc)

    # ── Summary ───────────────────────────────────────────────────
    lines: list[str] = [
        f"remediate_duplicate_sites  [{mode_str}]",
        f"started      : {started.isoformat()}",
        f"finished     : {finished.isoformat()}",
        f"duration     : {(finished - started).total_seconds():.2f}s",
        f"request_id   : {request_id}",
        f"customer_id  : {args.customer_id}",
        f"tenant       : {args.tenant or '(any)'}",
        f"import_batch : {args.import_batch_id or '(any)'}",
        "",
        "Counts",
        "------",
        f"  sites considered                : {totals['sites_considered']}",
        f"  duplicate groups found          : {totals['groups_found']}",
        f"  groups processed                : {totals['groups_processed']}",
        f"  duplicate sites marked merged   : {totals['duplicates_marked_merged']}",
        (
            f"  devices moved                   : {totals['devices_moved']}"
            if apply_writes else
            f"  devices that WOULD be moved     : {totals['devices_dryrun_planned']}"
        ),
        "",
        "Top groups by size",
        "------------------",
    ]
    for g in sorted(per_group_impact, key=lambda x: -int(x["size"]))[:15]:
        lines.append(
            f"  {g['group_id']}  size={int(g['size']):>3}  "
            f"canonical={g['canonical_site_id']}  "
            f"devices={int(g['device_count'])}  "
            f"lines_left={int(g['lines_left_attached_to_duplicates'])}  "
            f"incidents_left={int(g['incidents_left_attached_to_duplicates'])}"
        )
    if len(per_group_impact) > 15:
        lines.append(f"  … {len(per_group_impact) - 15} more groups in {GROUPS_CSV.name}")

    lines += [
        "",
        "What this run touched / did not touch",
        "-------------------------------------",
        "  TOUCHED:",
        "    - devices.site_id  (re-pointed from duplicate -> canonical)",
        "    - sites.status     (set to 'merged' on duplicates)",
        "    - action_audits    (one row per device move, one per site)",
        "  NOT TOUCHED:",
        "    - tenants, customers, registrations, registration_locations",
        "    - any Site column other than status",
        "    - any Device column other than site_id",
        "    - lines, recordings, telemetry_events, incidents,",
        "      command_activity, command_telemetry, e911_change_log,",
        "      notifications, verification_tasks, service_contracts,",
        "      sims, service_units, line_intelligence_events,",
        "      port_states, site_vendors, events, import_rows",
        "    Those rows still reference the duplicate site_id and the",
        "    duplicate row still exists (status='merged'), so no FK is",
        "    broken.  Migrating them is a Phase 2 decision.",
        "",
        "Rollback",
        "--------",
        f"  Every change is reversible from action_audits.request_id='{request_id}'.",
        "  See the script docstring for the exact SQL.",
        "",
        "Output files",
        "------------",
        f"  {GROUPS_CSV.name}",
        f"  {MOVES_CSV.name}",
        f"  {SUMMARY_TXT.name}",
    ]

    if not apply_writes:
        lines += [
            "",
            "This was a DRY-RUN.  No rows were modified.",
            "To apply, re-run with both --apply and DRY_RUN=false.",
        ]

    SUMMARY_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _banner("Summary")
    print("\n".join(lines))
    print()
    print(f"  wrote {GROUPS_CSV}")
    print(f"  wrote {MOVES_CSV}")
    print(f"  wrote {SUMMARY_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
