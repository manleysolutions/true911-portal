"""Customer Portfolio-Registry read model (READ-ONLY).

Renders the customer dashboard + Location/Building Workspace from the APPROVED
Portfolio Registry (canonical ``PortfolioBuilding`` rows) instead of raw ``Site``
rows.  A canonical building is linked to its True911 Site(s) — by an approved
``true911_device`` mapping, else store number, else address — and the customer-safe
operational / E911 / health facts are DERIVED from those sites (reusing the mature
assurance + service-inference logic).  Aliases and every source-system internal
(Zoho / Napco / Genesis ids, ICCID, IMEI, radio numbers, review payloads) are never
exposed.

Gating (all default OFF):
  * ``FEATURE_CUSTOMER_PORTFOLIO_REGISTRY`` + ``CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST``
    — turn on registry-backed mode for a tenant (two-key, mirrors the customer API gate).
  * ``CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS`` — also show high-confidence,
    customer-safe PENDING (unapproved) buildings to the customer.
  * ``CUSTOMER_PORTFOLIO_PREVIEW_PENDING`` + ``CUSTOMER_PORTFOLIO_PREVIEW_TENANT_ALLOWLIST``
    — internal RH pre-go-live: the test user previews ALL (approved + pending) buildings.

If registry mode is on but there are no VISIBLE buildings yet, the loaders return
``None`` so the caller falls back to the legacy Site path — the customer never sees
fallback language; the reason is logged internally only.

STRICTLY READ-ONLY: never writes the registry or any source, never auto-creates
Sites, never marks E911 verified, never fabricates data.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.customer import command_center as cc
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs
from app.services.customer.refs import decode_ref, encode_ref

logger = logging.getLogger("customer.portfolio_registry_view")

_VERIFIED_E911 = frozenset({"validated", "verified", "confirmed"})
_HIGH_CONFIDENCE = 80.0
# combine per-site protection into a building status (worst-of wins)
_PROT_RANK = {"Critical": 0, "Attention Needed": 1, "Pending Install": 2,
              "Unknown": 3, "Inactive": 4, "Protected": 5}


# ── mode gating (two-key, mirrors preview.py) ────────────────────────
def registry_mode_enabled(tenant_id) -> bool:
    return (settings.FEATURE_CUSTOMER_PORTFOLIO_REGISTRY == "true"
            and tenant_id in settings.customer_portfolio_registry_tenant_id_set)


def preview_pending_enabled(tenant_id) -> bool:
    return (settings.CUSTOMER_PORTFOLIO_PREVIEW_PENDING == "true"
            and tenant_id in settings.customer_portfolio_preview_tenant_id_set)


def show_pending_enabled() -> bool:
    return settings.CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS == "true"


def _include_pending(tenant_id) -> bool:
    return show_pending_enabled() or preview_pending_enabled(tenant_id)


# ── customer-visible building assembly ───────────────────────────────
async def _visible_building_rows(db, tenant_id):
    from app.models.portfolio_registry import PortfolioBuilding
    rows = (await db.execute(
        select(PortfolioBuilding).where(PortfolioBuilding.tenant_id == tenant_id))).scalars().all()
    include_pending = _include_pending(tenant_id)
    out = []
    for b in rows:
        if b.approved:
            out.append((b, False))
        elif include_pending:
            out.append((b, True))               # pending, shown only under a flag
    return out


async def _link_indexes(db, tenant_id, sites_portfolio):
    """Build the building→site linkage indexes from the approved device mappings and
    from store#/address, all tenant-scoped and read-only."""
    from app.models.portfolio_registry import PortfolioDeviceMapping

    site_by_id, by_store, by_addr = {}, {}, {}
    for site, protection in sites_portfolio:
        site_by_id[site.site_id] = (site, protection)
        st = _site_store_number(site.site_name)
        if st:
            by_store.setdefault(st, []).append(site.site_id)
        a = cs_norm_addr(site)
        if a:
            by_addr.setdefault(a, []).append(site.site_id)

    dev_site = {}      # normalized true911_device value -> site_id (identity mapping)
    for m in (await db.execute(
        select(PortfolioDeviceMapping).where(
            PortfolioDeviceMapping.tenant_id == tenant_id))).scalars().all():
        if m.active and m.kind == "true911_device":
            dev_site[m.value_normalized] = (m.building_id, m.value)
    return site_by_id, by_store, by_addr, dev_site


