"""Support feature models — sessions, messages, diagnostics, escalations, AI summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupportSession(Base):
    __tablename__ = "support_sessions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # Optional context scoping
    site_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Session metadata
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)  # active | resolved | escalated
    issue_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolution_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    message_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # AI structured output (only for assistant messages)
    structured_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportDiagnostic(Base):
    __tablename__ = "support_diagnostics"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    # What was checked
    check_type: Mapped[str] = mapped_column(String(50), nullable=False)  # heartbeat | device_status | sip_registration | telemetry | ata_reachability | incidents | e911 | zoho_ticket
    # Normalized results
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # ok | warning | critical | unknown
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)  # info | warning | critical
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    customer_safe_summary: Mapped[str] = mapped_column(Text, nullable=False)
    internal_summary: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportEscalation(Base):
    __tablename__ = "support_escalations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    site_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Escalation details
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    probable_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    escalation_level: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # offer | recommend | urgent
    diagnostics_checked: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    recommended_followup: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    handoff_summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Zoho Desk integration
    zoho_ticket_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    zoho_ticket_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zoho_ticket_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    zoho_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Open | On Hold | Closed etc.
    # Deduplication
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    was_deduplicated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    linked_escalation_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)  # ID of the original if deduped
    # Sync state
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)  # pending | created | failed | linked
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportRemediationAction(Base):
    __tablename__ = "support_remediation_actions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("support_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    escalation_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    site_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    issue_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(50), nullable=False)  # diagnostic | escalation | admin | system
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)  # refresh_diagnostics | retry_voice_check etc.
    action_level: Mapped[str] = mapped_column(String(20), default="safe", nullable=False)  # safe | low_risk | gated
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)  # pending | running | succeeded | failed | blocked | cooldown
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # passed | failed | skipped
    verification_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportAISummary(Base):
    __tablename__ = "support_ai_summaries"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    issue_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    probable_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    diagnostics_run: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    recommended_actions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # list of strings
    transcript_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
