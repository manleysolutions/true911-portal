"""Zoho staging COVERAGE audit (READ-ONLY).

Diagnoses why Subscription_Mgmnt data that exists in Zoho CRM is missing from the
staging tables the reconciliation reads. For each customer it compares the LIVE
Zoho count against the STAGED count and explains the gap + the exact fix.

Root cause this surfaces: staging is populated by (a) the webhook ingest, which
only captures events that arrive AFTER the flag was enabled — it never backfills
history; and (b) ``app.backfill_zoho_subscription_staging``, which only stages the
customers it is RUN for. So a customer whose subscriptions predate the webhook and
was never backfilled (e.g. Restoration Hardware, Integrity, R&R) shows
``staged=0`` even though Zoho has records.

Strictly READ-ONLY: only SELECTs + read-only Zoho GETs; no writes, no backfill, no
imports, no status changes. Zoho is queried best-effort — if it is unreachable the
staging side is still reported (coverage = ``zoho_unavailable``).

Run:
    python -m app.audit_zoho_staging_coverage
    python -m app.audit_zoho_staging_coverage --customer "R&R Realty" --export-json cov.json
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

from app.audit_zoho_true911_customer_reconciliation import name_matches  # noqa: E402

DEFAULT_CUSTOMERS = ["Restoration Hardware", "Integrity", "R&R Realty", "Webber Infra"]

REPORT_FIELDS = (
    "customer", "zoho_count", "staged_count", "map_count",
    "zoho_account_names", "staged_account_names", "account_ids",
    "staging_first_seen", "staging_last_updated",
    "coverage", "backfill_required", "reason", "recommended_fix",
)


# ── pure classification (unit-tested, no DB / no Zoho) ───────────────────
def classify_coverage(zoho_count: Optional[int], staged_count: int) -> str:
    """Coverage verdict from the live-Zoho vs staged counts.

      zoho_unavailable          — could not query Zoho.
      none_either_side          — 0 in Zoho and 0 staged.
      staged_no_zoho            — staged rows but Zoho returned 0 (name mismatch?).
      complete                  — staged >= zoho (and zoho > 0).
      missing_backfill_required — zoho > 0 but 0 staged.
      partial_backfill_required — 0 < staged < zoho.
    """
    if zoho_count is None:
        return "zoho_unavailable"
    if zoho_count == 0:
        return "staged_no_zoho" if staged_count > 0 else "none_either_side"
    if staged_count >= zoho_count:
        return "complete"
    return "missing_backfill_required" if staged_count == 0 else "partial_backfill_required"


def _diagnose(customer: str, coverage: str, zoho_count, staged_count) -> tuple:
    fix_backfill = (f"Run the staging backfill for this customer (dry-run first): "
                    f"python -m app.backfill_zoho_subscription_staging --customer {customer!r}  "
                    f"then FEATURE_ZOHO_BACKFILL=true ... --apply")
    if coverage == "missing_backfill_required":
        return (f"Zoho has {zoho_count} Subscription_Mgmnt record(s) but 0 are staged — "
                "never backfilled. The webhook ingest only captures NEW events; it does "
                "not backfill pre-existing records.", fix_backfill)
    if coverage == "partial_backfill_required":
        return (f"Zoho has {zoho_count} but only {staged_count} staged — staging incomplete.",
                fix_backfill)
    if coverage == "complete":
        return (f"Staged {staged_count} >= Zoho {zoho_count} — coverage complete.", "none")
    if coverage == "staged_no_zoho":
        return ("Staging has rows but Zoho returned 0 for this name — likely an account-name "
                "mismatch (records may be under Parent_Account, or a differently-spelled "
                "Account). Verify the filter name.", "Confirm the Zoho Account/Parent_Account name and re-query.")
    if coverage == "none_either_side":
        return ("No Zoho subscriptions and none staged — this customer may have no "
                "Subscription_Mgmnt records (or the name doesn't match Zoho).", "Confirm the customer has Zoho subscriptions.")
    return ("Could not query Zoho (not configured/unreachable) — only the staged count is "
            f"known ({staged_count}).", "Re-run where Zoho CRM credentials are configured.")


def assess_customer(customer: str, *, zoho_records: Optional[list],
                    staged_records: list, map_count: int) -> dict:
    """Build one coverage row (pure)."""
    zoho_count = len(zoho_records) if zoho_records is not None else None
    staged_count = len(staged_records)
    coverage = classify_coverage(zoho_count, staged_count)
    reason, fix = _diagnose(customer, coverage, zoho_count, staged_count)
    return {
        "customer": customer,
        "zoho_count": zoho_count,
        "staged_count": staged_count,
        "map_count": map_count,
        "zoho_account_names": sorted({r.get("account_name") for r in (zoho_records or [])
                                      if r.get("account_name")}),
        "staged_account_names": sorted({r.get("account_name") for r in staged_records
                                        if r.get("account_name")}),
        "account_ids": sorted({r.get("external_account_id") for r in (zoho_records or [])
                               if r.get("external_account_id")}),
        "staging_first_seen": min([r.get("first_seen_at") for r in staged_records
                                   if r.get("first_seen_at")], default=None),
        "staging_last_updated": max([r.get("updated_at") for r in staged_records
                                     if r.get("updated_at")], default=None),
        "coverage": coverage,
        "backfill_required": coverage in ("missing_backfill_required", "partial_backfill_required"),
        "reason": reason,
        "recommended_fix": fix,
    }


# ── data gathering (READ-ONLY) ───────────────────────────────────────────
async def _zoho_records_for(customer: str) -> Optional[list]:
    """Live Zoho Subscription_Mgmnt extracted records for a customer, or None."""
    try:
        from app.backfill_zoho_subscription_staging import (
            fetch_subscription_records, DEFAULT_MODULE, resolve_fields,
        )
        from app.services.zoho_subscription_ingest import extract_subscription_fields
        raw = await fetch_subscription_records(DEFAULT_MODULE, customer, resolve_fields(None))
        return [extract_subscription_fields(r) for r in raw]
    except Exception as exc:
        print(f"  (Zoho query for {customer!r} failed: {type(exc).__name__}: {str(exc)[:80]})")
        return None


async def _staging_for(db, customer: str) -> tuple:
    from sqlalchemy import select
    from app.models.zoho_subscription_record import ZohoSubscriptionRecord
    from app.models.external_record_map import ExternalRecordMap

    all_staged = (await db.execute(select(ZohoSubscriptionRecord))).scalars().all()
    staged = [{
        "subscription_mgmt_id": z.subscription_mgmt_id, "account_name": z.account_name,
        "facility_name": z.facility_name, "first_seen_at": z.first_seen_at,
        "updated_at": z.updated_at, "external_record_map_id": z.external_record_map_id,
    } for z in all_staged
        if name_matches(customer, z.account_name) or name_matches(customer, z.facility_name)]

    map_ids = {s["external_record_map_id"] for s in staged if s["external_record_map_id"]}
    map_count = 0
    if map_ids:
        map_count = len((await db.execute(select(ExternalRecordMap).where(
            ExternalRecordMap.id.in_(map_ids)))).scalars().all())
    return staged, map_count


async def run(customers: list[str], *, export_json: Optional[str] = None,
              export_csv: Optional[str] = None) -> list[dict]:
    from app.database import AsyncSessionLocal
    rows = []
    async with AsyncSessionLocal() as db:
        for cust in customers:
            zoho = await _zoho_records_for(cust)
            staged, map_count = await _staging_for(db, cust)
            rows.append(assess_customer(cust, zoho_records=zoho,
                                        staged_records=staged, map_count=map_count))
    _print(rows)
    if export_json:
        with open(export_json, "w", encoding="utf-8") as fh:
            json.dump({"read_only": True, "rows": rows}, fh, indent=2,
                      ensure_ascii=False, default=str)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        with open(export_csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(REPORT_FIELDS), extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({**r, "zoho_account_names": "; ".join(r["zoho_account_names"]),
                            "staged_account_names": "; ".join(r["staged_account_names"]),
                            "account_ids": "; ".join(map(str, r["account_ids"]))})
        print(f"  Wrote {len(rows)} rows (CSV) -> {export_csv}")
    return rows


def _print(rows: list[dict]) -> None:
    print("=" * 80)
    print("Zoho Staging Coverage Audit  —  READ-ONLY")
    print("=" * 80)
    for r in rows:
        print(f"\n• {r['customer']}  ->  [{r['coverage'].upper()}]  "
              f"backfill_required={r['backfill_required']}")
        print(f"    zoho_count={r['zoho_count']}  staged_count={r['staged_count']}  "
              f"map_count={r['map_count']}")
        print(f"    zoho_account_names={r['zoho_account_names']}")
        print(f"    staged_account_names={r['staged_account_names']}  account_ids={r['account_ids']}")
        print(f"    staging first_seen={r['staging_first_seen']}  last_updated={r['staging_last_updated']}")
        print(f"    REASON: {r['reason']}")
        print(f"    FIX: {r['recommended_fix']}")
    missing = [r["customer"] for r in rows if r["backfill_required"]]
    print("\n--- SUMMARY ---")
    print(f"  customers needing backfill: {missing or 'none'}")
    print("\n  (Read-only — no writes, no backfill, no imports.)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Zoho staging coverage audit.")
    parser.add_argument("--customer", action="append", default=[], help="customer (repeatable)")
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    args = parser.parse_args()
    customers = args.customer or DEFAULT_CUSTOMERS
    try:
        asyncio.run(run(customers, export_json=args.export_json, export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: coverage audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
