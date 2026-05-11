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


# ─────────────────────────────────────────────────────────────────────
# Internal review (Phase R3)
# ─────────────────────────────────────────────────────────────────────
#
# These schemas back the /api/registrations surface and are NOT used
# by the anonymous /api/public/registrations endpoints.  Internal
# users see more (reviewer fields, conversion linkage) and can edit
# fields the customer-facing PATCH does not expose.


class RegistrationAdminUpdate(BaseModel):
    """Fields an internal reviewer may edit on a registration.

    Status itself is intentionally NOT in this schema — transitions go
    through the /transition endpoint so the state machine enforces
    legality and writes a registration_status_events row.
    """

    reviewer_notes: Optional[str] = Field(None, max_length=8000)
    target_tenant_id: Optional[str] = Field(None, max_length=100)
    selected_plan_code: Optional[str] = Field(None, max_length=100)
    plan_quantity_estimate: Optional[conint(ge=0, le=10000)] = None
    billing_method: Optional[str] = Field(None, max_length=50)
    installer_notes: Optional[str] = Field(None, max_length=4000)


class RegistrationTransitionRequest(BaseModel):
    """Body for POST /api/registrations/{id}/transition."""

    to_status: str = Field(..., min_length=1, max_length=40)
    note: Optional[str] = Field(None, max_length=4000)


class RegistrationRequestInfoRequest(BaseModel):
    """Body for POST /api/registrations/{id}/request-info.

    `message` is stored on the resulting status event so the reviewer
    has a record of what they asked the customer to clarify.  R3 does
    not email the customer — that hook lands in a later phase.
    """

    message: str = Field(..., min_length=1, max_length=4000)


class RegistrationCancelRequest(BaseModel):
    """Body for POST /api/registrations/{id}/cancel."""

    reason: str = Field(..., min_length=1, max_length=4000)


class RegistrationListItemOut(BaseModel):
    """Slim row used by the internal list view.

    Carries pre-computed counts so the list page doesn't issue N+1
    queries from the frontend.  hardware/carrier summaries are pulled
    from the registration's service units and joined into a single
    human-readable string.
    """

    id: int
    registration_id: str
    tenant_id: str
    status: str

    submitter_email: str
    submitter_name: Optional[str] = None
    customer_name: Optional[str] = None

    poc_name: Optional[str] = None
    poc_phone: Optional[str] = None
    poc_email: Optional[str] = None

    locations_count: int = 0
    service_units_count: int = 0
    hardware_summary: Optional[str] = None
    carrier_summary: Optional[str] = None

    submitted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RegistrationInviteOut(BaseModel):
    """One-time invite issuance result attached to the transition
    response when the activation hook just created or rotated an
    invite.

    The plaintext ``invite_token`` is included here because the
    backend cannot recover it from storage on a subsequent request —
    this is the operator's only chance to copy the invite URL.  The
    GET /invite-status endpoint deliberately does NOT return the
    token for the same reason; once the modal closes, the token is
    gone for everyone except the customer who holds the URL.
    """

    user_id: str  # UUID rendered as string
    email: str
    invite_token: str
    invite_url: str
    invite_expires_at: datetime
    was_rotated: bool


class RegistrationInviteStatusOut(BaseModel):
    """Read-only status payload returned by
    GET /api/registrations/{id}/invite-status.

    ``has_invite=False`` covers the case where the registration has
    never reached ``ready_for_activation`` — there is no corresponding
    user yet.  The plaintext token is never included; see
    RegistrationInviteOut for why.
    """

    has_invite: bool
    user_id: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = False
    has_pending_invite: bool = False
    invite_expires_at: Optional[datetime] = None


class RegistrationDetailOut(RegistrationOut):
    """Full detail returned to the internal review surface.

    Extends the customer-visible RegistrationOut with reviewer state
    and the full status timeline.  resume_token is still never
    exposed — only the expiry timestamp inherited from RegistrationOut.
    """

    reviewer_user_id: Optional[str] = None  # UUID rendered as string
    reviewer_notes: Optional[str] = None
    target_tenant_id: Optional[str] = None
    customer_id: Optional[int] = None
    status_events: list[RegistrationStatusEventOut] = Field(default_factory=list)
    # Populated only on the transition response that just created or
    # rotated an invite — subsequent GETs return invite=None because
    # the plaintext token is not recoverable from storage.
    invite: Optional[RegistrationInviteOut] = None

    model_config = {"from_attributes": True}