def cs_norm_addr(site) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ",
                  f"{site.e911_street or ''} {site.e911_city or ''} {site.e911_state or ''}".lower()).strip()


def _site_store_number(name) -> str | None:
    import re
    m = re.search(r"#\s*0*(\d{1,4})\b", name or "")
    if m:
        return m.group(1)
    m = re.search(r"\brh\b[\s\-#]*0*(\d{1,4})", (name or "").lower())
    return m.group(1) if m else None


def _norm_id(v) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def _combine_protection(protections, now):
    if not protections:
        return cs.status_object("Unknown", as_of=now.isoformat())
    worst = min(protections, key=lambda p: _PROT_RANK.get(p.get("status"), 3))
    return worst


async def load_customer_buildings(db: AsyncSession, tenant_id: str, now):
    """Approved (+ optionally pending) canonical buildings for the tenant, each with
    derived customer-safe operational/E911/health facts.  Returns ``None`` when
    registry mode is off OR there are no visible buildings (→ legacy fallback)."""
    if not registry_mode_enabled(tenant_id):
        return None
    rows = await _visible_building_rows(db, tenant_id)
    if not rows:
        logger.info("portfolio_registry_view: tenant=%s registry mode ON but 0 visible "
                    "buildings — falling back to legacy Site path (internal only).", tenant_id)
        return None

    sites_portfolio = await cportfolio.load_portfolio(db, tenant_id, now)
    site_by_id, by_store, by_addr, dev_site = await _link_indexes(db, tenant_id, sites_portfolio)

    records = []
    for b, pending in rows:
        site_ids = _resolve_building_site_ids(b, by_store, by_addr, dev_site)
        linked = [site_by_id[sid] for sid in site_ids if sid in site_by_id]
        records.append(await _aggregate_building(db, tenant_id, b, pending, linked, now))
    return records


def _resolve_building_site_ids(b, by_store, by_addr, dev_site) -> set:
    ids = set()
    for norm_val, (bid, raw) in dev_site.items():
        if bid == b.id:
            ids.add(raw)                        # true911_device mapping names the site_id
    if b.store_number:
        ids.update(by_store.get(str(b.store_number), []))
    a = _norm_addr_parts(b.address, b.city, b.state)
    if a:
        ids.update(by_addr.get(a, []))
    return ids


def _norm_addr_parts(street, city, state) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", f"{street or ''} {city or ''} {state or ''}".lower()).strip()


