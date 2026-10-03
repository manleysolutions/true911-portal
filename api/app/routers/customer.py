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
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission
from app.models.user import User
from app.services import e911_review
from app.services.customer import command_center as cc
from app.services.customer import contributions as contrib
from app.services.customer import portfolio as cportfolio
from app.services.customer import portfolio_registry_view as prv
from app.services.customer import self_service as ss
from app.services.customer import serialize as cs
from app.services.customer.gate import require_customer_api, require_customer_self_service
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
    company = await cportfolio.company_name(db, current_user.tenant_id)
    # Registry-backed mode: canonical buildings instead of raw Site rows.
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        return {"as_of": now.isoformat(), "data": prv.dashboard(records, company, now)}
    portfolio = await cportfolio.load_portfolio(db, current_user.tenant_id, now)
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
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        return {"as_of": now.isoformat(),
                "data": prv.locations_page(records, status_filter=status_filter, q=q,
                                           page=page, page_size=page_size)}
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
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        detail = prv.building_detail(records, location_ref)
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
        return {"as_of": now.isoformat(), "data": detail}
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


# ── Customer E911 confirmation + correction workflow (additive) ──────
# Customers may CONFIRM the record or REQUEST a correction — they never overwrite
# the official E911 record (data-safety §9).  Submit is gated on
# CUSTOMER_SUBMIT_E911_REVIEW (ADMIN/MANAGER/SUPPORT/USER); read-only roles
# (VIEWER/READONLY) can still VIEW review status but not submit.
class _ConfirmBody(BaseModel):
    note: str | None = None


class _CorrectionBody(BaseModel):
    corrected_address: str | None = None
    suite: str | None = None
    floor: str | None = None
    unit: str | None = None
    callback_number: str | None = None
    service_identifier: str | None = None
    note: str | None = None


class _ContributionBody(BaseModel):
    """A customer Building-Workspace contribution.  ``payload`` carries the
    type-specific fields (e.g. contact name/phone, photo filename/caption); it is
    stored as data and NEVER written to protected records — an operator reviews it."""
    type: str
    payload: dict = {}
    note: str | None = None


async def _e911_site_and_snapshot(db, tenant_id, location_ref):
    """Resolve the site (tenant-scoped) + the exact E911 record the customer is
    shown (server-authoritative snapshot), or (None, None) for unknown refs."""
    site = await cportfolio.resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None, None
    endpoints = await cportfolio.load_e911_endpoints(db, tenant_id, site.site_id)
    return site, cs.e911_summary(site, endpoints=endpoints)


