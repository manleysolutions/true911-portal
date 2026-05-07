#!/usr/bin/env python3
"""Phase 2 backfill: populate sites.customer_id where it resolves cleanly.

DRY-RUN BY DEFAULT.  Real writes require an explicit ``--apply`` flag.

The script walks the ``sites`` table in batches, resolves each row's
``customer_name`` to a single matching ``customers`` row in the same
tenant, and (only in apply mode) sets ``sites.customer_id``.  Every
applied write is recorded both in ``action_audits`` and in a CSV.

Resolution rules (mirror Phase 0 preflight):

    1. customer_name_empty   - skip; emit to unresolved CSV
    2. would_resolve         - exactly one match in same tenant; apply
    3. multi_match           - multiple matches in same tenant; skip
    4. cross_tenant_only     - matches only in other tenants; skip
    5. no_match              - no match anywhere; skip
    6. inactive_only         - (only when --require-active) the single
                               match is not status='active'; skip

Safety guarantees:
    * Default mode is --dry-run.  No writes occur unless --apply is set.
    * Each apply UPDATE is conditioned on ``customer_id IS NULL``, so
      the script can be re-run without overwriting prior decisions.
    * Each batch of sites is selected with FOR UPDATE SKIP LOCKED, so
      the script never blocks live application writes.
    * customer_name is never modified.  Nothing is deleted or merged.

Usage on the Render shell:

    cd api
    # 1. Always dry-run first.
    python -m scripts.backfill_site_customer_id

    # 2. Scoped dry-run (one tenant) for review.
    python -m scripts.backfill_site_customer_id --tenant <slug>

    # 3. First apply: cap at 10 rows so any surprise is small.
    python -m scripts.backfill_site_customer_id --apply --limit 10

    # 4. Production apply.  Pace + batch tunable.
    python -m scripts.backfill_site_customer_id --apply

Outputs (under ``api/reports/``):
    site_customer_backfill_applied.csv     # rows that resolved (dry-run lists what *would* be set)
    site_customer_backfill_unresolved.csv  # everything else, with reason + candidates
    site_customer_backfill_summary.txt
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make ``app.*`` importable from either invocation form.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.action_audit import ActionAudit  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.site import Site  # noqa: E402


REPORTS_DIR = Path(_API_DIR) / "reports"
APPLIED_CSV = REPORTS_DIR / "site_customer_backfill_applied.csv"
UNRESOLVED_CSV = REPORTS_DIR / "site_customer_backfill_unresolved.csv"
SUMMARY_TXT = REPORTS_DIR / "site_customer_backfill_summary.txt"

ACTION_TYPE = "backfill_site_customer_id"
SYSTEM_ACTOR_EMAIL = "system@true911.local"
SYSTEM_ACTOR_ROLE = "system"


# ─────────────────────────────────────────────────────────────────────
# Normalization (must match audit_data_alignment + preflight).
# ─────────────────────────────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def norm_name(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def _pct(num: int, denom: int) -> str:
    if denom == 0:
        return "0.00%"
    return f"{(num / denom) * 100:.2f}%"


def _resolve(
    site: Site,
    by_tenant_name: dict[tuple[str, str], list[Customer]],
    by_name_global: dict[str, list[Customer]],
    require_active: bool,
) -> tuple[str, Customer | None, list[Customer], list[Customer]]:
    """Return (reason, chosen_customer_or_None, in_tenant_candidates, cross_tenant_candidates)."""
    cn = norm_name(site.customer_name)
    if not cn:
        return ("customer_name_empty", None, [], [])
    in_tenant = by_tenant_name.get((site.tenant_id, cn), [])
    if len(in_tenant) == 1:
        match = in_tenant[0]
        if require_active and (match.status or "").lower() != "active":
            return ("inactive_only", None, in_tenant, [])
        return ("would_resolve", match, in_tenant, [])
    if len(in_tenant) >= 2:
        return ("multi_match", None, in_tenant, [])
    cross = [c for c in by_name_global.get(cn, []) if c.tenant_id != site.tenant_id]
    if cross:
        return ("cross_tenant_only", None, [], cross)
    return ("no_match", None, [], [])


# ─────────────────────────────────────────────────────────────────────
# CSV writers
# ─────────────────────────────────────────────────────────────────────

_APPLIED_HEADER = [
    "mode",                       # dry_run | apply
    "site_pk",
    "site_id",
    "site_tenant_id",
    "site_name",
    "customer_name_on_site",
    "customer_name_normalized",
    "matched_customer_id",
    "matched_customer_name",
    "matched_customer_status",
    "audit_id",                   # set in apply mode; blank in dry-run
    "applied_at",                 # set in apply mode; blank in dry-run
]

_UNRESOLVED_HEADER = [
    "mode",
    "site_pk",
    "site_id",
    "site_tenant_id",
    "site_name",
    "customer_name_on_site",
    "customer_name_normalized",
    "reason",
    "in_tenant_candidate_ids",
    "in_tenant_candidate_statuses",
    "cross_tenant_candidate_ids",
    "cross_tenant_candidate_tenants",
    "recommended_action",
]


_RECOMMENDATIONS = {
    "customer_name_empty":  "set_customer_name_or_mark_orphan",
    "no_match":             "create_customer_or_rename_site",
    "multi_match":          "human_review_match",
    "cross_tenant_only":    "review_tenant_assignment",
    "inactive_only":        "reactivate_customer_or_drop_active_filter",
}


def _open_csvs(applied_path: Path, unresolved_path: Path):
    applied_fh = applied_path.open("w", encoding="utf-8", newline="")
    unresolved_fh = unresolved_path.open("w", encoding="utf-8", newline="")
    a_w = csv.writer(applied_fh)
    u_w = csv.writer(unresolved_fh)
    a_w.writerow(_APPLIED_HEADER)
    u_w.writerow(_UNRESOLVED_HEADER)
    return applied_fh, unresolved_fh, a_w, u_w


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply writes.  Default is dry-run (no DB modification).",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Optional: only process sites for this tenant_id slug.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of sites fetched per transaction (default: 500).",
    )
    parser.add_argument(
        "--pace-ms",
        type=int,
        default=100,
        help="Sleep between batches in milliseconds (default: 100).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Hard cap on total sites considered (safety for first --apply runs).",
    )
    parser.add_argument(
        "--require-active",
        action="store_true",
        help="Only resolve when the matched customer has status='active'.",
    )
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    request_id = f"backfill-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    mode_str = "APPLY (writes will occur)" if args.apply else "DRY-RUN (no writes)"
    _banner(f"Phase 2 backfill: sites.customer_id  [{mode_str}]")
    print(f"  reports dir   : {REPORTS_DIR}")
    print(f"  started       : {started.isoformat()}")
    print(f"  request_id    : {request_id}")
    print(f"  scope         : {'tenant=' + args.tenant if args.tenant else 'all tenants'}")
    print(f"  batch_size    : {args.batch_size}")
    print(f"  pace_ms       : {args.pace_ms}")
    print(f"  limit         : {args.limit if args.limit is not None else 'none'}")
    print(f"  require_active: {args.require_active}")
    if not args.apply:
        print("  >> dry-run: this script will NOT issue UPDATE or INSERT statements <<")

    applied_fh, unresolved_fh, a_w, u_w = _open_csvs(APPLIED_CSV, UNRESOLVED_CSV)

    counts: dict[str, int] = defaultdict(int)
    total_seen = 0
    total_applied = 0
    failed_updates = 0
    by_tenant_resolved: dict[str, int] = defaultdict(int)
    by_tenant_unresolved: dict[str, int] = defaultdict(int)

    try:
        async with AsyncSessionLocal() as db:
            # ── Build customer indexes (one read, all tenants) ────
            cust_r = await db.execute(select(Customer))
            customers = cust_r.scalars().all()
            by_tenant_name: dict[tuple[str, str], list[Customer]] = defaultdict(list)
            by_name_global: dict[str, list[Customer]] = defaultdict(list)
            for c in customers:
                n = norm_name(c.name)
                if not n:
                    continue
                by_tenant_name[(c.tenant_id, n)].append(c)
                by_name_global[n].append(c)
            print(f"  loaded customers: {len(customers)}")

            # ── Iterate sites by ascending id, keyset pagination ──
            last_id = 0
            while True:
                # Compute remaining budget vs --limit.
                if args.limit is not None and total_seen >= args.limit:
                    print(f"  reached --limit ({args.limit}); stopping")
                    break
                batch = args.batch_size
                if args.limit is not None:
                    batch = min(batch, args.limit - total_seen)

                q = (
                    select(Site)
                    .where(Site.customer_id.is_(None))
                    .where(Site.id > last_id)
                    .order_by(Site.id)
                    .limit(batch)
                )
                if args.tenant:
                    q = q.where(Site.tenant_id == args.tenant)
                if args.apply:
                    # Reserve each row in the batch so no other writer
                    # can touch it mid-update; SKIP LOCKED means we
                    # simply pass over rows another session is editing.
                    q = q.with_for_update(skip_locked=True)

                result = await db.execute(q)
                sites = result.scalars().all()
                if not sites:
                    break

                for site in sites:
                    total_seen += 1
                    reason, match, in_tenant, cross = _resolve(
                        site, by_tenant_name, by_name_global, args.require_active
                    )
                    counts[reason] += 1
                    cn_norm = norm_name(site.customer_name)

                    if reason == "would_resolve" and match is not None:
                        audit_id = ""
                        applied_at_iso = ""

                        if args.apply:
                            # Idempotent UPDATE: only set when still NULL.
                            upd = (
                                update(Site)
                                .where(Site.id == site.id)
                                .where(Site.customer_id.is_(None))
                                .values(customer_id=match.id)
                            )
                            res = await db.execute(upd)
                            if res.rowcount != 1:
                                # Another session got there first (or
                                # the row was filtered).  Treat as
                                # "skipped" and record so reviewers can
                                # see the gap; do not apply audit.
                                failed_updates += 1
                                u_w.writerow(
                                    [
                                        "apply",
                                        site.id,
                                        site.site_id,
                                        site.tenant_id,
                                        site.site_name,
                                        site.customer_name,
                                        cn_norm,
                                        "concurrent_update",
                                        ";".join(str(c.id) for c in in_tenant),
                                        ";".join(c.status or "" for c in in_tenant),
                                        "",
                                        "",
                                        "rerun_to_pick_up",
                                    ]
                                )
                                by_tenant_unresolved[site.tenant_id] += 1
                                continue

                            audit_id = uuid.uuid4().hex
                            applied_at_iso = datetime.now(timezone.utc).isoformat()
                            details = json.dumps(
                                {
                                    "old_customer_id": None,
                                    "new_customer_id": match.id,
                                    "matched_customer_name": match.name,
                                    "matched_customer_status": match.status or "",
                                    "rule": "exactly_one_in_tenant_match",
                                    "require_active": args.require_active,
                                    "request_id": request_id,
                                }
                            )
                            db.add(
                                ActionAudit(
                                    audit_id=audit_id,
                                    request_id=request_id,
                                    tenant_id=site.tenant_id,
                                    user_email=SYSTEM_ACTOR_EMAIL,
                                    requester_name="backfill_site_customer_id",
                                    role=SYSTEM_ACTOR_ROLE,
                                    action_type=ACTION_TYPE,
                                    site_id=site.site_id,
                                    timestamp=datetime.now(timezone.utc),
                                    result="applied",
                                    details=details,
                                )
                            )
                            total_applied += 1

                        a_w.writerow(
                            [
                                "apply" if args.apply else "dry_run",
                                site.id,
                                site.site_id,
                                site.tenant_id,
                                site.site_name,
                                site.customer_name,
                                cn_norm,
                                match.id,
                                match.name,
                                match.status or "",
                                audit_id,
                                applied_at_iso,
                            ]
                        )
                        by_tenant_resolved[site.tenant_id] += 1
                    else:
                        u_w.writerow(
                            [
                                "apply" if args.apply else "dry_run",
                                site.id,
                                site.site_id,
                                site.tenant_id,
                                site.site_name,
                                site.customer_name,
                                cn_norm,
                                reason,
                                ";".join(str(c.id) for c in in_tenant),
                                ";".join(c.status or "" for c in in_tenant),
                                ";".join(str(c.id) for c in cross),
                                ";".join(c.tenant_id for c in cross),
                                _RECOMMENDATIONS.get(reason, "review"),
                            ]
                        )
                        by_tenant_unresolved[site.tenant_id] += 1

                last_id = sites[-1].id

                if args.apply:
                    await db.commit()
                else:
                    # Defensive: ensure no SELECT side-effects remain
                    # in the session before the next iteration.
                    await db.rollback()

                if len(sites) < batch:
                    break
                if args.pace_ms > 0:
                    await asyncio.sleep(args.pace_ms / 1000.0)
    finally:
        applied_fh.close()
        unresolved_fh.close()

    # ── Summary ───────────────────────────────────────────────────
    finished = datetime.now(timezone.utc)
    resolved_count = counts.get("would_resolve", 0)
    unresolved_count = total_seen - resolved_count

    lines: list[str] = [
        f"Phase 2 backfill: sites.customer_id  [{mode_str}]",
        f"started     : {started.isoformat()}",
        f"finished    : {finished.isoformat()}",
        f"duration    : {(finished - started).total_seconds():.2f}s",
        f"request_id  : {request_id}",
        f"scope       : {'tenant=' + args.tenant if args.tenant else 'all tenants'}",
        f"options     : batch_size={args.batch_size} pace_ms={args.pace_ms} "
        f"limit={args.limit if args.limit is not None else 'none'} "
        f"require_active={args.require_active}",
        "",
        "Counts",
        "------",
        f"  sites considered          : {total_seen}",
        f"  would_resolve             : {counts.get('would_resolve', 0)}  "
        f"({_pct(counts.get('would_resolve', 0), total_seen)})",
        f"  multi_match               : {counts.get('multi_match', 0)}",
        f"  cross_tenant_only         : {counts.get('cross_tenant_only', 0)}",
        f"  no_match                  : {counts.get('no_match', 0)}",
        f"  customer_name_empty       : {counts.get('customer_name_empty', 0)}",
        f"  inactive_only             : {counts.get('inactive_only', 0)}",
        f"  total unresolved          : {unresolved_count}",
        "",
        "Apply result",
        "------------",
        f"  mode                      : {'apply' if args.apply else 'dry_run'}",
        f"  rows actually written     : {total_applied if args.apply else 0}",
        f"  concurrent_update misses  : {failed_updates if args.apply else 0}",
    ]

    if by_tenant_resolved or by_tenant_unresolved:
        lines += [
            "",
            "Per-tenant resolution",
            "---------------------",
            f"  {'tenant_id':<28} {'resolved':>9} {'unresolved':>11}",
            f"  {'-'*28} {'-'*9} {'-'*11}",
        ]
        for tid in sorted(set(by_tenant_resolved) | set(by_tenant_unresolved)):
            lines.append(
                f"  {tid:<28} "
                f"{by_tenant_resolved.get(tid, 0):>9} "
                f"{by_tenant_unresolved.get(tid, 0):>11}"
            )

    lines += [
        "",
        "Output files",
        "------------",
        f"  {APPLIED_CSV.name}     ({resolved_count} rows)",
        f"  {UNRESOLVED_CSV.name}  ({unresolved_count} rows)",
        f"  {SUMMARY_TXT.name}",
        "",
        "Audit trail",
        "-----------",
        "  Each apply write inserts an action_audits row with:",
        f"    request_id   = {request_id}",
        f"    action_type  = {ACTION_TYPE}",
        f"    user_email   = {SYSTEM_ACTOR_EMAIL}",
        "    details      = JSON {old_customer_id, new_customer_id, rule, ...}",
        f"  Cross-reference: SELECT * FROM action_audits WHERE request_id='{request_id}';",
        "",
        "Rerun",
        "-----",
        "  This script is idempotent.  Re-running with --apply will only",
        "  touch sites whose customer_id is still NULL.  Resolve unresolved",
        "  rows (rename customers, fix duplicates, add missing customers)",
        "  and re-run.",
    ]

    SUMMARY_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _banner("Summary")
    print("\n".join(lines))
    print()
    print(f"  wrote {APPLIED_CSV}")
    print(f"  wrote {UNRESOLVED_CSV}")
    print(f"  wrote {SUMMARY_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
