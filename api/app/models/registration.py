"""Top-level registration staging row.

Owned by the registration_service module.  No production-table side
effects occur from changes to this row in Phase R1 — conversion to
customers/sites/service_units/users lands in a later phase.
"""

import uuid as _uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, server_default="ops")
    status: Mapped[str] = mapped_column(String(40), index=True, server_default="draft")

    # Resume token is never stored in plaintext; only the sha256 hash and
    # an absolute expiry timestamp.  Plaintext is returned to the caller
    # at creation time and discarded by the server.
    resume_token_hash: Mapped[str] = mapped_column(String(128))
    resume_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # ── Step 1 — submitter / customer identity ───────────────────
    submitter_email: Mapped[str] = mapped_column(String(255))
    submitter_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    submitter_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_legal_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Step 1 / 8 — primary point of contact ────────────────────
    poc_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    poc_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    poc_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    poc_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Step 3 — use case ────────────────────────────────────────
    use_case_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Step 4 — plan (text-only in R1) ──────────────────────────
    selected_plan_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    plan_quantity_estimate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Step 7 — billing intake ──────────────────────────────────
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    billing_address_street: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    billing_address_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    billing_address_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    billing_address_zip: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    billing_address_country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    billing_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ── Step 8 — support preferences ─────────────────────────────
    support_preference_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ── Step 6 — install scheduling (manual capture only) ────────
    preferred_install_window_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    preferred_install_window_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    installer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Step 9 — internal review (no assignment logic in R1) ─────
    reviewer_user_id: Mapped[Optional[_uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Conversion linkage (set in later phases) ─────────────────
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        index=True,
    )
    target_tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Lifecycle timestamps ─────────────────────────────────────
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
