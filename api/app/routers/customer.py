"""Customer API namespace — /api/customer/* (RH Go-Live Phase 3).

PR-C1 ships the gated scaffold only.  Data endpoints (dashboard, locations,
services, equipment, e911, billing, reports, support) land in PR-C2+ and all
compose the existing engines through the allow-list serializer in
``app.services.customer.serialize``.

Every endpoint here uses ``require_customer_api`` (two-key flag gate, 404 when
off) IN ADDITION to a dedicated ``CUSTOMER_*`` permission guard.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission
from app.models.user import User
from app.services.customer import command_center as cc
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs
from app.services.customer.gate import require_customer_api
from app.services.customer.preview import preview_enabled

router = APIRouter()

# Attention feed ordering (most urgent first) + cap.
_ATTENTION_RANK = {"Critical": 0, "Attention Needed": 1, "Pending Install": 2,
                   "Inactive": 3, "Unknown": 4}
_ATTENTION_MAX = 10


@router.get("/_health")
async def customer_api_health(current_user: User = Depends(require_customer_api)) -> dict:
    """Liveness probe proving the two-key gate.  Returns 404 unless
    FEATURE_CUSTOMER_API is on AND the caller's tenant is allowlisted; returns
    200 otherwise.  Carries no tenant data."""
    return {"ok": True, "namespace": "customer"}


@router.get(
    "/dashboard",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_DASHBOARD"))],
)
async def customer_dashboard(
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Portfolio Morning Test — counts, headline, attention feed.  Each label
    is computed by the Assurance engine per site; no false green (evidence
    enforced in the serializer).  ``recent_manley_activity`` is deferred (PR-C2)."""
    now = datetime.now(timezone.utc)
    portfolio = await cportfolio.load_portfolio(db, current_user.tenant_id, now)
    company = await cportfolio.company_name(db, current_user.tenant_id)
    counts = cs.portfolio_counts([p["status"] for _, p in portfolio])
    feed = [cs.attention_item(s, protection=p) for s, p in portfolio if p["status"] != "Protected"]
    feed.sort(key=lambda it: _ATTENTION_RANK.get(it["status"], 9))
    return {
        "as_of": now.isoformat(),
        "data": {
            "company": company,
            "portfolio": counts,
            "headline": cs.headline(counts, now.isoformat()),
            "attention_feed": feed[:_ATTENTION_MAX],
            "recent_manley_activity": [],
        },
    }


