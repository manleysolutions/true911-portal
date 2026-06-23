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
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs
from app.services.customer.gate import require_customer_api

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
    """Single location detail.  No services[]/E911-detail (later slices).
    Unknown / forged / cross-tenant ref -> 404."""
    now = datetime.now(timezone.utc)
    resolved = await cportfolio.resolve_location(db, current_user.tenant_id, location_ref, now)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    site, protection = resolved
    return {"as_of": now.isoformat(), "data": cs.location_detail(site, protection=protection)}
