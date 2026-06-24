"""Pydantic schemas for the AI Customer Operations Center / Support Center."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ── Controlled vocabularies (validated in the router) ────────────────

ISSUE_CATEGORIES = [
    "no_dial_tone",
    "elevator_phone_issue",
    "fire_panel_issue",          # FACP / fire alarm communicator
    "gate_phone_issue",
    "area_of_refuge_issue",
    "device_offline",
    "billing_question",
    "location_update",           # location / site update
    "e911_question",
    "general_support",
]

SESSION_SOURCES = ["phone", "chat", "internal", "customer_portal"]

IDENTIFIER_TYPES = [
    # Elevator / analog line
    "elevator_phone",
    "msisdn",
    "device_label",
    "elevator_number",
    "site_name",
    "building_name",
    # FACP / fire alarm communicator
    "starlink_id",
    "napco_radio",
    "iccid",
    "central_station_account",
    "panel_location",
    # Gate / area of refuge / emergency phone
    "phone_number",
    # Generic extras supported by native-field fallback search
    "imei",
    "serial_number",
    "unit_name",
    "did",
]


# ── Asset identity (internal management) ─────────────────────────────

class AssetIdentityCreate(BaseModel):
    identifier_type: str
    identifier_value: str
    asset_kind: str  # device | site | service_unit | line
    asset_ref: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    service_unit_id: Optional[str] = None
    label: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = "manual"


class AssetIdentityOut(BaseModel):
    id: int
    tenant_id: str
    identifier_type: str
    identifier_value: str
    asset_kind: str
    asset_ref: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    service_unit_id: Optional[str] = None
    label: Optional[str] = None
    category: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Asset lookup (caller-facing — REDACTED before verification) ──────

class AssetLookupRequest(BaseModel):
    identifier: str = Field(..., description="Any known real-world identifier value.")
    identifier_type: Optional[str] = Field(
        None,
        description="Optional hint (elevator_phone, iccid, napco_radio, site_name, …). "
        "When omitted the lookup tries all identifier types.",
    )
    # When a session already exists, attach the best match to it.
    session_id: Optional[UUID] = None


class AssetMatch(BaseModel):
    """A redacted match — enough to confirm the asset and send an OTP, but
    NO billing/device-sensitive/customer-private data."""

    asset_kind: str
    asset_ref: str
    label: Optional[str] = None
    category: Optional[str] = None
    site_name: Optional[str] = None
    building_name: Optional[str] = None
    matched_identifier_type: Optional[str] = None
    match_source: str  # asset_identity | device | site | service_unit | line
    # Whether an authorized contact is on file (drives the OTP step).  The
    # number itself is masked.
    has_contact_on_file: bool = False
    contact_name: Optional[str] = None
    contact_phone_masked: Optional[str] = None
    # Internal tenant pointer — only populated for platform operators.
    tenant_id: Optional[str] = None


class AssetLookupResponse(BaseModel):
    query: str
    match_count: int
    matches: list[AssetMatch]
    note: Optional[str] = None


# ── Support session ──────────────────────────────────────────────────

class SessionCreate(BaseModel):
    caller_phone: Optional[str] = None
    source: str = "phone"
    issue_category: Optional[str] = None
    issue_summary: Optional[str] = None
    is_emergency: bool = False
    # Optional identifier to attempt an immediate match on creation.
    identifier: Optional[str] = None
    identifier_type: Optional[str] = None


class SessionEventOut(BaseModel):
    event_type: str
    actor: Optional[str] = None
    summary: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    """Caller-facing session view.

    Sensitive matched fields (device id, tenant id) are only populated by
    the router AFTER verification — see ``app.routers.ops_center``.
    """

    id: UUID
    session_ref: str
    caller_phone: Optional[str] = None
    source: str
    issue_category: Optional[str] = None
    issue_summary: Optional[str] = None
    is_emergency: bool
    status: str
    verification_status: str

    matched_asset_kind: Optional[str] = None
    matched_label: Optional[str] = None
    matched_site_id: Optional[str] = None
    matched_service_unit_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone_masked: Optional[str] = None

    # Verification-gated (None until verified).
    matched_tenant_id: Optional[str] = None
    matched_device_id: Optional[str] = None

    escalation_status: str = "none"
    handoff_number: Optional[str] = None
    incident_ref: Optional[str] = None
    ticket_ref: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SessionDetail(SessionOut):
    events: list[SessionEventOut] = []


# ── OTP ──────────────────────────────────────────────────────────────

class SendOtpRequest(BaseModel):
    # Optional override of the destination contact (e.g. operator confirms a
    # different authorized contact).  When omitted, the contact resolved at
    # match time is used.  This is a phone NUMBER, never echoed back in full.
    destination_override: Optional[str] = None


class SendOtpResponse(BaseModel):
    session_id: UUID
    otp_status: str  # otp_sent | failed
    destination_masked: Optional[str] = None
    provider: str
    simulated: bool = False
    expires_at: Optional[datetime] = None
    message: Optional[str] = None


class VerifyOtpRequest(BaseModel):
    code: str


class VerifyOtpResponse(BaseModel):
    session_id: UUID
    verified: bool
    verification_status: str
    attempts_remaining: Optional[int] = None
    message: Optional[str] = None


# ── Triage ───────────────────────────────────────────────────────────

class TriageCheck(BaseModel):
    check: str
    status: str  # ok | warning | critical | unknown | unavailable
    customer_safe_summary: str
    detail: Optional[dict] = None


class TriageResponse(BaseModel):
    session_id: UUID
    issue_category: Optional[str] = None
    overall: str  # ok | attention | critical | unknown
    checks: list[TriageCheck]
    recommended_action: Optional[str] = None


# ── Escalation / handoff ─────────────────────────────────────────────

class EscalateRequest(BaseModel):
    reason: Optional[str] = None
    handoff_number: Optional[str] = None
    create_incident: bool = False


class HandoffSummary(BaseModel):
    session_ref: str
    issue_category: Optional[str] = None
    issue_summary: Optional[str] = None
    is_emergency: bool
    verification_status: str
    customer: Optional[str] = None  # matched tenant (internal view only)
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    service_unit_id: Optional[str] = None
    asset_label: Optional[str] = None
    identifiers_used: list[str] = []
    diagnostics: list[TriageCheck] = []
    recommended_next_action: Optional[str] = None
    handoff_number: Optional[str] = None


class EscalateResponse(BaseModel):
    session_id: UUID
    escalation_status: str
    incident_ref: Optional[str] = None
    ticket_ref: Optional[str] = None
    handoff_number: Optional[str] = None
    handoff_summary: HandoffSummary
