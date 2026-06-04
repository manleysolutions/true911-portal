"""Restoration Hardware Zoho subscription classification (READ-ONLY).

Explains why RH has ~91 Zoho subscriptions but only ~51 True911 devices: classifies
every RH Zoho ``Subscription_Mgmt`` record against the True911 footprint
(customer-scoped) and produces a remediation roadmap.

Strictly READ-ONLY: only SELECTs. No writes, no migrations, no mapping changes, no
imports, no status changes.

Run:
    python -m app.audit_rh_subscription_classification
    python -m app.audit_rh_subscription_classification --customer "Restoration Hardware" \
        --export-json rh.json --export-csv rh.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.audit_zoho_true911_customer_reconciliation import (  # noqa: E402
    normalize_msisdn, normalize_name, name_matches, derive_zoho_lifecycle,
    facility_site_match, _load_true911,
)

DEFAULT_CUSTOMER = os.environ.get("RH_SUBS_CUSTOMER", "Restoration Hardware")
_DEACTIVATED = "deactivated"
_ACTIVE = "active"
_ACTIVE_DEVICE_STATES = frozenset({"active", "provisioning"})

CLASSIFICATIONS = (
    "matched_service", "historical_subscription", "duplicate_subscription",
    "replacement_subscription", "missing_device", "missing_site",
    "missing_iccid", "unresolved",
)

REPORT_FIELDS = (
    "subscription_id", "account", "facility", "msisdn", "iccid",
    "device_identifier", "device_activation_status", "subscription_type",
    "connection_type", "matched_site_id", "matched_device_id", "matched_line_id",
    "classification",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _norm_key(k: str) -> str:
    return _NON_ALNUM.sub("", str(k).lower())


def _from_raw(raw: Optional[dict], *candidates: str):
    """Tolerant lookup of a value in a sanitized raw payload by normalized key."""
    if not isinstance(raw, dict):
        return None
    idx = {_norm_key(k): v for k, v in raw.items()}
    for c in candidates:
        v = idx.get(_norm_key(c))
        if v not in (None, ""):
            return v
    return None


def normalize_iccid(s) -> str:
    if not s:
        return ""
    t = str(s).strip()
    if t and t[-1] in ("F", "f"):
        t = t[:-1]
    return "".join(ch for ch in t if ch.isdigit())


# ── pure classification (unit-tested, no DB) ─────────────────────────────
def classify_subscription(*, lifecycle: str, has_device_match: bool,
                          iccid_present: bool, msisdn_present: bool,
                          site_match: str, dup_count: int,
                          has_active_sibling: bool) -> str:
    """Primary classification for one subscription (first rule wins)."""
    deactivated = lifecycle == _DEACTIVATED
    if dup_count > 1:
        if deactivated and has_active_sibling:
            return "replacement_subscription"   # superseded by an active sibling
        return "duplicate_subscription"
    if has_device_match:
        return "historical_subscription" if deactivated else "matched_service"
    # singleton, no True911 device/line carries its identifier
    if deactivated:
        return "historical_subscription"        # retired billing record (no device)
    if msisdn_present and not iccid_present:
        return "missing_iccid"                  # active cellular sub lacking an ICCID
    if msisdn_present and iccid_present:
        return "missing_device"                 # has identifiers but no True911 device
    if site_match == "missing":
        return "missing_site"                   # no identifiers + facility unknown
    return "unresolved"


def build_classification(subs: list[dict], t911: dict) -> dict:
    """subs: enriched Zoho records; t911: customer-scoped footprint. Pure."""
    devices, lines, sites = t911.get("devices", []), t911.get("lines", []), t911.get("sites", [])
    dev_by_msisdn: dict = defaultdict(list)
    line_by_msisdn: dict = defaultdict(list)
    dev_by_iccid: dict = defaultdict(list)
    for d in devices:
        if normalize_msisdn(d.get("msisdn")):
            dev_by_msisdn[normalize_msisdn(d.get("msisdn"))].append(d)
        if normalize_iccid(d.get("iccid")):
            dev_by_iccid[normalize_iccid(d.get("iccid"))].append(d)
    for l in lines:
        if normalize_msisdn(l.get("did")):
            line_by_msisdn[normalize_msisdn(l.get("did"))].append(l)

    # duplicate detection by primary identifier (msisdn -> iccid -> device id)
    def primary_id(s):
        return (normalize_msisdn(s.get("msisdn")) or normalize_iccid(s.get("iccid"))
                or (s.get("device_identifier") or "").strip())
    groups: dict = defaultdict(list)
    for s in subs:
        pid = primary_id(s)
        if pid:
            groups[pid].append(s)

    rows = []
    for s in subs:
        m = normalize_msisdn(s.get("msisdn"))
        ic = normalize_iccid(s.get("iccid"))
        dev = (dev_by_msisdn.get(m) or dev_by_iccid.get(ic) or [None])[0]
        line = (line_by_msisdn.get(m) or [None])[0]
        site_match, site = facility_site_match(s.get("facility"), sites)
        lifecycle = derive_zoho_lifecycle({
            "lifecycle_state": s.get("lifecycle_state"),
            "device_activation_status": s.get("device_activation_status")})
        pid = primary_id(s)
        grp = groups.get(pid, [])
        has_active_sibling = any(
            derive_zoho_lifecycle({"lifecycle_state": o.get("lifecycle_state"),
                                   "device_activation_status": o.get("device_activation_status")}) == _ACTIVE
            for o in grp if o is not s)
        cls = classify_subscription(
            lifecycle=lifecycle, has_device_match=bool(dev or line),
            iccid_present=bool(ic), msisdn_present=bool(m), site_match=site_match,
            dup_count=len(grp), has_active_sibling=has_active_sibling)
        rows.append({
            "subscription_id": s.get("subscription_mgmt_id"), "account": s.get("account_name"),
            "facility": s.get("facility_name"), "msisdn": s.get("msisdn"), "iccid": s.get("iccid"),
            "device_identifier": s.get("device_identifier"),
            "device_activation_status": s.get("device_activation_status"),
            "subscription_type": s.get("subscription_type"), "connection_type": s.get("connection_type"),
            "matched_site_id": (site or {}).get("site_id"),
            "matched_device_id": (dev or {}).get("device_id") if dev else None,
            "matched_line_id": (line or {}).get("line_id") if line else None,
            "lifecycle": lifecycle, "classification": cls,
        })

    summary = {**{k: 0 for k in CLASSIFICATIONS},
               **Counter(r["classification"] for r in rows),
               "total_subscriptions": len(rows),
               "true911_devices": len(devices), "true911_lines": len(lines),
               "true911_sites": len(sites)}
    return {"rows": rows, "summary": summary, "recommendation": _recommend(summary)}


def _recommend(s: dict) -> list[str]:
    out = []
    if s["historical_subscription"]:
        out.append(f"{s['historical_subscription']} historical_subscription — De-activated billing "
                   "records with no live device. These explain most of the 91-vs-51 gap; archive/close "
                   "in Zoho (no True911 action).")
    if s["duplicate_subscription"] or s["replacement_subscription"]:
        out.append(f"{s['duplicate_subscription']} duplicate + {s['replacement_subscription']} replacement "
                   "— consolidate: keep the active subscription, retire the superseded ones.")
    if s["missing_device"]:
        out.append(f"{s['missing_device']} missing_device — active subs with identifiers but no True911 "
                   "device; import the device (NAPCO StarLink import) before mapping.")
    if s["missing_iccid"]:
        out.append(f"{s['missing_iccid']} missing_iccid — active cellular subs lacking an ICCID; run the "
                   "RH RadioNumber→ICCID backfill so they become matchable.")
    if s["missing_site"]:
        out.append(f"{s['missing_site']} missing_site — facility not matched to a True911 site; create/align "
                   "the site.")
    if s["unresolved"]:
        out.append(f"{s['unresolved']} unresolved — manual review.")
    out.append(f"matched_service={s['matched_service']} are in service and reconcile cleanly.")
    return out


# ── DB load (READ-ONLY) ──────────────────────────────────────────────────
async def _load_rh_subs(db, customer: str) -> list[dict]:
    from sqlalchemy import select
    from app.models.zoho_subscription_record import ZohoSubscriptionRecord

    recs = (await db.execute(select(ZohoSubscriptionRecord))).scalars().all()
    out = []
    for z in recs:
        if not (name_matches(customer, z.account_name) or name_matches(customer, z.facility_name)):
            continue
        raw = z.raw_json or {}
        out.append({
            "subscription_mgmt_id": z.subscription_mgmt_id, "account_name": z.account_name,
            "facility_name": z.facility_name, "msisdn": z.msisdn,
            "device_activation_status": z.device_activation_status,
            "lifecycle_state": z.lifecycle_state, "subscription_type": z.subscription_type,
            "connection_type": z.connection_type,
            "iccid": _from_raw(raw, "ICCID", "Iccid", "SIM_ICCID", "sim_iccid"),
            "device_identifier": _from_raw(raw, "RadioNumber", "Radio_Number", "Device_ID",
                                           "DeviceId", "Serial", "Serial_Number"),
        })
    return out


# ── export / report ──────────────────────────────────────────────────────
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


def _print(report: dict, customer: str) -> None:
    s = report["summary"]
    print("=" * 86)
    print(f"Restoration Hardware Subscription Classification — {customer}  (READ-ONLY)")
    print("=" * 86)
    print(f"  zoho_subscriptions={s['total_subscriptions']}  true911_devices={s['true911_devices']}  "
          f"lines={s['true911_lines']}  sites={s['true911_sites']}")
    print("\n--- SUMMARY by classification ---")
    for k in CLASSIFICATIONS:
        print(f"  {k:<26}: {s[k]}")
    print("\n--- DETAIL (first 40) ---")
    for r in report["rows"][:40]:
        print(f"  {str(r['subscription_id'])[:16]:<16} [{r['classification']:<24}] "
              f"msisdn={r['msisdn'] or '-'} status={r['device_activation_status'] or '-'} "
              f"facility={str(r['facility'])[:24]!r} dev={r['matched_device_id'] or '-'}")
    print("\n--- RECOMMENDED REMEDIATION ---")
    for line in report["recommendation"]:
        print(f"  • {line}")
    print("\n  (Read-only — no writes, no mapping/status changes.)")


async def run(customer: str, *, export_json: Optional[str] = None,
              export_csv: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        subs = await _load_rh_subs(db, customer)
        t911 = await _load_true911(db, customer)
    report = build_classification(subs, t911)
    _print(report, customer)
    if export_json:
        write_json(report, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(report["rows"], export_csv)
        print(f"  Wrote {n} rows (CSV) -> {export_csv}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only RH Zoho subscription classification.")
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER)
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.customer, export_json=args.export_json, export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: classification aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
