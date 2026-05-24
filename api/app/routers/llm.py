"""LLLM Phase 1 router — internal-only read-only AI Health Summary.

Every endpoint returns 404 when ``FEATURE_LLLM`` is not ``"true"`` so a
misconfigured client cannot tell the feature exists.  When the flag is
on, the routes additionally require:

  * a logged-in user with the ``VIEW_AI_SUMMARY`` permission, AND
  * the user is "in the internal context" — i.e. they are SuperAdmin
    OR their REAL (un-impersonated) tenant_id is in
    ``settings.INTERNAL_TENANT_IDS``.  Customer-tenant Admins are
    explicitly NOT granted access, even though their role technically
    holds ``VIEW_AI_SUMMARY``, because Phase 1 is internal-only.

This guard mirrors the pattern already used by
:func:`app.dependencies.require_platform_role` for the Registration
review queue.  It is duplicated here rather than reused because the
two surfaces have slightly different semantics during impersonation —
``require_platform_role`` rejects impersonation entirely; the LLLM
guard allows a SuperAdmin to look at any tenant via impersonation (the
audit row records both effective and original tenant_id so the
governance question stays answerable).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    is_platform_user,
    require_permission,
)
from app.models.user import User
from app.schemas.llm import HealthSummaryResponse
from app.services.llm import generate_health_summary

router = APIRouter()


def _require_feature() -> None:
    """Return 404 when FEATURE_LLLM is not exactly 'true'.

    404 (not 403) is deliberate — a misconfigured frontend should learn
    the surface does not exist, not that it exists and the user is
    forbidden.  This matches the pattern used by
    ``app.routers.line_intelligence._require_feature``.
    """
    if settings.FEATURE_LLLM.lower() != "true":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


def _require_internal_context(user: User) -> None:
    """Phase 1 internal-only gate.

    Customer-tenant Admins technically hold ``VIEW_AI_SUMMARY`` per
    permissions.json, but Phase 1 is internal-only.  Block them at the
    route by additionally requiring platform context.

    Customer rollout is Phase 3 (per docs/LLLM_AUDIT_AND_PLAN.md) and
    will gate per-tenant on a new ``tenants.settings_json['ai_enabled']``
    flag rather than relaxing this check.
    """
    if not is_platform_user(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "AI Health Summary is internal-only in Phase 1.",
        )


@router.get("/health-summary", response_model=HealthSummaryResponse)
async def get_health_summary(
    scope: str = Query("fleet"),
    scope_id: Optional[str] = Query(None, max_length=100),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_AI_SUMMARY")),
) -> HealthSummaryResponse:
    """Generate (or fetch cached) AI Health Summary.

    Always returns a valid HealthSummaryResponse.  When the provider
    is disabled / errors / times out / fails validation, the response
    will have ``deterministic_fallback=true`` and ``source="fallback"``
    — the UI should render it identically to a fresh provider response.

    Tenant scoping is enforced inside :class:`LLLMContext`; the caller
    cannot pass a tenant_id.
    """
    _require_feature()
    _require_internal_context(current_user)

    if scope not in {"fleet", "site", "device"}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scope must be one of: fleet, site, device",
        )
    if scope == "site" and not scope_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scope_id is required when scope='site'",
        )

    payload = await generate_health_summary(
        db=db,
        user=current_user,
        scope=scope,
        scope_id=scope_id,
        force_refresh=force_refresh,
    )
    return HealthSummaryResponse.model_validate(payload)


@router.post("/health-summary/refresh", response_model=HealthSummaryResponse)
async def refresh_health_summary(
    scope: str = Query("fleet"),
    scope_id: Optional[str] = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_AI_SUMMARY")),
) -> HealthSummaryResponse:
    """Same as GET, but bypasses the cache.

    Provided as a separate verb so the UI's 'Refresh' button has an
    obvious endpoint and so an audit reader can distinguish a
    deliberate refresh from a routine read.
    """
    _require_feature()
    _require_internal_context(current_user)

    if scope not in {"fleet", "site", "device"}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scope must be one of: fleet, site, device",
        )
    if scope == "site" and not scope_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scope_id is required when scope='site'",
        )

    payload = await generate_health_summary(
        db=db,
        user=current_user,
        scope=scope,
        scope_id=scope_id,
        force_refresh=True,
    )
    return HealthSummaryResponse.model_validate(payload)
