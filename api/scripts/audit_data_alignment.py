#!/usr/bin/env python3
"""Read-only data alignment audit.

Verifies that customers, sites, devices, lines, SIMs and service units are
correctly connected to the right tenant and the right customer / site /
device, and surfaces likely duplicates.

The site → customer link is the ``sites.customer_id`` FK introduced in
Phase 1 and populated by Phase 2 backfill + Phase 3a writers.  The
``sites.customer_name`` column is now a denormalized cache that can drift
after a customer rename; this audit reports both signals so reviewers
can spot drift and any rows still pending backfill.

READ ONLY.  Issues only SELECT statements via the existing app database
session.  Writes nothing to the database.  Does not change schema, tenant
logic, or auth behavior.  Output is CSV + a plain-text summary written
under ``api/reports/``.

Run on Render shell from the api/ directory:

    cd api
    python -m scripts.audit_data_alignment

CSV files written:
    tenant_distribution.csv
    site_customer_alignment.csv
    device_site_alignment.csv
    line_alignment.csv
    duplicate_sites_candidates.csv
    duplicate_devices_candidates.csv
    audit_summary.txt
"""

from __future__ import annotations

import asyncio
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Make ``app.*`` importable from either invocation form (module or script).
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.line import Line  # noqa: E402
from app.models.service_unit import ServiceUnit  # noqa: E402
from app.models.sim import Sim  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402


REPORTS_DIR = Path(_API_DIR) / "reports"


# ─────────────────────────────────────────────────────────────────────
# Normalization helpers (used for duplicate detection only — never to
# rewrite the underlying data).
# ─────────────────────────────────────────────────────────────────────

_STREET_ALIASES = {
    "street": "st",
    "str": "st",
    "avenue": "ave",
    "av": "ave",
    "boulevard": "blvd",
    "road": "rd",
    "drive": "dr",
    "lane": "ln",
    "court": "ct",
    "place": "pl",
    "highway": "hwy",
    "parkway": "pkwy",
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "suite": "ste",
    "apartment": "apt",
    "building": "bldg",
    "floor": "fl",
}

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\D+")


def norm_text(s: str | None) -> str:
    """Lowercase, strip punctuation and collapse whitespace."""
    if not s:
        return ""
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def norm_name(s: str | None) -> str:
    """Normalize a customer or site name for case-insensitive equality."""
    return norm_text(s)


def norm_street(s: str | None) -> str:
    """Normalize a street line by applying common abbreviation aliases."""
    base = norm_text(s)
    if not base:
        return ""
    parts = [_STREET_ALIASES.get(tok, tok) for tok in base.split(" ")]
    return " ".join(parts)


def norm_address(street: str | None, city: str | None, state: str | None, zip_: str | None) -> str:
    """Compose a normalized full-address key for duplicate detection."""
    return "|".join(
        [
            norm_street(street),
            norm_text(city),
            norm_text(state),
            norm_text(zip_),
        ]
    )


def norm_phone(s: str | None) -> str:
    """Strip all non-digit characters from a phone-like value."""
    if not s:
        return ""
    return _DIGITS_RE.sub("", s)


def norm_id(s: str | None) -> str:
    """Trim and lowercase a generic identifier (serial, IMEI, ICCID, etc.)."""
    if not s:
        return ""
    return s.strip().lower()


# ─────────────────────────────────────────────────────────────────────
# CSV writer helper
# ─────────────────────────────────────────────────────────────────────

