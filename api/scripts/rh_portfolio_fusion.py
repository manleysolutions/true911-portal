"""True911 Portfolio Fusion Engine — multi-source Building Digital Twin (READ-ONLY).

Extends the RH Portfolio Certification Engine from a single Zoho↔True911 check into
a **Portfolio Fusion Engine** that fuses FOUR trusted sources into one canonical
Building record (a "Building Digital Twin"):

    1. Zoho CRM              (subscription / billing / location context)
    2. Napco StarLink        (alarm-radio inventory: RadioNumber / ICCID)
    3. T-Mobile Genesis      (MS130v4 cellular modems: MSISDN / ICCID / IMEI)
    4. True911               (authoritative sites / devices / service units / E911)

For every building it resolves the four sources by store number, address, and
device identifiers (radio number / IMEI / ICCID / MSISDN), then emits a Building
Digital Twin with: building, services, devices, E911, per-source confidence,
missing assets, and duplicate assets — plus an executive dashboard summary.

Strictly READ-ONLY:
  * Never writes any source (Zoho / Napco / Genesis / True911) — SELECT / parse only.
  * E911 is NEVER marked verified; missing data is NEVER fabricated (unknown lowers
    confidence, it does not invent a value).
  * ``--csv`` / ``--json`` / ``--report`` write operator-requested artifacts only.

Sources are optional individually, but at least one non-True911 source is required
(True911 is always loaded from the tenant DB as the fusion spine).

Usage (on Render, against production):
    python -m scripts.rh_portfolio_fusion \
        --tenant restoration-hardware \
        --zoho-csv /path/to/Subscription_Mgmnt.csv \
        --napco-csv /path/to/napco_radiolist.csv \
        --genesis-csv /path/to/genesis_ms130.csv \
        --csv /tmp/rh_fusion.csv --json /tmp/rh_fusion.json \
        --report /tmp/rh_fusion.md
    # live Zoho instead of a CSV:
    python -m scripts.rh_portfolio_fusion --tenant restoration-hardware \
        --zoho-live --module Accounts --napco-csv /path/napco.csv --report /tmp/rh_fusion.md

Exit codes: 0 ok · 3 error (bad input / DB or Zoho not configured).
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

from scripts import rh_portfolio_certification as cert  # noqa: E402  (reuse normalizers)
from app.services import portfolio_registry as _registry  # noqa: E402  (load/reconcile)

DEFAULT_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")
DEFAULT_CSV = "/tmp/rh_portfolio_fusion.csv"
DEFAULT_JSON = "/tmp/rh_portfolio_fusion.json"
DEFAULT_REPORT = "/tmp/rh_portfolio_fusion.md"

SOURCE_ZOHO = "zoho"
SOURCE_NAPCO = "napco"
SOURCE_GENESIS = "genesis"
SOURCE_TRUE911 = "true911"
ALL_SOURCES = (SOURCE_ZOHO, SOURCE_NAPCO, SOURCE_GENESIS, SOURCE_TRUE911)

# Trust weights → per-building source_confidence (corroboration across sources).
SOURCE_WEIGHT = {SOURCE_TRUE911: 40, SOURCE_ZOHO: 25, SOURCE_NAPCO: 20, SOURCE_GENESIS: 15}

# site_type → building category
_CATEGORY = {
    "store": "Retail", "gallery": "Retail", "outlet": "Retail",
    "guest_house": "Hospitality", "special": "Special",
    "warehouse": "Warehouse", "distribution_center": "Distribution",
    "corporate": "Corporate",
}
VERIFIED_E911 = frozenset({"validated", "verified", "confirmed"})


def building_category(site_type) -> str:
    return _CATEGORY.get(site_type or "", "Commercial")


def _norm_id(v) -> str:
    """Normalize a device identifier for cross-source joins (alnum, upper)."""
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def _fusion_store_number(name) -> str | None:
    """Store number for fusion identity — the certification extractor PLUS bare
    ``RH <n>`` / ``RH -506`` forms that vendor labels (Napco/Genesis) use without a
    ``#``.  Leading zeros dropped."""
    st = cert.extract_store_number(name)
    if st:
        return st
    n = cert.norm_name(name)
    if re.search(r"\brh\b", n):
        m = re.search(r"\brh\b[\s\-#]*0*(\d{1,4})", n)          # "RH 149", "RH -506"
        if m:
            return m.group(1)
        nums = re.findall(r"\b0*(\d{3,4})\b", n)                # RH + a store-sized number
        if nums:
            return nums[0]
    return None


# ══════════════════════════════════════════════════════════════════════
# Source adapters — each returns a list of normalized SourceRecord dicts.
# A SourceRecord carries building identity + the devices/services it contributes.
# (pure; unit-tested)
# ══════════════════════════════════════════════════════════════════════
def _source_record(source, *, name=None, store_number=None, street=None, city=None,
                   state=None, zip_=None, site_type=None, site_id=None, e911_status=None,
                   devices=None, service_types=None) -> dict:
    return {
        "source": source, "name": name, "store_number": store_number,
        "street": street, "city": city, "state": (state or "").upper() or None, "zip": zip_,
        "site_type": site_type, "site_id": site_id, "e911_status": e911_status,
        "devices": devices or [], "service_types": sorted(set(service_types or [])),
    }


def _device(*, kind, source, radio_number=None, imei=None, iccid=None, msisdn=None,
            serial=None, starlink_id=None, model=None, service_type=None) -> dict:
    return {
        "kind": kind, "source": source, "radio_number": radio_number, "imei": imei,
        "iccid": iccid, "msisdn": cert.norm_phone(msisdn) or None, "serial": serial,
        "starlink_id": starlink_id, "model": model, "service_type": service_type,
    }


def _zoho_connection_service(conn) -> str | None:
    c = (conn or "").strip().lower()
    if "alarm" in c:
        return "alarm"
    if "elevator" in c:
        return "elevator"
    return None


