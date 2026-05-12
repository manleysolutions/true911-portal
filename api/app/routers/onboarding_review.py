"""Phase A — Onboarding Review queue router.

A non-destructive triage surface owned by the Data Steward role.

Permissions:
  * Read endpoints           — VIEW_ONBOARDING_REVIEW
  * Write endpoints (create, — MANAGE_ONBOARDING_REVIEW
    patch, assign, status)

There is intentionally no DELETE endpoint — workflow moves items to
``rejected`` or ``resolved`` instead of removing them, so the audit
trail of "what we triaged" survives indefinitely.

The queue is tenant-scoped to ``current_user.tenant_id`` on every
read and mutate; SuperAdmin sees the rows of whichever tenant they
are currently impersonating (or their own default tenant otherwise).
That matches the rest of the operational surface (customers, sites,
devices).
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.onboarding_review import OnboardingReview
from app.models.user import User
from app.schemas.onboarding_review import (
    OnboardingReviewCreate,
    OnboardingReviewListOut,
    OnboardingReviewOut,
    OnboardingReviewUpdate,
)

router = APIRouter()


# ── Constants ──────────────────────────────────────────────────────

# Statuses that mark the row as terminal — when a row transitions
# into one of these, ``resolved_at`` is stamped automatically.
_TERMINAL_STATUSES = frozenset({"imported", "resolved", "rejected"})


# ── Helpers ────────────────────────────────────────────────────────


def _new_review_id() -> str:
    """Generate an opaque public review id.

    Format: ``REV-<12 hex>`` — stable, human-quotable, but not so
    short that two stewards could collide on a same-day prefix.
    """

    return f"REV-{uuid.uuid4().hex[:12].upper()}"


async def _get_or_404(
    db: AsyncSession, review_id: str, tenant_id: str
) -> OnboardingReview:
    result = await db.execute(
        select(OnboardingReview).where(
            OnboardingReview.review_id == review_id,
            OnboardingReview.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Onboarding review item not found"
        )
    return row


# ── List + count ───────────────────────────────────────────────────


@router.get(
    "",
    response_model=OnboardingReviewListOut,
    dependencies=[Depends(require_permission("VIEW_ONBOARDING_REVIEW"))],
)
async def list_reviews(
    status_filter: Optional[str] = Query(None, alias="status"),
    issue_type: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(
        None,
        description=(
            "Substring match against review_id, entity_id, external_ref, "
            "or notes."
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(OnboardingReview).where(
        OnboardingReview.tenant_id == current_user.tenant_id
    )
    if status_filter:
        base = base.where(OnboardingReview.status == status_filter)
    if issue_type:
        base = base.where(OnboardingReview.issue_type == issue_type)
    if assigned_to:
        base = base.where(OnboardingReview.assigned_to == assigned_to)
    if entity_type:
        base = base.where(OnboardingReview.entity_type == entity_type)
    if priority:
        base = base.where(OnboardingReview.priority == priority)
    if search:
        like = f"%{search}%"
        base = base.where(
            (OnboardingReview.review_id.ilike(like))
            | (OnboardingReview.entity_id.ilike(like))
            | (OnboardingReview.external_ref.ilike(like))
            | (OnboardingReview.notes.ilike(like))
        )

    total_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_q)).scalar_one()

    rows_q = base.order_by(
        # High priority first, then oldest pending first.
        OnboardingReview.priority.desc(),
        OnboardingReview.created_at.asc(),
    ).limit(limit).offset(offset)
    rows = (await db.execute(rows_q)).scalars().all()

    return OnboardingReviewListOut(
        items=[OnboardingReviewOut.model_validate(r) for r in rows],
        total=int(total),
    )


# ── Create ─────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=OnboardingReviewOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("MANAGE_ONBOARDING_REVIEW"))],
)
async def create_review(
    payload: OnboardingReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = OnboardingReview(
        review_id=_new_review_id(),
        tenant_id=current_user.tenant_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        external_ref=payload.external_ref,
        issue_type=payload.issue_type,
        priority=payload.priority,
        assigned_to=payload.assigned_to,
        notes=payload.notes,
        created_by=current_user.email,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return OnboardingReviewOut.model_validate(row)


# ── CSV export ─────────────────────────────────────────────────────
# NOTE: declared BEFORE the /{review_id} routes so FastAPI doesn't
# match "export.csv" as a review_id path parameter.


@router.get(
    "/export.csv",
    dependencies=[Depends(require_permission("VIEW_ONBOARDING_REVIEW"))],
)
async def export_reviews_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    issue_type: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export the current filtered queue as CSV.

    Same filter semantics as the list endpoint, minus pagination.
    Result is capped at 5000 rows defensively — the queue is intended
    for triage, not bulk extraction.
    """

    q = select(OnboardingReview).where(
        OnboardingReview.tenant_id == current_user.tenant_id
    )
    if status_filter:
        q = q.where(OnboardingReview.status == status_filter)
    if issue_type:
        q = q.where(OnboardingReview.issue_type == issue_type)
    if assigned_to:
        q = q.where(OnboardingReview.assigned_to == assigned_to)
    if entity_type:
        q = q.where(OnboardingReview.entity_type == entity_type)
    if priority:
        q = q.where(OnboardingReview.priority == priority)
    q = q.order_by(OnboardingReview.created_at.asc()).limit(5000)
    rows = (await db.execute(q)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "review_id",
        "tenant_id",
        "entity_type",
        "entity_id",
        "external_ref",
        "issue_type",
        "status",
        "priority",
        "assigned_to",
        "created_by",
        "created_at",
        "updated_at",
        "resolved_at",
        "notes",
        "resolution_notes",
    ])
    for r in rows:
        writer.writerow([
            r.review_id,
            r.tenant_id,
            r.entity_type,
            r.entity_id or "",
            r.external_ref or "",
            r.issue_type,
            r.status,
            r.priority,
            r.assigned_to or "",
            r.created_by or "",
            r.created_at.isoformat() if r.created_at else "",
            r.updated_at.isoformat() if r.updated_at else "",
            r.resolved_at.isoformat() if r.resolved_at else "",
            (r.notes or "").replace("\n", " ").strip(),
            (r.resolution_notes or "").replace("\n", " ").strip(),
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                "attachment; "
                f"filename=onboarding-reviews-{current_user.tenant_id}.csv"
            ),
        },
    )


