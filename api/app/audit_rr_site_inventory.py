"""R&R site inventory diagnostic (READ-ONLY).

Before applying the device→site correction (PR #105), verify that the proposed
destination sites are TRULY DISTINCT properties and not duplicate site records.
The dry-run showed 54 destination sites all named the same ("R&R REALTY GROUP -
West Des Moines, IA - Main Office") — this tool checks whether those share an
address (duplicate records) or have distinct addresses (distinct properties).

Strictly READ-ONLY: only SELECTs. No writes, no migrations, no device reassignment,
no site merge, no deletes.

Run:
    python -m app.audit_rr_site_inventory --customer "R&R Realty Group"
    python -m app.audit_rr_site_inventory --customer "R&R Realty Group" --export-json rr_sites.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.audit_zoho_true911_customer_reconciliation import (  # noqa: E402
    normalize_name, normalize_msisdn, name_matches,
)

DEFAULT_CUSTOMER = os.environ.get("RR_SITE_INV_CUSTOMER", "R&R Realty Group")
PLACEHOLDER_DEVICE_MIN = 5      # device-only, address-less site holding >= this = bulk placeholder

CLASSIFICATIONS = (
    "valid_distinct_site", "duplicate_site_name_unique_address",
    "duplicate_site_name_same_address", "placeholder_site",
    "empty_site", "line_only_site", "device_only_site",
)

REPORT_FIELDS = (
    "site_id", "site_name", "e911_street", "e911_city", "e911_state", "e911_zip",
    "customer_id", "device_count", "line_count", "occupancy", "classification",
    "msisdns", "dids",
)


# ── pure helpers (unit-tested, no DB) ────────────────────────────────────
def _addr_sig(site: dict) -> tuple:
    return tuple(normalize_name(site.get(k)) for k in
                 ("e911_street", "e911_city", "e911_state", "e911_zip"))


def _addr_present(site: dict) -> bool:
    return any(_addr_sig(site))


def _occupancy(dev_count: int, line_count: int) -> str:
    if dev_count and line_count:
        return "both"
    if line_count:
        return "line_only"
    if dev_count:
        return "device_only"
    return "empty"


def classify_site(site: dict, *, dev_count: int, line_count: int,
                  same_name_siblings: list[dict]) -> str:
    if dev_count == 0 and line_count == 0:
        return "empty_site"
    if (not _addr_present(site)) and line_count == 0 and dev_count >= PLACEHOLDER_DEVICE_MIN:
        return "placeholder_site"

    if same_name_siblings:                       # name shared with >=1 other site
        present = _addr_present(site)
        sig = _addr_sig(site)
        for sib in same_name_siblings:
            sib_present = _addr_present(sib)
            if present and sib_present and _addr_sig(sib) == sig:
                return "duplicate_site_name_same_address"
            if not present and not sib_present:
                # shared name + neither has a distinguishing address -> treat as dup
                return "duplicate_site_name_same_address"
        return "duplicate_site_name_unique_address"

    if line_count and not dev_count:
        return "line_only_site"
    if dev_count and not line_count:
        return "device_only_site"
    return "valid_distinct_site"


def build_inventory(sites: list[dict], devices: list[dict], lines: list[dict]) -> dict:
    dev_by_site: dict = defaultdict(list)
    line_by_site: dict = defaultdict(list)
    for d in devices:
        dev_by_site[d.get("site_id")].append(d)
    for l in lines:
        line_by_site[l.get("site_id")].append(l)

    by_name: dict = defaultdict(list)
    for s in sites:
        by_name[normalize_name(s.get("site_name"))].append(s)

    rows = []
    for s in sites:
        sid = s.get("site_id")
        devs = dev_by_site.get(sid, [])
        lns = line_by_site.get(sid, [])
        siblings = [o for o in by_name[normalize_name(s.get("site_name"))]
                    if o.get("site_id") != sid]
        cls = classify_site(s, dev_count=len(devs), line_count=len(lns),
                            same_name_siblings=siblings)
        rows.append({
            "site_id": sid, "site_name": s.get("site_name"),
            "e911_street": s.get("e911_street"), "e911_city": s.get("e911_city"),
            "e911_state": s.get("e911_state"), "e911_zip": s.get("e911_zip"),
            "customer_id": s.get("customer_id"),
            "device_count": len(devs), "line_count": len(lns),
            "occupancy": _occupancy(len(devs), len(lns)),
            "classification": cls,
            "msisdns": sorted({normalize_msisdn(d.get("msisdn")) for d in devs if d.get("msisdn")}),
            "dids": sorted({normalize_msisdn(l.get("did")) for l in lns if l.get("did")}),
        })

    # name-group analysis (top duplicate site-name groups)
    name_groups = []
    for name, group in by_name.items():
        if len(group) > 1:
            sigs = {_addr_sig(g) for g in group}
            present = sum(1 for g in group if _addr_present(g))
            name_groups.append({
                "site_name": group[0].get("site_name"), "site_count": len(group),
                "distinct_addresses": len(sigs), "sites_with_address": present,
                "site_ids": [g.get("site_id") for g in group][:25],
            })
    name_groups.sort(key=lambda g: -g["site_count"])

    summary = {**{k: 0 for k in CLASSIFICATIONS},
               **Counter(r["classification"] for r in rows),
               "total_sites": len(rows)}
    return {"rows": rows, "summary": summary, "duplicate_name_groups": name_groups,
            "recommendation": _recommend(summary, name_groups)}


def _recommend(summary: dict, name_groups: list[dict]) -> str:
    same = summary.get("duplicate_site_name_same_address", 0)
    uniq = summary.get("duplicate_site_name_unique_address", 0)
    if same > 0:
        return (f"NOT SAFE to apply PR #105 yet: {same} destination site(s) appear to be "
                "DUPLICATE records (same name + same/duplicate or missing address). Moving "
                "devices onto duplicate site records would scatter them across dupes. "
                "Consolidate/merge the duplicate sites first, then re-run.")
    if uniq > 0:
        return (f"LIKELY SAFE: {uniq} destination site(s) share a generic name but have "
                "DISTINCT addresses (distinct properties). Verify a sample, then PR #105 apply "
                "is reasonable.")
    return ("REVIEW: no shared-name destination sites detected here — verify the proposed "
            "destinations against this inventory before applying.")


# ── export ───────────────────────────────────────────────────────────────
def write_json(report: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"read_only": True, **report}, fh, indent=2, ensure_ascii=False, default=str)


def write_csv(rows: list[dict], path: str) -> int:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(REPORT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "msisdns": ";".join(r["msisdns"]), "dids": ";".join(r["dids"])})
    return len(rows)


# ── DB load (READ-ONLY) ──────────────────────────────────────────────────
async def _load(db, customer: str) -> tuple:
    from sqlalchemy import select
    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.device import Device
    from app.models.line import Line

    custs = (await db.execute(select(Customer))).scalars().all()
    cust_ids = {c.id for c in custs if name_matches(customer, c.name)}
    if not cust_ids:
        return [], [], []
    sites = (await db.execute(select(Site).where(Site.customer_id.in_(cust_ids)))).scalars().all()
    site_ids = {s.site_id for s in sites}
    devices = (await db.execute(
        select(Device).where(Device.site_id.in_(site_ids)))).scalars().all() if site_ids else []
    lines = (await db.execute(select(Line).where(
        Line.customer_id.in_(cust_ids)))).scalars().all()

    sd = [{"site_id": s.site_id, "site_name": s.site_name, "customer_id": s.customer_id,
           "e911_street": s.e911_street, "e911_city": s.e911_city,
           "e911_state": s.e911_state, "e911_zip": s.e911_zip} for s in sites]
    dd = [{"device_id": d.device_id, "site_id": d.site_id, "msisdn": d.msisdn} for d in devices]
    ld = [{"line_id": l.line_id, "site_id": l.site_id, "did": l.did,
           "customer_id": l.customer_id} for l in lines]
    return sd, dd, ld


# ── report ───────────────────────────────────────────────────────────────
def _print(report: dict, customer: str) -> None:
    s = report["summary"]
    print("=" * 84)
    print(f"R&R Site Inventory — {customer}  (READ-ONLY)")
    print("=" * 84)
    print("\n--- SUMMARY by classification ---")
    for k in CLASSIFICATIONS:
        print(f"  {k:<34}: {s[k]}")
    print(f"  {'total_sites':<34}: {s['total_sites']}")

    print("\n--- TOP DUPLICATE SITE-NAME GROUPS ---")
    if not report["duplicate_name_groups"]:
        print("  (no shared site names)")
    for g in report["duplicate_name_groups"][:10]:
        print(f"  {g['site_count']}x  {g['site_name']!r}  "
              f"distinct_addresses={g['distinct_addresses']}  with_address={g['sites_with_address']}")

    print(f"\n--- RECOMMENDATION ---\n  {report['recommendation']}")
    print("\n  (Read-only — no writes, no merge, no reassignment.)")


async def run(customer: str, *, export_json: Optional[str] = None,
              export_csv: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        sites, devices, lines = await _load(db, customer)
    report = build_inventory(sites, devices, lines)
    _print(report, customer)
    if export_json:
        write_json(report, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(report["rows"], export_csv)
        print(f"  Wrote {n} site rows (CSV) -> {export_csv}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only R&R site inventory / duplicate-site diagnostic.")
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER)
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.customer, export_json=args.export_json, export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: site inventory aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
