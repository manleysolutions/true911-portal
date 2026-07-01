"""RH Portfolio Certification Wizard — Zoho export ↔ True911 (READ-ONLY).

Guarantees that every Restoration Hardware / RH-related **location, subscription,
line, and device** in a Zoho subscription export is represented correctly in
**True911** *before Judy receives her invite*.  It parses the uploaded Zoho CSV,
normalizes every RH row into a canonical portfolio record, reads True911
production (sites / devices / service units / lines / E911), matches the two
sides, classifies every result (A–L), and produces an executive certification
report with a go-live verdict (PASS / CONDITIONAL / BLOCKED) plus an operator
punch list.

Two READ-ONLY sources (exactly one required):
  * ``--zoho-csv <path>`` — an offline Zoho subscription CSV export.
  * ``--zoho-live``       — fetch RH records live from Zoho CRM, reusing the
    EXISTING authenticated client (``zoho_crm.fetch_records`` — same OAuth token
    refresh + pagination; no duplicated auth logic).  ``--module`` (default
    ``Accounts``) + ``--fields`` select what is read.

Strictly READ-ONLY:
  * True911 side — only SELECTs; never writes sites/devices/units/lines/E911.
  * Zoho side — reads the CSV export OR the authenticated Zoho GET layer ONLY;
    never writes Zoho.
  * E911 is NEVER marked verified; missing data is NEVER fabricated.
  * ``--csv`` / ``--json`` / ``--report`` write operator-requested report
    artifacts only (never a production-data change).

Usage (on Render, against production):
    # offline CSV mode
    python -m scripts.rh_portfolio_certification \
        --tenant restoration-hardware \
        --zoho-csv /path/to/Subscription_Mgmnt_2026_07_01.csv \
        --csv /tmp/rh_portfolio_certification.csv \
        --json /tmp/rh_portfolio_certification.json \
        --report /tmp/rh_portfolio_certification.md
    # live Zoho mode (reuses the existing OAuth client + pagination)
    python -m scripts.rh_portfolio_certification \
        --tenant restoration-hardware --zoho-live --module Accounts \
        --report /tmp/rh_portfolio_certification.md

Exit codes: 0 PASS · 1 CONDITIONAL · 2 BLOCKED · 3 error (CSV unreadable / Zoho not configured).
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
DEFAULT_CSV = "/tmp/rh_portfolio_certification.csv"
DEFAULT_JSON = "/tmp/rh_portfolio_certification.json"
DEFAULT_REPORT = "/tmp/rh_portfolio_certification.md"
VERIFIED_E911 = frozenset({"validated", "verified", "confirmed"})

# ── Zoho export column names (tolerant lookup handled in map_zoho_row) ──
Z_ACCOUNT = "Account Name"
Z_FACILITY = "FacilityName"
Z_SUBSCRIPTION = "Subscription Mgmnt Name"
Z_STREET = "FacilityAddress"
Z_CITY = "FacilityCity"
Z_STATE = "FacilityState"
Z_ZIP = "FacilityZipCode"
Z_FTYPE = "Facility Type"
Z_ACTIVATION = "Device Activation Status"
Z_MSISDN = "Mobile Number - MSISDN"
Z_EMERGENCY = "Emergency Line"
Z_CONNECTION = "Connection Type"
Z_IMEI = "Device IMEI"
Z_SIM = "SIM Number"
Z_STARLINK = "Starlink ID"

# US + territories (state codes we treat as domestic for E911 expectations).
US_STATES = frozenset("""AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD
MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY
DC PR VI GU AS MP""".split())

# ── Classification buckets (Task 7: A–L) ─────────────────────────────
CLASS_MATCHED = "A_matched"
CLASS_POSSIBLE = "B_possible_match_needs_review"
CLASS_MISSING_T911 = "C_missing_in_true911"
CLASS_MISSING_ZOHO = "D_missing_in_zoho"
CLASS_DUP_ZOHO = "E_duplicate_zoho_records"
CLASS_DUP_T911 = "F_duplicate_true911_sites"
CLASS_ADDR_MISMATCH = "G_address_mismatch"
CLASS_PHONE_MISMATCH = "H_phone_callback_mismatch"
CLASS_DEVICE_MISMATCH = "I_device_mismatch"
CLASS_MISSING_UNIT = "J_missing_service_unit"
CLASS_E911_UNVERIFIED = "K_e911_unverified"
CLASS_WEIRD_LABEL = "L_weird_rh_label_review"

CLASS_TITLES = {
    CLASS_MATCHED: "A. Matched",
    CLASS_POSSIBLE: "B. Possible match / needs review",
    CLASS_MISSING_T911: "C. Missing in True911",
    CLASS_MISSING_ZOHO: "D. Missing in Zoho",
    CLASS_DUP_ZOHO: "E. Duplicate Zoho records",
    CLASS_DUP_T911: "F. Duplicate True911 sites",
    CLASS_ADDR_MISMATCH: "G. Address mismatch",
    CLASS_PHONE_MISMATCH: "H. Phone / callback mismatch",
    CLASS_DEVICE_MISMATCH: "I. Device mismatch",
    CLASS_MISSING_UNIT: "J. Missing service unit",
    CLASS_E911_UNVERIFIED: "K. E911 unverified",
    CLASS_WEIRD_LABEL: "L. Weird RH label requiring review",
}

# Punch-list guidance per class: (recommended operator action, safe-to-auto-fix,
# operator-review-required).  Conservative — the script fixes nothing.
PUNCH_LIST = {
    CLASS_MISSING_T911: ("Create the True911 site for this canonical RH location", False, True),
    CLASS_MISSING_ZOHO: ("Confirm the True911 site in Zoho; mark non-customer/special if not RH-billable", False, True),
    CLASS_DUP_ZOHO: ("Review the duplicate Zoho records; collapse to one canonical location", False, True),
    CLASS_DUP_T911: ("Review / de-duplicate the True911 sites", False, True),
    CLASS_ADDR_MISMATCH: ("Reconcile the address; correct whichever record is wrong (verify with site)", False, True),
    CLASS_PHONE_MISMATCH: ("Attach / correct the callback number on the True911 line or device", False, True),
    CLASS_DEVICE_MISMATCH: ("Attach the device(s) (IMEI / SIM / Starlink) to the True911 site", False, True),
    CLASS_MISSING_UNIT: ("Create the Life-Safety service unit(s) for this location", False, True),
    CLASS_E911_UNVERIFIED: ("Verify the E911 record via the controlled operator flow (never auto-verified)", False, True),
    CLASS_WEIRD_LABEL: ("Manual review: confirm this is a real RH location or a special/non-customer record", False, True),
    CLASS_POSSIBLE: ("Manually confirm the match (single weak signal)", False, True),
}

# Which classes BLOCK go-live vs. merely warn (CONDITIONAL).
BLOCKING_CLASSES = frozenset({CLASS_MISSING_T911, CLASS_DUP_T911, CLASS_DEVICE_MISMATCH,
                              CLASS_MISSING_UNIT, CLASS_E911_UNVERIFIED})
CONDITIONAL_CLASSES = frozenset({CLASS_POSSIBLE, CLASS_MISSING_ZOHO, CLASS_DUP_ZOHO,
                                 CLASS_ADDR_MISMATCH, CLASS_PHONE_MISMATCH, CLASS_WEIRD_LABEL})


# ══════════════════════════════════════════════════════════════════════
# Pure normalization (unit-tested; no DB, no Zoho, no I/O)
# ══════════════════════════════════════════════════════════════════════
def norm_name(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def norm_addr(street, city, state) -> str:
    return norm_name(f"{street or ''} {city or ''} {state or ''}")


def norm_phone(s) -> str:
    digits = re.sub(r"\D", "", str(s or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def is_rh_label(*labels) -> bool:
    """True when any label looks Restoration-Hardware-related (incl. aliases)."""
    blob = " ".join((x or "") for x in labels).lower()
    if "restoration hardware" in blob or "restoration hdwr" in blob:
        return True
    # operator-confirmed known special location (e.g. a bare "MDC" / "RHNYC")
    if match_known_location(blob):
        return True
    # standalone RH token or an RH### / RH- store code
    return bool(re.search(r"\brh\b", blob) or re.search(r"\brh[#\-\s]?\d", blob))


def extract_store_number(name) -> str | None:
    """Store number from an RH label.  Numeric (#177 / # 177 / -150 / #001) is
    returned without leading zeros; an alpha store code (#RHNYC) is returned
    upper-cased.  Ambiguous / address-like numbers return None (manual review)."""
    n = name or ""
    m = re.search(r"#\s*0*(\d{1,4})\b", n)
    if m:
        return m.group(1)
    m = re.search(r"(?:hardware|hdwr)\s*[-–]\s*0*(\d{2,4})\b", n, re.I)
    if m:
        return m.group(1)
    m = re.search(r"#\s*(RH[A-Z0-9]+)\b", n, re.I)
    if m:
        return m.group(1).upper()
    return None


def detect_site_type(name) -> str:
    """Coarse RH location type from the label.  'store' is the default; the rest
    are context an operator should confirm."""
    b = (name or "").lower()
    if "guest" in b:
        return "guest_house"
    if "warehouse" in b:
        return "warehouse"
    if "outlet" in b:
        return "outlet"
    if "gallery" in b:
        return "gallery"
    if re.search(r"\bmdc\b", b) or "distribution" in b:
        return "distribution_center"
    if "main account" in b or "corporate" in b:
        return "corporate"
    if any(w in b for w in ("house", "modern", "grocery", "pier")):
        return "special"
    return "store"


# ══════════════════════════════════════════════════════════════════════
# Known RH special-location registry (operator-confirmed 2026-07-01).
#
# These labels are LEGITIMATE RH customer locations — they were previously flagged
# as "weird RH label" only because they lack a numeric store number.  The operator
# has confirmed each one, so we canonicalize them, give them a definitive
# ``site_type``, count them as real RH locations, and DO NOT flag them L.  They are
# still checked for missing-in-True911 / address / duplicate / device / service
# unit / E911 exactly like every other location.
#
# ``match`` tokens are matched against a NORMALIZED name (lowercase, alphanumeric).
# ``code`` is an optional alpha store code.  ``city``/``state`` are context for
# reporting/disambiguation only — never injected into the E911 address.
# ══════════════════════════════════════════════════════════════════════
KNOWN_RH_LOCATIONS = (
    {"alias": "Greenwich 265", "match": ("greenwich 265",),
     "canonical_name": "RH Greenwich (265)", "site_type": "special",
     "code": None, "city": "Greenwich", "state": "CT"},
    {"alias": "RHNYC", "match": ("rhnyc",),
     "canonical_name": "RH NYC Gallery", "site_type": "gallery",
     "code": "RHNYC", "city": "New York", "state": "NY"},
    {"alias": "Beverly Modern", "match": ("beverly modern",),
     "canonical_name": "RH Beverly Modern", "site_type": "special",
     "code": None, "city": None, "state": None},
    {"alias": "Patterson Warehouse", "match": ("patterson warehouse",),
     "canonical_name": "RH Patterson Warehouse", "site_type": "warehouse",
     "code": None, "city": None, "state": None},
    {"alias": "MDC", "match": ("mdc",),
     "canonical_name": "RH MDC (Distribution Center)", "site_type": "distribution_center",
     "code": None, "city": None, "state": None},
    {"alias": "Linden House", "match": ("linden house",),
     "canonical_name": "RH Linden House", "site_type": "special",
     "code": None, "city": None, "state": None},
)


def match_known_location(name) -> dict | None:
    """Return the known-RH-location registry entry whose alias token(s) appear in
    ``name`` (operator-confirmed legitimate special locations), else None.  Short
    codes (e.g. ``mdc``) are matched as whole normalized-name tokens to avoid
    substring false positives; multi-word aliases match as a phrase."""
    n = norm_name(name)
    if not n:
        return None
    tokens = set(n.split())
    for entry in KNOWN_RH_LOCATIONS:
        for tok in entry["match"]:
            if " " in tok:
                if tok in n:
                    return entry
            elif tok in tokens:
                return entry
    return None


def _pick(rec: dict, *keys):
    """First non-empty scalar value among ``keys`` (ignores dict/list Zoho lookups)."""
    for k in keys:
        v = rec.get(k)
        if v in (None, "") or isinstance(v, (dict, list)):
            continue
        return str(v).strip()
    return None


def _build_record(*, account, facility, street, city, state, zip_, facility_type,
                  activation, msisdn, emergency, connection, imei, sim, starlink) -> dict:
    """Assemble the canonical normalized row shared by CSV and live-Zoho sources."""
    return {
        "raw_zoho_name": account or facility,
        "account_name": account,
        "facility_name": facility,
        "street": street,
        "city": city,
        "state": (state or "").upper() or None,
        "zip": zip_,
        "facility_type": facility_type,
        "activation_status": activation,
        "msisdn": norm_phone(msisdn) or None,
        "emergency_line": str(emergency or "").strip().lower() == "true",
        "connection_type": connection,
        "imei": imei,
        "sim": sim,
        "starlink_id": starlink,
    }


def map_zoho_row(row: dict) -> dict:
    """Map one raw Zoho CSV export row to a normalized device/subscription record."""
    def g(*keys):
        return _pick(row, *keys)

    return _build_record(
        account=g(Z_ACCOUNT), facility=g(Z_FACILITY),
        street=g(Z_STREET), city=g(Z_CITY), state=g(Z_STATE), zip_=g(Z_ZIP),
        facility_type=g(Z_FTYPE), activation=g(Z_ACTIVATION), msisdn=g(Z_MSISDN),
        emergency=g(Z_EMERGENCY), connection=g(Z_CONNECTION),
        imei=g(Z_IMEI), sim=g(Z_SIM), starlink=g(Z_STARLINK))


def map_zoho_api_record(rec: dict) -> dict:
    """Map one live Zoho CRM API record to the SAME normalized shape as
    ``map_zoho_row``.  Tolerant of Zoho field API-name variants (Accounts billing/
    shipping fields, or a subscription module's device fields) so the downstream
    pipeline is identical whether the source is a CSV or the live API."""
    def g(*keys):
        return _pick(rec, *keys)

    return _build_record(
        account=g("Account_Name", "Account Name", "Name", "Store_Name", "Location_Name",
                  "Subscription_Mgmnt_Name", Z_FACILITY),
        facility=g(Z_FACILITY, "Facility_Name"),
        street=g(Z_STREET, "Facility_Address", "Billing_Street", "Shipping_Street", "Street", "Address"),
        city=g(Z_CITY, "Facility_City", "Billing_City", "Shipping_City", "City"),
        state=g(Z_STATE, "Facility_State", "Billing_State", "Shipping_State", "State"),
        zip_=g(Z_ZIP, "Facility_Zip_Code", "Billing_Code", "Shipping_Code", "Zip", "Zip_Code"),
        facility_type=g(Z_FTYPE, "Facility_Type"),
        activation=g(Z_ACTIVATION, "Device_Activation_Status"),
        msisdn=g(Z_MSISDN, "Mobile_Number_MSISDN", "MSISDN", "Phone", "Callback_Number"),
        emergency=g(Z_EMERGENCY, "Emergency_Line"),
        connection=g(Z_CONNECTION, "Connection_Type"),
        imei=g(Z_IMEI, "Device_IMEI", "IMEI"),
        sim=g(Z_SIM, "SIM_Number", "ICCID"),
        starlink=g(Z_STARLINK, "Starlink_ID"))


def canonical_key(name, store_number) -> tuple:
    """Stable grouping key: numeric store # → num; alpha code → code; else name."""
    if store_number and store_number.isdigit():
        return ("num", store_number)
    if store_number:
        return ("code", store_number)
    return ("name", norm_name(name))


def confidence_score(store_number, street, city, state, zip_, has_phone, has_device,
                     known_alias=False) -> int:
    """0–100 quality of a canonical Zoho record's identity (not a match score)."""
    score = 0
    if store_number and store_number.isdigit():
        score += 30
    if known_alias:
        score += 15                       # operator-confirmed known location
    if all([street, city, state, zip_]):
        score += 30
    elif any([street, city, state, zip_]):
        score += 10
    if has_phone:
        score += 20
    if has_device:
        score += 20
    return min(score, 100)


def build_canonical_locations(zoho_rows: list[dict]) -> list[dict]:
    """Collapse RH device/subscription rows into canonical portfolio locations.
    Each canonical location aggregates its device lines and carries a confidence
    score + manual_review_required flag."""
    groups: dict = defaultdict(list)
    for r in zoho_rows:
        name = r["account_name"] or r["facility_name"]
        key = canonical_key(name, extract_store_number(name))
        groups[key].append(r)

    canon = []
    for key, rows in groups.items():
        first = rows[0]
        name = first["account_name"] or first["facility_name"]
        store_number = extract_store_number(name)
        site_type = detect_site_type(name)
        # prefer the first row that actually carries an address
        addr_row = next((r for r in rows if r.get("street")), first)

        # Known operator-confirmed special location? -> legitimate; use its
        # definitive site_type / canonical name / code, and never flag it "weird".
        known = match_known_location(name)
        known_alias = bool(known)
        known_tokens = list(known["match"]) if known else []
        if known:
            site_type = known["site_type"]
            if known.get("code") and not (store_number and store_number.isdigit()):
                store_number = known["code"]

        devices = [{
            "imei": r.get("imei"), "sim": r.get("sim"), "starlink_id": r.get("starlink_id"),
            "msisdn": r.get("msisdn"), "connection_type": r.get("connection_type"),
            "emergency_line": r.get("emergency_line"), "activation_status": r.get("activation_status"),
        } for r in rows]
        phones = sorted({r["msisdn"] for r in rows if r.get("msisdn")})
        device_ids = sorted({v for r in rows for v in (r.get("imei"), r.get("sim"), r.get("starlink_id")) if v})
        state = addr_row.get("state")
        non_us = bool(state) and state not in US_STATES
        conf = confidence_score(store_number, addr_row.get("street"), addr_row.get("city"),
                                state, addr_row.get("zip"), bool(phones), bool(device_ids),
                                known_alias=known_alias)
        # A known location is legitimate by operator confirmation — it is NOT weird.
        # Everything else keeps the original manual-review heuristics.
        if known:
            manual = False
        else:
            manual = (
                store_number is None
                or not store_number.isdigit()
                or site_type in ("guest_house", "warehouse", "outlet", "distribution_center",
                                 "corporate", "special")
                or non_us
                or not all([addr_row.get("street"), addr_row.get("city"), state, addr_row.get("zip")])
            )
        canonical_name = known["canonical_name"] if known else _canonical_name(
            name, store_number, addr_row.get("city"))
        canon.append({
            "key": list(key),
            "canonical_location_name": canonical_name,
            "raw_zoho_name": name,
            "raw_zoho_names": sorted({(r["account_name"] or r["facility_name"] or "") for r in rows}),
            "store_number": store_number,
            "site_type": site_type,
            "known_alias": known_alias,
            "known_alias_label": known["alias"] if known else None,
            "known_tokens": known_tokens,
            "street": addr_row.get("street"), "city": addr_row.get("city"),
            "state": state, "zip": addr_row.get("zip"),
            "non_us": non_us,
            "phones": phones, "device_ids": device_ids,
            "device_count": len(devices), "devices": devices,
            "connection_types": sorted({r["connection_type"] for r in rows if r.get("connection_type")}),
            "confidence": conf, "manual_review_required": manual,
        })
    return sorted(canon, key=lambda c: (c["store_number"] or "zzz", c["raw_zoho_name"] or ""))


def _canonical_name(name, store_number, city) -> str:
    if store_number and store_number.isdigit():
        return f"RH #{store_number}" + (f" {city}" if city else "")
    return (name or "").strip() or "RH (unnamed)"


# ══════════════════════════════════════════════════════════════════════
# Pure matching + classification (unit-tested; no DB)
# ══════════════════════════════════════════════════════════════════════
def _site_indexes(true911: dict):
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

    site_phones = defaultdict(set)
    site_device_ids = defaultdict(set)
    for d in devices:
        for p in (norm_phone(d.get("msisdn")),):
            if p:
                site_phones[d.get("site_id")].add(p)
        for v in (d.get("imei"), d.get("iccid"), d.get("starlink_id"), d.get("serial_number")):
            if v:
                site_device_ids[d.get("site_id")].add(str(v).strip())
    for ln in lines:
        p = norm_phone(ln.get("did"))
        if p:
            site_phones[ln.get("site_id")].add(p)
    return sites, by_site_devices, by_site_units, site_phones, site_device_ids


def match_site(canon: dict, sites, site_phones, site_device_ids) -> list[dict]:
    """All True911 sites matching a canonical Zoho location, with the signals hit.
    ``known`` = an operator-confirmed alias appears in the True911 site name — a
    high-precision positive signal (e.g. "MDC", "Patterson Warehouse", "RHNYC")."""
    ca = norm_addr(canon.get("street"), canon.get("city"), canon.get("state"))
    cstore = canon.get("store_number")
    known_tokens = canon.get("known_tokens") or []
    out = []
    for s in sites:
        sid = s.get("site_id")
        raw_blob = f"{s.get('name') or ''} {sid or ''}"
        norm_blob = norm_name(raw_blob)
        # store signal: numeric store numbers only (alpha codes go via ``known``)
        sig_store = bool(cstore) and cstore.isdigit() and bool(
            re.search(rf"#?\s*0*{re.escape(cstore)}\b", raw_blob))
        sig_addr = bool(ca) and ca == norm_addr(s.get("street"), s.get("city"), s.get("state"))
        sig_name = _name_match(canon.get("raw_zoho_name"), s.get("name"))
        sig_phone = bool(set(canon.get("phones", [])) & site_phones.get(sid, set()))
        sig_device = bool(set(canon.get("device_ids", [])) & site_device_ids.get(sid, set()))
        sig_known = any(
            (tok in norm_blob if " " in tok else tok in set(norm_blob.split()))
            for tok in known_tokens)
        signals = {"store": sig_store, "addr": sig_addr, "name": sig_name,
                   "phone": sig_phone, "device": sig_device, "known": sig_known}
        if any(signals.values()):
            out.append({"site": s, "signals": signals, "score": sum(signals.values())})
    return sorted(out, key=lambda m: -m["score"])


# Generic RH tokens carry no matching information on their own — a name match must
# rest on the DISTINCTIVE part (store #, city, alias), never on "Restoration Hardware".
_GENERIC_RH_TOKENS = frozenset({"restoration", "hardware", "hdwr", "rh"})


def _distinctive_tokens(name) -> set:
    return set(norm_name(name).split()) - _GENERIC_RH_TOKENS


def _name_match(a, b) -> bool:
    """Match on shared DISTINCTIVE tokens (generic "Restoration Hardware" stripped).
    A single shared token counts only when it is specific — a numeric store number
    or a long token (>=5 chars) — so a bare 3-letter city like "nyc" alone does not
    force a match (avoids RHNYC ↔ generic-NYC confusion)."""
    shared = _distinctive_tokens(a) & _distinctive_tokens(b)
    if not shared:
        return False
    if len(shared) >= 2:
        return True
    tok = next(iter(shared))
    return tok.isdigit() or len(tok) >= 5


def certify(true911: dict, canon_locations: list[dict]) -> dict:
    """Cross-certify canonical Zoho RH locations against True911.  Returns
    per-location classification (A–L), findings, and summary counts."""
    sites, by_site_devices, by_site_units, site_phones, site_device_ids = _site_indexes(true911)
    findings = []
    matched_site_ids = set()
    results = []

    def add(cls, **kw):
        findings.append({"class": cls, "canonical": kw.get("canonical", ""),
                         "store_number": kw.get("store_number", ""),
                         "site_id": kw.get("site_id", ""), "site_name": kw.get("site_name", ""),
                         "detail": kw.get("detail", "")})

    # ── E. duplicate Zoho records (two canonicals, same full address) ──
    addr_index = defaultdict(list)
    for c in canon_locations:
        a = norm_addr(c.get("street"), c.get("city"), c.get("state"))
        if a:
            addr_index[a].append(c)
    dup_zoho_keys = set()
    for a, group in addr_index.items():
        if len(group) > 1:
            for c in group:
                dup_zoho_keys.add(tuple(c["key"]))
            add(CLASS_DUP_ZOHO, canonical=" / ".join(c["canonical_location_name"] for c in group),
                detail="Multiple Zoho canonical records share address: " + a)

    # ── Zoho → True911 per canonical location ──
    for c in canon_locations:
        matches = match_site(c, sites, site_phones, site_device_ids)
        classes = []
        if tuple(c["key"]) in dup_zoho_keys:
            classes.append(CLASS_DUP_ZOHO)
        if c["manual_review_required"]:
            classes.append(CLASS_WEIRD_LABEL)
            add(CLASS_WEIRD_LABEL, canonical=c["canonical_location_name"],
                store_number=c["store_number"] or "",
                detail=f"Manual review: type={c['site_type']}, store#={c['store_number']}, "
                       f"non_us={c['non_us']}, confidence={c['confidence']}")

        if not matches:
            classes.append(CLASS_MISSING_T911)
            add(CLASS_MISSING_T911, canonical=c["canonical_location_name"],
                store_number=c["store_number"] or "",
                detail="No True911 site matches this canonical RH location")
            results.append({**_result_row(c), "classes": classes, "match_site_id": None})
            continue

        if len(matches) > 1:
            classes.append(CLASS_DUP_T911)
            add(CLASS_DUP_T911, canonical=c["canonical_location_name"],
                detail="Ambiguously matches %d True911 sites: %s"
                       % (len(matches), ", ".join(m["site"].get("site_id") for m in matches)))

        best = matches[0]
        s = best["site"]
        sid = s.get("site_id")
        matched_site_ids.add(sid)
        # A recognized known-alias hit is high-precision -> counts as a strong match;
        # otherwise require >=2 independent signals.
        strong = best["score"] >= 2 or bool(best["signals"].get("known"))
        classes.append(CLASS_MATCHED if strong else CLASS_POSSIBLE)
        if not strong:
            add(CLASS_POSSIBLE, canonical=c["canonical_location_name"], site_id=sid,
                site_name=s.get("name"),
                detail="Single weak signal: " + ",".join(k for k, v in best["signals"].items() if v))

        # G. address mismatch
        ca = norm_addr(c.get("street"), c.get("city"), c.get("state"))
        sa = norm_addr(s.get("street"), s.get("city"), s.get("state"))
        if ca and sa and ca != sa:
            classes.append(CLASS_ADDR_MISMATCH)
            add(CLASS_ADDR_MISMATCH, canonical=c["canonical_location_name"], site_id=sid,
                site_name=s.get("name"),
                detail=f"Zoho='{c.get('street')}, {c.get('city')}, {c.get('state')}' vs "
                       f"True911='{s.get('street')}, {s.get('city')}, {s.get('state')}'")
        # H. phone / callback mismatch
        if c.get("phones") and not (set(c["phones"]) & site_phones.get(sid, set())):
            classes.append(CLASS_PHONE_MISMATCH)
            add(CLASS_PHONE_MISMATCH, canonical=c["canonical_location_name"], site_id=sid,
                site_name=s.get("name"),
                detail="Zoho phone(s) %s not present on the True911 site" % ", ".join(c["phones"]))
        # I. device mismatch
        if c.get("device_ids") and not (set(c["device_ids"]) & site_device_ids.get(sid, set())):
            classes.append(CLASS_DEVICE_MISMATCH)
            add(CLASS_DEVICE_MISMATCH, canonical=c["canonical_location_name"], site_id=sid,
                site_name=s.get("name"),
                detail="Zoho device id(s) not found on the site: " + ", ".join(c["device_ids"][:4]))
        # J. missing service unit
        if not by_site_units.get(sid):
            classes.append(CLASS_MISSING_UNIT)
            add(CLASS_MISSING_UNIT, canonical=c["canonical_location_name"], site_id=sid,
                site_name=s.get("name"), detail="Matched site has no Life-Safety service unit")
        # K. E911 unverified
        if (s.get("e911_status") or "").strip().lower() not in VERIFIED_E911:
            classes.append(CLASS_E911_UNVERIFIED)
            add(CLASS_E911_UNVERIFIED, canonical=c["canonical_location_name"], site_id=sid,
                site_name=s.get("name"),
                detail=f"E911 status = {s.get('e911_status')!r} (not verified)")

        results.append({**_result_row(c), "classes": classes, "match_site_id": sid,
                        "match_site_name": s.get("name"), "match_score": best["score"],
                        "match_signals": [k for k, v in best["signals"].items() if v],
                        "site_devices": len(by_site_devices.get(sid, [])),
                        "site_units": len(by_site_units.get(sid, [])),
                        "site_e911_status": s.get("e911_status")})

    # ── D. True911 RH sites missing from Zoho + F. duplicate True911 sites ──
    name_counts = Counter(norm_name(s.get("name")) for s in sites if norm_name(s.get("name")))
    for s in sites:
        sid = s.get("site_id")
        if sid not in matched_site_ids:
            add(CLASS_MISSING_ZOHO, site_id=sid, site_name=s.get("name"),
                detail="True911 site has no matching canonical Zoho RH location")
        if name_counts.get(norm_name(s.get("name")), 0) > 1:
            add(CLASS_DUP_T911, site_id=sid, site_name=s.get("name"),
                detail="Multiple True911 sites share this normalized name")

    by_class = Counter(f["class"] for f in findings)
    matched = sum(1 for r in results if CLASS_MATCHED in r["classes"])
    summary = {
        "tenant": true911.get("tenant"),
        "zoho_rows": true911.get("_zoho_rows", 0),
        "canonical_locations": len(canon_locations),
        "true911_sites": len(sites),
        "true911_devices": len(true911.get("devices", [])),
        "true911_service_units": len(true911.get("units", [])),
        "matched": matched,
        "possible": sum(1 for r in results if CLASS_POSSIBLE in r["classes"]),
        "missing_in_true911": by_class.get(CLASS_MISSING_T911, 0),
        "missing_in_zoho": by_class.get(CLASS_MISSING_ZOHO, 0),
        "duplicate_zoho": by_class.get(CLASS_DUP_ZOHO, 0),
        "duplicate_true911": by_class.get(CLASS_DUP_T911, 0),
        "address_mismatch": by_class.get(CLASS_ADDR_MISMATCH, 0),
        "phone_mismatch": by_class.get(CLASS_PHONE_MISMATCH, 0),
        "device_mismatch": by_class.get(CLASS_DEVICE_MISMATCH, 0),
        "missing_service_units": by_class.get(CLASS_MISSING_UNIT, 0),
        "e911_unverified": by_class.get(CLASS_E911_UNVERIFIED, 0),
        "weird_labels": by_class.get(CLASS_WEIRD_LABEL, 0),
        "manual_review": sum(1 for c in canon_locations if c["manual_review_required"]),
        "known_special_locations": sum(1 for c in canon_locations if c.get("known_alias")),
        "findings_total": len(findings),
        "by_class": dict(by_class),
    }
    summary["verdict"] = _verdict(summary, by_class)
    return {"summary": summary, "findings": findings, "results": results}


def _result_row(c: dict) -> dict:
    return {"canonical_location_name": c["canonical_location_name"], "raw_zoho_name": c["raw_zoho_name"],
            "store_number": c["store_number"], "site_type": c["site_type"],
            "known_alias": c.get("known_alias", False),
            "known_alias_label": c.get("known_alias_label"),
            "street": c["street"], "city": c["city"], "state": c["state"], "zip": c["zip"],
            "phones": c["phones"], "device_count": c["device_count"],
            "confidence": c["confidence"], "manual_review_required": c["manual_review_required"]}


def _match_status(classes: list) -> str:
    """Short human status for a canonical location from its assigned classes."""
    if CLASS_MATCHED in classes:
        return "Matched"
    if CLASS_POSSIBLE in classes:
        return "Possible"
    if CLASS_MISSING_T911 in classes:
        return "Missing in True911"
    return "Review"


def _verdict(summary: dict, by_class: Counter) -> str:
    """PASS only when nothing blocks and nothing needs review; CONDITIONAL when
    only soft issues remain; BLOCKED when a hard gate is tripped."""
    if any(by_class.get(k) for k in BLOCKING_CLASSES):
        return "BLOCKED"
    if any(by_class.get(k) for k in CONDITIONAL_CLASSES):
        return "CONDITIONAL"
    return "PASS"


# ══════════════════════════════════════════════════════════════════════
# Read-only loaders (run on Render against production)
# ══════════════════════════════════════════════════════════════════════
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
                "device_type": d.device_type, "msisdn": d.msisdn, "imei": d.imei,
                "iccid": d.iccid, "starlink_id": d.starlink_id, "serial_number": d.serial_number}
               for d in (await db.execute(select(Device).where(Device.tenant_id == tenant_id))).scalars().all()]
    units = [{"unit_id": u.unit_id, "site_id": u.site_id, "unit_type": u.unit_type,
              "device_id": u.device_id, "line_id": u.line_id}
             for u in (await db.execute(select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all()]
    lines = [{"line_id": ln.line_id, "site_id": ln.site_id, "did": ln.did}
             for ln in (await db.execute(select(Line).where(Line.tenant_id == tenant_id))).scalars().all()]
    return {"tenant": tenant_id, "sites": sites, "devices": devices, "units": units, "lines": lines}


def load_zoho_csv(path: str) -> tuple[list[dict], int]:
    """READ-ONLY parse of the operator-supplied Zoho export; keeps RH rows only.
    Returns (rh_rows, total_rows_scanned)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    rh = []
    for r in rows:
        if is_rh_label(r.get(Z_ACCOUNT), r.get(Z_FACILITY), r.get(Z_SUBSCRIPTION)):
            rh.append(map_zoho_row(r))
    return rh, len(rows)


# Safe default Zoho field set for the Accounts module (billing + shipping address +
# phone).  Zoho v5 requires an explicit field list for some modules; --fields
# overrides.  Non-Accounts modules pass None -> Zoho returns its default fields.
DEFAULT_ACCOUNT_FIELDS = (
    "Account_Name,Billing_Street,Billing_City,Billing_State,Billing_Code,"
    "Shipping_Street,Shipping_City,Shipping_State,Shipping_Code,Phone"
)


def resolve_fields(module: str, fields: str | None) -> str | None:
    """Explicit --fields wins; else the safe default set for Accounts; else None."""
    if fields:
        return fields
    if (module or "").strip().lower() == "accounts":
        return DEFAULT_ACCOUNT_FIELDS
    return None


async def load_zoho_live(module: str, fields: str | None) -> tuple[list[dict], int]:
    """READ-ONLY live fetch from Zoho CRM via the EXISTING authenticated client
    (``zoho_crm.fetch_records`` — reuses the OAuth token refresh + pagination).
    Never writes Zoho.  Keeps RH rows only; returns (rh_rows, total_records)."""
    from app.services import zoho_crm
    resolved = resolve_fields(module, fields)
    records = await zoho_crm.fetch_records(module, fields=resolved)
    rh = []
    for r in records:
        mapped = map_zoho_api_record(r)
        if is_rh_label(mapped.get("account_name"), mapped.get("facility_name")):
            rh.append(mapped)
    return rh, len(records)


# ══════════════════════════════════════════════════════════════════════
# Output artifacts
# ══════════════════════════════════════════════════════════════════════
def write_csv(path: str, findings: list[dict]) -> None:
    cols = ["class", "canonical", "store_number", "site_id", "site_name", "detail"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in findings:
            w.writerow({c: row.get(c, "") for c in cols})


def write_json(path: str, report: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)


def _top_issues(findings: list[dict], n: int = 25) -> list[dict]:
    order = {c: i for i, c in enumerate(
        [CLASS_MISSING_T911, CLASS_DUP_T911, CLASS_DEVICE_MISMATCH, CLASS_MISSING_UNIT,
         CLASS_E911_UNVERIFIED, CLASS_ADDR_MISMATCH, CLASS_PHONE_MISMATCH, CLASS_DUP_ZOHO,
         CLASS_MISSING_ZOHO, CLASS_WEIRD_LABEL, CLASS_POSSIBLE])}
    return sorted(findings, key=lambda f: order.get(f["class"], 99))[:n]


def write_markdown_report(path: str, report: dict) -> None:
    s, findings, results = report["summary"], report["findings"], report["results"]
    verdict = s["verdict"]
    badge = {"PASS": "✅ PASS", "CONDITIONAL": "🟡 CONDITIONAL", "BLOCKED": "⛔ BLOCKED"}[verdict]
    L = []
    L.append(f"# RH Portfolio Certification — {s['tenant']}")
    L.append("")
    L.append(f"## Go-live recommendation: {badge}")
    L.append("")
    L.append("> READ-ONLY certification. Nothing was written to Zoho or True911. "
             "E911 is never auto-verified; missing data is never fabricated.")
    L.append("")
    L.append("### Portfolio at a glance")
    L.append(f"- Total Zoho rows scanned: **{s['zoho_rows']}**")
    L.append(f"- Unique canonical RH locations: **{s['canonical_locations']}** "
             f"({s['manual_review']} need manual review)")
    L.append(f"- True911 sites (tenant): **{s['true911_sites']}** · devices: {s['true911_devices']} "
             f"· service units: {s['true911_service_units']}")
    L.append(f"- Matched: **{s['matched']}** · Possible: {s['possible']} "
             f"· Missing in True911: **{s['missing_in_true911']}** · Missing in Zoho: {s['missing_in_zoho']}")
    L.append(f"- Duplicate Zoho: {s['duplicate_zoho']} · Duplicate True911: {s['duplicate_true911']} "
             f"· Address mismatch: {s['address_mismatch']} · Phone mismatch: {s['phone_mismatch']} "
             f"· Device mismatch: {s['device_mismatch']}")
    L.append(f"- Missing service units: **{s['missing_service_units']}** · "
             f"E911 unverified: **{s['e911_unverified']}** · Weird labels: {s['weird_labels']}")
    L.append(f"- Known special RH locations (operator-confirmed): "
             f"**{s.get('known_special_locations', 0)}**")
    L.append("")

    L.append("### Why this verdict")
    if verdict == "BLOCKED":
        blk = [f"{CLASS_TITLES[k]} ({s['by_class'][k]})" for k in BLOCKING_CLASSES if s["by_class"].get(k)]
        L.append("Hard go-live gates are tripped — resolve before Judy's invite:")
        for b in blk:
            L.append(f"- {b}")
    elif verdict == "CONDITIONAL":
        L.append("No hard gates tripped, but soft issues remain — a human should review "
                 "before sending the invite.")
    else:
        L.append("Every canonical RH location is matched, populated (device + service unit), "
                 "E911-verified, with no duplicates or mismatches.")
    L.append("")

    # A. Matched
    L.append("## A. Matched locations")
    matched_rows = [r for r in results if CLASS_MATCHED in r["classes"]]
    if not matched_rows:
        L.append("_None matched._")
    else:
        L.append("| Canonical | Store # | Zoho name | Match site | Signals | Devices | Units | E911 |")
        L.append("|---|---|---|---|---|--:|--:|---|")
        for r in matched_rows:
            L.append(f"| {r['canonical_location_name']} | {r.get('store_number') or '—'} | "
                     f"{r['raw_zoho_name']} | {r.get('match_site_name') or r.get('match_site_id')} | "
                     f"{','.join(r.get('match_signals', []))} | {r.get('site_devices', '—')} | "
                     f"{r.get('site_units', '—')} | {r.get('site_e911_status') or '—'} |")
    L.append("")

    # Known special RH locations (operator-confirmed legitimate specials)
    L.append("## Known special RH locations")
    known_rows = [r for r in results if r.get("known_alias")]
    if not known_rows:
        L.append("_None in this portfolio._")
    else:
        L.append("> Operator-confirmed legitimate RH locations — counted as real, "
                 "not flagged as weird labels. Still checked for match / address / "
                 "device / service unit / E911.")
        L.append("")
        L.append("| Alias used | Canonical name | Site type | Match status | Confidence |")
        L.append("|---|---|---|---|--:|")
        for r in known_rows:
            L.append(f"| {r.get('known_alias_label') or r['raw_zoho_name']} | "
                     f"{r['canonical_location_name']} | {r.get('site_type') or '—'} | "
                     f"{_match_status(r['classes'])} | {r.get('confidence', '—')} |")
    L.append("")

    # Class sections C–L
    for cls in [CLASS_POSSIBLE, CLASS_MISSING_T911, CLASS_MISSING_ZOHO, CLASS_DUP_ZOHO,
                CLASS_DUP_T911, CLASS_ADDR_MISMATCH, CLASS_PHONE_MISMATCH, CLASS_DEVICE_MISMATCH,
                CLASS_MISSING_UNIT, CLASS_E911_UNVERIFIED, CLASS_WEIRD_LABEL]:
        rows = [f for f in findings if f["class"] == cls]
        L.append(f"## {CLASS_TITLES[cls]} ({len(rows)})")
        if not rows:
            L.append("_None._")
        else:
            L.append("| Canonical / Site | Store # | Detail |")
            L.append("|---|---|---|")
            for f in rows:
                who = f.get("canonical") or f.get("site_name") or f.get("site_id") or "—"
                L.append(f"| {who} | {f.get('store_number') or '—'} | {f['detail']} |")
        L.append("")

    # Top 25 issues
    L.append("## Top 25 issues")
    top = _top_issues(findings, 25)
    if not top:
        L.append("_No issues._")
    else:
        L.append("| # | Class | Where | Detail |")
        L.append("|--:|---|---|---|")
        for i, f in enumerate(top, 1):
            who = f.get("canonical") or f.get("site_name") or f.get("site_id") or "—"
            L.append(f"| {i} | {CLASS_TITLES[f['class']]} | {who} | {f['detail']} |")
    L.append("")

    # Operator punch list
    L.append("## Operator punch list")
    present = [k for k in PUNCH_LIST if s["by_class"].get(k)]
    if not present:
        L.append("_No issues — nothing to correct._")
    else:
        L.append("| Issue | Count | Recommended action | Safe to auto-fix | Operator review |")
        L.append("|---|--:|---|:--:|:--:|")
        for k in present:
            action, auto, review = PUNCH_LIST[k]
            L.append(f"| {CLASS_TITLES[k]} | {s['by_class'][k]} | {action} | "
                     f"{'yes' if auto else 'no'} | {'yes' if review else 'no'} |")
    L.append("")
    L.append("---")
    L.append("_Judy's invite remains BLOCKED until this certification reads PASS "
             "(or CONDITIONAL with explicit operator sign-off)._")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _print_summary(report: dict, paths: dict) -> None:
    s = report["summary"]
    print("=" * 72)
    print(f"RH Portfolio Certification — READ-ONLY   (tenant: {s['tenant']})")
    print("=" * 72)
    print(f"  Zoho rows: {s['zoho_rows']}   canonical RH locations: {s['canonical_locations']}"
          f"   True911 sites: {s['true911_sites']}")
    print(f"  Matched: {s['matched']}   Missing in True911: {s['missing_in_true911']}"
          f"   Missing units: {s['missing_service_units']}   E911 unverified: {s['e911_unverified']}")
    print(f"  Findings: {s['findings_total']}")
    for cls, n in sorted(s["by_class"].items(), key=lambda kv: -kv[1]):
        print(f"    {n:>4} × {cls}")
    print(f"\n  VERDICT: {s['verdict']}")
    print(f"  CSV : {paths['csv']}\n  JSON: {paths['json']}\n  MD  : {paths['report']}")
    print("  (Read-only — wrote nothing to True911 or Zoho; E911 never auto-verified.)")


async def _run(tenant: str, *, zoho_csv: str | None, zoho_live: bool,
               module: str, fields: str | None) -> dict:
    from app.database import AsyncSessionLocal
    if zoho_live:
        zoho_rows, total_rows = await load_zoho_live(module, fields)
    else:
        zoho_rows, total_rows = load_zoho_csv(zoho_csv)
    canon = build_canonical_locations(zoho_rows)
    async with AsyncSessionLocal() as db:
        true911 = await load_true911(db, tenant)
    true911["_zoho_rows"] = total_rows
    return certify(true911, canon)


def main() -> None:
    ap = argparse.ArgumentParser(description="RH Portfolio Certification Wizard (read-only).")
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--zoho-csv", default=None,
                    help="path to the Zoho subscription CSV export (offline mode)")
    ap.add_argument("--zoho-live", action="store_true",
                    help="fetch RH records live from Zoho CRM instead of a CSV")
    ap.add_argument("--module", default="Accounts",
                    help="Zoho CRM module to read in live mode (default: Accounts)")
    ap.add_argument("--fields", default=None,
                    help="comma-separated Zoho field list for live mode "
                         "(overrides the safe Accounts default)")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--json", default=DEFAULT_JSON)
    ap.add_argument("--report", default=DEFAULT_REPORT, help="Markdown certification report path")
    args = ap.parse_args()

    # Exactly one source: --zoho-live or --zoho-csv.
    if args.zoho_live and args.zoho_csv:
        ap.error("choose one source: --zoho-live OR --zoho-csv (not both)")
    if not args.zoho_live and not args.zoho_csv:
        ap.error("a source is required: --zoho-live OR --zoho-csv <path>")

    try:
        report = asyncio.run(_run(args.tenant, zoho_csv=args.zoho_csv, zoho_live=args.zoho_live,
                                  module=args.module, fields=args.fields))
    except FileNotFoundError as exc:
        print(f"ERROR: Zoho CSV not found — {exc}")
        raise SystemExit(3)
    except Exception as exc:  # DB connectivity / Zoho-not-configured edge
        print(f"ERROR: certification failed — {type(exc).__name__}: {exc}")
        raise SystemExit(3)

    paths = {"csv": args.csv, "json": args.json, "report": args.report}
    write_csv(args.csv, report["findings"])
    write_json(args.json, report)
    write_markdown_report(args.report, report)
    _print_summary(report, paths)
    raise SystemExit({"PASS": 0, "CONDITIONAL": 1, "BLOCKED": 2}[report["summary"]["verdict"]])


if __name__ == "__main__":
    main()
