"""R&R device→site assignment diagnostic (READ-ONLY).

The pairing audit found 54 ``site_mismatch`` pairings for R&R: a device and its
line share the MSISDN and customer but sit on DIFFERENT site_ids — devices appear
to have been bulk-imported onto a placeholder site while the lines carry the real
locations. This tool quantifies that: per device it shows the device site vs the
matching line's site, classifies each, and proposes a correction (line's site as
the truth) — WITHOUT changing anything.

Strictly READ-ONLY: only SELECTs via the reconciliation customer-scoped loader. No
writes, no migrations, no matcher changes, no tenant changes.

Run:
    python -m app.audit_rr_site_assignment
    python -m app.audit_rr_site_assignment --customer "R&R Realty Group" --export-json rr_sites.json
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
    normalize_msisdn, _load_true911,
)

DEFAULT_CUSTOMER = os.environ.get("RR_SITE_CUSTOMER", "R&R Realty Group")

CLASSIFICATIONS = ("likely_correct", "likely_wrong_site", "unassigned", "ambiguous")

REPORT_FIELDS = (
    "device_id", "msisdn", "device_site_id", "device_site_name",
    "line_did", "line_site_id", "line_site_name", "customer_id", "customer_name",
    "classification", "proposed_site_id",
)


# ── pure classification + aggregation (unit-tested, no DB) ───────────────
def classify_device(device: dict, line: Optional[dict], line_count: int) -> tuple:
    """Return (classification, proposed_site_id)."""
    dsite = device.get("site_id")
    if not dsite:
        return "unassigned", None
    if line is None or line_count == 0:
        return "ambiguous", None          # no line to corroborate the location
    if line_count > 1:
        return "ambiguous", None          # MSISDN on >1 line — can't pick a truth
    lsite = line.get("site_id")
    if not lsite:
        return "ambiguous", None
    if dsite == lsite:
        return "likely_correct", None
    # same MSISDN + customer, different site -> the line's site is the likely truth.
    return "likely_wrong_site", lsite


def build_report(devices: list[dict], lines: list[dict], sites: list[dict],
                 *, customer_id, customer_name) -> dict:
    site_name = {s.get("site_id"): s.get("site_name") for s in sites}
    lines_by_m: dict = defaultdict(list)
    for l in lines:
        m = normalize_msisdn(l.get("did"))
        if m:
            lines_by_m[m].append(l)

    rows = []
    for d in devices:
        m = normalize_msisdn(d.get("msisdn"))
        matches = lines_by_m.get(m, []) if m else []
        line = matches[0] if len(matches) == 1 else None
        cls, proposed = classify_device(d, line, len(matches))
        rows.append({
            "device_id": d.get("device_id"), "msisdn": d.get("msisdn"),
            "device_site_id": d.get("site_id"),
            "device_site_name": site_name.get(d.get("site_id")),
            "line_did": (line or {}).get("did") if line else (matches[0].get("did") if matches else None),
            "line_site_id": (line or {}).get("site_id"),
            "line_site_name": site_name.get((line or {}).get("site_id")),
            "customer_id": customer_id, "customer_name": customer_name,
            "classification": cls, "proposed_site_id": proposed,
        })

    device_by_site = Counter(d.get("site_id") for d in devices if d.get("site_id"))
    line_by_site = Counter(l.get("site_id") for l in lines if l.get("site_id"))
    devices_sharing_site = {sid: n for sid, n in device_by_site.items() if n > 1}

    dominant = device_by_site.most_common(1)[0] if device_by_site else (None, 0)
    total_dev = sum(device_by_site.values())
    dominance_pct = round(100.0 * dominant[1] / total_dev, 1) if total_dev else 0.0
    single_site_dominates = bool(dominant[0]) and dominance_pct >= 50.0

    dev_distinct = len([s for s in device_by_site])
    line_distinct = len([s for s in line_by_site])
    lines_more_realistic = single_site_dominates and line_distinct > dev_distinct

    return {
        "customer_id": customer_id, "customer_name": customer_name,
        "rows": rows,
        "summary": {**{k: 0 for k in CLASSIFICATIONS},
                    **Counter(r["classification"] for r in rows),
                    "total_devices": len(devices), "total_lines": len(lines)},
        "device_count_by_site": dict(device_by_site.most_common()),
        "line_count_by_site": dict(line_by_site.most_common()),
        "devices_sharing_site": devices_sharing_site,
        "dominant_site": {"site_id": dominant[0], "device_count": dominant[1],
                          "pct": dominance_pct, "single_site_dominates": single_site_dominates,
                          "site_name": site_name.get(dominant[0])},
        "device_distinct_sites": dev_distinct,
        "line_distinct_sites": line_distinct,
        "lines_more_realistic": lines_more_realistic,
    }


# ── export ───────────────────────────────────────────────────────────────
def write_json(report: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"read_only": True, **report}, fh, indent=2, ensure_ascii=False, default=str)


def write_csv(rows: list[dict], path: str) -> int:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(REPORT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


# ── report ───────────────────────────────────────────────────────────────
def _print(report: dict, customer: str) -> None:
    s = report["summary"]
    print("=" * 84)
    print(f"R&R device→site assignment diagnostic — {customer}  (READ-ONLY)")
    print("=" * 84)
    print("\n--- SUMMARY ---")
    for k in CLASSIFICATIONS:
        print(f"  {k:<20}: {s[k]}")
    print(f"  {'total_devices':<20}: {s['total_devices']}   total_lines: {s['total_lines']}")

    dom = report["dominant_site"]
    print("\n--- SITE DISTRIBUTION ---")
    print(f"  device_distinct_sites={report['device_distinct_sites']}  "
          f"line_distinct_sites={report['line_distinct_sites']}")
    print(f"  dominant device site={dom['site_id']} ({dom['site_name']}) holds "
          f"{dom['device_count']} devices ({dom['pct']}%)  "
          f"single_site_dominates={dom['single_site_dominates']}")
    print(f"  lines_more_realistic={report['lines_more_realistic']}")
    print(f"  device_count_by_site (top 5): {dict(list(report['device_count_by_site'].items())[:5])}")

    wrong = [r for r in report["rows"] if r["classification"] == "likely_wrong_site"]
    print(f"\n--- TOP 25 likely_wrong_site ({len(wrong)} total) ---")
    for r in wrong[:25]:
        print(f"  {r['device_id']}  msisdn={r['msisdn']}")
        print(f"      device.site={r['device_site_id']} ({r['device_site_name']})  ->  "
              f"line.site={r['line_site_id']} ({r['line_site_name']})  [proposed: {r['proposed_site_id']}]")
    print("\n  (Read-only — diagnostic + proposal only; no writes.)")


async def run(customer: str, *, export_json: Optional[str] = None,
              export_csv: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        t911 = await _load_true911(db, customer)
    sites = t911.get("sites", [])
    cust_id = Counter(s.get("customer_id") for s in sites if s.get("customer_id")).most_common(1)
    customer_id = cust_id[0][0] if cust_id else None
    customer_name = (t911.get("customer") or {}).get("name") or customer
    report = build_report(t911.get("devices", []), t911.get("lines", []), sites,
                          customer_id=customer_id, customer_name=customer_name)
    _print(report, customer)
    if export_json:
        write_json(report, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(report["rows"], export_csv)
        print(f"  Wrote {n} rows (CSV) -> {export_csv}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only R&R device→site assignment diagnostic.")
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER)
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.customer, export_json=args.export_json, export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: site-assignment diagnostic aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
