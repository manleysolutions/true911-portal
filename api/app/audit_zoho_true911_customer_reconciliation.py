"""Zoho CRM ↔ True911 customer reconciliation audit (READ-ONLY).

Compares the staged Zoho CRM lifecycle data (the ``zoho_subscription_records``
mirror + ``external_record_map``) against True911 customer / site / device / line
data, customer-by-customer, so an operator can find setup/status mismatches
BEFORE any automated Zoho→True911 sync is enabled.

Strictly READ-ONLY:
  * Only SELECTs — never writes customers/sites/devices/lines/subscriptions or
    any staging table.
  * No backfill, no import, no automation, no webhook/auth changes, no schema
    change, no migration.
  * ``--export-json`` / ``--export-csv`` write an operator-requested report file
    (an artifact, never a production-data change).

Source of Zoho data is the STAGED mirror already populated by the gated webhook
ingest (``zoho_subscription_records``) — this audit does NOT call the live Zoho
API. Lifecycle is derived with the existing pure normalizer so it works even
when ``lifecycle_state`` was never populated (normalizer flag off).

Run:
    python -m app.audit_zoho_true911_customer_reconciliation --customer "Webber"
    python -m app.audit_zoho_true911_customer_reconciliation --all
    python -m app.audit_zoho_true911_customer_reconciliation --all \
        --export-json /tmp/zoho_recon.json --export-csv /tmp/zoho_recon.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.zoho_status_normalizer import (  # noqa: E402
    ACTIVE, DEACTIVATED, normalize_activation_status,
)

# ── Classifications (task 5) ─────────────────────────────────────────────
MATCHED_OK = "matched_ok"
MISSING_IN_TRUE911 = "missing_in_true911"
MISSING_IN_ZOHO = "missing_in_zoho"
STATUS_MISMATCH = "status_mismatch"
IDENTIFIER_MISMATCH = "identifier_mismatch"
NEEDS_MAPPING = "needs_mapping"
DUPLICATE_CANDIDATE = "duplicate_candidate"
DEACT_ZOHO_ACTIVE_T911 = "deactivated_in_zoho_active_in_true911"
ACTIVE_ZOHO_INACTIVE_T911 = "active_in_zoho_inactive_in_true911"

CLASSIFICATIONS = (
    MATCHED_OK, MISSING_IN_TRUE911, MISSING_IN_ZOHO, STATUS_MISMATCH,
    IDENTIFIER_MISMATCH, NEEDS_MAPPING, DUPLICATE_CANDIDATE,
    DEACT_ZOHO_ACTIVE_T911, ACTIVE_ZOHO_INACTIVE_T911,
)

# True911 device/line statuses that count as "active / monitored".
_ACTIVE_DEVICE_STATES = frozenset({"active", "provisioning"})
_ACTIVE_LINE_STATES = frozenset({"active", "provisioning"})


# ── pure helpers (unit-tested, no DB) ────────────────────────────────────
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_NAME_SUFFIXES = ("inc", "llc", "lp", "corp", "co", "company", "ltd", "infra",
                  "infrastructure")


def normalize_name(s: Optional[str]) -> str:
    """Lowercase, strip punctuation + trailing legal/common suffix tokens."""
    if not s:
        return ""
    toks = [t for t in _NON_ALNUM.sub(" ", str(s).lower()).split() if t]
    while toks and toks[-1] in _NAME_SUFFIXES:
        toks.pop()
    return " ".join(toks)


def name_matches(query: Optional[str], name: Optional[str]) -> bool:
    """Fuzzy customer-name match: normalized substring either direction."""
    q, n = normalize_name(query), normalize_name(name)
    if not q or not n:
        return False
    return q in n or n in q


def normalize_msisdn(s: Optional[str]) -> str:
    """Digits only; US 11-digit '1NXXNXXXXXX' collapses to the 10-digit form."""
    if not s:
        return ""
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def normalize_iccid(s: Optional[str]) -> str:
    """Digits only, dropping a trailing 'F' pad. Local copy — independent of
    any NAPCO/RH audit module."""
    if not s:
        return ""
    t = str(s).strip()
    if t and t[-1] in ("F", "f"):
        t = t[:-1]
    return "".join(ch for ch in t if ch.isdigit())


def derive_zoho_lifecycle(zrec: dict) -> str:
    """Canonical lifecycle for a Zoho staging record.

    Prefers the normalized ``lifecycle_state`` column when present; otherwise
    derives it from the raw ``device_activation_status`` so the audit works
    regardless of whether the normalizer flag was ever enabled.
    """
    ls = (zrec.get("lifecycle_state") or "").strip().lower()
    if ls:
        return ls
    return normalize_activation_status(zrec.get("device_activation_status"))


def true911_presents_active(t911: dict) -> bool:
    """Does True911 currently treat this customer as active / monitored?

    True when the tenant is active AND (the customer status is active, or any
    device/line is in an active state). Deactivated tenants are never active.
    """
    tenant = t911.get("tenant") or {}
    if tenant.get("is_active") is False:
        return False
    cust = t911.get("customer") or {}
    cust_active = (cust.get("status") or "").strip().lower() == "active"
    dev_active = any((d.get("status") or "").strip().lower() in _ACTIVE_DEVICE_STATES
                     for d in t911.get("devices", []))
    line_active = any((l.get("status") or "").strip().lower() in _ACTIVE_LINE_STATES
                      for l in t911.get("lines", []))
    return bool(cust_active or dev_active or line_active)


@dataclass(frozen=True)
class Finding:
    classification: str
    scope: str              # customer | msisdn | site | device | mapping
    key: str                # the identifier this finding is about
    detail: str
    zoho: dict = field(default_factory=dict)
    true911: dict = field(default_factory=dict)


@dataclass
class CustomerReconciliation:
    query: str
    matched_customer_name: Optional[str]
    tenant_id: Optional[str]
    zoho_record_count: int
    true911_device_count: int
    true911_line_count: int
    findings: list
    summary: dict


def _t911_msisdn_entities(t911: dict) -> list[dict]:
    """Flatten device + line MSISDN-bearing entities for matching."""
    out: list[dict] = []
    for d in t911.get("devices", []):
        m = normalize_msisdn(d.get("msisdn"))
        if m:
            out.append({"kind": "device", "id": d.get("device_id"), "msisdn": m,
                        "status": d.get("status"), "raw": d})
    for l in t911.get("lines", []):
        m = normalize_msisdn(l.get("did"))
        if m:
            out.append({"kind": "line", "id": l.get("line_id"), "msisdn": m,
                        "status": l.get("status"), "raw": l})
    return out


def reconcile_customer(query: str, zoho_records: list[dict], t911: dict) -> CustomerReconciliation:
    """Pure reconciliation engine for one customer. No DB, no I/O.

    ``zoho_records`` — list of dicts from ``zoho_subscription_records`` (+ the
    record's ``map_status`` from external_record_map).
    ``t911`` — {customer, tenant, sites, devices, lines}.
    """
    findings: list[Finding] = []
    cust = t911.get("customer") or {}
    tenant = t911.get("tenant") or {}
    matched_name = cust.get("name") or tenant.get("name") or tenant.get("tenant_id")
    tenant_id = tenant.get("tenant_id") or cust.get("tenant_id")
    t911_has_entities = bool(t911.get("devices") or t911.get("lines")
                             or t911.get("sites") or cust)

    # ── mapping resolution (needs_mapping) ──
    if zoho_records and not t911_has_entities:
        findings.append(Finding(
            NEEDS_MAPPING, "customer", query,
            "Zoho records exist but no True911 customer/tenant resolves by name",
            zoho={"account_names": sorted({z.get("account_name") for z in zoho_records if z.get("account_name")})}))
    for z in zoho_records:
        ms = (z.get("map_status") or "unmapped").strip().lower()
        if ms != "confirmed":
            findings.append(Finding(
                NEEDS_MAPPING, "mapping", z.get("subscription_mgmt_id") or "<no-id>",
                f"Zoho subscription mapping is '{ms}' (not confirmed) — operator must confirm",
                zoho={"subscription_mgmt_id": z.get("subscription_mgmt_id"),
                      "account_name": z.get("account_name"), "map_status": ms}))

    # ── customer-level cross-axis (the headline: Webber case) ──
    zoho_states = [derive_zoho_lifecycle(z) for z in zoho_records]
    has_zoho_active = ACTIVE in zoho_states
    has_zoho_deact = DEACTIVATED in zoho_states
    t911_active = true911_presents_active(t911)
    if zoho_records:
        if (not has_zoho_active) and has_zoho_deact and t911_active:
            findings.append(Finding(
                DEACT_ZOHO_ACTIVE_T911, "customer", matched_name or query,
                "Zoho lifecycle is De-activated but True911 still treats this "
                "customer as active/monitored",
                zoho={"lifecycle": DEACTIVATED, "states": zoho_states},
                true911={"presents_active": True,
                         "tenant_active": tenant.get("is_active"),
                         "customer_status": cust.get("status")}))
        elif has_zoho_active and not t911_active:
            findings.append(Finding(
                ACTIVE_ZOHO_INACTIVE_T911, "customer", matched_name or query,
                "Zoho lifecycle is Active but True911 shows the customer as "
                "inactive/not monitored",
                zoho={"lifecycle": ACTIVE, "states": zoho_states},
                true911={"presents_active": False,
                         "tenant_active": tenant.get("is_active"),
                         "customer_status": cust.get("status")}))
        elif has_zoho_active and t911_active:
            findings.append(Finding(
                MATCHED_OK, "customer", matched_name or query,
                "Zoho active and True911 active — lifecycle/operational aligned"))
        elif (not has_zoho_active) and t911_has_entities and not t911_active:
            findings.append(Finding(
                MATCHED_OK, "customer", matched_name or query,
                "Zoho not-active and True911 not-active — aligned"))

    # ── per-MSISDN reconciliation ──
    t911_entities = _t911_msisdn_entities(t911)
    by_msisdn: dict[str, list] = {}
    for e in t911_entities:
        by_msisdn.setdefault(e["msisdn"], []).append(e)
    zoho_msisdn_counts = Counter(
        normalize_msisdn(z.get("msisdn")) for z in zoho_records if normalize_msisdn(z.get("msisdn")))

    for z in zoho_records:
        m = normalize_msisdn(z.get("msisdn"))
        if not m:
            continue
        zstate = derive_zoho_lifecycle(z)
        if zoho_msisdn_counts[m] > 1:
            findings.append(Finding(
                DUPLICATE_CANDIDATE, "msisdn", m,
                f"MSISDN appears on {zoho_msisdn_counts[m]} Zoho subscription records",
                zoho={"subscription_mgmt_id": z.get("subscription_mgmt_id")}))
        matches = by_msisdn.get(m, [])
        if len(matches) == 0:
            findings.append(Finding(
                MISSING_IN_TRUE911, "msisdn", m,
                "Zoho has this MSISDN but no True911 device/line carries it",
                zoho={"account_name": z.get("account_name"), "lifecycle": zstate}))
        elif len(matches) > 1:
            findings.append(Finding(
                DUPLICATE_CANDIDATE, "msisdn", m,
                f"MSISDN matches {len(matches)} True911 entities (ambiguous)",
                true911={"entities": [f"{e['kind']}:{e['id']}" for e in matches]}))
        else:
            ent = matches[0]
            ent_active = (ent.get("status") or "").strip().lower() in _ACTIVE_DEVICE_STATES
            if zstate == DEACTIVATED and ent_active:
                findings.append(Finding(
                    STATUS_MISMATCH, "msisdn", m,
                    "Zoho De-activated but the matched True911 entity is active",
                    zoho={"lifecycle": zstate},
                    true911={"entity": f"{ent['kind']}:{ent['id']}", "status": ent.get("status")}))
            elif zstate == ACTIVE and not ent_active:
                findings.append(Finding(
                    STATUS_MISMATCH, "msisdn", m,
                    "Zoho Active but the matched True911 entity is not active",
                    zoho={"lifecycle": zstate},
                    true911={"entity": f"{ent['kind']}:{ent['id']}", "status": ent.get("status")}))
            else:
                findings.append(Finding(
                    MATCHED_OK, "msisdn", m,
                    "MSISDN matched and status aligned",
                    true911={"entity": f"{ent['kind']}:{ent['id']}"}))

    # ── True911 MSISDNs absent from Zoho ──
    zoho_norm_set = {m for m in zoho_msisdn_counts}
    for e in t911_entities:
        if e["msisdn"] not in zoho_norm_set:
            findings.append(Finding(
                MISSING_IN_ZOHO, "msisdn", e["msisdn"],
                f"True911 {e['kind']} {e['id']} has an MSISDN with no Zoho record",
                true911={"entity": f"{e['kind']}:{e['id']}", "status": e.get("status")}))

    # ── facility / site presence ──
    t911_site_names = {normalize_name(s.get("site_name")) for s in t911.get("sites", [])}
    for z in zoho_records:
        fac = normalize_name(z.get("facility_name"))
        if fac and t911_site_names and fac not in t911_site_names \
                and not any(fac in sn or sn in fac for sn in t911_site_names if sn):
            findings.append(Finding(
                MISSING_IN_TRUE911, "site", z.get("facility_name") or "<facility>",
                "Zoho FacilityName has no matching True911 site",
                zoho={"facility_name": z.get("facility_name")}))

    summary = dict(Counter(f.classification for f in findings))
    return CustomerReconciliation(
        query=query, matched_customer_name=matched_name, tenant_id=tenant_id,
        zoho_record_count=len(zoho_records),
        true911_device_count=len(t911.get("devices", [])),
        true911_line_count=len(t911.get("lines", [])),
        findings=findings, summary=summary,
    )


# ── report assembly / export ─────────────────────────────────────────────
def to_dict(rec: CustomerReconciliation) -> dict:
    return {
        "query": rec.query,
        "matched_customer_name": rec.matched_customer_name,
        "tenant_id": rec.tenant_id,
        "zoho_record_count": rec.zoho_record_count,
        "true911_device_count": rec.true911_device_count,
        "true911_line_count": rec.true911_line_count,
        "summary": rec.summary,
        "findings": [asdict(f) for f in rec.findings],
    }


def overall_summary(recs: list[CustomerReconciliation]) -> dict:
    total = Counter()
    for r in recs:
        total.update(r.summary)
    return {c: total.get(c, 0) for c in CLASSIFICATIONS}


def write_json(recs: list[CustomerReconciliation], path: str) -> None:
    doc = {"read_only": True, "overall_summary": overall_summary(recs),
           "customers": [to_dict(r) for r in recs]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False, default=str)


def write_csv(recs: list[CustomerReconciliation], path: str) -> int:
    rows = 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["customer", "tenant_id", "classification", "scope", "key", "detail"])
        for r in recs:
            for f in r.findings:
                w.writerow([r.matched_customer_name or r.query, r.tenant_id or "",
                            f.classification, f.scope, f.key, f.detail])
                rows += 1
    return rows


# ── customer-scoped ownership (pure, unit-tested) ────────────────────────
def scope_true911_by_customer(
    query: str, customers: list[dict], sites: list[dict],
    devices: list[dict], lines: list[dict],
) -> dict:
    """Scope a customer's True911 footprint by OWNERSHIP, not by tenant.

    Customer -> Sites (``sites.customer_id``) -> Devices (``devices.site_id``).
    Lines belong to the customer by ``customer_id`` OR by owning a scoped site.
    Devices have no ``customer_id``, so they are reached only through their site.

    Why: a shared tenant (e.g. ``default``) holds many customers' data, so
    tenant-scoping over-counts (the Webber bug: 177 devices were the whole
    ``default`` tenant).  Here, in a SHARED tenant only explicit customer links
    count — other customers' devices are never attributed.

    Safe dedicated-tenant handling: when the matched customer is the SOLE
    customer of its tenant, rows with no explicit customer link in that tenant
    are adopted (they can only belong to that one customer) — so a dedicated
    tenant whose sites lack ``customer_id`` still reports its full footprint.
    """
    customers = customers or []
    matched = [c for c in customers if name_matches(query, c.get("name"))]
    if not matched:
        return {"customer": {}, "tenant": {}, "sites": [], "devices": [],
                "lines": [], "matched_customer_ids": [], "matched_customer_count": 0}

    cust_ids = {c.get("id") for c in matched}
    matched_tenants = {c.get("tenant_id") for c in matched}
    per_tenant = Counter(c.get("tenant_id") for c in customers)
    sole_tenants = {t for t in matched_tenants if per_tenant.get(t) == 1}

    def _site_owned(s: dict) -> bool:
        if s.get("customer_id") in cust_ids:
            return True
        return not s.get("customer_id") and s.get("tenant_id") in sole_tenants

    scoped_sites = [s for s in (sites or []) if _site_owned(s)]
    site_ids = {s.get("site_id") for s in scoped_sites}
    scoped_devices = [
        d for d in (devices or [])
        if d.get("site_id") in site_ids
        or (not d.get("site_id") and d.get("tenant_id") in sole_tenants)
    ]
    scoped_lines = [
        l for l in (lines or [])
        if l.get("customer_id") in cust_ids
        or l.get("site_id") in site_ids
        or (not l.get("customer_id") and not l.get("site_id")
            and l.get("tenant_id") in sole_tenants)
    ]

    primary = matched[0]
    return {
        "customer": {"name": primary.get("name"), "status": primary.get("status"),
                     "tenant_id": primary.get("tenant_id"),
                     "zoho_account_id": primary.get("zoho_account_id"),
                     "onboarding_status": primary.get("onboarding_status")},
        "tenant": {"tenant_id": primary.get("tenant_id")},
        "sites": scoped_sites, "devices": scoped_devices, "lines": scoped_lines,
        "matched_customer_ids": sorted(i for i in cust_ids if i is not None),
        "matched_customer_count": len(matched),
    }


# ── DB load (READ-ONLY) ──────────────────────────────────────────────────
async def _load_zoho_records(db, query: Optional[str]) -> list[dict]:
    from sqlalchemy import select
    from app.models.zoho_subscription_record import ZohoSubscriptionRecord
    from app.models.external_record_map import ExternalRecordMap

    recs = (await db.execute(select(ZohoSubscriptionRecord))).scalars().all()
    # map_status lookup keyed by external_record_map_id.
    maps = {m.id: m.map_status for m in
            (await db.execute(select(ExternalRecordMap))).scalars().all()}
    out = []
    for z in recs:
        if query and not (name_matches(query, z.account_name)
                          or name_matches(query, z.facility_name)):
            continue
        out.append({
            "subscription_mgmt_id": z.subscription_mgmt_id,
            "account_name": z.account_name, "facility_name": z.facility_name,
            "msisdn": z.msisdn, "device_activation_status": z.device_activation_status,
            "lifecycle_state": z.lifecycle_state, "connection_type": z.connection_type,
            "subscription_type": z.subscription_type,
            "map_status": maps.get(z.external_record_map_id, "unmapped"),
        })
    return out


_EMPTY_T911 = {"customer": {}, "tenant": {}, "sites": [], "devices": [], "lines": []}


async def _load_true911(db, query: Optional[str]) -> dict:
    """Load a customer's True911 footprint scoped by OWNERSHIP (customer -> sites
    -> devices), NOT by tenant. READ-ONLY."""
    from sqlalchemy import select
    from app.models.customer import Customer
    from app.models.tenant import Tenant
    from app.models.site import Site
    from app.models.device import Device
    from app.models.line import Line

    if not query:
        return dict(_EMPTY_T911)

    customers = [{
        "id": c.id, "name": c.name, "status": c.status, "tenant_id": c.tenant_id,
        "zoho_account_id": c.zoho_account_id, "onboarding_status": c.onboarding_status,
    } for c in (await db.execute(select(Customer))).scalars().all()]

    matched = [c for c in customers if name_matches(query, c["name"])]
    if not matched:
        # No customer by name — fall back to a tenant-name match (legacy: a
        # dedicated tenant with no Customer row, devices directly under it).
        tenant = next((t for t in (await db.execute(select(Tenant))).scalars().all()
                       if name_matches(query, t.name) or name_matches(query, t.display_name)
                       or name_matches(query, t.tenant_id)), None)
        return await _load_tenant_scoped(db, tenant) if tenant else dict(_EMPTY_T911)

    tenant_ids = {c["tenant_id"] for c in matched}
    sites = [{"site_id": s.site_id, "site_name": s.site_name, "status": s.status,
              "customer_id": s.customer_id, "tenant_id": s.tenant_id}
             for s in (await db.execute(
                 select(Site).where(Site.tenant_id.in_(tenant_ids)))).scalars().all()]
    devices = [{"device_id": d.device_id, "site_id": d.site_id, "status": d.status,
                "model": d.model, "iccid": d.iccid, "msisdn": d.msisdn,
                "network_status": d.network_status, "tenant_id": d.tenant_id}
               for d in (await db.execute(
                   select(Device).where(Device.tenant_id.in_(tenant_ids)))).scalars().all()]
    lines = [{"line_id": l.line_id, "site_id": l.site_id, "status": l.status,
              "did": l.did, "sim_iccid": l.sim_iccid, "customer_id": l.customer_id,
              "tenant_id": l.tenant_id}
             for l in (await db.execute(
                 select(Line).where(Line.tenant_id.in_(tenant_ids)))).scalars().all()]

    scoped = scope_true911_by_customer(query, customers, sites, devices, lines)
    # Attach tenant name / is_active for the primary customer's tenant (reference).
    primary_tid = scoped["customer"].get("tenant_id")
    tobj = (await db.execute(
        select(Tenant).where(Tenant.tenant_id == primary_tid))).scalar_one_or_none() \
        if primary_tid else None
    scoped["tenant"] = {"tenant_id": primary_tid, "name": getattr(tobj, "name", None),
                        "is_active": getattr(tobj, "is_active", None)}
    return scoped


async def _load_tenant_scoped(db, tenant) -> dict:
    """Legacy fallback: scope by tenant when no Customer row matches the name
    (a dedicated tenant with devices directly under it)."""
    from sqlalchemy import select
    from app.models.site import Site
    from app.models.device import Device
    from app.models.line import Line

    tid = tenant.tenant_id
    sites = (await db.execute(select(Site).where(Site.tenant_id == tid))).scalars().all()
    devices = (await db.execute(select(Device).where(Device.tenant_id == tid))).scalars().all()
    lines = (await db.execute(select(Line).where(Line.tenant_id == tid))).scalars().all()
    return {
        "customer": {"tenant_id": tid},
        "tenant": {"tenant_id": tid, "name": tenant.name, "is_active": tenant.is_active},
        "sites": [{"site_id": s.site_id, "site_name": s.site_name, "status": s.status} for s in sites],
        "devices": [{"device_id": d.device_id, "site_id": d.site_id, "status": d.status,
                     "model": d.model, "iccid": d.iccid, "msisdn": d.msisdn,
                     "network_status": d.network_status} for d in devices],
        "lines": [{"line_id": l.line_id, "site_id": l.site_id, "status": l.status,
                   "did": l.did, "sim_iccid": l.sim_iccid} for l in lines],
    }


def _distinct_queries(db_zoho: list[dict]) -> list[str]:
    return sorted({z.get("account_name") for z in db_zoho if z.get("account_name")})


async def run(*, customers: list[str], do_all: bool,
              export_json: Optional[str], export_csv: Optional[str]) -> list:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        queries = list(customers)
        if do_all:
            all_zoho = await _load_zoho_records(db, None)
            queries = sorted(set(queries) | set(_distinct_queries(all_zoho)))
        if not queries:
            print("No --customer or --all given. Nothing to reconcile.")
            return []
        recs = []
        for q in queries:
            zoho = await _load_zoho_records(db, q)
            t911 = await _load_true911(db, q)
            recs.append(reconcile_customer(q, zoho, t911))

    _print(recs)
    if export_json:
        write_json(recs, export_json)
        print(f"\n  Wrote JSON report -> {export_json}")
    if export_csv:
        n = write_csv(recs, export_csv)
        print(f"  Wrote {n} finding rows (CSV) -> {export_csv}")
    return recs


def _print(recs: list) -> None:
    print("=" * 78)
    print("Zoho CRM ↔ True911 — Customer Reconciliation Audit  (READ-ONLY)")
    print("=" * 78)
    for r in recs:
        print(f"\n### {r.matched_customer_name or r.query}  (tenant={r.tenant_id or '—'})")
        print(f"    zoho_records={r.zoho_record_count}  "
              f"true911_devices={r.true911_device_count}  lines={r.true911_line_count}")
        if not r.findings:
            print("    (no findings)")
        for f in r.findings:
            print(f"    [{f.classification}] {f.scope}:{f.key} — {f.detail}")
    print("\n--- OVERALL SUMMARY ---")
    for c, n in overall_summary(recs).items():
        print(f"  {c:<42}: {n}")
    print("\n  (Findings only — this audit writes nothing to the database.)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Zoho↔True911 customer reconciliation audit.")
    parser.add_argument("--customer", action="append", default=[],
                        help="customer name to reconcile (repeatable)")
    parser.add_argument("--all", dest="do_all", action="store_true",
                        help="reconcile every customer found in the Zoho staging mirror")
    parser.add_argument("--export-json", dest="export_json", help="write JSON report")
    parser.add_argument("--export-csv", dest="export_csv", help="write CSV report")
    args = parser.parse_args()
    try:
        asyncio.run(run(customers=args.customer, do_all=args.do_all,
                        export_json=args.export_json, export_csv=args.export_csv))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
