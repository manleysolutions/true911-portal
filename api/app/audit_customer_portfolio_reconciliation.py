"""Portfolio-wide customer reconciliation rollup (READ-ONLY).

A dashboard across ALL customers (those with Zoho Subscription_Mgmt records and/or
True911 devices/lines): per-customer reconciliation counts + a customer-level
classification + recommended next action, so remediation can be prioritized by
impact/risk instead of one customer at a time.

Reuses the per-customer reconciliation and the RH subscription classifier. Strictly
READ-ONLY: only SELECTs. No writes, migrations, mapping confirmations, or status
changes.

Run:
    python -m app.audit_customer_portfolio_reconciliation
    python -m app.audit_customer_portfolio_reconciliation --customer-filter "R&R" --limit 20 \
        --export-json portfolio.json --export-csv portfolio.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.audit_zoho_true911_customer_reconciliation import (  # noqa: E402
    reconcile_customer, normalize_name, name_matches,
    _load_zoho_records, _load_true911,
)
from app.audit_rh_subscription_classification import (  # noqa: E402
    build_classification, _load_rh_subs,
)

CUSTOMER_CLASSES = (
    "clean", "needs_mapping_confirmation", "needs_site_alignment",
    "needs_iccid_backfill", "needs_retirement_review", "needs_import_backfill",
    "needs_manual_review",
)

# Structural issue -> customer class, in low-risk / high-impact-first priority.
_STRUCTURAL_PRIORITY = (
    "needs_retirement_review", "needs_site_alignment",
    "needs_iccid_backfill", "needs_import_backfill",
)

REPORT_FIELDS = (
    "customer", "tenant", "zoho_subscription_count", "device_count", "line_count",
    "site_count", "matched_ok", "needs_mapping", "missing_in_true911",
    "missing_in_zoho", "duplicate_candidate", "status_mismatch",
    "historical_subscription", "missing_iccid", "missing_site",
    "classification", "recommended_action",
)

_ACTIONS = {
    "clean": "No action — reconciles cleanly.",
    "needs_mapping_confirmation": "Confirm Zoho↔True911 mappings in the review surface (no structural issues).",
    "needs_site_alignment": "Run site inventory + gated device→site correction — duplicate/site mismatch.",
    "needs_iccid_backfill": "Run the RH RadioNumber→ICCID backfill so active subs become matchable.",
    "needs_retirement_review": "Run gated retirement for the De-activated/historical subscriptions (Webber pattern).",
    "needs_import_backfill": "Import the missing devices (NAPCO/subscriber import) before mapping.",
    "needs_manual_review": "Mixed/insufficient data — check Zoho staging coverage and review manually.",
}


# ── pure classification (unit-tested, no DB) ─────────────────────────────
def classify_customer(row: dict) -> str:
    """Pick the dominant remediation class for a customer from its counts.

    Structural issues win by largest count (tie-break = low-risk-first priority).
    needs_mapping alone -> needs_mapping_confirmation (every unconfirmed Zoho record
    is needs_mapping, so it is a baseline, not a structural signal). Records that
    reconcile with nothing else wrong -> clean.
    """
    structural = {
        "needs_retirement_review": row.get("historical_subscription", 0) + row.get("replacement_subscription", 0),
        "needs_site_alignment": row.get("duplicate_candidate", 0) + row.get("missing_site", 0),
        "needs_iccid_backfill": row.get("missing_iccid", 0),
        "needs_import_backfill": row.get("missing_in_true911", 0) + row.get("missing_device", 0),
    }
    best, best_val = None, 0
    for cls in _STRUCTURAL_PRIORITY:          # priority order = stable tie-break
        if structural[cls] > best_val:
            best, best_val = cls, structural[cls]
    if best_val > 0:
        return best
    if row.get("needs_mapping", 0) > 0:
        return "needs_mapping_confirmation"
    if row.get("zoho_subscription_count", 0) > 0 or row.get("device_count", 0) > 0:
        return "clean"
    return "needs_manual_review"


def build_row(customer: str, tenant: Optional[str], recon_summary: dict,
              cls_summary: dict, *, zoho_count: int, device_count: int,
              line_count: int, site_count: int) -> dict:
    row = {
        "customer": customer, "tenant": tenant,
        "zoho_subscription_count": zoho_count, "device_count": device_count,
        "line_count": line_count, "site_count": site_count,
        "matched_ok": recon_summary.get("matched_ok", 0),
        "needs_mapping": recon_summary.get("needs_mapping", 0),
        "missing_in_true911": recon_summary.get("missing_in_true911", 0),
        "missing_in_zoho": recon_summary.get("missing_in_zoho", 0),
        "duplicate_candidate": recon_summary.get("duplicate_candidate", 0),
        "status_mismatch": recon_summary.get("status_mismatch", 0),
        "historical_subscription": cls_summary.get("historical_subscription", 0),
        "replacement_subscription": cls_summary.get("replacement_subscription", 0),
        "missing_iccid": cls_summary.get("missing_iccid", 0),
        "missing_site": cls_summary.get("missing_site", 0),
        "missing_device": cls_summary.get("missing_device", 0),
    }
    row["classification"] = classify_customer(row)
    row["recommended_action"] = _ACTIONS[row["classification"]]
    return row


# Remediation order: low-risk / high-impact first.
_ORDER_RANK = {
    "needs_retirement_review": 0, "needs_site_alignment": 1, "needs_iccid_backfill": 2,
    "needs_import_backfill": 3, "needs_mapping_confirmation": 4, "needs_manual_review": 5,
    "clean": 6,
}


def remediation_order(rows: list[dict]) -> list[dict]:
    """Order customers by class priority, then by impact (subscription count)."""
    return sorted(rows, key=lambda r: (_ORDER_RANK.get(r["classification"], 9),
                                       -r.get("zoho_subscription_count", 0),
                                       -r.get("device_count", 0)))


# ── DB enumeration + per-customer rollup (READ-ONLY) ─────────────────────
async def _enumerate_customers(db, customer_filter: Optional[str]) -> list[str]:
    from sqlalchemy import select
    from app.models.customer import Customer

    names: dict = {}   # normalized -> display name
    for z in await _load_zoho_records(db, None):
        n = z.get("account_name")
        if n and normalize_name(n) not in names:
            names[normalize_name(n)] = n
    for c in (await db.execute(select(Customer))).scalars().all():
        if c.name and normalize_name(c.name) not in names:
            names[normalize_name(c.name)] = c.name
    out = sorted(names.values(), key=normalize_name)
    if customer_filter:
        out = [n for n in out if name_matches(customer_filter, n)]
    return out


async def _rollup_customer(db, name: str) -> dict:
    zoho = await _load_zoho_records(db, name)
    t911 = await _load_true911(db, name)
    recon = reconcile_customer(name, zoho, t911)
    subs = await _load_rh_subs(db, name)
    cls = build_classification(subs, t911)
    tenant = (t911.get("tenant") or {}).get("tenant_id")
    return build_row(
        name, tenant, recon.summary, cls["summary"],
        zoho_count=len(zoho), device_count=len(t911.get("devices", [])),
        line_count=len(t911.get("lines", [])), site_count=len(t911.get("sites", [])))


# ── export / report ──────────────────────────────────────────────────────
def write_json(rows: list[dict], path: str) -> None:
    from collections import Counter
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"read_only": True,
                   "by_class": dict(Counter(r["classification"] for r in rows)),
                   "customers": remediation_order(rows)},
                  fh, indent=2, ensure_ascii=False, default=str)


def write_csv(rows: list[dict], path: str) -> int:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(REPORT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in remediation_order(rows):
            w.writerow(r)
    return len(rows)


def _print(rows: list[dict]) -> None:
    from collections import Counter
    print("=" * 100)
    print("Customer Portfolio Reconciliation — REMEDIATION DASHBOARD  (READ-ONLY)")
    print("=" * 100)
    print(f"  {'customer':<28} {'tenant':<14} {'zoho':>5} {'dev':>4} {'line':>4} "
          f"{'mok':>4} {'dup':>4} {'hist':>4} {'icc':>4} -> classification")
    for r in remediation_order(rows):
        print(f"  {str(r['customer'])[:27]:<28} {str(r['tenant'] or '-')[:13]:<14} "
              f"{r['zoho_subscription_count']:>5} {r['device_count']:>4} {r['line_count']:>4} "
              f"{r['matched_ok']:>4} {r['duplicate_candidate']:>4} "
              f"{r['historical_subscription']:>4} {r['missing_iccid']:>4} -> {r['classification']}")
    print("\n--- PORTFOLIO BY CLASS ---")
    for k, v in Counter(r["classification"] for r in rows).most_common():
        print(f"  {k:<28}: {v}")
    print("\n--- RECOMMENDED REMEDIATION ORDER (low-risk / high-impact first) ---")
    for i, r in enumerate(remediation_order(rows), 1):
        if r["classification"] == "clean":
            continue
        print(f"  {i}. {r['customer']}  [{r['classification']}]  {r['recommended_action']}")
    print("\n  (Read-only — dashboard only; no writes, no mapping/status changes.)")


async def run(*, customer_filter: Optional[str] = None, limit: Optional[int] = None,
              export_json: Optional[str] = None, export_csv: Optional[str] = None) -> list[dict]:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        names = await _enumerate_customers(db, customer_filter)
        if limit:
            names = names[:limit]
        rows = [await _rollup_customer(db, n) for n in names]
    _print(rows)
    if export_json:
        write_json(rows, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(rows, export_csv)
        print(f"  Wrote {n} customer rows (CSV) -> {export_csv}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only portfolio-wide reconciliation dashboard.")
    parser.add_argument("--customer-filter", dest="customer_filter", help="substring filter on customer name")
    parser.add_argument("--limit", type=int, help="cap the number of customers processed")
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    args = parser.parse_args()
    try:
        asyncio.run(run(customer_filter=args.customer_filter, limit=args.limit,
                        export_json=args.export_json, export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: portfolio rollup aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
