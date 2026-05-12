"""Phase A — onboarding review queue.

A lightweight, non-destructive workflow table that lets Data Stewards
triage records that need attention across customers/sites/devices/lines
and import rows.

Design constraints (Phase A):
  * Additive only — no FKs to production tables.  ``entity_type`` plus
    ``entity_id`` / ``external_ref`` are free-form pointers; integrity
    is the steward's job, not the DB's.  This keeps the queue isolated
    from production cascades and decoupled from tenant architecture.
  * No delete endpoint exists on the router — rows transition to
    ``rejected`` or ``resolved`` instead.  The model itself supports
    deletion only via direct DB access (out of band).
  * Tenant-scoped via ``tenant_id`` so a future per-tenant queue is a
    filter change, not a schema change.

Statuses, issue types, and priorities are stored as plain strings to
avoid an enum migration.  The router enforces the allowed values.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OnboardingReview(Base):
    __tablename__ = "onboarding_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    # Free-form pointer into whatever the queue item is about.  The
    # router restricts ``entity_type`` to the enumerated set below.
    entity_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    # ``customer | site | device | line | import_row | other``

    # Either a stable internal id (string-coerced) or an external ref
    # such as a CSV row number or Zoho id.  Both are nullable so a
    # review can be created before the record exists.
    entity_id: Mapped[Optional[str]] = mapped_column(
        String(100), index=True, nullable=True
    )
    external_ref: Mapped[Optional[str]] = mapped_column(
        String(255), index=True, nullable=True
    )

    issue_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    # ``missing_address | missing_identifier | duplicate_candidate |
    #   e911_needs_review | customer_site_mismatch |
    #   napco_manual_verification | other``

    status: Mapped[str] = mapped_column(
        String(30), index=True, nullable=False, server_default="pending_review"
    )
    # ``pending_review | waiting_on_stuart | ready_to_import | imported |
    #   hold | resolved | rejected``

    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="normal"
    )
    # ``low | normal | high``

    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