@router.post(
    "/locations/{location_ref}/e911/confirm",
    dependencies=[Depends(require_permission("CUSTOMER_SUBMIT_E911_REVIEW"))],
)
async def customer_e911_confirm(
    location_ref: str,
    body: _ConfirmBody,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Confirm the emergency record is correct.  Records a customer confirmation
    (append-only audit) — does NOT mark the official record verified."""
    now = datetime.now(timezone.utc)
    site, snapshot = await _e911_site_and_snapshot(db, current_user.tenant_id, location_ref)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    data = await e911_review.record_confirmation(db, current_user, site, snapshot=snapshot, note=body.note or "")
    return {"as_of": now.isoformat(), "data": data}


@router.post(
    "/locations/{location_ref}/e911/correction-request",
    dependencies=[Depends(require_permission("CUSTOMER_SUBMIT_E911_REVIEW"))],
)
async def customer_e911_correction(
    location_ref: str,
    body: _CorrectionBody,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Request an emergency-record correction.  Creates a PENDING correction
    request (append-only) — never overwrites the official site/service-unit/line."""
    now = datetime.now(timezone.utc)
    site, snapshot = await _e911_site_and_snapshot(db, current_user.tenant_id, location_ref)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    corrected = {
        "address": body.corrected_address, "suite": body.suite, "floor": body.floor,
        "unit": body.unit, "callback_number": body.callback_number,
        "service_identifier": body.service_identifier,
    }
    data = await e911_review.record_correction(db, current_user, site, corrected=corrected,
                                               snapshot=snapshot, note=body.note or "")
    return {"as_of": now.isoformat(), "data": data}


@router.get(
    "/locations/{location_ref}/e911/review-status",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_E911"))],
)
async def customer_e911_review_status(
    location_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The friendly review state for this location's emergency record (own tenant
    only): Verification Pending / Verification Requested / Awaiting Review /
    Verified."""
    now = datetime.now(timezone.utc)
    site = await cportfolio.resolve_site(db, current_user.tenant_id, location_ref)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return {"as_of": now.isoformat(),
            "data": await e911_review.location_review_status(db, current_user.tenant_id, site)}


# ── Building-Workspace contributions (Phase 2/6) ──────────────────────
# Collaborative Digital-Twin improvement.  A contribution is a REQUEST stored as
# an append-only workflow event — it never writes protected data (Site /
# ServiceUnit / Line / E911).  Submit is gated on CUSTOMER_CONTRIBUTE
# (ADMIN/MANAGER/SUPPORT/USER); read-only roles can still VIEW the log.
@router.post(
    "/locations/{location_ref}/contributions",
    dependencies=[Depends(require_permission("CUSTOMER_CONTRIBUTE"))],
)
async def customer_add_contribution(
    location_ref: str,
    body: _ContributionBody,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit a Building-Workspace contribution (contact / inspection / photo /
    document / procedure / note / service_request).  Recorded as an append-only
    submission for operator review — never writes the protected record."""
    now = datetime.now(timezone.utc)
    site = await cportfolio.resolve_site(db, current_user.tenant_id, location_ref)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    try:
        data = await contrib.record_contribution(
            db, current_user, site, ctype=body.type, payload=body.payload or {},
            note=body.note or "")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return {"as_of": now.isoformat(), "data": data}


@router.get(
    "/locations/{location_ref}/contributions",
    dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))],
)
async def customer_list_contributions(
    location_ref: str,
    current_user: User = Depends(require_customer_api),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """This location's contribution log (own tenant only), newest first, with
    by-type counts — the collaborative Building-Workspace history."""
    now = datetime.now(timezone.utc)
    site = await cportfolio.resolve_site(db, current_user.tenant_id, location_ref)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return {"as_of": now.isoformat(),
            "data": await contrib.list_contributions(db, current_user.tenant_id, site.site_id)}


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
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        company = await cportfolio.company_name(db, current_user.tenant_id)
        return {"as_of": now.isoformat(), "data": prv.summary(records, company, now)}
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
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        return {"as_of": now.isoformat(), "data": prv.health(records)}
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
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        return {"as_of": now.isoformat(), "data": prv.services_summary(records)}
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
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        return {"as_of": now.isoformat(), "data": prv.search(records, q)}
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
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        detail = prv.building_detail(records, location_ref)
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
        data = {"location": detail["display_name"], "services": detail["services"]}
        if "service_inventory" in detail:
            # canonical mode: the inventory is authoritative - legacy inferred
            # service cards (and their devices / numbers) are not presented
            data = {"location": detail["display_name"], "services": [],
                    "service_inventory": detail["service_inventory"]}
        return {"as_of": now.isoformat(), "data": data}
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
    now = datetime.now(timezone.utc)
    records = await prv.load_customer_buildings(db, current_user.tenant_id, now)
    if records is not None:
        data = prv.location_health_detail(records, location_ref)
        if data is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
        return {"as_of": now.isoformat(), "data": data}
    return await _twin_subresource(cc.load_location_health, db, current_user.tenant_id,
                                   location_ref, now, pass_now=True)


# ══════════════════════════════════════════════════════════════════════
# Customer Self-Service — the Customer Operations Console (flag-gated).
# Every route: customer API two-key gate + FEATURE_CUSTOMER_SELF_SERVICE gate
# (404 when off) + a CUSTOMER_* permission, tenant-scoped server-side.  Customer-
# owned fields are written to the customer overlay (never Site / Device / registry
# / E911); provisioning, identity and E911 changes become GOVERNED requests.
# System-managed fields (SIM / ICCID / IMEI / carrier / network / verified E911 ...)
# are refused with 403.  See docs/customer/CUSTOMER_SELF_SERVICE.md.
# ══════════════════════════════════════════════════════════════════════
class _ProfileBody(BaseModel):
    changes: dict


class _ContactsBody(BaseModel):
    contacts: dict


class _ConnectionBody(BaseModel):
    changes: dict


class _RequestBody(BaseModel):
    request_type: str
    notes: str | None = None
    requested_changes: dict | None = None
    connection_ref: str | None = None
    priority: str = "normal"


class _RequestNoteBody(BaseModel):
    notes: str | None = None


class _E911VerifyBody(BaseModel):
    """The customer's portion of E911 verification.  ``attest`` must be true.
    Corrections are stored as a request - never written to the official record."""
    number_confirmed: bool = False
    address_confirmed: bool = False
    building_confirmed: bool = False
    corrected_address: str | None = None
    suite: str | None = None
    floor: str | None = None
    additional_location: str | None = None
    callback_number: str | None = None
    contact: dict | None = None
    note: str | None = None
    attest: bool = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ss_ctx(db, user, location_ref, *, full=False):
    ctx = await ss.resolve_location_context(db, user.tenant_id, location_ref,
                                            datetime.now(timezone.utc), full=full)
    if ctx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return ctx


async def _ss_run(coro) -> dict:
    """Await a self-service mutation, mapping a refusal to its HTTP status."""
    try:
        data = await coro
    except ss.SelfServiceError as exc:
        raise HTTPException(exc.status, exc.as_detail())
    return {"as_of": _now_iso(), "data": data}


@router.get("/self-service/capabilities",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_self_service_capabilities(
    current_user: User = Depends(require_customer_self_service),
) -> dict:
    """What this user may do in the operations console (drives the UI; the
    server re-checks every permission on every mutation)."""
    return {"as_of": _now_iso(), "data": ss.capabilities(current_user)}


@router.get("/action-center",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_DASHBOARD"))])
async def customer_action_center(
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """What do I need to do? - needs attention, E911 verification required,
    missing contacts, open change requests / problems, recent updates."""
    now = datetime.now(timezone.utc)
    return {"as_of": now.isoformat(), "data": await ss.action_center(db, current_user, now)}


@router.get("/locations/{location_ref}/workspace",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_location_workspace(
    location_ref: str,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The actionable location workspace: overview, connections, contacts,
    notes, E911 state, requests, activity, outstanding actions."""
    now = datetime.now(timezone.utc)
    ctx = await _ss_ctx(db, current_user, location_ref, full=True)
    return {"as_of": now.isoformat(), "data": await ss.location_workspace(db, current_user, ctx, now)}


@router.patch("/locations/{location_ref}/profile",
              dependencies=[Depends(require_permission("CUSTOMER_MANAGE_LOCATION"))])
async def customer_update_location_profile(
    location_ref: str, body: _ProfileBody,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Customer-owned location fields apply directly (audited old/new); identity
    fields (name / address / store #) create a location-correction request."""
    ctx = await _ss_ctx(db, current_user, location_ref)
    return await _ss_run(ss.update_location_profile(db, current_user, ctx, body.changes))


@router.put("/locations/{location_ref}/contacts",
            dependencies=[Depends(require_permission("CUSTOMER_MANAGE_CONTACTS"))])
async def customer_update_contacts(
    location_ref: str, body: _ContactsBody,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Facility / emergency / property-manager contacts (null clears one)."""
    ctx = await _ss_ctx(db, current_user, location_ref)
    return await _ss_run(ss.update_contacts(db, current_user, ctx, body.contacts))


@router.patch("/locations/{location_ref}/connections/{connection_ref}",
              dependencies=[Depends(require_permission("CUSTOMER_MANAGE_LOCATION"))])
async def customer_update_connection(
    location_ref: str, connection_ref: str, body: _ConnectionBody,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Friendly name / purpose / notes / contact apply directly; a telephone or
    callback number or service-type change becomes a governed request."""
    ctx = await _ss_ctx(db, current_user, location_ref)
    conn_key = ss.decode_connection_ref(ctx, connection_ref)
    if conn_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    return await _ss_run(ss.update_connection(db, current_user, ctx, conn_key, body.changes))


@router.post("/locations/{location_ref}/requests",
             dependencies=[Depends(require_permission("CUSTOMER_SUBMIT_REQUESTS"))])
async def customer_submit_request(
    location_ref: str, body: _RequestBody,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add / remove / move a service, change a number or service type, replace
    equipment, correct the location, or report a problem - a governed request;
    nothing is provisioned or changed until operations act on it."""
    ctx = await _ss_ctx(db, current_user, location_ref)
    conn_key = None
    if body.connection_ref:
        conn_key = ss.decode_connection_ref(ctx, body.connection_ref)
        if conn_key is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    return await _ss_run(ss.submit_request(
        db, current_user, ctx, request_type=body.request_type, notes=body.notes,
        changes=body.requested_changes, connection_key=conn_key, priority=body.priority))


@router.get("/locations/{location_ref}/requests",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_REQUESTS"))])
async def customer_location_requests(
    location_ref: str,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await _ss_ctx(db, current_user, location_ref)
    rows = await ss.load_requests(db, current_user.tenant_id, location_key=ctx.key)
    return {"as_of": _now_iso(), "data": {"requests": [ss.serialize_request(r) for r in rows]}}


@router.get("/requests", dependencies=[Depends(require_permission("CUSTOMER_VIEW_REQUESTS"))])
async def customer_requests(
    open_only: bool = Query(False, alias="open"),
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Every request for this portfolio (own tenant only), newest first."""
    rows = await ss.load_requests(db, current_user.tenant_id, open_only=open_only)
    return {"as_of": _now_iso(), "data": {"requests": [ss.serialize_request(r) for r in rows]}}


async def _own_request(db, user, request_ref):
    req = await ss.get_request(db, user.tenant_id, request_ref)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return req


@router.get("/requests/{request_ref}",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_REQUESTS"))])
async def customer_request_detail(
    request_ref: str,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    req = await _own_request(db, current_user, request_ref)
    return {"as_of": _now_iso(), "data": ss.serialize_request(req)}


@router.post("/requests/{request_ref}/cancel",
             dependencies=[Depends(require_permission("CUSTOMER_SUBMIT_REQUESTS"))])
async def customer_cancel_request(
    request_ref: str, body: _RequestNoteBody,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    req = await _own_request(db, current_user, request_ref)
    return await _ss_run(ss.customer_cancel(db, current_user, req, notes=body.notes))


@router.post("/requests/{request_ref}/respond",
             dependencies=[Depends(require_permission("CUSTOMER_SUBMIT_REQUESTS"))])
async def customer_respond_request(
    request_ref: str, body: _RequestNoteBody,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Answer a request that is waiting on the customer."""
    req = await _own_request(db, current_user, request_ref)
    return await _ss_run(ss.customer_respond(db, current_user, req, notes=body.notes))


@router.get("/locations/{location_ref}/e911/verification",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_E911"))])
async def customer_e911_verification_state(
    location_ref: str,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The self-service E911 state + what the customer is asked to review."""
    now = datetime.now(timezone.utc)
    ctx = await _ss_ctx(db, current_user, location_ref, full=True)
    ws = await ss.location_workspace(db, current_user, ctx, now)
    return {"as_of": now.isoformat(),
            "data": {**ws["e911"], "location": ws["location"]["display_name"]}}


@router.post("/locations/{location_ref}/e911/verification",
             dependencies=[Depends(require_permission("CUSTOMER_ATTEST_E911"))])
async def customer_e911_verification_submit(
    location_ref: str, body: _E911VerifyBody,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit the customer's E911 attestation.  Creates a pending verification
    (never marks E911 verified) and feeds the existing E911 review queue."""
    ctx = await _ss_ctx(db, current_user, location_ref, full=True)
    return await _ss_run(ss.submit_e911_verification(db, current_user, ctx, body.model_dump()))


@router.get("/locations/{location_ref}/activity",
            dependencies=[Depends(require_permission("CUSTOMER_VIEW_LOCATIONS"))])
async def customer_location_activity(
    location_ref: str,
    current_user: User = Depends(require_customer_self_service),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await _ss_ctx(db, current_user, location_ref)
    return {"as_of": _now_iso(),
            "data": {"activity": await ss.load_activity(db, current_user.tenant_id,
                                                         location_key=ctx.key)}}