def adapt_zoho(rows: list[dict]) -> list[dict]:
    """Zoho subscription rows (already normalized by ``cert.map_zoho_row``) ->
    SourceRecords.  Each row is one building+device line."""
    out = []
    for r in rows:
        name = r.get("account_name") or r.get("facility_name")
        known = cert.match_known_location(name) if hasattr(cert, "match_known_location") else None
        store = _fusion_store_number(name)
        if known and known.get("code") and not (store and store.isdigit()):
            store = known["code"]
        site_type = known["site_type"] if known else cert.detect_site_type(name)
        svc = _zoho_connection_service(r.get("connection_type"))
        kind = "napco_radio" if r.get("starlink_id") else ("cellular" if (r.get("imei") or r.get("msisdn")) else "device")
        dev = _device(kind=kind, source=SOURCE_ZOHO, imei=r.get("imei"), iccid=r.get("sim"),
                      msisdn=r.get("msisdn"), starlink_id=r.get("starlink_id"),
                      serial=r.get("starlink_id"), service_type=svc)
        out.append(_source_record(
            SOURCE_ZOHO, name=name, store_number=store, street=r.get("street"),
            city=r.get("city"), state=r.get("state"), zip_=r.get("zip"), site_type=site_type,
            devices=[dev] if any((dev["imei"], dev["iccid"], dev["msisdn"], dev["starlink_id"])) else [],
            service_types=[svc] if svc else []))
    return out


def load_napco_csv(path: str) -> list:
    """READ-ONLY parse of a Napco StarLink Radiolist via the existing vendor
    adapter (RadioNumber / ICCID / SubscriberName; sensitive fields dropped)."""
    from app.services.inventory_reconciliation.adapters import napco
    return napco.parse(path)


def adapt_napco(vendor_records: list) -> list[dict]:
    """Napco VendorRecords -> SourceRecords.  The subscriber name doubles as the
    site label; the radio is an alarm device."""
    out = []
    for vr in vendor_records:
        label = getattr(vr, "subscriber_name", None) or getattr(vr, "site_hint", None)
        store = _fusion_store_number(label)
        known = cert.match_known_location(label) if hasattr(cert, "match_known_location") else None
        if known and known.get("code") and not (store and store.isdigit()):
            store = known["code"]
        site_type = known["site_type"] if known else cert.detect_site_type(label)
        radio = getattr(vr, "radio_number", None)
        dev = _device(kind="napco_radio", source=SOURCE_NAPCO, radio_number=radio,
                      iccid=getattr(vr, "iccid", None), serial=radio, starlink_id=radio,
                      service_type="alarm")
        out.append(_source_record(SOURCE_NAPCO, name=label, store_number=store,
                                  site_type=site_type, devices=[dev], service_types=["alarm"]))
    return out


# Genesis (MS130v4) CSV — tolerant column aliases (no fixed vendor schema).
_G_ICCID = ("iccid", "sim_iccid", "sim", "sim_number")
_G_MSISDN = ("msisdn", "phone_number", "phone", "mdn", "subscriber", "did")
_G_IMEI = ("imei", "device_imei")
_G_MODEL = ("model", "device_model", "hardware_model")
_G_NAME = ("label", "description", "account_name", "site_name", "subscriber_name",
           "customer_name", "name", "location_name")
_G_STREET = ("street", "street_address", "address", "site_address", "facilityaddress", "e911_street")
_G_CITY = ("city", "site_city", "facilitycity", "e911_city")
_G_STATE = ("state", "site_state", "facilitystate", "e911_state")
_G_ZIP = ("zip", "zip_code", "site_zip", "facilityzipcode", "e911_zip")
_G_STATUS = ("status", "activation_status", "network_status", "sim_status",
             "provisioning_status", "device_status")


