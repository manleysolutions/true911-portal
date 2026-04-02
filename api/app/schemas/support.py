"""Pydantic schemas for the Support feature."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ── Session ─────────────────────────────────────────────────────

class SupportSessionCreate(BaseModel):
    site_id: Optional[int] = None
    device_id: Optional[int] = None
    initial_message: Optional[str] = None


class SupportSessionOut(BaseModel):
    id: UUID
    tenant_id: str
    user_id: UUID
    site_id: Optional[int] = None
    device_id: Optional[int] = None
    status: str
    issue_category: Optional[str] = None
    resolution_summary: Optional[str] = None
    escalated: bool
    message_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class SupportSessionUpdate(BaseModel):
    status: Optional[str] = None  # active | resolved | escalated
    resolution_summary: Optional[str] = None


# ── Message ─────────────────────────────────────────────────────

class SupportMessageSend(BaseModel):
    content: str


class SupportMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    structured_response: Optional[dict] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class SupportSessionDetail(BaseModel):
    session: SupportSessionOut
    messages: list[SupportMessageOut]
    diagnostics: list[SupportDiagnosticOut] = []
    escalations: list[SupportEscalationOut] = []  # admin-only; empty for subscribers


# ── Diagnostic ──────────────────────────────────────────────────

class SupportDiagnosticOut(BaseModel):
    id: UUID
    session_id: UUID
    check_type: str
    status: str
    severity: str
    confidence: float
    customer_safe_summary: str
    # internal fields only shown to admins — set to None for customers
    internal_summary: Optional[str] = None
    raw_payload: Optional[dict] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class DiagnosticRunRequest(BaseModel):
    session_id: UUID
    site_id: Optional[int] = None
    device_id: Optional[int] = None
    checks: Optional[list[str]] = None  # specific checks to run, or None for all


class DiagnosticResult(BaseModel):
    check_type: str
    status: str
    severity: str
    confidence: float
    customer_safe_summary: str
    internal_summary: str
    raw_payload: Optional[dict] = None


# ── Escalation ──────────────────────────────────────────────────

class EscalationRequest(BaseModel):
    session_id: UUID
    reason: str
    additional_notes: Optional[str] = None


class SupportEscalationOut(BaseModel):
    """Full escalation detail — admin view. Use sanitize_for_subscriber() for customer view."""
    id: UUID
    session_id: UUID
    reason: str
    probable_cause: Optional[str] = None
    issue_category: Optional[str] = None
    escalation_level: Optional[str] = None
    handoff_summary: str
    zoho_ticket_id: Optional[str] = None
    zoho_ticket_number: Optional[str] = None
    zoho_ticket_url: Optional[str] = None
    zoho_status: Optional[str] = None
    dedupe_key: Optional[str] = None
    was_deduplicated: bool = False
    linked_escalation_id: Optional[UUID] = None
    status: str
    synced_at: Optional[datetime] = None
    sync_error: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class SupportEscalationCustomerOut(BaseModel):
    """Subscriber-safe escalation response — no Zoho/internal details."""
    id: UUID
    session_id: UUID
    status: str  # simplified: "submitted" always for customer
    message: str  # calm confirmation
    created_at: datetime


# ── Remediation ─────────────────────────────────────────────────

class RemediationRunRequest(BaseModel):
    action_type: str
    session_id: Optional[UUID] = None
    escalation_id: Optional[UUID] = None
    tenant_id: Optional[str] = None  # admin override; defaults to current_user.tenant_id
    site_id: Optional[int] = None
    device_id: Optional[int] = None
    issue_category: Optional[str] = None


class RemediationActionOut(BaseModel):
    id: UUID
    session_id: Optional[UUID] = None
    escalation_id: Optional[UUID] = None
    tenant_id: str
    site_id: Optional[int] = None
    device_id: Optional[int] = None
    issue_category: Optional[str] = None
    trigger_source: str
    action_type: str
    action_level: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    verification_status: Optional[str] = None
    verification_summary: Optional[str] = None
    attempt_count: int
    blocked_reason: Optional[str] = None
    raw_result: Optional[dict] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── AI Structured Response ──────────────────────────────────────

class AIStructuredResponse(BaseModel):
    issue_category: str = ""
    probable_cause: str = ""
    customer_response: str = ""
    recommended_actions: list[str] = []
    escalate: bool = False
    escalation_reason: str = ""
    confidence: float = 0.0


# Forward reference fix — SupportSessionDetail uses SupportDiagnosticOut
SupportSessionDetail.model_rebuild()
