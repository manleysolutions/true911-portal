#!/usr/bin/env python3
"""Phase 0 preflight for the sites.customer_id FK migration.

READ ONLY.  DRY RUN ONLY.  Writes nothing to the database.  Does not
create or alter any column, constraint or index.  Does not modify any
model.  Does not backfill data.  Produces only CSV + text reports under
``api/reports/``.

The script simulates Phase 2 backfill to answer one question:

    "If we ran the backfill today, how many sites would resolve to
     exactly one customer in the same tenant?"

Resolution rules (mirror the Phase 2 plan):

    1. customer_name_empty   - sites.customer_name is missing/blank
    2. would_resolve         - exactly one customers.name match in the
                               same tenant (case-insensitive, whitespace
                               normalized)
    3. multi_match           - 2+ customers in the same tenant share
                               that normalized name
    4. cross_tenant_only     - no in-tenant match, but one or more
                               customers in OTHER tenants do match
    5. no_match              - the normalized name does not match any
                               customer in any tenant

Run on Render shell from the api/ directory:

    cd api
    python -m scripts.preflight_site_customer_id

Optional flag:

    --tenant <slug>    scope the report to a single tenant_id

Outputs:
    api/reports/site_customer_preflight_resolved.csv
    api/reports/site_customer_preflight_unresolved.csv
    api/reports/site_customer_preflight_summary.txt
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make ``app.*`` importable from either invocation form.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.line import Line  # noqa: E402
from app.models.site import Site  # noqa: E402


REPORTS_DIR = Path(_API_DIR) / "reports"
RESOLVED_CSV = REPORTS_DIR / "site_customer_preflight_resolved.csv"
UNRESOLVED_CSV = REPORTS_DIR / "site_customer_preflight_unresolved.csv"
SUMMARY_TXT = REPORTS_DIR / "site_customer_preflight_summary.txt"


# ─────────────────────────────────────────────────────────────────────
# Normalization (case-insensitive, whitespace-collapsed, punctuation
# stripped — same rule used by audit_data_alignment).
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
# Resolution
# ─────────────────────────────────────────────────────────────────────

# Reasons in display/sort order.
_REASONS = [
    "would_resolve",
    "multi_match",
    "cross_tenant_only",
    "no_match",
    "customer_name_empty",
]


def _resolve(
    site: Site,
    by_tenant_name: dict[tuple[str, str], list[Customer]],
    by_name_global: dict[str, list[Customer]],
) -> tuple[str, list[Customer], list[Customer]]:
    """Return (reason, in_tenant_candidates, cross_tenant_candidates)."""
    cn = norm_name(site.customer_name)
    if not cn:
        return ("customer_name_empty", [], [])
    in_tenant = by_tenant_name.get((site.tenant_id, cn), [])
    if len(in_tenant) == 1:
        return ("would_resolve", in_tenant, [])
    if len(in_tenant) >= 2:
        return ("multi_match", in_tenant, [])
    cross = [c for c in by_name_global.get(cn, []) if c.tenant_id != site.tenant_id]
    if cross:
        return ("cross_tenant_only", [], cross)
    return ("no_match", [], [])


# ─────────────────────────────────────────────────────────────────────
# Banner
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


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--tenant",
        default=None,
        help="Optional: only audit sites for this tenant_id slug.",
    )
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    _banner("Phase 0 preflight: sites.customer_id  (READ ONLY, DRY RUN)")
    print(f"  reports dir:  {REPORTS_DIR}")
    print(f"  started:      {started.isoformat()}")
    if args.tenant:
        print(f"  tenant scope: {args.tenant}")
    print("  this script writes NOTHING to the database.")

    async with AsyncSessionLocal() as db:
        # ── Load customers ────────────────────────────────────────
        cust_q = select(Customer)
        if args.tenant:
            cust_q = cust_q.where(Customer.tenant_id == args.tenant)
        # Cross-tenant detection requires loading customers across all
        # tenants regardless of --tenant scope; load globally.
        cust_q_global = select(Customer)
        cust_r = await db.execute(cust_q_global)
        all_customers = cust_r.scalars().all()

        by_tenant_name: dict[tuple[str, str], list[Customer]] = defaultdict(list)
        by_name_global: dict[str, list[Customer]] = defaultdict(list)
        for c in all_customers:
            n = norm_name(c.name)
            if not n:
                continue
            by_tenant_name[(c.tenant_id, n)].append(c)
            by_name_global[n].append(c)

        # ── Load sites (scoped if requested) ──────────────────────
        site_q = select(Site)
        if args.tenant:
            site_q = site_q.where(Site.tenant_id == args.tenant)
        site_r = await db.execute(site_q)
        sites = site_r.scalars().all()

        # ── Per-site_id device / line counts (for triage) ─────────
        site_id_strs = [s.site_id for s in sites if s.site_id]
        if site_id_strs:
            dev_r = await db.execute(
                select(Device.site_id, func.count())
                .where(Device.site_id.in_(site_id_strs))
                .group_by(Device.site_id)
            )
            dev_count = {sid: int(n) for sid, n in dev_r.all()}
            line_r = await db.execute(
                select(Line.site_id, func.count())
                .where(Line.site_id.in_(site_id_strs))
                .group_by(Line.site_id)
            )
            line_count = {sid: int(n) for sid, n in line_r.all()}
        else:
            dev_count = {}
            line_count = {}

    # ── Resolve every site ────────────────────────────────────────
    resolved_rows: list[list[Any]] = []
    unresolved_rows: list[list[Any]] = []

    # Counters for the summary.
    total = len(sites)
    by_reason: dict[str, int] = defaultdict(int)
    by_reason_active_only: dict[str, int] = defaultdict(int)
    by_tenant_total: dict[str, int] = defaultdict(int)
    by_tenant_resolved: dict[str, int] = defaultdict(int)
    by_tenant_unresolved_reasons: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for s in sites:
        reason, in_tenant, cross = _resolve(s, by_tenant_name, by_name_global)
        by_reason[reason] += 1
        by_tenant_total[s.tenant_id] += 1

        # Active-only variant: would the resolution still be "would_resolve"
        # if we restricted to status='active' customers?  Recorded for the
        # summary so reviewers can see whether status filtering changes the
        # picture.
        if reason == "would_resolve":
            active_in_tenant = [c for c in in_tenant if (c.status or "").lower() == "active"]
            if len(active_in_tenant) == 1:
                by_reason_active_only["would_resolve"] += 1
            elif len(active_in_tenant) >= 2:
                by_reason_active_only["multi_match"] += 1
            else:
                # The single match was non-active — still resolvable but
                # the operator may want to confirm.
                by_reason_active_only["would_resolve_inactive_only"] += 1
        else:
            by_reason_active_only[reason] += 1

        dc = dev_count.get(s.site_id, 0)
        lc = line_count.get(s.site_id, 0)
        cn_norm = norm_name(s.customer_name)

        if reason == "would_resolve":
            c = in_tenant[0]
            by_tenant_resolved[s.tenant_id] += 1
            resolved_rows.append(
                [
                    s.id,
                    s.site_id,
                    s.tenant_id,
                    s.site_name,
                    s.customer_name,
                    cn_norm,
                    c.id,
                    c.name,
                    c.tenant_id,
                    c.status,
                    "yes" if (c.status or "").lower() == "active" else "no",
                    dc,
                    lc,
                    s.created_at.isoformat() if isinstance(s.created_at, datetime) else "",
                ]
            )
        else:
            by_tenant_unresolved_reasons[s.tenant_id][reason] += 1
            recommended = {
                "customer_name_empty": "set_customer_name_or_mark_orphan",
                "no_match": "create_customer_or_rename_site",
                "multi_match": "human_review_match",
                "cross_tenant_only": "review_tenant_assignment",
            }[reason]
            unresolved_rows.append(
                [
                    s.id,
                    s.site_id,
                    s.tenant_id,
                    s.site_name,
                    s.customer_name,
                    cn_norm,
                    reason,
                    ";".join(str(c.id) for c in in_tenant),
                    ";".join(c.tenant_id for c in in_tenant),
                    ";".join(c.status or "" for c in in_tenant),
                    ";".join(str(c.id) for c in cross),
                    ";".join(c.tenant_id for c in cross),
                    ";".join(c.status or "" for c in cross),
                    dc,
                    lc,
                    recommended,
                    s.created_at.isoformat() if isinstance(s.created_at, datetime) else "",
                ]
            )

    # ── Write CSVs ────────────────────────────────────────────────
    with RESOLVED_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "site_pk",
                "site_id",
                "site_tenant_id",
                "site_name",
                "customer_name_on_site",
                "customer_name_normalized",
                "matched_customer_id",
                "matched_customer_name",
                "matched_customer_tenant_id",
                "matched_customer_status",
                "matched_customer_is_active",
                "device_count",
                "line_count",
                "site_created_at",
            ]
        )
        for row in resolved_rows:
            w.writerow(["" if v is None else v for v in row])

    with UNRESOLVED_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "site_pk",
                "site_id",
                "site_tenant_id",
                "site_name",
                "customer_name_on_site",
                "customer_name_normalized",
                "reason",
                "in_tenant_candidate_ids",
                "in_tenant_candidate_tenants",
                "in_tenant_candidate_statuses",
                "cross_tenant_candidate_ids",
                "cross_tenant_candidate_tenants",
                "cross_tenant_candidate_statuses",
                "device_count",
                "line_count",
                "recommended_action",
                "site_created_at",
            ]
        )
        for row in unresolved_rows:
            w.writerow(["" if v is None else v for v in row])

    # ── Build summary ─────────────────────────────────────────────
    finished = datetime.now(timezone.utc)

    resolved_count = by_reason.get("would_resolve", 0)
    unresolved_count = total - resolved_count
    expected_backfill_pct = _pct(resolved_count, total)
    happy_path_gate_pct = 95.0
    happy_path_pct_value = (resolved_count / total * 100.0) if total else 0.0
    gate_verdict = (
        "PASS — proceed to Phase 1"
        if happy_path_pct_value >= happy_path_gate_pct
        else "FAIL — clean unresolved data before Phase 1"
    )

    lines: list[str] = [
        "Phase 0 preflight: sites.customer_id  (READ ONLY, DRY RUN)",
        f"started:  {started.isoformat()}",
        f"finished: {finished.isoformat()}",
        f"duration: {(finished - started).total_seconds():.2f}s",
        f"scope:    {'tenant=' + args.tenant if args.tenant else 'all tenants'}",
        "",
        "Totals",
        "------",
        f"  total sites in scope         : {total}",
        f"  total customers in DB        : {len(all_customers)}",
        "",
        "Resolution-rate analysis",
        "------------------------",
    ]
    for r in _REASONS:
        n = by_reason.get(r, 0)
        lines.append(f"  {r:<22} : {n:>6}  ({_pct(n, total)})")
    lines += [
        "",
        f"  expected backfill percentage : {expected_backfill_pct}",
        f"  Phase 1 gate (≥{happy_path_gate_pct:.0f}%)        : {gate_verdict}",
        "",
        "Resolution-rate analysis (active-customer-only refinement)",
        "-----------------------------------------------------------",
        "  (would_resolve restricted to customers.status = 'active';",
        "   would_resolve_inactive_only counts sites that match exactly",
        "   one customer but it is not active — operator review recommended)",
    ]
    for r in [
        "would_resolve",
        "would_resolve_inactive_only",
        "multi_match",
        "cross_tenant_only",
        "no_match",
        "customer_name_empty",
    ]:
        n = by_reason_active_only.get(r, 0)
        lines.append(f"  {r:<32} : {n:>6}  ({_pct(n, total)})")

    # Per-tenant breakdown — only for tenants with sites in scope.
    lines += [
        "",
        "Per-tenant resolution",
        "---------------------",
        f"  {'tenant_id':<28} {'sites':>6} {'resolved':>9} {'unresolved':>11} {'resolved_%':>11}",
        f"  {'-'*28} {'-'*6} {'-'*9} {'-'*11} {'-'*11}",
    ]
    for tenant_id in sorted(by_tenant_total.keys()):
        t_total = by_tenant_total[tenant_id]
        t_resolved = by_tenant_resolved.get(tenant_id, 0)
        t_unresolved = t_total - t_resolved
        lines.append(
            f"  {tenant_id:<28} {t_total:>6} {t_resolved:>9} "
            f"{t_unresolved:>11} {_pct(t_resolved, t_total):>11}"
        )

    # Top tenants by unresolved volume.
    lines += [
        "",
        "Top tenants by unresolved sites",
        "-------------------------------",
    ]
    ranked = sorted(
        by_tenant_total.keys(),
        key=lambda t: (by_tenant_total[t] - by_tenant_resolved.get(t, 0)),
        reverse=True,
    )
    shown = 0
    for tenant_id in ranked:
        t_unresolved = by_tenant_total[tenant_id] - by_tenant_resolved.get(tenant_id, 0)
        if t_unresolved == 0:
            continue
        if shown >= 10:
            break
        reasons = by_tenant_unresolved_reasons.get(tenant_id, {})
        rs = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items()))
        lines.append(f"  {tenant_id:<28} unresolved={t_unresolved}  ({rs})")
        shown += 1
    if shown == 0:
        lines.append("  none — every tenant in scope is fully resolvable")

    # File pointers + dry-run reminder
    lines += [
        "",
        "Output files",
        "------------",
        f"  {RESOLVED_CSV.name}  ({len(resolved_rows)} rows)",
        f"  {UNRESOLVED_CSV.name}  ({len(unresolved_rows)} rows)",
        f"  {SUMMARY_TXT.name}",
        "",
        "Dry-run reminder",
        "----------------",
        "  - This script issued only SELECT statements.",
        "  - No rows were inserted, updated or deleted.",
        "  - No schema, model, migration or index was created or altered.",
        "  - The 'would_resolve' figure is the *expected* Phase 2 backfill",
        "    yield, computed against today's data.  It will drift as new",
        "    sites are imported or customers are renamed/created.",
        "",
        "Next steps",
        "----------",
        "  1. Review this summary with the onboarding team.",
        "  2. Triage the unresolved CSV by 'reason' and 'recommended_action'.",
        "  3. Re-run this script after data clean-up to watch the gate %.",
        "  4. Phase 1 (schema-only DDL) is gated on happy-path ≥ 95%.",
    ]

    SUMMARY_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _banner("Summary")
    print("\n".join(lines))
    print()
    print(f"  wrote {RESOLVED_CSV}")
    print(f"  wrote {UNRESOLVED_CSV}")
    print(f"  wrote {SUMMARY_TXT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