def load_genesis_csv(path: str) -> list[dict]:
    """READ-ONLY parse of a T-Mobile Genesis / MS130v4 export.  Tolerant of column
    naming; keys rows by device identifier (msisdn / iccid / imei)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        raw = list(csv.DictReader(f))
    rows = []
    for r in raw:
        norm = {(k or "").strip().lower().replace(" ", "_").replace("-", "_"): (v or "").strip()
                for k, v in r.items()}

        def g(keys):
            for k in keys:
                if norm.get(k):
                    return norm[k]
            return None
        rows.append({
            "iccid": g(_G_ICCID), "msisdn": g(_G_MSISDN), "imei": g(_G_IMEI),
            "model": g(_G_MODEL) or "MS130v4",
            "name": g(_G_NAME), "label": g(_G_NAME), "status": g(_G_STATUS),
            "street": g(_G_STREET), "city": g(_G_CITY),
            "state": g(_G_STATE), "zip": g(_G_ZIP),
        })
    return rows


def adapt_genesis(rows: list[dict]) -> list[dict]:
    """Genesis MS130 rows -> SourceRecords (each row is a cellular modem)."""
    out = []
    for r in rows:
        if not any((r.get("iccid"), r.get("msisdn"), r.get("imei"))):
            continue
        name = r.get("name")
        store = _fusion_store_number(name)
        site_type = cert.detect_site_type(name) if name else None
        dev = _device(kind="ms130", source=SOURCE_GENESIS, imei=r.get("imei"),
                      iccid=r.get("iccid"), msisdn=r.get("msisdn"),
                      model=r.get("model") or "MS130v4", service_type="cellular")
        out.append(_source_record(SOURCE_GENESIS, name=name, store_number=store,
                                  street=r.get("street"), city=r.get("city"),
                                  state=r.get("state"), zip_=r.get("zip"),
                                  site_type=site_type, devices=[dev], service_types=["cellular"]))
    return out


# ── Genesis RH filtering ─────────────────────────────────────────────
# A raw Genesis export is the WHOLE Infatrac book, not just RH.  Filter to RH rows
# BEFORE fusing so the engine never invents thousands of non-RH buildings.  Two
# stages: (A) a direct RH label match, (B) a contextual match when the row's
# phone/identifier is known to belong to RH from Zoho / Napco / True911.
def _phone_key(v):
    return cert.norm_phone(v) or None


def _build_rh_context(zoho_rows, napco_records, true911) -> dict:
    """RH footprint drawn from the already-RH sources: store numbers, city tokens,
    and device identifiers (phones / ICCID / IMEI / radio) that prove an RH device."""
    stores, cities, idents = set(), set(), set()

    def add_store(nm):
        st = cert.extract_store_number(nm)
        if st and str(st).isdigit():
            stores.add(str(st))

    def add_city(c):
        for tok in cert.norm_name(c).split():
            if len(tok) >= 4:            # skip 2–3 char noise / state codes
                cities.add(tok)

    def add_ident(v):
        nid = _norm_id(v)
        if nid:
            idents.add(nid)

    def add_phone(v):
        pk = _phone_key(v)
        if pk:
            idents.add(pk)

    for r in zoho_rows or []:
        nm = r.get("account_name") or r.get("facility_name")
        add_store(nm)
        add_city(r.get("city"))
        add_phone(r.get("msisdn"))
        for v in (r.get("sim"), r.get("imei"), r.get("starlink_id")):
            add_ident(v)
    for vr in napco_records or []:
        nm = getattr(vr, "subscriber_name", None) or getattr(vr, "site_hint", None)
        if nm and cert.is_rh_label(nm):
            add_store(nm)
            add_ident(getattr(vr, "radio_number", None))
            add_ident(getattr(vr, "iccid", None))
    for s in (true911 or {}).get("sites", []):
        add_store(s.get("name"))
        add_city(s.get("city"))
    for d in (true911 or {}).get("devices", []):
        add_phone(d.get("msisdn"))
        for v in (d.get("iccid"), d.get("imei"), d.get("starlink_id"), d.get("serial_number")):
            add_ident(v)
    for ln in (true911 or {}).get("lines", []):
        add_phone(ln.get("did"))
    for e in getattr(cert, "KNOWN_RH_LOCATIONS", ()):
        add_city(e.get("city"))
    return {"stores": stores, "cities": cities, "idents": idents}


def _label_rh_reason(label, ctx: dict):
    """Direct RH label match (shared by Napco + Genesis).  None -> no label match.
    A bare, standalone "RH" only counts with corroboration (store #, known store #,
    or a known RH city) so generic "Restoration Hardware" alone never overmatches."""
    n = cert.norm_name(label)
    if not n:
        return None
    if "restoration hardware" in n or "restoration hdwr" in n:
        return "label:restoration_hardware"
    if hasattr(cert, "match_known_location") and cert.match_known_location(label):
        return "label:known_alias"
    if re.search(r"\brh\b", n):            # standalone RH token (never a stray "…rh…")
        m = re.search(r"\brh\b[\s\-#]*(\d{1,4})", n)          # "RH 150", "RH -506"
        if m:
            return f"label:rh_store_{m.group(1)}"
        if set(re.findall(r"\b(\d{3,4})\b", n)) & ctx["stores"]:   # RH + known store #
            return "label:rh_store_context"
        city_hit = sorted(set(n.split()) & ctx["cities"])          # "RH Hollywood" etc.
        if city_hit:
            return "label:rh_city_" + city_hit[0]
    return None


def _infer_canonical(label):
    """Best canonical building name for a bare vendor label (known alias / store #)."""
    known = cert.match_known_location(label) if hasattr(cert, "match_known_location") else None
    if known:
        return known["canonical_name"]
    st = cert.extract_store_number(label)
    if st and str(st).isdigit():
        return f"RH #{st}"
    m = re.search(r"\brh\b[\s\-#]*(\d{1,4})", cert.norm_name(label))
    return f"RH #{m.group(1)}" if m else None


_infer_genesis_canonical = _infer_canonical      # back-compat alias


def _genesis_rh_reason(row: dict, ctx: dict):
    """Why (if at all) a Genesis row is RH.  None -> excluded."""
    reason = _label_rh_reason(row.get("name") or row.get("label"), ctx)
    if reason:
        return reason
    # Stage B: phone / identifier context (proves an RH device)
    if _phone_key(row.get("msisdn")) and _phone_key(row.get("msisdn")) in ctx["idents"]:
        return "context:msisdn"
    for v in (row.get("iccid"), row.get("imei")):
        nid = _norm_id(v)
        if nid and nid in ctx["idents"]:
            return "context:identifier"
    return None


def genesis_rh_filter(rows: list[dict], ctx: dict) -> tuple[list[dict], int]:
    """Keep only RH-related Genesis rows (two-stage).  Returns (rh_rows, excluded)."""
    included, excluded = [], 0
    for r in rows:
        reason = _genesis_rh_reason(r, ctx)
        if reason:
            r2 = dict(r)
            r2["_rh_reason"] = reason
            r2["_rh_canonical"] = _infer_canonical(r.get("name") or r.get("label"))
            included.append(r2)
        else:
            excluded += 1
    return included, excluded


# ── Napco RH filtering ───────────────────────────────────────────────
# A Napco Radiolist is the dealer's WHOLE book (schools, apartments, other retailers,
# individuals, municipalities) — filter to RH before fusing.  Stage A: the subscriber
# label is RH.  Stage B: the radio number / ICCID is a known RH device (from Zoho /
# True911).
def _napco_rh_reason(vr, ctx: dict):
    label = getattr(vr, "subscriber_name", None) or getattr(vr, "site_hint", None) or ""
    reason = _label_rh_reason(label, ctx)
    if reason:
        return reason
    for v, kind in ((getattr(vr, "radio_number", None), "radio"),
                    (getattr(vr, "iccid", None), "iccid")):
        nid = _norm_id(v)
        if nid and nid in ctx["idents"]:
            return f"context:{kind}"
    return None


def napco_rh_filter(vendor_records: list, ctx: dict) -> tuple[list[dict], int]:
    """Keep only RH-related Napco VendorRecords.  Returns (list of
    {record, reason, canonical}, excluded)."""
    included, excluded = [], 0
    for vr in vendor_records:
        reason = _napco_rh_reason(vr, ctx)
        if reason:
            label = getattr(vr, "subscriber_name", None) or getattr(vr, "site_hint", None)
            included.append({"record": vr, "reason": reason, "canonical": _infer_canonical(label)})
        else:
            excluded += 1
    return included, excluded


def load_genesis_api(iccids=None):
    """Optional live Genesis mode.  T-Mobile TAAP exposes per-ICCID SubscriberInquiry
    (read-only), NOT a bulk portfolio list — so a live pull requires a seed set of
    ICCIDs from another source.  Kept read-only; raises a clear error when no bulk
    source is configured rather than fabricating one."""
    raise RuntimeError("Genesis live/API mode needs a seed ICCID list and TAAP creds; "
                       "use --genesis-csv for the bulk MS130 export.")


def _t911_device_kind(d: dict) -> str:
    it = (d.get("identifier_type") or "").lower()
    model = (d.get("model") or "").lower()
    if d.get("starlink_id") or it == "starlink" or "starlink" in model or "sle" in model:
        return "napco_radio"
    if "ms130" in model:
        return "ms130"
    if it == "ata" or "ata" in (d.get("device_type") or "").lower():
        return "ata"
    if it == "cellular" or d.get("msisdn"):
        return "cellular"
    return "device"


def adapt_true911(true911: dict) -> list[dict]:
    """True911 sites/devices/units/lines -> one SourceRecord per site (the spine)."""
    sites = true911.get("sites", [])
    devices = true911.get("devices", [])
    units = true911.get("units", [])
    lines = true911.get("lines", [])
    by_site_dev = defaultdict(list)
    for d in devices:
        by_site_dev[d.get("site_id")].append(d)
    by_site_units = defaultdict(list)
    for u in units:
        by_site_units[u.get("site_id")].append(u)
    by_site_lines = defaultdict(list)
    for ln in lines:
        by_site_lines[ln.get("site_id")].append(ln)

    out = []
    for s in sites:
        sid = s.get("site_id")
        name = s.get("name")
        store = _fusion_store_number(name)
        devs = []
        for d in by_site_dev.get(sid, []):
            devs.append(_device(kind=_t911_device_kind(d), source=SOURCE_TRUE911,
                                imei=d.get("imei"), iccid=d.get("iccid"), msisdn=d.get("msisdn"),
                                serial=d.get("serial_number"), starlink_id=d.get("starlink_id"),
                                model=d.get("model"),
                                service_type=(d.get("device_type") or None)))
        # line DIDs become phone-bearing devices too (for phone-number joins)
        for ln in by_site_lines.get(sid, []):
            if ln.get("did"):
                devs.append(_device(kind="line", source=SOURCE_TRUE911, msisdn=ln.get("did"),
                                    iccid=ln.get("sim_iccid"), service_type="voice"))
        svc = [u.get("unit_type") for u in by_site_units.get(sid, []) if u.get("unit_type")]
        out.append(_source_record(
            SOURCE_TRUE911, name=name, store_number=store, street=s.get("street"),
            city=s.get("city"), state=s.get("state"), zip_=s.get("zip"),
            site_type=cert.detect_site_type(name), site_id=sid, e911_status=s.get("e911_status"),
            devices=devs, service_types=svc))
    return out


# ══════════════════════════════════════════════════════════════════════
# Fusion — resolve source records into buildings + Building Digital Twins.
# (pure; unit-tested)
# ══════════════════════════════════════════════════════════════════════
_GENERIC_RH_TOKENS = frozenset({"restoration", "hardware", "hdwr", "rh"})


def _building_key(r: dict):
    """The strongest *identity* join key for a record — numeric store #, alpha store
    code, known alias, or a distinctive location-token set.  Bare "Restoration
    Hardware" (no distinctive tokens) yields no key, so it never overmatches."""
    name = r.get("name")
    store = r.get("store_number")
    if store and str(store).isdigit():
        return ("store", str(store))
    if store:
        return ("code", str(store).upper())
    known = cert.match_known_location(name) if hasattr(cert, "match_known_location") else None
    if known:
        return ("alias", known["canonical_name"])
    # distinctive alpha tokens (>=4 chars, generic RH words stripped, digits dropped)
    toks = sorted(t for t in (set(cert.norm_name(name).split()) - _GENERIC_RH_TOKENS)
                  if len(t) >= 4 and not t.isdigit())
    return ("name", " ".join(toks)) if toks else None


def _record_join_keys(r: dict) -> set:
    keys = set()
    bk = _building_key(r)                 # store # / code / alias / distinctive name
    if bk:
        keys.add(bk)
    if r.get("street"):
        na = cert.norm_addr(r.get("street"), r.get("city"), r.get("state"))
        if na:
            keys.add(("addr", na))
    for d in r.get("devices", []):
        for v in (d.get("radio_number"), d.get("imei"), d.get("iccid"), d.get("msisdn"),
                  d.get("starlink_id"), d.get("serial")):
            nid = _norm_id(v)
            if nid:
                keys.add(("dev", nid))
    return keys


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def fuse_records(records: list[dict]) -> list[list[dict]]:
    """Cluster SourceRecords into buildings by shared store#, address, or device id."""
    uf = _UF(len(records))
    key_idx = defaultdict(list)
    for i, r in enumerate(records):
        for k in _record_join_keys(r):
            key_idx[k].append(i)
    for idxs in key_idx.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)
    clusters = defaultdict(list)
    for i, r in enumerate(records):
        clusters[uf.find(i)].append(r)
    return list(clusters.values())


