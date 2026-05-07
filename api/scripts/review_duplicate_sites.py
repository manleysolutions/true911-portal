#!/usr/bin/env python3
"""Read-only duplicate-site review.

Reads ``api/reports/duplicate_sites_candidates.csv`` (produced by
``audit_data_alignment``) and produces a *merge plan*.  Never modifies
the database.  Issues only SELECT statements to enrich each candidate
group with device count, line count and created_at.

Inputs
------
api/reports/duplicate_sites_candidates.csv

Outputs
-------
api/reports/duplicate_site_merge_plan.csv
api/reports/duplicate_site_review_summary.txt

Classification rules
--------------------
Each duplicate "cluster" (connected component of sites that share at
least one match key) is classified as:

    exact_duplicate   - cluster has at least one A-type edge
                        (cust + full-addr) AND every member shares the
                        same normalized customer_name AND the same
                        normalized full address (street + city + state).

    likely_duplicate  - cluster has any A-, B-, or C-type edge but does
                        not meet the exact-duplicate test.  Includes
                        D-type clusters where customer_name agrees and
                        city+state agree.

    not_duplicate     - cluster only has D-type edges (same site_name)
                        with materially different customer_name or
                        addresses, OR addresses are entirely empty.

Canonical selection
-------------------
Per cluster, the canonical record is selected by ranking each site on:

    (device_count, line_count, e911_completeness, -created_at_epoch)

…in descending order.  Ties are broken by lowest site primary key.

The resulting plan is advisory only.  No data is changed.

Run on Render shell from the api/ directory:

    cd api
    python -m scripts.review_duplicate_sites
"""

from __future__ import annotations

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
from app.models.device import Device  # noqa: E402
from app.models.line import Line  # noqa: E402
from app.models.site import Site  # noqa: E402


REPORTS_DIR = Path(_API_DIR) / "reports"
CANDIDATES_CSV = REPORTS_DIR / "duplicate_sites_candidates.csv"
PLAN_CSV = REPORTS_DIR / "duplicate_site_merge_plan.csv"
SUMMARY_TXT = REPORTS_DIR / "duplicate_site_review_summary.txt"


# ─────────────────────────────────────────────────────────────────────
# Normalization helpers (mirror audit_data_alignment for consistency).
# ─────────────────────────────────────────────────────────────────────

_STREET_ALIASES = {
    "street": "st", "str": "st",
    "avenue": "ave", "av": "ave",
    "boulevard": "blvd",
    "road": "rd",
    "drive": "dr",
    "lane": "ln",
    "court": "ct",
    "place": "pl",
    "highway": "hwy",
    "parkway": "pkwy",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "suite": "ste", "apartment": "apt", "building": "bldg", "floor": "fl",
}
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def norm_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def norm_name(s: str | None) -> str:
    return norm_text(s)


def norm_street(s: str | None) -> str:
    base = norm_text(s)
    if not base:
        return ""
    return " ".join(_STREET_ALIASES.get(tok, tok) for tok in base.split(" "))


def norm_full_address(street: str | None, city: str | None, state: str | None) -> str:
    """Compose a normalized street+city+state key (zip excluded — too noisy)."""
    return "|".join([norm_street(street), norm_text(city), norm_text(state)])


# ─────────────────────────────────────────────────────────────────────
# Union-Find for cluster discovery
# ─────────────────────────────────────────────────────────────────────