def _write_csv(name: str, header: list[str], rows: Iterable[list[Any]]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow(["" if v is None else v for v in row])
    return path


def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


# ─────────────────────────────────────────────────────────────────────
# Audit checks
# ─────────────────────────────────────────────────────────────────────

_TENANT_TABLES: list[tuple[str, type]] = [
    ("customers",     Customer),
    ("sites",         Site),
    ("devices",       Device),
    ("lines",         Line),
    ("sims",          Sim),
    ("service_units", ServiceUnit),
    ("users",         User),
]


async def check_tenant_distribution(db) -> tuple[list[str], list[list[Any]], dict[str, dict[str, int]]]:
    """Per-tenant row counts across the seven core tables."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for label, model in _TENANT_TABLES:
        r = await db.execute(
            select(model.tenant_id, func.count()).group_by(model.tenant_id)
        )
        for slug, n in r.all():
            counts[slug or "<NULL>"][label] = int(n or 0)

    # Also pull tenant metadata so we can flag orphan tenant_ids.
    r = await db.execute(select(Tenant.tenant_id, Tenant.name, Tenant.is_active))
    tenants = {row[0]: (row[1], row[2]) for row in r.all()}

    header = ["tenant_id", "tenant_name", "is_active", "in_tenants_table"] + [lbl for lbl, _ in _TENANT_TABLES]
    rows: list[list[Any]] = []
    for slug in sorted(counts.keys()):
        meta = tenants.get(slug)
        rows.append(
            [
                slug,
                meta[0] if meta else "",
                meta[1] if meta else "",
                "yes" if meta else "no",
            ]
            + [counts[slug].get(lbl, 0) for lbl, _ in _TENANT_TABLES]
        )
    # Include tenants that exist but have no rows.
    for slug, (name, active) in sorted(tenants.items()):
        if slug not in counts:
            rows.append([slug, name, active, "yes"] + [0 for _ in _TENANT_TABLES])
    return header, rows, counts


async def check_site_customer_alignment(db) -> tuple[list[str], list[list[Any]], int, dict[str, int]]:
    """For each site, surface alignment issues using the customer_id FK
    as the primary signal and the customer_name cache as a fallback.

    Returns (header, rows, flag_count, linkage_counts).  ``linkage_counts``
    is a histogram over linkage_type values: linked_via_fk |
    linked_via_name_only | unresolved | fk_orphan.
    """
    sites_r = await db.execute(select(Site))
    sites = sites_r.scalars().all()

    customers_r = await db.execute(select(Customer))
    customers = customers_r.scalars().all()

    # Index customers by tenant_id + normalized name and by id.
    by_tenant_name: dict[tuple[str, str], list[Customer]] = defaultdict(list)
    by_id: dict[int, Customer] = {}
    for c in customers:
        by_tenant_name[(c.tenant_id, norm_name(c.name))].append(c)
        by_id[c.id] = c

    header = [
        "site_id",
        "site_pk",
        "site_name",
        "site_tenant_id",
        "customer_name_on_site",
        "site_customer_id",
        "linkage_type",
        "matched_customer_id",
        "matched_customer_name",
        "matched_customer_tenant_id",
        "tenant_mismatch",
        "cache_drift",
        "e911_street",
        "e911_city",
        "e911_state",
        "e911_zip",
        "flags",
    ]
    rows: list[list[Any]] = []
    flag_count = 0
    linkage_counts: dict[str, int] = defaultdict(int)
    for s in sites:
        flags: list[str] = []
        matched_id: Any = ""
        matched_name = ""
        matched_tenant: Any = ""
        tenant_mismatch = ""
        cache_drift = ""
        linkage_type = ""
        site_customer_id = s.customer_id  # may be None

        if site_customer_id is not None:
            # Primary path: site is linked via FK.
            c = by_id.get(site_customer_id)
            if c is None:
                # The FK constraint should prevent this; flag if seen.
                linkage_type = "fk_orphan"
                flags.append("fk_points_to_missing_customer")
            elif c.tenant_id != s.tenant_id:
                # Phase 4 trigger should prevent this; flag for now.
                linkage_type = "fk_orphan"
                matched_id = c.id
                matched_name = c.name
                matched_tenant = c.tenant_id
                tenant_mismatch = "yes"
                flags.append("fk_tenant_mismatch")
            else:
                linkage_type = "linked_via_fk"
                matched_id = c.id
                matched_name = c.name
                matched_tenant = c.tenant_id
                tenant_mismatch = "no"
                # Cache drift: cached customer_name diverges from the
                # canonical name on the linked customer.
                if norm_name(s.customer_name) != norm_name(c.name):
                    cache_drift = "yes"
                    flags.append("cache_drift")
                else:
                    cache_drift = "no"
        else:
            # Fallback path: customer_id IS NULL, fall back to name match.
            if not s.customer_name or not s.customer_name.strip():
                linkage_type = "unresolved"
                flags.append("site_customer_name_missing")
            else:
                cust_list = by_tenant_name.get(
                    (s.tenant_id, norm_name(s.customer_name)), []
                )
                if not cust_list:
                    cross_tenant = [
                        c for c in customers
                        if norm_name(c.name) == norm_name(s.customer_name)
                    ]
                    if cross_tenant:
                        linkage_type = "unresolved"
                        flags.append("customer_match_in_other_tenant")
                        matched_id = ";".join(str(c.id) for c in cross_tenant)
                        matched_tenant = ";".join(c.tenant_id for c in cross_tenant)
                        tenant_mismatch = "yes"
                    else:
                        linkage_type = "unresolved"
                        flags.append("site_customer_name_no_match")
                elif len(cust_list) > 1:
                    linkage_type = "unresolved"
                    flags.append("multiple_customers_match_name")
                    matched_id = ";".join(str(c.id) for c in cust_list)
                    matched_tenant = ";".join(c.tenant_id for c in cust_list)
                    tenant_mismatch = "no"
                else:
                    # Exactly one in-tenant match — would resolve via the
                    # Phase 2 backfill but isn't FK-linked yet.  Still
                    # correctly aligned today; flag for visibility.
                    c = cust_list[0]
                    linkage_type = "linked_via_name_only"
                    matched_id = c.id
                    matched_name = c.name
                    matched_tenant = c.tenant_id
                    tenant_mismatch = "no"
                    flags.append("backfill_pending")

        linkage_counts[linkage_type] += 1
        if flags:
            flag_count += 1

        rows.append(
            [
                s.site_id,
                s.id,
                s.site_name,
                s.tenant_id,
                s.customer_name,
                site_customer_id if site_customer_id is not None else "",
                linkage_type,
                matched_id,
                matched_name,
                matched_tenant,
                tenant_mismatch,
                cache_drift,
                s.e911_street,
                s.e911_city,
                s.e911_state,
                s.e911_zip,
                ";".join(flags),
            ]
        )
    return header, rows, flag_count, linkage_counts


async def check_device_site_alignment(db) -> tuple[list[str], list[list[Any]], int]:
    """For each device, walk to its site and surface tenant / linkage drift."""
    devices_r = await db.execute(select(Device))
    devices = devices_r.scalars().all()

    sites_r = await db.execute(select(Site))
    sites_by_slug = {s.site_id: s for s in sites_r.scalars().all()}

    # Pre-compute identifier counts for "duplicate identifier" flag.
    serial_counts: Counter[str] = Counter()
    starlink_counts: Counter[str] = Counter()
    imei_counts: Counter[str] = Counter()
    iccid_counts: Counter[str] = Counter()
    msisdn_counts: Counter[str] = Counter()
    for d in devices:
        if d.serial_number:
            serial_counts[norm_id(d.serial_number)] += 1
        if d.starlink_id:
            starlink_counts[norm_id(d.starlink_id)] += 1
        if d.imei:
            imei_counts[norm_id(d.imei)] += 1
        if d.iccid:
            iccid_counts[norm_id(d.iccid)] += 1
        if d.msisdn:
            msisdn_counts[norm_phone(d.msisdn)] += 1

    header = [
        "device_id",
        "device_pk",
        "device_type",
        "model",
        "serial_number",
        "starlink_id",
        "imei",
        "iccid",
        "msisdn",
        "device_tenant_id",
        "site_id",
        "site_exists",
        "site_name",
        "site_tenant_id",
        "tenant_mismatch",
        "duplicate_identifier",
        "flags",
    ]
    rows: list[list[Any]] = []
    flag_count = 0
    for d in devices:
        flags: list[str] = []
        site = sites_by_slug.get(d.site_id) if d.site_id else None

        if not d.site_id:
            flags.append("device_no_site")
            site_exists = ""
            site_name = ""
            site_tenant = ""
            tenant_mismatch = ""
        elif site is None:
            flags.append("device_site_id_does_not_exist")
            site_exists = "no"
            site_name = ""
            site_tenant = ""
            tenant_mismatch = ""
        else:
            site_exists = "yes"
            site_name = site.site_name
            site_tenant = site.tenant_id
            if site.tenant_id != d.tenant_id:
                flags.append("device_tenant_differs_from_site")
                tenant_mismatch = "yes"
            else:
                tenant_mismatch = "no"

        dup_fields: list[str] = []
        if d.serial_number and serial_counts[norm_id(d.serial_number)] > 1:
            dup_fields.append("serial_number")
        if d.starlink_id and starlink_counts[norm_id(d.starlink_id)] > 1:
            dup_fields.append("starlink_id")
        if d.imei and imei_counts[norm_id(d.imei)] > 1:
            dup_fields.append("imei")
        if d.iccid and iccid_counts[norm_id(d.iccid)] > 1:
            dup_fields.append("iccid")
        if d.msisdn and msisdn_counts[norm_phone(d.msisdn)] > 1:
            dup_fields.append("msisdn")
        if dup_fields:
            flags.append("duplicate_identifier")

        if flags:
            flag_count += 1

        rows.append(
            [
                d.device_id,
                d.id,
                d.device_type,
                d.model,
                d.serial_number,
                d.starlink_id,
                d.imei,
                d.iccid,
                d.msisdn,
                d.tenant_id,
                d.site_id,
                site_exists,
                site_name,
                site_tenant,
                tenant_mismatch,
                ";".join(dup_fields),
                ";".join(flags),
            ]
        )
    return header, rows, flag_count


async def check_line_alignment(db) -> tuple[list[str], list[list[Any]], int]:
    """For each line, verify site/device existence and tenant alignment."""
    lines_r = await db.execute(select(Line))
    lines = lines_r.scalars().all()

    sites_r = await db.execute(select(Site))
    sites_by_slug = {s.site_id: s for s in sites_r.scalars().all()}

    devices_r = await db.execute(select(Device))
    devices_by_slug = {d.device_id: d for d in devices_r.scalars().all()}

    # Duplicate DID/MSISDN detection (digits-only).
    did_counts: Counter[str] = Counter()
    for ln in lines:
        if ln.did:
            did_counts[norm_phone(ln.did)] += 1

    header = [
        "line_id",
        "line_pk",
        "tenant_id",
        "did",
        "provider",
        "protocol",
        "line_type",
        "customer_id",
        "site_id",
        "site_exists",
        "site_tenant_id",
        "device_id",
        "device_exists",
        "device_tenant_id",
        "tenant_mismatch_with_site",
        "tenant_mismatch_with_device",
        "duplicate_did",
        "flags",
    ]
    rows: list[list[Any]] = []
    flag_count = 0
    for ln in lines:
        flags: list[str] = []

        if not ln.site_id:
            flags.append("line_no_site")
            site_exists = ""
            site_tenant = ""
            site_mismatch = ""
        else:
            site = sites_by_slug.get(ln.site_id)
            if site is None:
                flags.append("line_site_id_does_not_exist")
                site_exists = "no"
                site_tenant = ""
                site_mismatch = ""
            else:
                site_exists = "yes"
                site_tenant = site.tenant_id
                if site.tenant_id != ln.tenant_id:
                    flags.append("line_tenant_differs_from_site")
                    site_mismatch = "yes"
                else:
                    site_mismatch = "no"

        if not ln.device_id:
            flags.append("line_no_device")
            device_exists = ""
            device_tenant = ""
            device_mismatch = ""
        else:
            dev = devices_by_slug.get(ln.device_id)
            if dev is None:
                flags.append("line_device_id_does_not_exist")
                device_exists = "no"
                device_tenant = ""
                device_mismatch = ""
            else:
                device_exists = "yes"
                device_tenant = dev.tenant_id
                if dev.tenant_id != ln.tenant_id:
                    flags.append("line_tenant_differs_from_device")
                    device_mismatch = "yes"
                else:
                    device_mismatch = "no"

        is_dup = bool(ln.did and did_counts[norm_phone(ln.did)] > 1)
        if is_dup:
            flags.append("duplicate_did")

        if flags:
            flag_count += 1

        rows.append(
            [
                ln.line_id,
                ln.id,
                ln.tenant_id,
                ln.did,
                ln.provider,
                ln.protocol,
                ln.line_type,
                ln.customer_id,
                ln.site_id,
                site_exists,
                site_tenant,
                ln.device_id,
                device_exists,
                device_tenant,
                site_mismatch,
                device_mismatch,
                "yes" if is_dup else "no",
                ";".join(flags),
            ]
        )
    return header, rows, flag_count


async def check_duplicate_sites(db) -> tuple[list[str], list[list[Any]], int]:
    """Group likely duplicate sites by several heuristics.

    A "duplicate group" is any cluster of two or more sites that match on
    one of the following keys:
      A. exact normalized customer_name + normalized full address
      B. normalized customer_name + city + state + similar site_name
         (similarity here = identical normalized site_name)
      C. identical normalized full address (regardless of customer_name)
      D. identical normalized site_name (regardless of address)

    Output groups duplicates and recommends a canonical record (lowest id).
    """
    sites_r = await db.execute(select(Site))
    sites = sites_r.scalars().all()

    groups: dict[tuple[str, str], list[Site]] = defaultdict(list)
    for s in sites:
        cust = norm_name(s.customer_name)
        addr = norm_address(s.e911_street, s.e911_city, s.e911_state, s.e911_zip)
        city_state = "|".join([norm_text(s.e911_city), norm_text(s.e911_state)])
        site_name = norm_name(s.site_name)

        if cust and addr and addr != "|||":
            groups[("A_cust+addr", f"{cust}::{addr}")].append(s)
        if cust and city_state and site_name and city_state != "|":
            groups[("B_cust+city+state+name", f"{cust}::{city_state}::{site_name}")].append(s)
        if addr and addr != "|||":
            groups[("C_addr", addr)].append(s)
        if site_name:
            groups[("D_name", site_name)].append(s)

    header = [
        "match_type",
        "match_key",
        "group_size",
        "canonical_site_pk",
        "canonical_site_id",
        "site_pk",
        "site_id",
        "site_name",
        "customer_name",
        "tenant_id",
        "e911_street",
        "e911_city",
        "e911_state",
        "e911_zip",
    ]
    rows: list[list[Any]] = []
    seen_pairs: set[tuple[str, int]] = set()
    group_count = 0
    for (match_type, key), members in groups.items():
        if len(members) < 2:
            continue
        group_count += 1
        canonical = min(members, key=lambda x: x.id)
        for m in members:
            tag = (f"{match_type}::{key}", m.id)
            if tag in seen_pairs:
                continue
            seen_pairs.add(tag)
            rows.append(
                [
                    match_type,
                    key,
                    len(members),
                    canonical.id,
                    canonical.site_id,
                    m.id,
                    m.site_id,
                    m.site_name,
                    m.customer_name,
                    m.tenant_id,
                    m.e911_street,
                    m.e911_city,
                    m.e911_state,
                    m.e911_zip,
                ]
            )
    rows.sort(key=lambda r: (r[0], r[1], r[5]))
    return header, rows, group_count


async def check_duplicate_devices(db) -> tuple[list[str], list[list[Any]], int]:
    """Group devices that share a hardware identifier or model+site identity."""
    devices_r = await db.execute(select(Device))
    devices = devices_r.scalars().all()

    groups: dict[tuple[str, str], list[Device]] = defaultdict(list)
    for d in devices:
        if d.serial_number:
            groups[("serial_number", norm_id(d.serial_number))].append(d)
        if d.starlink_id:
            groups[("starlink_id", norm_id(d.starlink_id))].append(d)
        if d.imei:
            groups[("imei", norm_id(d.imei))].append(d)
        if d.iccid:
            groups[("iccid", norm_id(d.iccid))].append(d)
        if d.msisdn:
            groups[("msisdn", norm_phone(d.msisdn))].append(d)
        if d.model and d.site_id and d.serial_number:
            key = f"{norm_id(d.model)}::{d.site_id}::{norm_id(d.serial_number)}"
            groups[("model+site+serial", key)].append(d)

    header = [
        "match_type",
        "match_key",
        "group_size",
        "canonical_device_pk",
        "canonical_device_id",
        "device_pk",
        "device_id",
        "device_type",
        "model",
        "serial_number",
        "starlink_id",
        "imei",
        "iccid",
        "msisdn",
        "tenant_id",
        "site_id",
    ]
    rows: list[list[Any]] = []
    seen: set[tuple[str, str, int]] = set()
    group_count = 0
    for (match_type, key), members in groups.items():
        if len(members) < 2:
            continue
        group_count += 1
        canonical = min(members, key=lambda x: x.id)
        for d in members:
            tag = (match_type, key, d.id)
            if tag in seen:
                continue
            seen.add(tag)
            rows.append(
                [
                    match_type,
                    key,
                    len(members),
                    canonical.id,
                    canonical.device_id,
                    d.id,
                    d.device_id,
                    d.device_type,
                    d.model,
                    d.serial_number,
                    d.starlink_id,
                    d.imei,
                    d.iccid,
                    d.msisdn,
                    d.tenant_id,
                    d.site_id,
                ]
            )
    rows.sort(key=lambda r: (r[0], r[1], r[5]))
    return header, rows, group_count


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

async def main() -> int:
    started = datetime.now(timezone.utc)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        _banner("True911 data alignment audit  (READ ONLY)")
        print(f"  reports dir: {REPORTS_DIR}")
        print(f"  started:     {started.isoformat()}")

        # ── 1. tenant distribution ────────────────────────────────
        _banner("1. Tenant distribution")
        td_header, td_rows, td_counts = await check_tenant_distribution(db)
        td_path = _write_csv("tenant_distribution.csv", td_header, td_rows)
        print(f"  wrote {td_path.name}  ({len(td_rows)} tenants)")
        print(f"  {'tenant_id':<28} " + "  ".join(f"{lbl:>13}" for lbl, _ in _TENANT_TABLES))
        for row in td_rows:
            slug = row[0]
            data = row[4:]
            print(f"  {slug:<28} " + "  ".join(f"{int(v):>13}" for v in data))

        # ── 2. site → customer alignment ──────────────────────────
        _banner("2. Site → customer alignment")
        sc_header, sc_rows, sc_flags, sc_linkage = await check_site_customer_alignment(db)
        sc_path = _write_csv("site_customer_alignment.csv", sc_header, sc_rows)
        print(f"  wrote {sc_path.name}  ({len(sc_rows)} sites, {sc_flags} flagged)")
        for lt in ("linked_via_fk", "linked_via_name_only", "unresolved", "fk_orphan"):
            n = sc_linkage.get(lt, 0)
            if n:
                print(f"    linkage_type={lt:<22} {n:>6}")

        # ── 3. device → site alignment ────────────────────────────
        _banner("3. Device → site alignment")
        ds_header, ds_rows, ds_flags = await check_device_site_alignment(db)
        ds_path = _write_csv("device_site_alignment.csv", ds_header, ds_rows)
        print(f"  wrote {ds_path.name}  ({len(ds_rows)} devices, {ds_flags} flagged)")

        # ── 4. line → site/device alignment ───────────────────────
        _banner("4. Line → site/device alignment")
        ln_header, ln_rows, ln_flags = await check_line_alignment(db)
        ln_path = _write_csv("line_alignment.csv", ln_header, ln_rows)
        print(f"  wrote {ln_path.name}  ({len(ln_rows)} lines, {ln_flags} flagged)")

        # ── 5. duplicate sites ────────────────────────────────────
        _banner("5. Duplicate site candidates")
        dups_header, dups_rows, dups_groups = await check_duplicate_sites(db)
        dups_path = _write_csv("duplicate_sites_candidates.csv", dups_header, dups_rows)
        print(f"  wrote {dups_path.name}  ({dups_groups} duplicate groups, {len(dups_rows)} rows)")

        # ── 6. duplicate devices ──────────────────────────────────
        _banner("6. Duplicate device candidates")
        dupd_header, dupd_rows, dupd_groups = await check_duplicate_devices(db)
        dupd_path = _write_csv("duplicate_devices_candidates.csv", dupd_header, dupd_rows)
        print(f"  wrote {dupd_path.name}  ({dupd_groups} duplicate groups, {len(dupd_rows)} rows)")

        # ── 7. summary file ───────────────────────────────────────
        finished = datetime.now(timezone.utc)
        summary_lines: list[str] = [
            "True911 data alignment audit  (READ ONLY)",
            f"started:  {started.isoformat()}",
            f"finished: {finished.isoformat()}",
            f"duration: {(finished - started).total_seconds():.2f}s",
            "",
            "Tenant distribution",
            "-------------------",
        ]
        # totals
        totals: dict[str, int] = defaultdict(int)
        for slug_counts in td_counts.values():
            for lbl, n in slug_counts.items():
                totals[lbl] += n
        for lbl, _ in _TENANT_TABLES:
            summary_lines.append(f"  {lbl:<14} total = {totals.get(lbl, 0)}")
        summary_lines += [
            "",
            "Site → customer linkage (post-Phase 3a)",
            "---------------------------------------",
            f"  linked_via_fk          : {sc_linkage.get('linked_via_fk', 0)}",
            f"  linked_via_name_only   : {sc_linkage.get('linked_via_name_only', 0)}  (backfill pending)",
            f"  unresolved             : {sc_linkage.get('unresolved', 0)}",
            f"  fk_orphan              : {sc_linkage.get('fk_orphan', 0)}",
            "",
            "Alignment flags",
            "----------------",
            f"  sites flagged    : {sc_flags}",
            f"  devices flagged  : {ds_flags}",
            f"  lines flagged    : {ln_flags}",
            "",
            "Duplicate candidates",
            "--------------------",
            f"  duplicate site groups   : {dups_groups}",
            f"  duplicate device groups : {dupd_groups}",
            "",
            "Output files",
            "------------",
            f"  {td_path.name}",
            f"  {sc_path.name}",
            f"  {ds_path.name}",
            f"  {ln_path.name}",
            f"  {dups_path.name}",
            f"  {dupd_path.name}",
            "",
            "Notes",
            "-----",
            "  - Read only.  No data was modified.",
            "  - Site→customer link is the customer_id FK (Phase 1).  sites.customer_name is",
            "    a denormalized cache; the cache_drift flag marks rows where it diverges from",
            "    the canonical customers.name.",
            "  - linked_via_name_only rows have customer_id=NULL but resolve to one in-tenant",
            "    customer; they are correctly aligned today and will be FK-linked once the",
            "    Phase 2 backfill is re-run for them.",
            "  - fk_orphan rows are unexpected — the FK constraint should prevent missing",
            "    targets, and the Phase 4 trigger should prevent tenant drift; investigate.",
            "  - Duplicate detection uses normalized text/phone keys; review before any merges.",
        ]
        summary_path = REPORTS_DIR / "audit_summary.txt"
        summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

        _banner("Summary")
        print("\n".join(summary_lines))
        print()
        print(f"  wrote {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