def _merge_devices(records: list[dict]) -> list[dict]:
    """Union devices within a building by shared identifier -> unified device list."""
    devs = [d for r in records for d in r.get("devices", [])]
    if not devs:
        return []
    uf = _UF(len(devs))
    key_idx = defaultdict(list)
    for i, d in enumerate(devs):
        for v in (d.get("radio_number"), d.get("imei"), d.get("iccid"), d.get("msisdn"),
                  d.get("starlink_id"), d.get("serial")):
            nid = _norm_id(v)
            if nid:
                key_idx[nid].append(i)
    for idxs in key_idx.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)
    groups = defaultdict(list)
    for i, d in enumerate(devs):
        groups[uf.find(i)].append(d)

    _KIND_RANK = {"napco_radio": 0, "ms130": 1, "cellular": 2, "ata": 3, "line": 4, "device": 5}
    merged = []
    for group in groups.values():
        sources = sorted({d["source"] for d in group})
        kind = sorted((d["kind"] for d in group), key=lambda k: _KIND_RANK.get(k, 9))[0]

        def _first(field):
            return next((d[field] for d in group if d.get(field)), None)
        merged.append({
            "kind": kind, "sources": sources,
            "radio_number": _first("radio_number"), "imei": _first("imei"),
            "iccid": _first("iccid"), "msisdn": _first("msisdn"),
            "starlink_id": _first("starlink_id"), "serial": _first("serial"),
            "model": _first("model"), "service_type": _first("service_type"),
            "in_true911": SOURCE_TRUE911 in sources,
        })
    return merged


def _pick(records, source_order, field):
    """First non-empty ``field`` scanning records in preferred-source order."""
    for src in source_order:
        for r in records:
            if r["source"] == src and r.get(field):
                return r[field]
    return None