class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, x: int) -> None:
        if x not in self.parent:
            self.parent[x] = x

    def find(self, x: int) -> int:
        self.add(x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


# ─────────────────────────────────────────────────────────────────────
# Banner / prints
# ─────────────────────────────────────────────────────────────────────

def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    started = datetime.now(timezone.utc)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    _banner("Duplicate site review  (READ ONLY — produces a plan, no DB writes)")
    print(f"  reading: {CANDIDATES_CSV}")
    print(f"  started: {started.isoformat()}")

    if not CANDIDATES_CSV.exists():
        print()
        print("  ERROR: candidates CSV not found.")
        print("  Run the audit first:")
        print("    cd api && python -m scripts.audit_data_alignment")
        return 2

    # ── 1. Parse the candidates CSV ───────────────────────────────
    # Each row: match_type, match_key, group_size, canonical_site_pk,
    # canonical_site_id, site_pk, site_id, site_name, customer_name,
    # tenant_id, e911_street, e911_city, e911_state, e911_zip
    rows_by_group: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with CANDIDATES_CSV.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = (row["match_type"], row["match_key"])
            rows_by_group[key].append(row)

    if not rows_by_group:
        print("  candidates CSV is empty — nothing to review.")
        # Still emit empty outputs so downstream tooling sees a result.
        with PLAN_CSV.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow(_plan_header())
        SUMMARY_TXT.write_text(
            f"Duplicate site review  (READ ONLY)\n"
            f"started:  {started.isoformat()}\n"
            f"input:    {CANDIDATES_CSV.name}\n"
            f"input was empty — no duplicate clusters to review.\n",
            encoding="utf-8",
        )
        print(f"  wrote {PLAN_CSV.name} (empty)")
        print(f"  wrote {SUMMARY_TXT.name}")
        return 0

    # ── 2. Build clusters via union-find ──────────────────────────
    uf = UnionFind()
    edge_types_for_pair: dict[frozenset[int], set[str]] = defaultdict(set)
    site_pks_seen: set[int] = set()
    for (match_type, _key), rows in rows_by_group.items():
        pks = sorted({int(r["site_pk"]) for r in rows})
        for pk in pks:
            uf.add(pk)
            site_pks_seen.add(pk)
        for i, a in enumerate(pks):
            for b in pks[i + 1 :]:
                uf.union(a, b)
                edge_types_for_pair[frozenset({a, b})].add(match_type)

    # Group site_pks by cluster root
    clusters: dict[int, list[int]] = defaultdict(list)
    for pk in site_pks_seen:
        clusters[uf.find(pk)].append(pk)

    # Drop singletons defensively (shouldn't happen, but just in case)
    clusters = {root: pks for root, pks in clusters.items() if len(pks) >= 2}
    print(f"  parsed {len(rows_by_group)} candidate groups → {len(clusters)} unique clusters")

    # ── 3. Enrich with DB facts ───────────────────────────────────
    all_pks = list(site_pks_seen)
    async with AsyncSessionLocal() as db:
        sites_r = await db.execute(select(Site).where(Site.id.in_(all_pks)))
        sites_by_pk = {s.id: s for s in sites_r.scalars().all()}

        # device count per site_id (string slug)
        site_id_strs = [s.site_id for s in sites_by_pk.values() if s.site_id]
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

    # ── 4. Score each site & classify each cluster ────────────────
    plan_rows: list[list[Any]] = []
    classification_counts: dict[str, int] = defaultdict(int)
    cluster_summaries: list[dict[str, Any]] = []

    for ci, (root, pks) in enumerate(sorted(clusters.items()), start=1):
        members = [sites_by_pk[pk] for pk in pks if pk in sites_by_pk]
        if len(members) < 2:
            continue

        # Match-type edges that touched anything in this cluster
        cluster_edge_types: set[str] = set()
        for i in range(len(pks)):
            for j in range(i + 1, len(pks)):
                cluster_edge_types |= edge_types_for_pair.get(frozenset({pks[i], pks[j]}), set())

        # Score per site
        scored: list[tuple[Site, tuple[int, int, int, float]]] = []
        for s in members:
            dc = dev_count.get(s.site_id, 0)
            lc = line_count.get(s.site_id, 0)
            completeness = sum(
                1 for v in (s.e911_street, s.e911_city, s.e911_state, s.e911_zip) if v and str(v).strip()
            )
            created = s.created_at
            age_score = -created.timestamp() if isinstance(created, datetime) else 0.0
            scored.append((s, (dc, lc, completeness, age_score)))

        scored.sort(key=lambda t: (t[1], -t[0].id), reverse=True)
        canonical_site, canonical_score = scored[0]
        canonical_dc, canonical_lc, canonical_comp, canonical_age = canonical_score

        # Classification
        cust_norms = {norm_name(s.customer_name) for s in members}
        addr_norms = {
            norm_full_address(s.e911_street, s.e911_city, s.e911_state) for s in members
        }
        addr_all_present = all(
            (s.e911_street and s.e911_city and s.e911_state) for s in members
        )

        cluster_starts = {t[:1] for t in cluster_edge_types}  # 'A_…','B_…','C_…','D_…' → 'A','B','C','D'
        cluster_starts = {t[0] for t in cluster_edge_types}

        if (
            "A" in cluster_starts
            and len(cust_norms) == 1
            and len(addr_norms) == 1
            and addr_all_present
            and "" not in cust_norms
        ):
            classification = "exact_duplicate"
        elif cluster_starts & {"A", "B", "C"}:
            classification = "likely_duplicate"
        else:
            # only D-type edges (name match)
            cities = {norm_text(s.e911_city) for s in members}
            states = {norm_text(s.e911_state) for s in members}
            if len(cust_norms) == 1 and "" not in cust_norms and len(cities) == 1 and len(states) == 1:
                classification = "likely_duplicate"
            else:
                classification = "not_duplicate"

        classification_counts[classification] += 1

        # Reason string for canonical
        reason_parts = []
        if canonical_dc:
            reason_parts.append(f"{canonical_dc} device(s)")
        if canonical_lc:
            reason_parts.append(f"{canonical_lc} line(s)")
        reason_parts.append(f"{canonical_comp}/4 e911 fields")
        if isinstance(canonical_site.created_at, datetime):
            reason_parts.append(f"created {canonical_site.created_at.date().isoformat()}")
        canonical_reason = "; ".join(reason_parts)

        # Tied canonicals?
        top_score = canonical_score
        ties = [s for s, sc in scored if sc == top_score]
        tie_break_used = "lowest_pk" if len(ties) > 1 else ""

        proposed_action = {
            "exact_duplicate": "merge_into_canonical",
            "likely_duplicate": "review_then_merge",
            "not_duplicate": "keep_separate",
        }[classification]

        # Emit one row per member
        cluster_id = f"C{ci:04d}"
        for s, sc in scored:
            dc, lc, comp, age_s = sc
            is_canonical = (s.id == canonical_site.id)
            plan_rows.append(
                [
                    cluster_id,
                    classification,
                    proposed_action,
                    len(members),
                    sorted(cluster_edge_types),
                    canonical_site.id,
                    canonical_site.site_id,
                    canonical_site.site_name,
                    canonical_reason,
                    tie_break_used,
                    "yes" if is_canonical else "no",
                    s.id,
                    s.site_id,
                    s.site_name,
                    s.customer_name,
                    s.tenant_id,
                    s.e911_street,
                    s.e911_city,
                    s.e911_state,
                    s.e911_zip,
                    dc,
                    lc,
                    comp,
                    s.created_at.isoformat() if isinstance(s.created_at, datetime) else "",
                ]
            )

        cluster_summaries.append(
            {
                "cluster_id": cluster_id,
                "classification": classification,
                "size": len(members),
                "canonical_site_id": canonical_site.site_id,
                "canonical_site_pk": canonical_site.id,
                "canonical_reason": canonical_reason,
                "edges": sorted(cluster_edge_types),
                "tie": bool(tie_break_used),
            }
        )

    # ── 5. Write outputs ──────────────────────────────────────────
    with PLAN_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(_plan_header())
        for row in plan_rows:
            # Render list-typed cells as ";"-joined strings.
            rendered = [";".join(v) if isinstance(v, list) else ("" if v is None else v) for v in row]
            w.writerow(rendered)

    finished = datetime.now(timezone.utc)
    summary_lines: list[str] = [
        "Duplicate site review  (READ ONLY — proposed plan, NO database changes)",
        f"started:  {started.isoformat()}",
        f"finished: {finished.isoformat()}",
        f"duration: {(finished - started).total_seconds():.2f}s",
        f"input:    {CANDIDATES_CSV.name}",
        f"output:   {PLAN_CSV.name}",
        "",
        "Cluster classification",
        "----------------------",
        f"  exact_duplicate  : {classification_counts.get('exact_duplicate', 0)}",
        f"  likely_duplicate : {classification_counts.get('likely_duplicate', 0)}",
        f"  not_duplicate    : {classification_counts.get('not_duplicate', 0)}",
        f"  total clusters   : {len(cluster_summaries)}",
        "",
        "Top clusters needing attention",
        "------------------------------",
    ]
    by_size = sorted(cluster_summaries, key=lambda c: c["size"], reverse=True)
    for c in by_size[:10]:
        summary_lines.append(
            f"  {c['cluster_id']}  size={c['size']:>2}  "
            f"{c['classification']:<17}  canonical={c['canonical_site_id']}  "
            f"({c['canonical_reason']})"
        )
    if len(by_size) > 10:
        summary_lines.append(f"  … {len(by_size) - 10} more clusters in {PLAN_CSV.name}")

    summary_lines += [
        "",
        "Tied canonicals (manual review recommended)",
        "-------------------------------------------",
    ]
    tied = [c for c in cluster_summaries if c["tie"]]
    if not tied:
        summary_lines.append("  none — all canonical picks had a clear winner")
    else:
        for c in tied:
            summary_lines.append(
                f"  {c['cluster_id']}  classification={c['classification']}  "
                f"size={c['size']}  tied → fell back to lowest_pk"
            )

    summary_lines += [
        "",
        "Action legend",
        "-------------",
        "  merge_into_canonical : exact duplicates — safe to schedule a merge",
        "  review_then_merge    : likely duplicates — eyeball each cluster before merging",
        "  keep_separate        : the only commonality is site_name; do not merge",
        "",
        "Reminder",
        "--------",
        "  This is a PLAN.  No rows were modified.  Merges are out of scope until",
        "  approved.  Rerun audit_data_alignment if upstream data has changed.",
    ]

    SUMMARY_TXT.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    _banner("Summary")
    print("\n".join(summary_lines))
    print()
    print(f"  wrote {PLAN_CSV}")
    print(f"  wrote {SUMMARY_TXT}")

    return 0


def _plan_header() -> list[str]:
    return [
        "cluster_id",
        "classification",
        "proposed_action",
        "cluster_size",
        "match_types_in_cluster",
        "canonical_site_pk",
        "canonical_site_id",
        "canonical_site_name",
        "canonical_reason",
        "tie_break",
        "is_canonical",
        "site_pk",
        "site_id",
        "site_name",
        "customer_name",
        "tenant_id",
        "e911_street",
        "e911_city",
        "e911_state",
        "e911_zip",
        "device_count",
        "line_count",
        "e911_completeness_0_4",
        "created_at",
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