async def _aggregate_building(db, tenant_id, b, pending, linked, now) -> dict:
    """Derive the customer-safe facts for one canonical building from its linked
    True911 sites (reusing the service-inference + assurance logic)."""
    protections = [p for _s, p in linked]
    protection = _combine_protection(protections, now)

    services, equipment_count, phones = [], 0, set()
    e911_verified_sites, e911_any = 0, 0
    for site, _p in linked:
        svcs = await cc._build_location_services(db, tenant_id, site, now)
        services.extend(svcs)
        for svc in svcs:
            equipment_count += svc.get("equipment_count", 0) or 0
            for ph in (svc.get("phone_numbers") or []):
                phones.add(ph)
        e911_any += 1
        if (site.e911_status or "").strip().lower() in _VERIFIED_E911:
            e911_verified_sites += 1

    protected_services = sum(1 for s in services if s.get("status", {}).get("status") == "Protected")
    operational = cs._pct(protected_services, len(services)) if services else None
    has_address = bool(b.address or (linked and linked[0][0].e911_street))
    completeness = cs._pct(sum([bool(services), equipment_count > 0, bool(has_address),
                                bool(linked)]), 4)
    e911_all_verified = bool(linked) and e911_verified_sites == e911_any and e911_any > 0
    separated = cs.separated_health(operational=operational, completeness=completeness,
                                    compliance=None,
                                    documentation=0.0 if linked else None)
    maturity = cs.building_maturity({
        "documentation": False, "contacts": any(getattr(s, "poc_name", None) for s, _ in linked),
        "procedures": False, "testing": False, "compliance": False, "photos": False,
        "e911": e911_all_verified})

    site_type = b.site_type
    return {
        "id": b.id, "building_ref": encode_ref("bldg", b.id),
        "canonical_name": b.canonical_name, "display_name": None,
        "store_number": b.store_number, "site_type": site_type,
        "building_category": _category(site_type), "status": b.status,
        "address": b.address, "city": b.city, "state": b.state, "zip": b.zip,
        "map_point": _map_point(b, linked),
        "pending": pending, "approved": b.approved,
        "confidence": _HIGH_CONFIDENCE if b.approved else 60.0,
        "protection": protection,
        "services": services, "equipment_count": equipment_count, "phone_count": len(phones),
        "e911_state": _e911_state(e911_all_verified, e911_any, pending),
        "e911_verified": e911_all_verified,
        "separated_health": separated, "maturity": maturity, "completeness": completeness,
        "_site_ids": [s.site_id for s, _ in linked],
    }


_CATEGORY = {"store": "Retail", "gallery": "Retail", "outlet": "Retail",
             "guest_house": "Hospitality", "special": "Special", "warehouse": "Warehouse",
             "distribution_center": "Distribution", "corporate": "Corporate"}


def _category(site_type):
    return _CATEGORY.get((site_type or "").lower(), "Commercial")


def _map_point(b, linked):
    for site, _p in linked:
        if getattr(site, "lat", None) is not None and getattr(site, "lng", None) is not None:
            return {"lat": site.lat, "lng": site.lng}
    return None


def _e911_state(all_verified, any_sites, pending):
    if pending:
        return "Verification Pending"
    if any_sites == 0:
        return "Verification Pending"
    return "Verified" if all_verified else "Verification Pending"


# ── customer-facing outputs (built ON the aggregated records) ────────
def dashboard(records: list[dict], company, now) -> dict:
    counts = cs.portfolio_counts([r["protection"].get("status") for r in records])
    feed = [{**cs.portfolio_building_summary(r), "reason": r["protection"].get("reason")}
            for r in records if r["protection"].get("status") != "Protected"]
    feed.sort(key=lambda it: _PROT_RANK.get(it["protection"].get("status"), 9))
    return {
        "company": company,
        "portfolio": counts,
        "headline": cs.headline(counts, now.isoformat()),
        "attention_feed": feed[:10],
        "recent_manley_activity": [],
    }


def summary(records: list[dict], company, now) -> dict:
    total = len(records)
    protected = sum(1 for r in records if r["protection"].get("status") == "Protected")
    services = sum(r["life_safety_services_count"] if "life_safety_services_count" in r
                   else len(r["services"]) for r in records)
    protected_services = sum(sum(1 for s in r["services"]
                                 if s.get("status", {}).get("status") == "Protected") for r in records)
    devices = sum(r["equipment_count"] for r in records)
    phones = sum(r["phone_count"] for r in records)
    e911_verified = sum(1 for r in records if r["e911_verified"])
    e911_with_addr = sum(1 for r in records if r.get("address") or r["_site_ids"])
    health = cs.health_score({
        "e911_verified": cs._pct(e911_verified, total) if total else None,
        "service_coverage": cs._pct(protected_services, services) if services else None,
        "telemetry": None, "alarm_testing": None, "carrier": None})
    return {
        "portfolio_name": company,
        "locations_total": total,
        "locations_protected": protected,
        "life_safety_services": services,
        "protected_services": protected_services,
        "total_devices": devices,
        "total_phone_numbers": phones,
        "e911_verification_pct": cs._pct(e911_verified, total) if total else None,
        "service_availability_pct": cs._pct(protected_services, services) if services else None,
        "monthly_health_score": health,
        "upcoming_maintenance": [],
        "recent_activity": [],
    }