def build_twin(records: list[dict], index: int) -> dict:
    """One Building Digital Twin fused from a cluster of SourceRecords."""
    sources = sorted({r["source"] for r in records})
    # identity — prefer the most authoritative source per field
    store = _pick(records, (SOURCE_TRUE911, SOURCE_ZOHO, SOURCE_NAPCO, SOURCE_GENESIS), "store_number")
    best_name = _pick(records, (SOURCE_TRUE911, SOURCE_ZOHO, SOURCE_NAPCO, SOURCE_GENESIS), "name")
    known = cert.match_known_location(best_name) if hasattr(cert, "match_known_location") else None
    if known:
        canonical_name = known["canonical_name"]
        site_type = known["site_type"]
    else:
        site_type = _pick(records, (SOURCE_TRUE911, SOURCE_ZOHO, SOURCE_NAPCO, SOURCE_GENESIS), "site_type")
        canonical_name = (best_name or (f"RH #{store}" if store else "RH (unnamed)"))
    street = _pick(records, (SOURCE_TRUE911, SOURCE_ZOHO, SOURCE_GENESIS), "street")
    city = _pick(records, (SOURCE_TRUE911, SOURCE_ZOHO, SOURCE_GENESIS), "city")
    state = _pick(records, (SOURCE_TRUE911, SOURCE_ZOHO, SOURCE_GENESIS), "state")
    zip_ = _pick(records, (SOURCE_TRUE911, SOURCE_ZOHO, SOURCE_GENESIS), "zip")
    e911_status = _pick(records, (SOURCE_TRUE911,), "e911_status")
    site_id = _pick(records, (SOURCE_TRUE911,), "site_id")

    devices = _merge_devices(records)
    services = sorted({s for r in records for s in r.get("service_types", [])})
    source_names = {}
    for r in records:
        if r.get("name"):
            source_names.setdefault(r["source"], []).append(r["name"])

    # source confidence — corroboration across trusted sources (weighted, capped)
    confidence = min(100, sum(SOURCE_WEIGHT.get(s, 0) for s in sources))

    # missing assets
    missing = []
    if SOURCE_TRUE911 not in sources:
        missing.append("No True911 site (present in %s only)" % ", ".join(sources))
    if SOURCE_ZOHO not in sources:
        missing.append("No Zoho subscription record")
    for d in devices:
        if not d["in_true911"]:
            ident = d.get("radio_number") or d.get("iccid") or d.get("imei") or d.get("msisdn") or "?"
            missing.append("%s device %s (from %s) not in True911"
                           % (d["kind"], ident, ", ".join(d["sources"])))
    t911_has_units = any(r.get("service_types") for r in records if r["source"] == SOURCE_TRUE911)
    if SOURCE_TRUE911 in sources and not t911_has_units:
        missing.append("No service unit at the True911 site")
    if SOURCE_TRUE911 in sources and (e911_status or "").strip().lower() not in VERIFIED_E911:
        missing.append("E911 not verified (status=%r)" % e911_status)

    # duplicate assets — multiple True911 sites fused into one building
    t911_site_ids = sorted({r.get("site_id") for r in records
                            if r["source"] == SOURCE_TRUE911 and r.get("site_id")})
    duplicates = []
    if len(t911_site_ids) > 1:
        duplicates.append("Multiple True911 sites fused: " + ", ".join(t911_site_ids))

    return {
        "building_id": f"BLD-{index:04d}",
        "canonical_name": canonical_name,
        "store_number": store,
        "site_type": site_type,
        "building_category": building_category(site_type),
        "address": {"street": street, "city": city, "state": state, "zip": zip_},
        "sources": sources,
        "source_names": source_names,
        "source_confidence": confidence,
        "services": services,
        "devices": devices,
        "e911": {"status": e911_status, "verified": (e911_status or "").strip().lower() in VERIFIED_E911,
                 "site_id": site_id},
        "missing_assets": missing,
        "duplicate_assets": duplicates,
    }


def fuse_portfolio(*, zoho_rows=None, napco_records=None, genesis_rows=None,
                   true911=None, tenant=None, registry=None) -> dict:
    """Adapt all four sources, fuse into buildings, and build the fusion report.
    Genesis rows are RH-filtered first (the raw export is the whole Infatrac book).

    ``registry`` is a READ-ONLY approved Portfolio Registry snapshot (see
    ``app.services.portfolio_registry.load_registry``).  When supplied, each fused
    candidate is reconciled against it — approved mappings resolve a building BEFORE
    any heuristic, and unmapped candidates become review items.  This function never
    writes the registry (or any source)."""
    zoho_rows = zoho_rows or []
    napco_records = napco_records or []
    genesis_rows = genesis_rows or []
    true911 = true911 or {}

    # Vendor exports (Napco Radiolist, Genesis book) contain the WHOLE dealer/carrier
    # book — filter each to RH before fusing.  Build the RH context from the already-RH
    # spine (Zoho + True911) first, then extend it with the RH-matched Napco devices so
    # Genesis can also match on Napco-proven identifiers.
    base_ctx = _build_rh_context(zoho_rows, [], true911)
    napco_total = len(napco_records)
    napco_incl, napco_excluded = napco_rh_filter(napco_records, base_ctx)
    napco_rh = [d["record"] for d in napco_incl]

    full_ctx = _build_rh_context(zoho_rows, napco_rh, true911)
    genesis_total = len(genesis_rows)
    genesis_incl, genesis_excluded = genesis_rh_filter(genesis_rows, full_ctx)

    records = []
    records += adapt_zoho(zoho_rows)
    records += adapt_napco(napco_rh)
    records += adapt_genesis(genesis_incl)
    records += adapt_true911(true911)

    clusters = fuse_records(records)
    twins = [build_twin(c, i + 1) for i, c in enumerate(
        sorted(clusters, key=lambda c: (c[0].get("store_number") or "zzz",
                                        c[0].get("name") or "")))]

    # cross-building duplicate address detection
    addr_index = defaultdict(list)
    for t in twins:
        a = cert.norm_addr(t["address"]["street"], t["address"]["city"], t["address"]["state"])
        if a:
            addr_index[a].append(t)
    for a, group in addr_index.items():
        if len(group) > 1:
            names = ", ".join(t["canonical_name"] for t in group)
            for t in group:
                t["duplicate_assets"].append("Shares address with another building: " + names)

    summary = _dashboard(twins, tenant, records)
    summary["source_rows"] = {
        SOURCE_ZOHO: len(zoho_rows), SOURCE_NAPCO: napco_total,
        SOURCE_GENESIS: genesis_total, SOURCE_TRUE911: len(true911.get("sites", [])),
    }
    summary["napco_rows_total"] = napco_total
    summary["napco_rows_rh_matched"] = len(napco_incl)
    summary["napco_rows_excluded"] = napco_excluded
    summary["genesis_rows_total"] = genesis_total
    summary["genesis_rows_rh_matched"] = len(genesis_incl)
    summary["genesis_rows_excluded"] = genesis_excluded

    genesis_included = [{
        "msisdn": _phone_key(r.get("msisdn")) or r.get("msisdn"),
        "status": r.get("status"), "label": r.get("name") or r.get("label"),
        "reason": r.get("_rh_reason"), "canonical": r.get("_rh_canonical"),
    } for r in genesis_incl]
    napco_included = [{
        "radio_number": getattr(d["record"], "radio_number", None),
        "subscriber_name": getattr(d["record"], "subscriber_name", None),
        "iccid": getattr(d["record"], "iccid", None),
        "canonical": d["canonical"], "reason": d["reason"],
    } for d in napco_incl]

    # ── Reconcile candidates against the approved Portfolio Registry (read-only) ──
    registry = registry or _registry.empty_registry(tenant)
    recon = _registry.reconcile(twins, registry)
    for r in recon["resolved"]:
        i = r.get("candidate_index")
        if i is not None:
            twins[i]["registry"] = {"building_id": r["building_id"], "method": r["method"],
                                    "status": "ambiguous" if r["method"] == "ambiguous" else "known"}
    for t in twins:
        t.setdefault("registry", {"building_id": None, "method": None, "status": "new"})

    summary.update(_registry_summary(twins, registry, recon))
    summary["confidence_distribution"] = _confidence_distribution(twins)

    return {"summary": summary, "buildings": twins,
            "napco_included": napco_included, "genesis_included": genesis_included,
            "review_items": recon["review_items"], "resolved": recon["resolved"]}


