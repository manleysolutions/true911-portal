"""Pydantic schemas for the Phase A onboarding review queue.

Enumerated string sets are kept as plain Literal types so the matrix
is visible in one place.  If a value changes, both the create and
patch paths reject anything else with a 422.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


EntityType = Literal[
    "customer",
    "site",
    "device",
    "line",
    "import_row",
    "other",
]

IssueType = Literal[
    "missing_address",
    "missing_identifier",
    "duplicate_candidate",
    "e911_needs_review",
    "customer_site_mismatch",
    "napco_manual_verification",
    "other",
]

ReviewStatus = Literal[
    "pending_review",
    "waiting_on_stuart",
    "ready_to_import",
    "imported",
    "hold",
    "resolved",
    "rejected",
]

Priority = Literal["low", "normal", "high"]


class OnboardingReviewCreate(BaseModel):
    entity_type: EntityType
    entity_id: Optional[str] = None
    external_ref: Optional[str] = None
    issue_type: IssueType
    priority: Priority = "normal"
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class OnboardingReviewUpdate(BaseModel):
    """Partial update — every field optional.

    ``status`` and ``resolution_notes`` are the two fields that drive
    workflow progression.  ``resolved_at`` is set automatically by the
    router when ``status`` enters a terminal state.
    """

    status: Optional[ReviewStatus] = None
    priority: Optional[Priority] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    resolution_notes: Optional[str] = None
    entity_id: Optional[str] = None
    external_ref: Optional[str] = None


class OnboardingReviewOut(BaseModel):
    id: int
    review_id: str
    tenant_id: str
    entity_type: str
    entity_id: Optional[str] = None
    external_ref: Optional[str] = None
    issue_type: str
    status: str
    priority: str
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    resolution_notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OnboardingReviewListOut(BaseModel):
    items: list[OnboardingReviewOut]
    total: int = Field(
        ...,
        description=(
            "Total count after filters, before pagination.  Useful for "
            "showing 'N of M' in the queue UI."
        ),
    )