class RegistrationCountByStatus(BaseModel):
    """Returned by GET /api/registrations/count.

    `total` is included for the sidebar badge; per-status counts let
    the list page render filter tabs without extra round trips.
    """

    total: int
    by_status: dict[str, int] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────
# Conversion (Phase R4)
# ─────────────────────────────────────────────────────────────────────
#
# Convert is the single bridge between the staging schema (registrations
# / registration_locations / registration_service_units) and the
# production schema (tenants / customers / sites / service_units /
# subscriptions).  The schemas below back the
# POST /api/registrations/{id}/convert endpoint.
#
# The convert path explicitly does NOT touch devices, sims, lines,
# users, or any external integration (T-Mobile, Field Nation, billing,
# E911 carrier).  Those are out of scope for Phase R4.


class RegistrationConvertRequest(BaseModel):
    """Body for POST /api/registrations/{id}/convert.

    The two `_choice` discriminators force the reviewer to be explicit
    about whether each downstream row already exists or should be
    created.  Conversion never auto-decides this — fuzzy matching
    could merge into the wrong tenant or customer.
    """

    tenant_choice: str = Field(..., description="'attach_existing' or 'create_new'")
    existing_tenant_id: Optional[str] = Field(None, max_length=100)
    new_tenant_id: Optional[str] = Field(None, max_length=100)
    new_tenant_name: Optional[str] = Field(None, max_length=255)

    customer_choice: str = Field(..., description="'attach_existing' or 'create_new'")
    existing_customer_id: Optional[int] = None

    create_subscription: bool = False

    dry_run: bool = False
    # `confirm` must be true on a real run.  Guards against reviewers
    # who hit Convert without realising they were on the production
    # tab instead of the dry-run preview.
    confirm: bool = False

    @model_validator(mode="after")
    def _validate_choices(self) -> "RegistrationConvertRequest":
        if self.tenant_choice not in ("attach_existing", "create_new"):
            raise ValueError(
                "tenant_choice must be 'attach_existing' or 'create_new'"
            )
        if self.tenant_choice == "attach_existing" and not self.existing_tenant_id:
            raise ValueError(
                "tenant_choice='attach_existing' requires existing_tenant_id"
            )
        if self.tenant_choice == "create_new":
            if not self.new_tenant_id or not self.new_tenant_name:
                raise ValueError(
                    "tenant_choice='create_new' requires both new_tenant_id and new_tenant_name"
                )

        if self.customer_choice not in ("attach_existing", "create_new"):
            raise ValueError(
                "customer_choice must be 'attach_existing' or 'create_new'"
            )
        if self.customer_choice == "attach_existing" and not self.existing_customer_id:
            raise ValueError(
                "customer_choice='attach_existing' requires existing_customer_id"
            )

        # Real (non-dry-run) calls must carry confirm=true.  Dry runs
        # don't need it — they cannot mutate state.
        if not self.dry_run and not self.confirm:
            raise ValueError(
                "confirm must be true to run a real conversion. "
                "Set dry_run=true to preview without writing."
            )
        return self


class ConvertedTenantOut(BaseModel):
    tenant_id: str
    name: str
    was_created: bool


class ConvertedCustomerOut(BaseModel):
    id: Optional[int] = None  # null in dry_run
    name: str
    tenant_id: str
    was_created: bool


class ConvertedSiteOut(BaseModel):
    id: Optional[int] = None  # null in dry_run
    site_id: str
    location_label: str
    registration_location_id: int
    was_created: bool


class ConvertedServiceUnitOut(BaseModel):
    id: Optional[int] = None  # null in dry_run
    unit_id: str
    unit_label: str
    site_id: str
    registration_service_unit_id: int
    was_created: bool


class ConvertedSubscriptionOut(BaseModel):
    id: Optional[int] = None  # null in dry_run
    plan_name: str
    status: str
    was_created: bool


class RegistrationConvertResponse(BaseModel):
    """Returned by POST /api/registrations/{id}/convert.

    Carries the materialized rows so the frontend can immediately
    render links to the new tenant/customer/sites without a second
    round trip.  In dry_run mode, ids are null but the rest of the
    payload reflects exactly what a real run would have created.
    """

    registration: RegistrationDetailOut
    dry_run: bool
    tenant: ConvertedTenantOut
    customer: ConvertedCustomerOut
    sites: list[ConvertedSiteOut] = Field(default_factory=list)
    service_units: list[ConvertedServiceUnitOut] = Field(default_factory=list)
    subscription: Optional[ConvertedSubscriptionOut] = None
