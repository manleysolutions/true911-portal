"""Pydantic schemas for the self-service customer registration intake.

Used by api/app/routers/public.py (anonymous endpoints) and the
registration_service module.

R1 scope: input validation, length caps, and read shapes.  Internal
review / approval / conversion schemas land in a later phase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, conint, model_validator


# Payload caps — enforced by Pydantic so over-sized submissions fail
# with a 422 before they ever touch the service layer.
MAX_LOCATIONS_PER_REGISTRATION = 50
MAX_SERVICE_UNITS_PER_LOCATION = 50
MAX_SERVICE_UNITS_PER_REGISTRATION = 250


# ─────────────────────────────────────────────────────────────────────
# Service unit (nested under location on submit)
# ─────────────────────────────────────────────────────────────────────

class RegistrationServiceUnitIn(BaseModel):
    unit_label: str = Field(..., min_length=1, max_length=255)
    unit_type: str = Field(..., min_length=1, max_length=50)
    phone_number_existing: Optional[str] = Field(None, max_length=50)
    hardware_model_request: Optional[str] = Field(None, max_length=255)
    carrier_request: Optional[str] = Field(None, max_length=100)
    quantity: conint(ge=1, le=100) = 1
    install_type: Optional[str] = Field(None, max_length=30)
    notes: Optional[str] = Field(None, max_length=4000)


class RegistrationServiceUnitUpdate(BaseModel):
    unit_label: Optional[str] = Field(None, min_length=1, max_length=255)
    unit_type: Optional[str] = Field(None, min_length=1, max_length=50)
    phone_number_existing: Optional[str] = Field(None, max_length=50)
    hardware_model_request: Optional[str] = Field(None, max_length=255)
    carrier_request: Optional[str] = Field(None, max_length=100)
    quantity: Optional[conint(ge=1, le=100)] = None
    install_type: Optional[str] = Field(None, max_length=30)
    notes: Optional[str] = Field(None, max_length=4000)


class RegistrationServiceUnitOut(BaseModel):
    id: int
    registration_id: int
    registration_location_id: int
    unit_label: str
    unit_type: str
    phone_number_existing: Optional[str] = None
    hardware_model_request: Optional[str] = None
    carrier_request: Optional[str] = None
    quantity: int
    install_type: Optional[str] = None
    notes: Optional[str] = None
    materialized_service_unit_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# Location
# ─────────────────────────────────────────────────────────────────────

class RegistrationLocationIn(BaseModel):
    location_label: str = Field(..., min_length=1, max_length=255)
    street: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip: Optional[str] = Field(None, max_length=30)
    country: Optional[str] = Field(None, max_length=50)
    poc_name: Optional[str] = Field(None, max_length=255)
    poc_phone: Optional[str] = Field(None, max_length=50)
    poc_email: Optional[EmailStr] = None
    dispatchable_description: Optional[str] = Field(None, max_length=4000)
    access_notes: Optional[str] = Field(None, max_length=4000)

    # Service units may be supplied inline at create time.  The cap is
    # enforced here as well as on the service layer so a malformed
    # client-side wizard can't get past the API edge.
    service_units: list[RegistrationServiceUnitIn] = Field(
        default_factory=list,
        max_length=MAX_SERVICE_UNITS_PER_LOCATION,
    )


class RegistrationLocationUpdate(BaseModel):
    location_label: Optional[str] = Field(None, min_length=1, max_length=255)
    street: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip: Optional[str] = Field(None, max_length=30)
    country: Optional[str] = Field(None, max_length=50)
    poc_name: Optional[str] = Field(None, max_length=255)
    poc_phone: Optional[str] = Field(None, max_length=50)
    poc_email: Optional[EmailStr] = None
    dispatchable_description: Optional[str] = Field(None, max_length=4000)
    access_notes: Optional[str] = Field(None, max_length=4000)


class RegistrationLocationOut(BaseModel):
    id: int
    registration_id: int
    location_label: str
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    poc_name: Optional[str] = None
    poc_phone: Optional[str] = None
    poc_email: Optional[str] = None
    dispatchable_description: Optional[str] = None
    access_notes: Optional[str] = None
    materialized_site_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    service_units: list[RegistrationServiceUnitOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# Registration (top-level)
# ─────────────────────────────────────────────────────────────────────

class RegistrationCreate(BaseModel):
    """Initial submission from /api/public/registrations.

    All step-1 fields are accepted at create time.  Everything else
    (plan, billing, support prefs, install scheduling, etc.) can be
    PATCHed in later turns of the wizard.

    Locations and their nested service units may also be supplied on
    create — useful for clients that collect the whole tree before
    POSTing.
    """

    submitter_email: EmailStr
    submitter_name: Optional[str] = Field(None, max_length=255)
    submitter_phone: Optional[str] = Field(None, max_length=50)
    customer_name: Optional[str] = Field(None, max_length=255)
    customer_legal_name: Optional[str] = Field(None, max_length=255)
    customer_account_number: Optional[str] = Field(None, max_length=100)

    poc_name: Optional[str] = Field(None, max_length=255)
    poc_phone: Optional[str] = Field(None, max_length=50)
    poc_email: Optional[EmailStr] = None
    poc_role: Optional[str] = Field(None, max_length=100)

    use_case_summary: Optional[str] = Field(None, max_length=8000)

    selected_plan_code: Optional[str] = Field(None, max_length=100)
    plan_quantity_estimate: Optional[conint(ge=0, le=10000)] = None

    billing_email: Optional[EmailStr] = None
    billing_address_street: Optional[str] = Field(None, max_length=500)
    billing_address_city: Optional[str] = Field(None, max_length=100)
    billing_address_state: Optional[str] = Field(None, max_length=50)
    billing_address_zip: Optional[str] = Field(None, max_length=30)
    billing_address_country: Optional[str] = Field(None, max_length=50)
    billing_method: Optional[str] = Field(None, max_length=50)

    support_preference_json: Optional[dict[str, Any]] = None

    preferred_install_window_start: Optional[datetime] = None
    preferred_install_window_end: Optional[datetime] = None
    installer_notes: Optional[str] = Field(None, max_length=4000)

    locations: list[RegistrationLocationIn] = Field(
        default_factory=list,
        max_length=MAX_LOCATIONS_PER_REGISTRATION,
    )

    @model_validator(mode="after")
    def _cap_total_service_units(self) -> "RegistrationCreate":
        total = sum(len(loc.service_units) for loc in self.locations)
        if total > MAX_SERVICE_UNITS_PER_REGISTRATION:
            raise ValueError(
                f"too many service units in submission: {total} > "
                f"{MAX_SERVICE_UNITS_PER_REGISTRATION}"
            )
        return self


class RegistrationUpdate(BaseModel):
    """Partial update.  Only the fields a customer may legitimately
    edit during the wizard are exposed here — internal-only fields
    (reviewer_user_id, reviewer_notes, customer_id, target_tenant_id,
    lifecycle timestamps, status) are not accepted on this surface and
    will be ignored if sent.
    """

    submitter_name: Optional[str] = Field(None, max_length=255)
    submitter_phone: Optional[str] = Field(None, max_length=50)
    customer_name: Optional[str] = Field(None, max_length=255)
    customer_legal_name: Optional[str] = Field(None, max_length=255)
    customer_account_number: Optional[str] = Field(None, max_length=100)

    poc_name: Optional[str] = Field(None, max_length=255)
    poc_phone: Optional[str] = Field(None, max_length=50)
    poc_email: Optional[EmailStr] = None
    poc_role: Optional[str] = Field(None, max_length=100)

    use_case_summary: Optional[str] = Field(None, max_length=8000)

    selected_plan_code: Optional[str] = Field(None, max_length=100)
    plan_quantity_estimate: Optional[conint(ge=0, le=10000)] = None

    billing_email: Optional[EmailStr] = None
    billing_address_street: Optional[str] = Field(None, max_length=500)
    billing_address_city: Optional[str] = Field(None, max_length=100)
    billing_address_state: Optional[str] = Field(None, max_length=50)
    billing_address_zip: Optional[str] = Field(None, max_length=30)
    billing_address_country: Optional[str] = Field(None, max_length=50)
    billing_method: Optional[str] = Field(None, max_length=50)

    support_preference_json: Optional[dict[str, Any]] = None

    preferred_install_window_start: Optional[datetime] = None
    preferred_install_window_end: Optional[datetime] = None
    installer_notes: Optional[str] = Field(None, max_length=4000)


class RegistrationStatusEventOut(BaseModel):
    id: int
    registration_id: int
    from_status: Optional[str] = None
    to_status: str
    actor_user_id: Optional[str] = None  # rendered as string for transport
    actor_email: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RegistrationOut(BaseModel):
    """Public read shape — does NOT include resume_token_hash or
    internal review fields beyond what's strictly informational.
    """

    id: int
    registration_id: str
    tenant_id: str
    status: str

    submitter_email: str
    submitter_name: Optional[str] = None
    submitter_phone: Optional[str] = None
    customer_name: Optional[str] = None
    customer_legal_name: Optional[str] = None
    customer_account_number: Optional[str] = None

    poc_name: Optional[str] = None
    poc_phone: Optional[str] = None
    poc_email: Optional[str] = None
    poc_role: Optional[str] = None

    use_case_summary: Optional[str] = None

    selected_plan_code: Optional[str] = None
    plan_quantity_estimate: Optional[int] = None

    billing_email: Optional[str] = None
    billing_address_street: Optional[str] = None
    billing_address_city: Optional[str] = None
    billing_address_state: Optional[str] = None
    billing_address_zip: Optional[str] = None
    billing_address_country: Optional[str] = None
    billing_method: Optional[str] = None

    support_preference_json: Optional[dict[str, Any]] = None

    preferred_install_window_start: Optional[datetime] = None
    preferred_install_window_end: Optional[datetime] = None
    installer_notes: Optional[str] = None

    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None

    resume_token_expires_at: datetime

    locations: list[RegistrationLocationOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RegistrationCreateResponse(BaseModel):
    """Returned only at POST time — carries the plaintext resume_token
    so the client can persist it.  Subsequent reads never expose it.
    """

    registration: RegistrationOut
    resume_token: str