def _confidence_distribution(twins: list[dict]) -> dict:
    buckets = {"90-100": 0, "70-89": 0, "40-69": 0, "0-39": 0}
    for t in twins:
        c = t["source_confidence"]
        key = "90-100" if c >= 90 else "70-89" if c >= 70 else "40-69" if c >= 40 else "0-39"
        buckets[key] += 1
    return buckets


def _registry_summary(twins, registry, recon) -> dict:
    st = recon["stats"]
    return {
        "portfolio_buildings": st["portfolio_buildings"],
        "known_aliases": st["known_aliases"],
        "approved_mappings": st["approved_mappings"],
        "pending_review": st["pending_review_new"],
        "review_by_type": st["review_by_type"],
        "rejected_suggestions": st["rejected_suggestions"],
        "buildings_known": sum(1 for t in twins if t["registry"]["status"] == "known"),
        "buildings_new": sum(1 for t in twins if t["registry"]["status"] == "new"),
        "buildings_ambiguous": sum(1 for t in twins if t["registry"]["status"] == "ambiguous"),
        "coverage_by_source": {s: sum(1 for t in twins if s in t["sources"]) for s in ALL_SOURCES},
    }


def _dashboard(twins: list[dict], tenant, records) -> dict:
    src_coverage = {s: sum(1 for t in twins if s in t["sources"]) for s in ALL_SOURCES}
    by_category = dict(Counter(t["building_category"] for t in twins))
    fully_fused = sum(1 for t in twins if set(ALL_SOURCES) <= set(t["sources"]))
    total_devices = sum(len(t["devices"]) for t in twins)
    devices_missing_t911 = sum(1 for t in twins for d in t["devices"] if not d["in_true911"])
    device_counts_by_source = {
        s: sum(1 for t in twins for d in t["devices"] if s in d["sources"]) for s in ALL_SOURCES}
    return {
        "tenant": tenant,
        "source_records": len(records),
        "buildings": len(twins),
        "by_category": by_category,
        "source_coverage": src_coverage,
        "device_counts_by_source": device_counts_by_source,
        "fully_fused_all_sources": fully_fused,
        "buildings_missing_true911": sum(1 for t in twins if SOURCE_TRUE911 not in t["sources"]),
        "buildings_e911_unverified": sum(1 for t in twins if not t["e911"]["verified"]),
        "total_devices": total_devices,
        "devices_missing_in_true911": devices_missing_t911,
        "buildings_with_missing_assets": sum(1 for t in twins if t["missing_assets"]),
        "buildings_with_duplicates": sum(1 for t in twins if t["duplicate_assets"]),
        "avg_source_confidence": round(sum(t["source_confidence"] for t in twins) / len(twins), 1)
        if twins else 0.0,
    }


