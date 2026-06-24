"""AI Customer Operations Center / Support Center models.

This module backs the caller-facing Tier-1 support workflow:

  * ``AssetIdentity``      — a flexible map of real-world identifiers
                             (elevator phone number, Napco radio number,
                             ICCID, site/building name, …) onto an asset
                             so a caller WITHOUT an account number can be
                             matched.
  * ``OpsSupportSession``  — a temporary support session created when a
                             caller contacts support.  Tracks the caller,
                             the matched customer/site/device, the issue,
                             verification state, escalation, and an audit
                             trail (via ``OpsSessionEvent``).
  * ``OpsOtpChallenge``    — an SMS one-time-passcode challenge sent to an
                             authorized contact on file.  The plaintext
                             code is NEVER stored — only a salted hash.
  * ``OpsSessionEvent``    — append-only audit trail of every lookup /
                             verification / triage / escalation event on a
                             session.

This is a SEPARATE namespace from the internal AI Support Assistant
(``app.models.support`` / ``support_*`` tables), which serves
authenticated users.  See docs/SUPPORT_CENTER_ARCHITECTURE.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssetIdentity(Base):
    """One real-world identifier pointing at one asset (device/site/unit/line).

    Multiple identities can point at the same asset — e.g. an elevator
    phone has an MSISDN, an elevator phone number, a device label, an
    elevator number, a site name, and a building name.  Lookup matches on
    ``identifier_value_normalized`` so phones match regardless of
    formatting and names match case-insensitively.

    Identity rows carry NO sensitive data — they are an index, not a
    record.  Sensitive fields stay on Device / Site / Customer and are
    only exposed AFTER caller verification.
    """

    __tablename__ = "asset_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    # What kind of identifier this is.  Free string (router enforces the
    # allowed set) to avoid an enum migration, matching project convention.
    #   elevator_phone | msisdn | device_label | elevator_number |
    #   site_name | building_name | starlink_id | napco_radio | iccid |
    #   central_station_account | panel_location | phone_number | imei |
    #   serial_number | unit_name | did
    identifier_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(255), nullable=False)
    # Normalized form used for matching: digits-only for phone-like types,
    # lower-cased + whitespace-collapsed for name-like types.
    identifier_value_normalized: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # What the identifier points at.
    asset_kind: Mapped[str] = mapped_column(String(30), nullable=False)  # device | site | service_unit | line
    asset_ref: Mapped[str] = mapped_column(String(100), nullable=False)  # business id (device_id/site_id/unit_id/line_id)
    # Convenience cross-links (loose coupling — strings, no FK constraints).
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    service_unit_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Human label and category for the redacted match shown pre-verification.
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # elevator | facp | gate | area_of_refuge | emergency_phone | other
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # import | manual | derived
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "identifier_type",
            "identifier_value_normalized",
            name="uq_asset_identity_tenant_type_value",
        ),
        Index("ix_asset_identities_type_value", "identifier_type", "identifier_value_normalized"),
    )


class OpsSupportSession(Base):
    """A temporary caller-facing support session."""

    __tablename__ = "ops_support_sessions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Short human-friendly reference, e.g. "OPS-3F9A2B1C".
    session_ref: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)

    # ── Caller ──────────────────────────────────────────────────────
    caller_phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    caller_phone_normalized: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(30), default="phone", nullable=False)  # phone | chat | internal | customer_portal

    # ── Issue ───────────────────────────────────────────────────────
    issue_category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    issue_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    # ── Lifecycle ───────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False)
    # open | matched | verifying | verified | escalated | resolved | closed | abandoned
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified", nullable=False)
    # unverified | otp_sent | verified | failed | bypassed_emergency

    # ── Matched context (populated by asset lookup) ─────────────────
    matched_tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    matched_site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    matched_device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    matched_service_unit_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    matched_asset_identity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    matched_asset_kind: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    matched_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Authorized contact selected for OTP — name + MASKED number only.
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone_masked: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # ── Escalation / handoff ────────────────────────────────────────
    escalation_status: Mapped[str] = mapped_column(String(30), default="none", nullable=False)  # none | requested | created | failed
    handoff_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    incident_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ticket_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Operator (internal user who opened/handled it, if any) ──────
    opened_by_user_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    opened_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    opened_by_tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OpsOtpChallenge(Base):
    """An SMS one-time-passcode challenge for caller verification.

    SECURITY: the plaintext code is never persisted.  ``code_hash`` is a
    salted SHA-256 of the code; ``destination_hash`` lets us correlate
    without storing the full contact number in clear (only a masked form
    is kept for display).
    """

    __tablename__ = "ops_otp_challenges"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ops_support_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    destination_masked: Mapped[str] = mapped_column(String(40), nullable=False)
    destination_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    provider: Mapped[str] = mapped_column(String(40), nullable=False)  # stub | console | twilio | telnyx
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="sent", nullable=False)  # sent | verified | failed | expired | cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpsSessionEvent(Base):
    """Append-only audit trail entry for a support session."""

    __tablename__ = "ops_session_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ops_support_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # session_created | asset_lookup | asset_matched | otp_sent | otp_verified |
    # otp_failed | triage_run | escalated | emergency_incident_created |
    # sensitive_access_blocked | session_closed
    actor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # operator email | "system" | "caller"
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
