"""Restoration Hardware — Zoho CRM ↔ True911 reconciliation (READ-ONLY).

Verifies that every RH location / device / E911 record in **Zoho CRM** exists
correctly in **True911**, and vice-versa.  Matches by store name, address,
city/state, phone number, and device/line label, then flags the gaps an operator
must resolve before go-live.

Strictly READ-ONLY:
  * True911 side — only SELECTs; never writes sites/devices/units/lines/E911.
  * Zoho side — only the existing authenticated GET layer (``zoho_crm.fetch_records``);
    NEVER writes to Zoho.
  * ``--csv`` / ``--json`` write an operator-requested report artifact (never a
    production-data change).

Usage:
    python -m scripts.rh_zoho_reconciliation
    python -m scripts.rh_zoho_reconciliation --tenant restoration-hardware \
        --module Accounts --csv /tmp/rh_zoho_reconciliation.csv \
        --json /tmp/rh_zoho_reconciliation.json --report /tmp/rh_zoho_sync_report.md
    # override the Zoho field set (default is a safe Accounts set):
    python -m scripts.rh_zoho_reconciliation --module Accounts \
        --fields "Account_Name,Billing_Street,Billing_City,Billing_State,Billing_Code,\
Shipping_Street,Shipping_City,Shipping_State,Shipping_Code,Phone"

Exit codes: 0 clean (no findings) · 1 findings present · 2 error / Zoho not configured.
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")
DEFAULT_CSV = "/tmp/rh_zoho_reconciliation.csv"
DEFAULT_JSON = "/tmp/rh_zoho_reconciliation.json"
DEFAULT_REPORT = "/tmp/rh_zoho_sync_report.md"
VERIFIED_E911 = frozenset({"validated", "verified", "confirmed"})

# Safe default field set for the Accounts module (billing + shipping address +
# phone).  Zoho v5 requires an explicit ``fields`` list for some orgs/modules;
# --fields overrides this.  Only used when the module is Accounts and no --fields
# is given (other modules pass None -> Zoho returns its default field set).
DEFAULT_ACCOUNT_FIELDS = (
    "Account_Name,Billing_Street,Billing_City,Billing_State,Billing_Code,"
    "Shipping_Street,Shipping_City,Shipping_State,Shipping_Code,Phone"
)

# Finding kinds (requirement §5).
KIND_ZOHO_MISSING = "zoho_location_missing_in_true911"
KIND_T911_MISSING = "true911_location_missing_in_zoho"
KIND_ADDR_MISMATCH = "address_mismatch"
KIND_MISSING_DEVICE = "missing_device"
KIND_MISSING_UNIT = "missing_service_unit"
KIND_MISSING_CALLBACK = "missing_callback_number"
KIND_E911_UNVERIFIED = "e911_unverified"
KIND_DUP_SITES = "duplicate_sites"
KIND_DUP_PHONES = "duplicate_phone_numbers"
KIND_BLANK_ADDRESS = "blank_or_malformed_address"
KIND_UNKNOWN_NAME = "unknown_store_name"
KIND_MISSING_E911_ENDPOINT = "missing_e911_endpoint_detail"

# Which findings are "inconsistencies" (B) vs "needs investigation" (C).
INCONSISTENCY_KINDS = frozenset({
    KIND_ADDR_MISMATCH, KIND_MISSING_DEVICE, KIND_MISSING_UNIT, KIND_MISSING_CALLBACK,
    KIND_E911_UNVERIFIED, KIND_DUP_PHONES, KIND_MISSING_E911_ENDPOINT,
})
INVESTIGATION_KINDS = frozenset({
    KIND_ZOHO_MISSING, KIND_T911_MISSING, KIND_DUP_SITES, KIND_BLANK_ADDRESS, KIND_UNKNOWN_NAME,
})

# Punch-list guidance per finding kind (source of truth · safe to auto-fix later ·
# operator review required).  Conservative: nothing is auto-fixed here.
PUNCH_LIST = {
    KIND_ZOHO_MISSING: ("Confirm the location exists in True911 (create the site if real)", "Zoho CRM", False, True),
    KIND_T911_MISSING: ("Confirm the True911 site in Zoho (add the account/location if real)", "True911", False, True),
    KIND_ADDR_MISMATCH: ("Reconcile the address; correct whichever record is wrong", "Zoho = billing; True911 E911 = dispatch (verify with site)", False, True),
    KIND_MISSING_DEVICE: ("Add the device(s) that deliver this location's service", "True911 inventory / install", False, True),
    KIND_MISSING_UNIT: ("Create the Life-Safety service unit(s) for this location", "True911", False, True),
    KIND_MISSING_CALLBACK: ("Add the callback / line number for the emergency endpoint", "True911 line/device", False, True),
    KIND_MISSING_E911_ENDPOINT: ("Add emergency-endpoint detail (service type / callback / floor)", "True911", False, True),
    KIND_E911_UNVERIFIED: ("Verify the E911 record via the controlled Manley flow", "True911 E911 (never auto-verified)", False, True),
    KIND_DUP_SITES: ("Investigate / de-duplicate the sites", "review", False, True),
    KIND_DUP_PHONES: ("Investigate the shared phone number; split or correct", "review", False, True),
    KIND_BLANK_ADDRESS: ("Fill in the missing/blank address parts", "Zoho + site confirmation", False, True),
    KIND_UNKNOWN_NAME: ("Give the site a real store/location name", "Zoho / site", False, True),
}


# ── pure normalization (unit-tested) ─────────────────────────────────
def norm_name(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def norm_addr(street, city, state) -> str:
    return norm_name(f"{street or ''} {city or ''} {state or ''}")


def norm_phone(s) -> str:
    digits = re.sub(r"\D", "", str(s or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def name_match(a: str, b: str) -> bool:
    a, b = norm_name(a), norm_name(b)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def map_zoho_location(rec: dict) -> dict:
    """Map a raw Zoho record to a normalized location, tolerant of field naming."""
    def pick(*keys):
        for k in keys:
            if rec.get(k):
                return rec[k]
        return None
    return {
        "zoho_id": str(rec.get("id", "") or ""),
        "name": pick("Account_Name", "Name", "Store_Name", "Location_Name"),
        "street": pick("Billing_Street", "Street", "Shipping_Street", "Address"),
        "city": pick("Billing_City", "City", "Shipping_City"),
        "state": pick("Billing_State", "State", "Shipping_State"),
        "zip": pick("Billing_Code", "Zip", "Zip_Code", "Shipping_Code"),
        "phone": pick("Phone", "Callback_Number", "Phone_Number", "phone"),
    }


# ── pure reconciliation (unit-tested; no DB, no Zoho) ────────────────
def reconcile(true911: dict, zoho_locations: list[dict]) -> dict:
    sites = true911.get("sites", [])
    devices = true911.get("devices", [])
    units = true911.get("units", [])
    lines = true911.get("lines", [])

    by_site_devices = defaultdict(list)
    for d in devices:
        by_site_devices[d.get("site_id")].append(d)
    by_site_units = defaultdict(list)
    for u in units:
        by_site_units[u.get("site_id")].append(u)
    # phone numbers per site (device msisdn + line did) + global phone→sites index
    site_phones = defaultdict(set)
    phone_sites = defaultdict(set)
    for d in devices:
        p = norm_phone(d.get("msisdn"))
        if p:
            site_phones[d.get("site_id")].add(p); phone_sites[p].add(d.get("site_id"))
    for ln in lines:
        p = norm_phone(ln.get("did"))
        if p:
            site_phones[ln.get("site_id")].add(p); phone_sites[p].add(ln.get("site_id"))

    findings = []

    def add(kind, severity, **kw):
        findings.append({"kind": kind, "severity": severity, "zoho_id": kw.get("zoho_id", ""),
                         "zoho_name": kw.get("zoho_name", ""), "site_id": kw.get("site_id", ""),
                         "site_name": kw.get("site_name", ""), "detail": kw.get("detail", "")})

    # ── Zoho -> True911 matching ──
    matched_site_ids = set()
    matched = []
    for z in zoho_locations:
        za = norm_addr(z.get("street"), z.get("city"), z.get("state"))
        zp = norm_phone(z.get("phone"))
        matches = []
        for s in sites:
            sig_name = name_match(z.get("name"), s.get("name"))
            sig_addr = bool(za) and za == norm_addr(s.get("street"), s.get("city"), s.get("state"))
            sig_phone = bool(zp) and zp in site_phones.get(s.get("site_id"), set())
            if sig_name or sig_addr or sig_phone:
                matches.append((s, sig_name, sig_addr, sig_phone))
        if not matches:
            add(KIND_ZOHO_MISSING, "high", zoho_id=z.get("zoho_id"), zoho_name=z.get("name"),
                detail="Zoho location has no matching True911 site")
            continue
        for s, *_ in matches:
            matched_site_ids.add(s.get("site_id"))
        if len(matches) > 1:
            add(KIND_DUP_SITES, "high", zoho_id=z.get("zoho_id"), zoho_name=z.get("name"),
                detail="Zoho location AMBIGUOUSLY matches "
                       + str(len(matches)) + " True911 sites: "
                       + ", ".join(s.get("site_id") for s, *_ in matches))
            continue
        # single confident match -> record it + check address mismatch
        s, sig_name, sig_addr, sig_phone = matches[0]
        signals = sum([sig_name, sig_addr, sig_phone])
        confidence = "high" if signals >= 2 else "medium"
        sa = norm_addr(s.get("street"), s.get("city"), s.get("state"))
        matched.append({
            "site_id": s.get("site_id"), "site_name": s.get("name"), "zoho_name": z.get("name"),
            "address": s.get("street"), "city": s.get("city"), "state": s.get("state"),
            "zip": s.get("zip"), "devices": len(by_site_devices.get(s.get("site_id"), [])),
            "service_units": len(by_site_units.get(s.get("site_id"), [])),
            "e911_status": s.get("e911_status"), "confidence": confidence,
        })
        if za and sa and za != sa:
            add(KIND_ADDR_MISMATCH, "medium", zoho_id=z.get("zoho_id"), zoho_name=z.get("name"),
                site_id=s.get("site_id"), site_name=s.get("name"),
                detail=f"Zoho='{z.get('street')}, {z.get('city')}, {z.get('state')}' vs "
                       f"True911='{s.get('street')}, {s.get('city')}, {s.get('state')}'")

    # ── True911 -> Zoho + per-site integrity ──
    name_counts = Counter(norm_name(s.get("name")) for s in sites if norm_name(s.get("name")))
    for s in sites:
        sid = s.get("site_id")
        if sid not in matched_site_ids:
            add(KIND_T911_MISSING, "high", site_id=sid, site_name=s.get("name"),
                detail="True911 site has no matching Zoho location")
        if not by_site_devices.get(sid):
            add(KIND_MISSING_DEVICE, "medium", site_id=sid, site_name=s.get("name"),
                detail="No devices at this location")
        if not by_site_units.get(sid):
            add(KIND_MISSING_UNIT, "medium", site_id=sid, site_name=s.get("name"),
                detail="No service units at this location")
        if not site_phones.get(sid):
            add(KIND_MISSING_CALLBACK, "medium", site_id=sid, site_name=s.get("name"),
                detail="No callback / phone number on any device or line")
        if (s.get("e911_status") or "").strip().lower() not in VERIFIED_E911:
            add(KIND_E911_UNVERIFIED, "high", site_id=sid, site_name=s.get("name"),
                detail=f"E911 status = {s.get('e911_status')!r} (not verified)")
        if name_counts.get(norm_name(s.get("name")), 0) > 1:
            add(KIND_DUP_SITES, "medium", site_id=sid, site_name=s.get("name"),
                detail="Multiple True911 sites share this normalized name")
        # blank / malformed address (some parts present, some missing, or all blank)
        addr_parts = [s.get("street"), s.get("city"), s.get("state"), s.get("zip")]
        present = [p for p in addr_parts if (p or "").strip()]
        if 0 < len(present) < 4 or len(present) == 0:
            add(KIND_BLANK_ADDRESS, "medium", site_id=sid, site_name=s.get("name"),
                detail=f"Address incomplete ({len(present)}/4 parts present)")
        # unknown / blank store name
        if not norm_name(s.get("name")):
            add(KIND_UNKNOWN_NAME, "medium", site_id=sid, detail="Site has no usable store name")
        # missing E911 endpoint detail: an addressed site with no service-unit endpoint
        if len(present) == 4 and not by_site_units.get(sid):
            add(KIND_MISSING_E911_ENDPOINT, "medium", site_id=sid, site_name=s.get("name"),
                detail="Addressed location has no emergency service unit / endpoint")

    # ── duplicate phone numbers (across the tenant) ──
    for phone, ids in phone_sites.items():
        if len(ids) > 1:
            add(KIND_DUP_PHONES, "high", detail=f"Phone …{phone[-4:]} appears on {len(ids)} sites: "
                                                 + ", ".join(sorted(str(i) for i in ids)))

    summary = {
        "tenant": true911.get("tenant"),
        "true911_sites": len(sites), "true911_devices": len(devices),
        "true911_service_units": len(units), "zoho_locations": len(zoho_locations),
        "matched": len(matched),
        "inconsistencies": sum(1 for f in findings if f["kind"] in INCONSISTENCY_KINDS),
        "needs_investigation": sum(1 for f in findings if f["kind"] in INVESTIGATION_KINDS),
        "missing_service_units": sum(1 for f in findings if f["kind"] == KIND_MISSING_UNIT),
        "e911_unverified": sum(1 for f in findings if f["kind"] == KIND_E911_UNVERIFIED),
        "findings_total": len(findings),
        "by_kind": dict(Counter(f["kind"] for f in findings)),
    }
    return {"summary": summary, "findings": findings, "matched": matched}


# ── read-only loaders ────────────────────────────────────────────────
async def load_true911(db, tenant_id: str) -> dict:
    from sqlalchemy import select

    from app.models.device import Device
    from app.models.line import Line
    from app.models.service_unit import ServiceUnit
    from app.models.site import Site

    sites = [{"site_id": s.site_id, "name": s.site_name, "street": s.e911_street,
              "city": s.e911_city, "state": s.e911_state, "zip": s.e911_zip,
              "e911_status": s.e911_status}
             for s in (await db.execute(select(Site).where(Site.tenant_id == tenant_id))).scalars().all()]
    devices = [{"device_id": d.device_id, "site_id": d.site_id, "model": d.model,
                "device_type": d.device_type, "msisdn": d.msisdn}
               for d in (await db.execute(select(Device).where(Device.tenant_id == tenant_id))).scalars().all()]
    units = [{"unit_id": u.unit_id, "site_id": u.site_id, "unit_type": u.unit_type,
              "device_id": u.device_id, "line_id": u.line_id}
             for u in (await db.execute(select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all()]
    lines = [{"line_id": ln.line_id, "site_id": ln.site_id, "did": ln.did}
             for ln in (await db.execute(select(Line).where(Line.tenant_id == tenant_id))).scalars().all()]
    return {"tenant": tenant_id, "sites": sites, "devices": devices, "units": units, "lines": lines}


def resolve_fields(module: str, fields: str | None) -> str | None:
    """Explicit --fields wins; else the safe default set for Accounts; else None
    (let Zoho return its module default)."""
    if fields:
        return fields
    if (module or "").strip().lower() == "accounts":
        return DEFAULT_ACCOUNT_FIELDS
    return None


async def fetch_zoho(module: str, fields: str | None = None) -> list[dict]:
    """READ-ONLY: pull RH locations from Zoho via the existing integration,
    requesting the resolved ``fields`` set."""
    from app.services import zoho_crm
    resolved = resolve_fields(module, fields)
    return [map_zoho_location(r) for r in await zoho_crm.fetch_records(module, fields=resolved)]


# ── output ───────────────────────────────────────────────────────────
def write_csv(path: str, findings: list[dict]) -> None:
    cols = ["kind", "severity", "zoho_id", "zoho_name", "site_id", "site_name", "detail"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in findings:
            w.writerow({c: row.get(c, "") for c in cols})


def write_json(path: str, report: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)


def _findings_by_kinds(findings, kinds):
    return [f for f in findings if f["kind"] in kinds]


def write_markdown_report(path: str, report: dict) -> None:
    """A/B/C/D operator sync report (Task 7).  Read-only summary of the findings —
    recommends corrections but changes nothing."""
    s, findings, matched = report["summary"], report["findings"], report.get("matched", [])
    L = []
    L.append(f"# RH ↔ Zoho sync report — {s['tenant']}")
    L.append("")
    L.append("> READ-ONLY reconciliation. Nothing was written to Zoho or True911. "
             "E911 is never auto-verified.")
    L.append("")
    L.append(f"- True911 sites: **{s['true911_sites']}** · devices: {s['true911_devices']} "
             f"· service units: {s['true911_service_units']}")
    L.append(f"- Zoho locations: **{s['zoho_locations']}**")
    L.append(f"- Matched: **{s['matched']}** · Inconsistencies: **{s['inconsistencies']}** "
             f"· Needs investigation: **{s['needs_investigation']}**")
    L.append("")

    L.append("## A. Matched locations")
    if not matched:
        L.append("_None matched._")
    else:
        L.append("| True911 site | Zoho name | Address | City/State/Zip | Devices | Units | E911 | Confidence |")
        L.append("|---|---|---|---|--:|--:|---|---|")
        for m in matched:
            L.append(f"| {m['site_name']} | {m['zoho_name']} | {m.get('address') or '—'} | "
                     f"{m.get('city') or ''}/{m.get('state') or ''}/{m.get('zip') or ''} | "
                     f"{m['devices']} | {m['service_units']} | {m.get('e911_status') or '—'} | {m['confidence']} |")
    L.append("")

    def _section(title, kinds):
        L.append(title)
        rows = _findings_by_kinds(findings, kinds)
        if not rows:
            L.append("_None._")
        else:
            L.append("| Kind | Site | Zoho | Detail |")
            L.append("|---|---|---|---|")
            for f in rows:
                L.append(f"| {f['kind']} | {f.get('site_name') or f.get('site_id') or '—'} | "
                         f"{f.get('zoho_name') or '—'} | {f['detail']} |")
        L.append("")

    _section("## B. Inconsistencies", INCONSISTENCY_KINDS)
    _section("## C. Needs investigation", INVESTIGATION_KINDS)

    L.append("## D. True911 sync punch list")
    kinds_present = [k for k in PUNCH_LIST if s["by_kind"].get(k)]
    if not kinds_present:
        L.append("_No issues — nothing to correct._")
    else:
        L.append("| Issue | Count | Recommended correction | Source of truth | Safe to auto-fix later | Operator review required |")
        L.append("|---|--:|---|---|:--:|:--:|")
        for k in kinds_present:
            corr, sot, auto, review = PUNCH_LIST[k]
            L.append(f"| {k} | {s['by_kind'][k]} | {corr} | {sot} | "
                     f"{'yes' if auto else 'no'} | {'yes' if review else 'no'} |")
    L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _print_summary(report: dict, csv_path: str, json_path: str) -> None:
    s = report["summary"]
    print("=" * 70)
    print(f"RH ↔ Zoho reconciliation — READ-ONLY   (tenant: {s['tenant']})")
    print("=" * 70)
    print(f"  True911: sites={s['true911_sites']} devices={s['true911_devices']} "
          f"service_units={s['true911_service_units']}   Zoho locations={s['zoho_locations']}")
    print(f"  Findings: {s['findings_total']}")
    for kind, n in sorted(s["by_kind"].items(), key=lambda kv: -kv[1]):
        print(f"    {n:>4} × {kind}")
    print(f"\n  CSV : {csv_path}\n  JSON: {json_path}")
    print("  (Read-only — wrote nothing to True911 or Zoho.)")


async def _run(tenant: str, module: str, fields: str | None) -> dict:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        true911 = await load_true911(db, tenant)
    zoho = await fetch_zoho(module, fields)
    return reconcile(true911, zoho)


def main() -> None:
    ap = argparse.ArgumentParser(description="RH ↔ Zoho reconciliation (read-only).")
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--module", default="Accounts", help="Zoho CRM module holding RH locations")
    ap.add_argument("--fields", default=None,
                    help="comma-separated Zoho field list (overrides the safe Accounts default)")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--json", default=DEFAULT_JSON)
    ap.add_argument("--report", default=DEFAULT_REPORT, help="Markdown sync report path")
    args = ap.parse_args()

    try:
        report = asyncio.run(_run(args.tenant, args.module, args.fields))
    except Exception as exc:  # connectivity / Zoho-not-configured edge
        print(f"ERROR: cannot reconcile — {type(exc).__name__}: {exc}")
        raise SystemExit(2)

    write_csv(args.csv, report["findings"])
    write_json(args.json, report)
    write_markdown_report(args.report, report)
    _print_summary(report, args.csv, args.json)
    print(f"  MD  : {args.report}")
    raise SystemExit(1 if report["summary"]["findings_total"] else 0)


if __name__ == "__main__":
    main()