# ── Detail ─────────────────────────────────────────────────────────


@router.get(
    "/{review_id}",
    response_model=OnboardingReviewOut,
    dependencies=[Depends(require_permission("VIEW_ONBOARDING_REVIEW"))],
)
async def get_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await _get_or_404(db, review_id, current_user.tenant_id)
    return OnboardingReviewOut.model_validate(row)


# ── Patch (status / priority / notes / assignment) ─────────────────


@router.patch(
    "/{review_id}",
    response_model=OnboardingReviewOut,
    dependencies=[Depends(require_permission("MANAGE_ONBOARDING_REVIEW"))],
)
async def update_review(
    review_id: str,
    payload: OnboardingReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await _get_or_404(db, review_id, current_user.tenant_id)

    updates = payload.model_dump(exclude_unset=True)
    transitioned_to_terminal = (
        "status" in updates
        and updates["status"] in _TERMINAL_STATUSES
        and row.status not in _TERMINAL_STATUSES
    )
    transitioned_out_of_terminal = (
        "status" in updates
        and updates["status"] not in _TERMINAL_STATUSES
        and row.status in _TERMINAL_STATUSES
    )

    for field, value in updates.items():
        setattr(row, field, value)

    if transitioned_to_terminal:
        row.resolved_at = datetime.now(timezone.utc)
    elif transitioned_out_of_terminal:
        row.resolved_at = None

    await db.commit()
    await db.refresh(row)
    return OnboardingReviewOut.model_validate(row)
