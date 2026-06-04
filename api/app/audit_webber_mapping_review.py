"""Webber (or any customer) Zoho ↔ True911 MAPPING REVIEW report (READ-ONLY).

The reconciliation audit tells you WHAT is mismatched; this report puts each Zoho
Subscription_Mgmt record side-by-side with its closest True911 candidates
(line/device by MSISDN, site by normalized facility name) and a recommended
operator action — the worksheet for confirming mappings by hand.

Strictly READ-ONLY: only SELECTs (via the reconciliation loaders); no writes, no
migrations, no webhook/auth changes, no status changes, and it CONFIRMS NOTHING —
it only proposes. ``--export-json`` / ``--export-csv`` write an operator-requested
report file.

Run:
    python -m app.audit_webber_mapping_review
    python -m app.audit_webber_mapping_review --customer "Webber Infra" \
        --export-json webber_map.json --export-csv webber_map.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import defaultdict
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Reuse the reconciliation primitives (all read-only / pure).
from app.audit_zoho_true911_customer_reconciliation import (  # noqa: E402
    derive_zoho_lifecycle, normalize_msisdn, normalize_name, facility_site_match,
    _load_zoho_records, _load_true911,
)

DEFAULT_CUSTOMER = os.environ.get("WEBBER_REVIEW_CUSTOMER", "Webber Infra")

_ACTIVE_STATES = frozenset({"active", "provisioning"})

REPORT_FIELDS = (
    "zoho_subscription_id", "zoho_account_name", "zoho_facility_name",
    "zoho_msisdn", "zoho_activation_status", "zoho_lifecycle",
    "msisdn_match", "matched_true911_entity", "matched_entity_status",
    "site_match", "matched_site_id", "matched_site_name",
    "classification", "recommended_action",
)


# ── pure matching core (unit-tested, no DB) ──────────────────────────────
def _true911_msisdn_index(t911: dict) -> dict:
    """normalized MSISDN -> list of (kind, id, status) from devices + lines."""
    idx: dict[str, list] = defaultdict(list)
    for d in t911.get("devices", []):
        m = normalize_msisdn(d.get("msisdn"))
        if m:
            idx[m].append(("device", d.get("device_id"), d.get("status")))
    for l in t911.get("lines", []):
        m = normalize_msisdn(l.get("did"))
        if m:
            idx[m].append(("line", l.get("line_id"), l.get("status")))
    return idx


def _closest_site(facility: Optional[str], sites: list[dict]) -> tuple:
    """Return (site_match, site_dict_or_None): exact | fuzzy | missing.

    Delegates to the shared ``facility_site_match`` (suffix-strip + token overlap
    + abbreviations). A ``fuzzy`` result is a review lead, never auto-confirmed.
    """
    return facility_site_match(facility, sites)


def _overall(msisdn_match: str, site_match: str) -> str:
    """Best-available identity classification for the record."""
    if msisdn_match == "duplicate":
        return "duplicate"            # ambiguous — resolve before anything else
    if msisdn_match == "exact":
        return "exact"
    if site_match in ("exact", "fuzzy"):
        return "fuzzy"                # no MSISDN identity; only a name lead
    return "missing"


def _recommend(classification: str, n_matches: int, site: Optional[dict],
               lifecycle_note: Optional[str]) -> str:
    if classification == "exact":
        base = "Confirm: MSISDN matches one True911 line/device — map this subscription to it."
    elif classification == "duplicate":
        base = (f"Resolve duplicate: MSISDN matches {n_matches} True911 entities — "
                "pick the correct one before mapping.")
    elif classification == "fuzzy":
        sn = (site or {}).get("site_name")
        base = (f"Verify by site name (closest: {sn!r}) — no MSISDN match; confirm the "
                "device/line, then map.")
    else:
        base = ("Locate/provision: no True911 line/device/site for this MSISDN/facility — "
                "create or import before mapping.")
    if lifecycle_note:
        base += f" | {lifecycle_note}"
    return base


def build_review(zoho_records: list[dict], t911: dict) -> list[dict]:
    """Pair each Zoho record with its closest True911 candidates. Pure."""
    by_msisdn = _true911_msisdn_index(t911)
    sites = t911.get("sites", [])
    rows: list[dict] = []

    for z in zoho_records:
        zm = normalize_msisdn(z.get("msisdn"))
        matches = by_msisdn.get(zm, []) if zm else []
        if len(matches) == 1:
            msisdn_match = "exact"
            entity = f"{matches[0][0]}:{matches[0][1]}"
            entity_status = matches[0][2]
        elif len(matches) > 1:
            msisdn_match = "duplicate"
            entity = f"{len(matches)} entities: " + ", ".join(f"{k}:{i}" for k, i, _ in matches)
            entity_status = None
        else:
            msisdn_match = "missing"
            entity = None
            entity_status = None

        site_match, msite = _closest_site(z.get("facility_name"), sites)
        classification = _overall(msisdn_match, site_match)

        zlife = derive_zoho_lifecycle(z)
        lifecycle_note = None
        if zlife == "deactivated" and entity_status \
                and str(entity_status).strip().lower() in _ACTIVE_STATES:
            lifecycle_note = ("Zoho De-activated but matched True911 entity is ACTIVE — "
                              "review lifecycle")

        rows.append({
            "zoho_subscription_id": z.get("subscription_mgmt_id"),
            "zoho_account_name": z.get("account_name"),
            "zoho_facility_name": z.get("facility_name"),
            "zoho_msisdn": z.get("msisdn"),
            "zoho_activation_status": z.get("device_activation_status"),
            "zoho_lifecycle": zlife,
            "msisdn_match": msisdn_match,
            "matched_true911_entity": entity,
            "matched_entity_status": entity_status,
            "site_match": site_match,
            "matched_site_id": (msite or {}).get("site_id"),
            "matched_site_name": (msite or {}).get("site_name"),
            "classification": classification,
            "recommended_action": _recommend(
                classification, len(matches), msite, lifecycle_note),
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    from collections import Counter
    c = Counter(r["classification"] for r in rows)
    return {"records": len(rows), **{k: c.get(k, 0)
            for k in ("exact", "duplicate", "fuzzy", "missing")}}


# ── export ───────────────────────────────────────────────────────────────
def write_json(rows: list[dict], summary: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"read_only": True, "summary": summary, "records": rows},
                  fh, indent=2, ensure_ascii=False, default=str)


def write_csv(rows: list[dict], path: str) -> int:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(REPORT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


# ── report ─────────────────────────────────────────────────────────────
def _print(rows: list[dict], summary: dict, customer: str, t911: dict) -> None:
    print("=" * 80)
    print(f"Webber mapping review — Zoho ↔ True911 candidates  (READ-ONLY)")
    print(f"customer={customer}  zoho_records={len(rows)}  "
          f"true911_devices={len(t911.get('devices', []))}  "
          f"lines={len(t911.get('lines', []))}  sites={len(t911.get('sites', []))}")
    print("=" * 80)
    for r in rows:
        print(f"\n• sub_id={r['zoho_subscription_id']}  msisdn={r['zoho_msisdn']}  "
              f"[{r['classification'].upper()}]")
        print(f"    zoho: account={r['zoho_account_name']!r} facility={r['zoho_facility_name']!r} "
              f"status={r['zoho_activation_status']!r} ({r['zoho_lifecycle']})")
        print(f"    true911 MSISDN match: {r['msisdn_match']} -> {r['matched_true911_entity'] or '-'}"
              f" (status={r['matched_entity_status'] or '-'})")
        print(f"    true911 site match : {r['site_match']} -> "
              f"{r['matched_site_name'] or '-'} ({r['matched_site_id'] or '-'})")
        print(f"    ACTION: {r['recommended_action']}")
    print("\n--- SUMMARY ---")
    for k in ("records", "exact", "duplicate", "fuzzy", "missing"):
        print(f"  {k:<10}: {summary[k]}")
    print("\n  (Review only — confirms nothing, writes nothing.)")


async def run(customer: str, *, export_json: Optional[str] = None,
              export_csv: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        zoho = await _load_zoho_records(db, customer)
        t911 = await _load_true911(db, customer)
    rows = build_review(zoho, t911)
    summary = summarize(rows)
    _print(rows, summary, customer, t911)
    if export_json:
        write_json(rows, summary, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(rows, export_csv)
        print(f"  Wrote {n} rows (CSV) -> {export_csv}")
    return {"rows": rows, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Webber Zoho↔True911 mapping review report.")
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER,
                        help=f"customer name (default {DEFAULT_CUSTOMER!r})")
    parser.add_argument("--export-json", dest="export_json", help="write JSON report")
    parser.add_argument("--export-csv", dest="export_csv", help="write CSV report")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.customer, export_json=args.export_json,
                        export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: review aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