def health(records: list[dict]) -> dict:
    total = len(records)
    protected = sum(1 for r in records if r["protection"].get("status") == "Protected")
    services = sum(len(r["services"]) for r in records)
    protected_services = sum(sum(1 for s in r["services"]
                                 if s.get("status", {}).get("status") == "Protected") for r in records)
    e911_verified = sum(1 for r in records if r["e911_verified"])
    return cs.health_score({
        "e911_verified": cs._pct(e911_verified, total) if total else None,
        "service_coverage": cs._pct(protected_services, services) if services else None,
        "telemetry": None, "alarm_testing": None, "carrier": None})


def services_summary(records: list[dict]) -> dict:
    from collections import Counter
    all_services = [s for r in records for s in r["services"]]
    protected = sum(1 for s in all_services if s.get("status", {}).get("status") == "Protected")
    attention = sum(1 for s in all_services
                    if s.get("status", {}).get("status") in ("Attention Needed", "Critical"))
    inv = Counter(s.get("service") for s in all_services if s.get("service"))
    return {
        "total_services": len(all_services),
        "protected_services": protected,
        "attention_services": attention,
        "inventory": [{"service": k, "count": v} for k, v in inv.most_common()],
    }


def locations_page(records, *, status_filter=None, q=None, page=1, page_size=25) -> dict:
    items = records
    if status_filter:
        items = [r for r in items if r["protection"].get("status") == status_filter]
    if q:
        ql = q.lower()
        items = [r for r in items if _matches(r, ql)]
    total = len(items)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size,
            "items": [cs.portfolio_building_summary(r) for r in items[start:start + page_size]]}


def search(records, q) -> dict:
    q = (q or "").strip()
    if not q:
        return {"query": q, "results": []}
    ql = q.lower()
    return {"query": q,
            "results": [cs.portfolio_building_summary(r) for r in records if _matches(r, ql)]}


def _matches(r, ql) -> bool:
    hay = " ".join(str(x or "").lower() for x in (
        r.get("canonical_name"), cs.building_display_name(r.get("canonical_name"),
                                                          r.get("store_number"), r.get("city"),
                                                          r.get("site_type")),
        r.get("store_number"), r.get("city"), r.get("state")))
    if ql in hay:
        return True
    # phone / service-type match
    for s in r.get("services", []):
        if ql in (s.get("service") or "").lower():
            return True
        if any(ql in (p or "").lower() for p in (s.get("phone_numbers") or [])):
            return True
    return False


def building_detail(records, building_ref):
    raw = decode_ref("bldg", building_ref)
    if raw is None:
        return None
    try:
        bid = int(raw)
    except (TypeError, ValueError):
        return None
    for r in records:
        if r["id"] == bid:
            detail = cs.portfolio_building(r)
            detail["services"] = r["services"]      # services primary, devices nested within
            return detail
    return None


def location_health_detail(records, building_ref):
    raw = decode_ref("bldg", building_ref)
    if raw is None:
        return None
    try:
        bid = int(raw)
    except (TypeError, ValueError):
        return None
    for r in records:
        if r["id"] == bid:
            return {"location": cs.building_display_name(r.get("canonical_name"), r.get("store_number"),
                                                         r.get("city"), r.get("site_type")),
                    "building_health": r["separated_health"], "maturity": r["maturity"],
                    "health": health([r])}
    return None