@router.get(
    "/locations",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))],
)
async def customer_locations(
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tenant-scoped, plain-language location list (assurance label per site)."""
    now = datetime.now(timezone.utc)
    portfolio = await cportfolio.load_portfolio(db, current_user.tenant_id, now)
    if status_filter:
        portfolio = [(s, p) for s, p in portfolio if p["status"] == status_filter]
    if q:
        ql = q.lower()
        portfolio = [(s, p) for s, p in portfolio if ql in (s.site_name or "").lower()]
    total = len(portfolio)
    start = (page - 1) * page_size
    page_items = portfolio[start:start + page_size]
    return {
        "as_of": now.isoformat(),
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [cs.location_summary(s, protection=p) for s, p in page_items],
        },
    }


@router.get(
    "/locations/{location_ref}",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))],
)
async def customer_location_detail(
    location_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Single location detail with a minimal services[] preview (PR-C3).  No
    full E911 object (its own endpoint).  Unknown / forged / cross-tenant -> 404."""
    now = datetime.now(timezone.utc)
    resolved = await cportfolio.resolve_location(db, current_user.tenant_id, location_ref, now)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    site, protection, services, devices = resolved
    return {
        "as_of": now.isoformat(),
        "data": cs.location_detail(site, protection=protection, services=services, devices=devices),
    }


@router.get(
    "/services/{service_ref}",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_SERVICES"))],
)
async def customer_service_detail(
    service_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One service (emergency endpoint) + its equipment health.  Service and
    equipment protection both derive from the site assurance engine."""
    now = datetime.now(timezone.utc)
    resolved = await cportfolio.resolve_service(db, current_user.tenant_id, service_ref, now)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")
    unit, device, service_protection, equipment_protection = resolved
    preview = preview_enabled(current_user.tenant_id)
    equipment = cs.equipment_from_device(device, protection=equipment_protection, preview=preview) if device is not None else None
    return {
        "as_of": now.isoformat(),
        "data": cs.service_from_unit(unit, protection=service_protection, equipment=equipment),
    }


@router.get(
    "/services/{service_ref}/equipment",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_DEVICES"))],
)
async def customer_service_equipment(
    service_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Equipment health for a service.  No linked device -> Unknown empty state."""
    now = datetime.now(timezone.utc)
    resolved = await cportfolio.resolve_service(db, current_user.tenant_id, service_ref, now)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")
    _unit, device, _service_protection, equipment_protection = resolved
    if device is None:
        return {"as_of": now.isoformat(), "data": {"equipment": None, "protection": equipment_protection}}
    preview = preview_enabled(current_user.tenant_id)
    return {"as_of": now.isoformat(), "data": cs.equipment_from_device(device, protection=equipment_protection, preview=preview)}


@router.get(
    "/locations/{location_ref}/e911",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_E911"))],
)
async def customer_location_e911(
    location_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Read-only emergency-address summary — E911 axis ONLY (never device
    health).  ``is_critical`` = active location with an unverified address."""
    now = datetime.now(timezone.utc)
    site = await cportfolio.resolve_site(db, current_user.tenant_id, location_ref)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    logs = await cportfolio.load_e911_history(db, current_user.tenant_id, site.site_id)
    history = [cs.e911_history_item(log) for log in logs]
    endpoints = await cportfolio.load_e911_endpoints(db, current_user.tenant_id, site.site_id)
    return {"as_of": now.isoformat(), "data": cs.e911_summary(site, history=history, endpoints=endpoints)}


# ══════════════════════════════════════════════════════════════════════
# Command Center endpoints (additive — Phase 1/3/4/6/8).  Each keeps the
# two-key gate (require_customer_api) + a CUSTOMER_* permission; none reads
# or exposes an internal operational field.
# ══════════════════════════════════════════════════════════════════════
@router.get(
    "/portfolio/summary",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_DASHBOARD"))],
)
async def customer_portfolio_summary(
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Executive portfolio metrics (Command Center header) — aggregates over
    customer-safe data + an evidence-graded health score."""
    now = datetime.now(timezone.utc)
    return {"as_of": now.isoformat(), "data": await cc.load_portfolio_summary(db, current_user.tenant_id, now)}


@router.get(
    "/portfolio/health",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_DASHBOARD"))],
)
async def customer_portfolio_health(
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enterprise Portfolio Health score + component breakdown (Phase 6).
    Unknown inputs lower confidence; nothing is fabricated."""
    now = datetime.now(timezone.utc)
    return {"as_of": now.isoformat(), "data": await cc.load_portfolio_health(db, current_user.tenant_id, now)}


@router.get(
    "/portfolio/services",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_SERVICES"))],
)
async def customer_services_summary(
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Portfolio Life-Safety service inventory — totals, protected/attention, and
    a by-type breakdown (Phase 6).  Service-derived, not a raw device count."""
    now = datetime.now(timezone.utc)
    return {"as_of": now.isoformat(), "data": await cc.load_services_summary(db, current_user.tenant_id, now)}


@router.get(
    "/search",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))],
)
async def customer_search(
    q: str = Query("", max_length=120),
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enterprise search across store name/number, city, state, phone number,
    and service/equipment type — returns matching locations (customer-safe)."""
    now = datetime.now(timezone.utc)
    return {"as_of": now.isoformat(), "data": await cc.search_portfolio(db, current_user.tenant_id, q, now)}


@router.get(
    "/locations/{location_ref}/services",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_SERVICES"))],
)
async def customer_location_services(
    location_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Life-Safety Services for a location, each with the equipment that supports
    it grouped beneath (service-first).  Unknown / cross-tenant -> 404."""
    now = datetime.now(timezone.utc)
    data = await cc.load_location_services(db, current_user.tenant_id, location_ref, now)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return {"as_of": now.isoformat(), "data": data}


@router.get(
    "/locations/{location_ref}/timeline",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))],
)
async def customer_location_timeline(
    location_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Customer-safe activity timeline for a location (real data only)."""
    now = datetime.now(timezone.utc)
    data = await cc.load_location_timeline(db, current_user.tenant_id, location_ref)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return {"as_of": now.isoformat(), "data": data}


# ══════════════════════════════════════════════════════════════════════
# Location Digital Twin sub-resources (additive — Phase 3/5/7).  Each is a
# location sub-resource: two-key gate + `CUSTOMER_VIEW_LOCATIONS`, tenant-scoped,
# 404 on unknown/cross-tenant ref.  Documents/Photos/Inspections are honest
# future-ready placeholders; Contacts + Health return real customer-safe data.
# ══════════════════════════════════════════════════════════════════════
async def _twin_subresource(loader, db, tenant_id, location_ref, now, *, pass_now=False):
    data = await (loader(db, tenant_id, location_ref, now) if pass_now
                  else loader(db, tenant_id, location_ref))
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return {"as_of": now.isoformat(), "data": data}


@router.get("/locations/{location_ref}/documents",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_location_documents(location_ref: str,
                                      current_user: User = Depends(require_customer_api),
                                      db: AsyncSession = Depends(get_db)) -> dict:
    """Location documents (future storage — permits/floor plans/inspection reports/…)."""
    return await _twin_subresource(cc.load_location_documents, db, current_user.tenant_id,
                                   location_ref, datetime.now(timezone.utc))


@router.get("/locations/{location_ref}/photos",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_location_photos(location_ref: str,
                                   current_user: User = Depends(require_customer_api),
                                   db: AsyncSession = Depends(get_db)) -> dict:
    """Location photos (future storage)."""
    return await _twin_subresource(cc.load_location_photos, db, current_user.tenant_id,
                                   location_ref, datetime.now(timezone.utc))


@router.get("/locations/{location_ref}/contacts",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_location_contacts(location_ref: str,
                                     current_user: User = Depends(require_customer_api),
                                     db: AsyncSession = Depends(get_db)) -> dict:
    """Customer-safe site contacts for a location."""
    return await _twin_subresource(cc.load_location_contacts, db, current_user.tenant_id,
                                   location_ref, datetime.now(timezone.utc))


@router.get("/locations/{location_ref}/inspections",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_location_inspections(location_ref: str,
                                        current_user: User = Depends(require_customer_api),
                                        db: AsyncSession = Depends(get_db)) -> dict:
    """Inspection history (real entries only; empty until a source exists)."""
    return await _twin_subresource(cc.load_location_inspections, db, current_user.tenant_id,
                                   location_ref, datetime.now(timezone.utc))


@router.get("/locations/{location_ref}/health",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_location_health(location_ref: str,
                                   current_user: User = Depends(require_customer_api),
                                   db: AsyncSession = Depends(get_db)) -> dict:
    """Digital Twin building health for one location (real signals; unknown lowers
    confidence, never fabricated)."""
    return await _twin_subresource(cc.load_location_health, db, current_user.tenant_id,
                                   location_ref, datetime.now(timezone.utc), pass_now=True)