# ══════════════════════════════════════════════════════════════════════
# Output artifacts
# ══════════════════════════════════════════════════════════════════════
def write_csv(path: str, report: dict) -> None:
    cols = ["building_id", "store_number", "canonical_name", "building_category", "site_type",
            "sources", "source_confidence", "services", "device_count",
            "devices_missing_in_true911", "e911_status", "missing_count", "duplicate_count"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for t in report["buildings"]:
            w.writerow({
                "building_id": t["building_id"], "store_number": t["store_number"] or "",
                "canonical_name": t["canonical_name"], "building_category": t["building_category"],
                "site_type": t["site_type"] or "", "sources": ",".join(t["sources"]),
                "source_confidence": t["source_confidence"], "services": ",".join(t["services"]),
                "device_count": len(t["devices"]),
                "devices_missing_in_true911": sum(1 for d in t["devices"] if not d["in_true911"]),
                "e911_status": t["e911"]["status"] or "",
                "missing_count": len(t["missing_assets"]),
                "duplicate_count": len(t["duplicate_assets"]),
            })


def write_json(path: str, report: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)


def _dashboard_lines(s: dict) -> list[str]:
    L = ["## Executive dashboard", ""]
    # Source ROW counts are distinct from canonical BUILDING counts.
    sr = s.get("source_rows", {})
    if sr:
        L.append(f"- Source rows in — Zoho {sr.get('zoho', 0)} · Napco {sr.get('napco', 0)} · "
                 f"Genesis {sr.get('genesis', 0)} · True911 {sr.get('true911', 0)}")
    L.append(f"- **Canonical buildings: {s['buildings']}** (fused from {s['source_records']} "
             f"RH-matched source records)")
    L.append(f"- Fully fused (all 4 sources): **{s['fully_fused_all_sources']}**")
    cov = s["source_coverage"]
    L.append(f"- Building coverage — Zoho {cov['zoho']} · Napco {cov['napco']} · "
             f"Genesis {cov['genesis']} · True911 {cov['true911']}")
    dc = s.get("device_counts_by_source", {})
    if dc:
        L.append(f"- Devices by source — Zoho {dc.get('zoho', 0)} · Napco {dc.get('napco', 0)} · "
                 f"Genesis {dc.get('genesis', 0)} · True911 {dc.get('true911', 0)}")
    L.append("- By category — " + (", ".join(f"{k}: {v}" for k, v in sorted(s["by_category"].items()))
                                    or "—"))
    L.append(f"- Buildings missing a True911 site: **{s['buildings_missing_true911']}**")
    L.append(f"- Buildings with E911 unverified: **{s['buildings_e911_unverified']}**")
    L.append(f"- Devices: {s['total_devices']} · not in True911: **{s['devices_missing_in_true911']}**")
    L.append(f"- Buildings with missing assets: {s['buildings_with_missing_assets']} · "
             f"with duplicates: {s['buildings_with_duplicates']}")
    L.append(f"- Average source confidence: **{s['avg_source_confidence']}**")
    if "napco_rows_total" in s:
        L.append(f"- Napco rows — total {s['napco_rows_total']} · "
                 f"RH matched **{s['napco_rows_rh_matched']}** · "
                 f"excluded (non-RH) {s['napco_rows_excluded']}")
    if "genesis_rows_total" in s:
        L.append(f"- Genesis rows — total {s['genesis_rows_total']} · "
                 f"RH matched **{s['genesis_rows_rh_matched']}** · "
                 f"excluded (non-RH) {s['genesis_rows_excluded']}")
    if "portfolio_buildings" in s:
        L.append(f"- **Portfolio Registry** — buildings {s['portfolio_buildings']} · "
                 f"known aliases {s['known_aliases']} · approved mappings "
                 f"{s['approved_mappings']} · rejected suggestions {s['rejected_suggestions']}")
        L.append(f"- Reconciliation — known **{s['buildings_known']}** · "
                 f"new **{s['buildings_new']}** · ambiguous {s['buildings_ambiguous']} · "
                 f"pending review **{s['pending_review']}**")
        cd = s.get("confidence_distribution", {})
        L.append("- Confidence distribution — " + " · ".join(f"{k}: {v}" for k, v in cd.items()))
    L.append("")
    return L


def write_markdown_report(path: str, report: dict) -> None:
    s, twins = report["summary"], report["buildings"]
    L = [f"# True911 Portfolio Fusion — {s.get('tenant')}", ""]
    L.append("> READ-ONLY multi-source fusion (Zoho · Napco StarLink · T-Mobile Genesis · "
             "True911). Nothing was written to any source. E911 is never auto-verified; "
             "missing data is never fabricated.")
    L.append("")
    L += _dashboard_lines(s)

    # Per-building fusion table
    L.append("## Buildings (Digital Twins)")
    L.append("| Building | Store # | Category | Sources | Conf | Svcs | Devices | E911 | Missing | Dup |")
    L.append("|---|---|---|---|--:|--:|--:|---|--:|--:|")
    for t in twins:
        L.append(f"| {t['canonical_name']} | {t['store_number'] or '—'} | {t['building_category']} | "
                 f"{','.join(t['sources'])} | {t['source_confidence']} | {len(t['services'])} | "
                 f"{len(t['devices'])} | {t['e911']['status'] or '—'} | "
                 f"{len(t['missing_assets'])} | {len(t['duplicate_assets'])} |")
    L.append("")

    # Missing assets
    L.append("## Missing assets")
    miss = [(t, m) for t in twins for m in t["missing_assets"]]
    if not miss:
        L.append("_None._")
    else:
        L.append("| Building | Missing asset |")
        L.append("|---|---|")
        for t, m in miss[:200]:
            L.append(f"| {t['canonical_name']} | {m} |")
        if len(miss) > 200:
            L.append(f"| … | (+{len(miss) - 200} more — see JSON) |")
    L.append("")

    # Duplicate assets
    L.append("## Duplicate assets")
    dup = [(t, d) for t in twins for d in t["duplicate_assets"]]
    if not dup:
        L.append("_None._")
    else:
        L.append("| Building | Duplicate |")
        L.append("|---|---|")
        for t, d in dup:
            L.append(f"| {t['canonical_name']} | {d} |")
    L.append("")

    # Duplicate / ambiguous clusters — buildings fused from >1 True911 site or a
    # shared address (candidates for de-duplication, not separate real buildings)
    L.append("## Duplicate / ambiguous clusters")
    ambiguous = [t for t in twins if t["duplicate_assets"]]
    if not ambiguous:
        L.append("_None._")
    else:
        L.append("| Building | Store # | Sources | Devices | Issue |")
        L.append("|---|---|---|--:|---|")
        for t in ambiguous:
            L.append(f"| {t['canonical_name']} | {t['store_number'] or '—'} | "
                     f"{','.join(t['sources'])} | {len(t['devices'])} | "
                     f"{'; '.join(t['duplicate_assets'])} |")
    L.append("")

    # Napco RH rows included (why each Napco radio was kept)
    L.append("## Napco RH rows included")
    if "napco_rows_total" in s:
        L.append(f"Napco rows total **{s['napco_rows_total']}** · RH matched "
                 f"**{s['napco_rows_rh_matched']}** · excluded (non-RH) "
                 f"**{s['napco_rows_excluded']}**.")
        L.append("")
    ni = report.get("napco_included", [])
    if not ni:
        L.append("_No Napco source provided, or no RH rows matched._")
    else:
        L.append("| Radio # | Subscriber name | ICCID | Canonical | Match reason |")
        L.append("|---|---|---|---|---|")
        for n_ in ni[:200]:
            L.append(f"| {n_['radio_number'] or '—'} | {n_['subscriber_name'] or '—'} | "
                     f"{n_['iccid'] or '—'} | {n_['canonical'] or '—'} | {n_['reason']} |")
        if len(ni) > 200:
            L.append(f"| … | | | | (+{len(ni) - 200} more — see JSON) |")
    L.append("")

    # Genesis RH rows included (why each Genesis row was kept)
    L.append("## Genesis RH rows included")
    if "genesis_rows_total" in s:
        L.append(f"Genesis rows total **{s['genesis_rows_total']}** · RH matched "
                 f"**{s['genesis_rows_rh_matched']}** · excluded (non-RH) "
                 f"**{s['genesis_rows_excluded']}**.")
        L.append("")
    gi = report.get("genesis_included", [])
    if not gi:
        L.append("_No Genesis source provided, or no RH rows matched._")
    else:
        L.append("| MSISDN | Status | Label | Match reason | Canonical |")
        L.append("|---|---|---|---|---|")
        for g in gi[:200]:
            L.append(f"| {g['msisdn'] or '—'} | {g['status'] or '—'} | {g['label'] or '—'} | "
                     f"{g['reason']} | {g['canonical'] or '—'} |")
        if len(gi) > 200:
            L.append(f"| … | | | (+{len(gi) - 200} more — see JSON) | |")
    L.append("")

    # Portfolio Registry review queue (proposed — NOT auto-applied)
    L.append("## Portfolio Registry — review queue (pending)")
    if "portfolio_buildings" in s:
        L.append(f"Portfolio buildings **{s['portfolio_buildings']}** · reconciled known "
                 f"**{s['buildings_known']}** · new **{s['buildings_new']}** · ambiguous "
                 f"{s['buildings_ambiguous']}. Nothing below is applied automatically — an "
                 f"operator must approve each item.")
        L.append("")
    ri = report.get("review_items", [])
    if not ri:
        L.append("_No review items — every candidate maps to the approved registry._")
    else:
        L.append("| Review type | Candidate | Store # | Suggested building | Detail |")
        L.append("|---|---|---|---|---|")
        for it in ri[:200]:
            L.append(f"| {it['review_type']} | {it.get('candidate_name') or '—'} | "
                     f"{it.get('store_number') or '—'} | {it.get('suggested_building_id') or '—'} | "
                     f"{it['detail']} |")
        if len(ri) > 200:
            L.append(f"| … | | | | (+{len(ri) - 200} more — see JSON) |")
    L.append("")
    L.append("---")
    L.append("_Read-only fusion — wrote nothing to Zoho, Napco, Genesis, True911, or the "
             "Portfolio Registry. Registry changes require the explicit approval workflow._")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _print_summary(report: dict, paths: dict) -> None:
    s = report["summary"]
    print("=" * 72)
    print(f"True911 Portfolio Fusion — READ-ONLY   (tenant: {s.get('tenant')})")
    print("=" * 72)
    cov = s["source_coverage"]
    print(f"  Buildings: {s['buildings']}   fully-fused(4): {s['fully_fused_all_sources']}")
    print(f"  Coverage: zoho={cov['zoho']} napco={cov['napco']} genesis={cov['genesis']} "
          f"true911={cov['true911']}")
    print(f"  Missing True911: {s['buildings_missing_true911']}   E911 unverified: "
          f"{s['buildings_e911_unverified']}   devices not in True911: {s['devices_missing_in_true911']}")
    print(f"  Avg confidence: {s['avg_source_confidence']}")
    print(f"\n  CSV : {paths['csv']}\n  JSON: {paths['json']}\n  MD  : {paths['report']}")
    print("  (Read-only — wrote nothing to any source; E911 never auto-verified.)")


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════
async def _run(args) -> dict:
    from app.database import AsyncSessionLocal

    zoho_rows = []
    if args.zoho_live:
        zoho_rows, _ = await cert.load_zoho_live(args.module, args.fields)
    elif args.zoho_csv:
        zoho_rows, _ = cert.load_zoho_csv(args.zoho_csv)

    napco_records = load_napco_csv(args.napco_csv) if args.napco_csv else []

    if args.genesis_api:
        genesis_rows = load_genesis_api()          # raises clear error (no bulk API)
    else:
        genesis_rows = load_genesis_csv(args.genesis_csv) if args.genesis_csv else []

    async with AsyncSessionLocal() as db:
        true911 = await cert.load_true911(db, args.tenant)
        # READ-ONLY load of the approved Portfolio Registry (unless disabled).
        registry = (_registry.empty_registry(args.tenant) if args.no_registry
                    else await _registry.load_registry(db, args.tenant))
        report = fuse_portfolio(zoho_rows=zoho_rows, napco_records=napco_records,
                                genesis_rows=genesis_rows, true911=true911,
                                tenant=args.tenant, registry=registry)
        # Persist NEW pending review items ONLY on explicit opt-in (writes the review
        # queue, never the approved registry).
        if args.sync_review_queue and report.get("review_items"):
            synced = await _registry.sync_review_queue(db, args.tenant, report["review_items"])
            report["summary"]["review_queue_synced"] = synced
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="True911 Portfolio Fusion Engine (read-only).")
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--zoho-csv", default=None, help="Zoho subscription CSV export")
    ap.add_argument("--zoho-live", action="store_true", help="fetch Zoho live via the existing client")
    ap.add_argument("--module", default="Accounts", help="Zoho module for --zoho-live")
    ap.add_argument("--fields", default=None, help="Zoho field list for --zoho-live")
    ap.add_argument("--napco-csv", default=None, help="Napco StarLink Radiolist export")
    ap.add_argument("--genesis-csv", default=None, help="T-Mobile Genesis / MS130v4 export")
    ap.add_argument("--genesis-api", action="store_true",
                    help="live Genesis mode (needs a seed ICCID list + TAAP creds)")
    ap.add_argument("--no-registry", action="store_true",
                    help="ignore the approved Portfolio Registry (bootstrap / discovery mode)")
    ap.add_argument("--sync-review-queue", action="store_true",
                    help="persist NEW pending review items to the queue (writes the queue "
                         "only, never the approved registry)")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--json", default=DEFAULT_JSON)
    ap.add_argument("--report", default=DEFAULT_REPORT, help="Markdown fusion report path")
    args = ap.parse_args()

    if not any((args.zoho_csv, args.zoho_live, args.napco_csv, args.genesis_csv, args.genesis_api)):
        ap.error("at least one non-True911 source is required "
                 "(--zoho-csv / --zoho-live / --napco-csv / --genesis-csv)")

    try:
        report = asyncio.run(_run(args))
    except FileNotFoundError as exc:
        print(f"ERROR: input file not found — {exc}")
        raise SystemExit(3)
    except Exception as exc:  # DB / Zoho / Genesis-not-configured edge
        print(f"ERROR: fusion failed — {type(exc).__name__}: {exc}")
        raise SystemExit(3)

    paths = {"csv": args.csv, "json": args.json, "report": args.report}
    write_csv(args.csv, report)
    write_json(args.json, report)
    write_markdown_report(args.report, report)
    _print_summary(report, paths)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
