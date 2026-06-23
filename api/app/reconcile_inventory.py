"""Inventory reconciliation runner (EPIC-GEN-003) — READ-ONLY.

Customer- and vendor-agnostic: reconciles a vendor export (via a pluggable
adapter) against True911 inventory and writes INVENTORY_RECONCILIATION.csv +
.json + summary statistics. No DB writes, no feature flags, no production
mutation.

Run:
    # NAPCO, all tenants:
    python -m app.reconcile_inventory --vendor napco --vendor-export /path/to/Radiolist.xlsx
    # scoped to one customer/tenant, custom output base:
    python -m app.reconcile_inventory --vendor napco --vendor-export R.tsv \
        --tenant restoration-hardware --out /tmp/INVENTORY_RECONCILIATION
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.inventory_reconciliation import engine, export  # noqa: E402
from app.services.inventory_reconciliation.adapters import base  # noqa: E402
from app.services.inventory_reconciliation.adapters import napco  # noqa: E402,F401 (registers "napco")
from app.services.inventory_reconciliation.inventory import load_true911_inventory  # noqa: E402


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Read-only inventory reconciliation.")
    ap.add_argument("--vendor", default="napco", help=f"adapter ({', '.join(base.available())})")
    ap.add_argument("--vendor-export", required=True, help="path to the vendor export file")
    ap.add_argument("--tenant", default=None, help="optional True911 tenant_id scope")
    ap.add_argument("--out", default="INVENTORY_RECONCILIATION", help="output base path")
    return ap.parse_args(argv)


async def _run(vendor_records, args):
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        items = await load_true911_inventory(db, tenant_id=args.tenant)
        await db.rollback()  # never write
    rows, summary = engine.reconcile(vendor_records, items)
    csv_path, json_path = export.write_reports(args.out, rows, summary)
    print("=" * 64)
    print(f"Inventory reconciliation — vendor={args.vendor} tenant={args.tenant or 'ALL'}")
    print("=" * 64)
    for k in ("vendor_records", "matched", "partial", "missing_in_true911",
              "missing_in_vendor", "duplicate", "review", "match_rate"):
        print(f"  {k:<20} {summary.get(k)}")
    print(f"\n  CSV:  {csv_path}\n  JSON: {json_path}")
    return summary


def main():
    args = _parse_args()
    adapter = base.get_adapter(args.vendor)
    if adapter is None:
        print(f"Unknown vendor {args.vendor!r}. Available: {base.available()}")
        raise SystemExit(2)
    vendor_records = adapter.parse(args.vendor_export)
    if not vendor_records:
        print(f"No records parsed from {args.vendor_export!r}. Nothing to reconcile.")
        raise SystemExit(1)
    try:
        asyncio.run(_run(vendor_records, args))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: reconciliation aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
