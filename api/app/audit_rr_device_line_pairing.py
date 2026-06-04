"""R&R device↔line pairing diagnostic (READ-ONLY).

PR #102 collapses a device and its line into one service ONLY when the line is
linked by ``lines.device_id == devices.device_id``. R&R's duplicate_candidate count
stayed high, which means that linkage is not present on the live data. This tool
shows, per MSISDN, exactly why the collapse did or did not fire — and classifies
each pairing so the safe matcher relaxation can be designed.

Strictly READ-ONLY: only SELECTs (via the reconciliation customer-scoped loader);
no writes, no migrations, no mapping changes, no webhook changes.

Run:
    python -m app.audit_rr_device_line_pairing
    python -m app.audit_rr_device_line_pairing --customer "R&R Realty Group" --export-json rr.json
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

DEFAULT_CUSTOMER = os.environ.get("RR_PAIRING_CUSTOMER", "R&R Realty Group")

CLASSIFICATIONS = (
    "collapsible_exact", "collapsible_by_msisdn_site", "line_device_id_missing",
    "line_device_id_mismatch", "site_mismatch", "customer_mismatch",
    "true_duplicate", "missing_line", "missing_device",
)

REPORT_FIELDS = (
    "msisdn", "device_id", "device_msisdn", "device_site_id", "device_customer_id",
    "line_id", "line_did", "line_device_id", "line_site_id", "line_customer_id",
    "msisdn_equal", "device_id_linked", "site_match", "customer_match",
    "classification", "reason", "would_collapse_under",
)


# ── pure pairing + classification (unit-tested, no DB) ───────────────────
def classify_pair(msisdn: str, devices: list[dict], lines: list[dict],
                  site_customer: dict) -> dict:
    base = {"msisdn": msisdn, "device_count": len(devices), "line_count": len(lines)}

    if not devices and lines:
        return {**base, "classification": "missing_device",
                "reason": "line(s) carry this MSISDN but no device does",
                "line_id": ",".join(l.get("line_id") or "" for l in lines),
                "would_collapse_under": "no"}
    if devices and not lines:
        return {**base, "classification": "missing_line",
                "reason": "device(s) carry this MSISDN but no line does",
                "device_id": ",".join(d.get("device_id") or "" for d in devices),
                "would_collapse_under": "no"}
    if len(devices) > 1 or len(lines) > 1:
        return {**base, "classification": "true_duplicate",
                "reason": f"{len(devices)} device(s) / {len(lines)} line(s) share this MSISDN (ambiguous)",
                "device_id": ",".join(d.get("device_id") or "" for d in devices),
                "line_id": ",".join(l.get("line_id") or "" for l in lines),
                "would_collapse_under": "no"}

    d, l = devices[0], lines[0]
    dcust = site_customer.get(d.get("site_id"))
    lcust = l.get("customer_id") if l.get("customer_id") is not None \
        else site_customer.get(l.get("site_id"))

    msisdn_equal = normalize_msisdn(d.get("msisdn")) == normalize_msisdn(l.get("did"))
    linked = l.get("device_id") is not None and l.get("device_id") == d.get("device_id")
    dev_id_missing = l.get("device_id") is None
    dev_id_mismatch = l.get("device_id") is not None and l.get("device_id") != d.get("device_id")
    site_match = (l.get("site_id") is None) or (l.get("site_id") == d.get("site_id"))
    site_mismatch = l.get("site_id") is not None and l.get("site_id") != d.get("site_id")
    cust_mismatch = lcust is not None and dcust is not None and lcust != dcust
    customer_match = not cust_mismatch

    fields = {
        **base,
        "device_id": d.get("device_id"), "device_msisdn": d.get("msisdn"),
        "device_site_id": d.get("site_id"), "device_customer_id": dcust,
        "line_id": l.get("line_id"), "line_did": l.get("did"),
        "line_device_id": l.get("device_id"), "line_site_id": l.get("site_id"),
        "line_customer_id": lcust,
        "msisdn_equal": msisdn_equal, "device_id_linked": linked,
        "site_match": site_match, "customer_match": customer_match,
    }

    if dev_id_mismatch:
        cls, reason, coll = ("line_device_id_mismatch",
                             "line.device_id points to a DIFFERENT device", "no")
    elif site_mismatch:
        cls, reason, coll = ("site_mismatch",
                             "device and line are on different sites", "no")
    elif cust_mismatch:
        cls, reason, coll = ("customer_mismatch",
                             "device and line owned by different customers", "no")
    elif linked and site_match:
        cls, reason, coll = ("collapsible_exact",
                             "linked by device_id + same site — collapses today (#102)", "exact")
    elif dev_id_missing and site_match and customer_match:
        cls, reason, coll = ("collapsible_by_msisdn_site",
                             "same MSISDN + same site + same customer, but line.device_id is "
                             "NULL — #102 required the device_id link, so it did NOT collapse",
                             "relaxed")
    elif dev_id_missing:
        cls, reason, coll = ("line_device_id_missing",
                             "line.device_id is NULL and site/customer cannot be confirmed equal", "no")
    else:
        cls, reason, coll = ("true_duplicate", "unresolved pairing", "no")

    return {**fields, "classification": cls, "reason": reason, "would_collapse_under": coll}


def pair_and_classify(devices: list[dict], lines: list[dict], sites: list[dict]) -> list[dict]:
    site_customer = {s.get("site_id"): s.get("customer_id") for s in sites}
    dev_by_m: dict = defaultdict(list)
    ln_by_m: dict = defaultdict(list)
    for d in devices:
        m = normalize_msisdn(d.get("msisdn"))
        if m:
            dev_by_m[m].append(d)
    for l in lines:
        m = normalize_msisdn(l.get("did"))
        if m:
            ln_by_m[m].append(l)
    rows = []
    for m in sorted(set(dev_by_m) | set(ln_by_m)):
        rows.append(classify_pair(m, dev_by_m.get(m, []), ln_by_m.get(m, []), site_customer))
    return rows


def summarize(rows: list[dict]) -> dict:
    c = Counter(r["classification"] for r in rows)
    return {"total_msisdns": len(rows), **{k: c.get(k, 0) for k in CLASSIFICATIONS}}


# ── export ───────────────────────────────────────────────────────────────
def write_json(rows: list[dict], summary: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"read_only": True, "summary": summary, "rows": rows},
                  fh, indent=2, ensure_ascii=False, default=str)


def write_csv(rows: list[dict], path: str) -> int:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(REPORT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


# ── report ───────────────────────────────────────────────────────────────
def _print(rows: list[dict], summary: dict, customer: str) -> None:
    print("=" * 84)
    print(f"R&R device↔line pairing diagnostic — {customer}  (READ-ONLY)")
    print("=" * 84)
    print("\n--- SUMMARY by classification ---")
    for k in CLASSIFICATIONS:
        print(f"  {k:<28}: {summary[k]}")
    print(f"  {'total_msisdns':<28}: {summary['total_msisdns']}")

    failed = [r for r in rows if r["would_collapse_under"] != "exact"
              and r["classification"] not in ("missing_line", "missing_device")]
    print(f"\n--- TOP 20 PAIRS THAT DID NOT COLLAPSE ({len(failed)} total) ---")
    for r in failed[:20]:
        print(f"  msisdn={r['msisdn']}  [{r['classification']}]  collapse={r['would_collapse_under']}")
        print(f"      device={r.get('device_id')} (site={r.get('device_site_id')}, cust={r.get('device_customer_id')})")
        print(f"      line  ={r.get('line_id')} did={r.get('line_did')} line.device_id={r.get('line_device_id')} "
              f"(site={r.get('line_site_id')}, cust={r.get('line_customer_id')})")
        print(f"      why: {r['reason']}")
    print("\n  (Read-only — diagnostic only; no writes, no matcher change.)")


async def run(customer: str, *, export_json: Optional[str] = None,
              export_csv: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        t911 = await _load_true911(db, customer)
    rows = pair_and_classify(t911.get("devices", []), t911.get("lines", []),
                             t911.get("sites", []))
    summary = summarize(rows)
    _print(rows, summary, customer)
    if export_json:
        write_json(rows, summary, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(rows, export_csv)
        print(f"  Wrote {n} rows (CSV) -> {export_csv}")
    return {"rows": rows, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only R&R device↔line pairing diagnostic.")
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER)
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.customer, export_json=args.export_json, export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: pairing diagnostic aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
