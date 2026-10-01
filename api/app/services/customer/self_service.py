"""Customer Self-Service — the Customer Operations Console backend.

Moves the customer plane from "dashboard + call support for changes" to
"customer operations console + governed escalation".  A CUSTOMER_* user manages
the CUSTOMER-OWNED operational layer of their portfolio directly, and asks for
anything that touches provisioning, identity or life-safety verification through
a GOVERNED request that operations review.

THE OWNERSHIP BOUNDARY (the whole module rests on it — see
``docs/customer/CUSTOMER_SELF_SERVICE.md`` §2):

  * CUSTOMER-MANAGED — written directly (with an audit event carrying old/new):
    location display name, location / access notes, customer reference,
    notification preferences, facility / emergency / property-manager contacts,
    and per-connection friendly name, purpose, notes and point of contact.
    These live in ``customer_managed_fields`` — an OVERLAY beside the system
    records, never inside them — so no customer edit can overwrite a Site,
    Device, Line, registry or E911 value.
  * REQUEST-BASED — never applied directly; submitting one creates a
    ``CustomerServiceRequest``: canonical name / address / store number
    (location_correction), telephone or E911 callback number (change_number),
    service type (change_service_type), add / remove / move service, replace
    equipment, problem reports, and E911 verification.
  * SYSTEM-MANAGED — refused outright (HTTP 403): SIM / ICCID / IMEI / MSISDN,
    carrier & SIP & network configuration, device hardware identity, monitoring
    / health / audit / certification evidence, verified-E911 status, and
    source-system / registry mappings.

E911 is never asserted by a customer: an attestation is recorded with full
provenance and routed to the existing verification queue; ``verified`` derives
ONLY from the official emergency record (Constitution §4.3 / §4.6, D-006).

Tenant isolation: every read and write is filtered by the caller's tenant; a
location is resolved from an HMAC-signed ref and then re-checked against the
tenant, and a connection ref is signed together with its location key.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.action_audit import ActionAudit
from app.models.customer_self_service import (
    CustomerActivityEvent,
    CustomerManagedField,
    CustomerServiceRequest,
)
from app.services.customer import physical_devices as pdev
from app.services.customer.refs import decode_ref, encode_ref
from app.services.rbac import can as rbac_can

# ══════════════════════════════════════════════════════════════════════
# Ownership boundary
# ══════════════════════════════════════════════════════════════════════
CONNECTION_PURPOSES = ("elevator", "fire_alarm", "emergency_phone", "security", "fax", "gate",
                       "other")
PURPOSE_LABELS = {"elevator": "Elevator", "fire_alarm": "Fire Alarm",
                  "emergency_phone": "Emergency Phone", "security": "Security",
                  "fax": "Fax", "gate": "Gate", "other": "Other"}
CONTACT_ROLES = ("facility", "emergency", "property_manager")
CONTACT_LABELS = {"facility": "Facility contact", "emergency": "Emergency contact",
                  "property_manager": "Property / facility manager"}
NOTIFY_EVENTS = ("service_issue", "e911_update", "request_update")

# Location-level fields the customer owns (field -> max length, or "prefs").
LOCATION_FIELDS = {"display_name": 120, "location_notes": 4000, "access_notes": 4000,
                   "customer_reference": 120, "notification_preferences": "prefs"}
LOCATION_FIELD_LABELS = {"display_name": "location name", "location_notes": "location notes",
                         "access_notes": "access notes",
                         "customer_reference": "customer reference",
                         "notification_preferences": "notification preferences"}
# Connection-level fields the customer owns.
CONNECTION_FIELDS = {"friendly_name": 120, "purpose": "purpose", "customer_notes": 2000,
                     "customer_contact": "contact"}
CONNECTION_FIELD_LABELS = {"friendly_name": "connection name", "purpose": "connection purpose",
                           "customer_notes": "connection notes",
                           "customer_contact": "connection contact"}

# Fields a customer may ASK to change — each maps to the governed request type.
REQUEST_BASED_LOCATION_FIELDS = {
    "canonical_name": "location_correction", "address": "location_correction",
    "city": "location_correction", "state": "location_correction",
    "zip": "location_correction", "store_number": "location_correction",
    "site_type": "location_correction",
}
REQUEST_BASED_CONNECTION_FIELDS = {
    "phone_number": "change_number", "callback_number": "change_number",
    "telephone_number": "change_number", "service_type": "change_service_type",
}

# Never customer-writable — refused with 403 (and nothing in the call is applied).
SYSTEM_MANAGED_FIELDS = frozenset({
    "iccid", "imei", "imsi", "sim", "sim_id", "sim_status", "sim_activation",
    "sim_activation_state", "msisdn", "carrier", "carrier_account", "carrier_account_id",
    "carrier_provisioning", "provisioning", "sip", "sip_username", "sip_password",
    "sip_credentials", "network", "network_config", "network_configuration", "apn",
    "ip_address", "device_id", "device_identity", "hardware_identity", "serial_number",
    "mac_address", "firmware_version", "model", "radio_number", "starlink_id",
    "e911_status", "e911_verified", "verified", "verification_status", "verified_by",
    "verification_method", "verification_timestamp", "monitoring", "monitoring_evidence",
    "health", "telemetry", "last_heartbeat", "audit", "audit_evidence", "certification",
    "certification_evidence", "source_mapping", "source_system_mapping", "registry_mapping",
    "approved", "approved_by", "approved_at", "zoho_account", "napco_radio",
    "genesis_msisdn", "tenant_id", "building_id", "site_id", "status",
})

REQUEST_TYPES = {
    "add_service": "Add service",
    "remove_service": "Remove service",
    "move_service": "Move service",
    "change_number": "Change telephone number",
    "change_service_type": "Change service type",
    "replace_device": "Replace equipment",
    "e911_verification": "E911 verification",
    "location_correction": "Location correction",
    "support_request": "Problem report",
}
CHANGE_REQUEST_TYPES = frozenset({"add_service", "remove_service", "move_service",
                                  "change_number", "change_service_type", "replace_device",
                                  "location_correction"})
REQUEST_STATUSES = ("submitted", "under_review", "approved", "in_progress", "waiting_customer",
                    "completed", "rejected", "cancelled")
STATUS_LABELS = {"submitted": "Submitted", "under_review": "Under review",
                 "approved": "Approved", "in_progress": "In progress",
                 "waiting_customer": "Waiting on you", "completed": "Completed",
                 "rejected": "Not approved", "cancelled": "Cancelled"}
TERMINAL_STATUSES = frozenset({"completed", "rejected", "cancelled"})
PRIORITIES = ("normal", "high", "urgent")

# Operations-side state machine (every transition is audited).
OPERATIONS_TRANSITIONS = {
    "submitted": {"under_review", "approved", "rejected", "waiting_customer", "in_progress"},
    "under_review": {"approved", "rejected", "waiting_customer", "in_progress"},
    "approved": {"in_progress", "completed", "rejected", "waiting_customer"},
    "in_progress": {"completed", "waiting_customer", "rejected"},
    "waiting_customer": {"under_review", "in_progress", "rejected"},
}
# Customer-side: cancel an open request, or respond when operations asked.
CUSTOMER_CANCELLABLE = frozenset({"submitted", "under_review", "waiting_customer"})

# E911 self-service states (the customer never reaches "verified" on their own).
E911_STATE_LABELS = {
    "not_verified": "E911 record being prepared",
    "customer_confirmation_required": "Confirmation needed",
    "customer_submitted": "Submitted — awaiting verification",
    "verification_pending": "Verification in progress",
    "requires_review": "Correction under review",
    "failed": "Needs correction",
    "verified": "Verified",
}
# The ONLY states in which the customer can act (Verify E911).  ``not_verified``
# means there is no dispatch address on file yet: there is nothing for the
# customer to confirm, so it is never presented as a confirmation — operations
# prepare the record first (the go-live audit reports it as a system warning).
E911_CUSTOMER_ACTION_STATES = frozenset({"customer_confirmation_required", "failed"})
E911_STATE_REASONS = {
    "not_verified": "No dispatch address on file yet — the verification team is preparing this record.",
    "customer_confirmation_required": "Review the dispatch address and numbers, then confirm.",
    "customer_submitted": "Thank you — the verification team will complete verification.",
    "requires_review": "Your correction is being reviewed.",
    "verification_pending": "The verification team is completing verification.",
    "failed": "The verification team could not verify this record — please review and resubmit.",
    "verified": "Verified on the official emergency record.",
}
_E911_VERIFIED = frozenset({"validated", "verified", "confirmed"})

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_CHANGES_JSON = 8000

ORIGIN_CUSTOMER = "customer_portal"
ORIGIN_OPERATIONS = "operations"
AUDIT_ACTION = "customer_self_service"


class SelfServiceError(Exception):
    """A rejected self-service mutation.  ``status`` is the HTTP code the router
    returns; ``code`` is a stable machine token; ``message`` is customer-safe."""

    def __init__(self, status: int, code: str, message: str, fields: Optional[list] = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or []

    def as_detail(self) -> dict:
        return {"code": self.code, "message": self.message, "fields": self.fields}


# ══════════════════════════════════════════════════════════════════════
# Gating + capabilities
# ══════════════════════════════════════════════════════════════════════
def self_service_enabled(user) -> bool:
    """Two-key flag gate + optional per-user narrowing (RH Test before Judy)."""
    if settings.FEATURE_CUSTOMER_SELF_SERVICE != "true":
        return False
    if getattr(user, "tenant_id", None) not in settings.customer_self_service_tenant_id_set:
        return False
    users = settings.customer_self_service_user_set
    return not users or (getattr(user, "email", "") or "").lower() in users


def capabilities(user) -> dict:
    role = getattr(user, "role", "")
    enabled = self_service_enabled(user)

    def c(perm):
        return bool(enabled and rbac_can(role, perm))
    return {
        "enabled": enabled,
        "can_manage_location": c("CUSTOMER_MANAGE_LOCATION"),
        "can_manage_contacts": c("CUSTOMER_MANAGE_CONTACTS"),
        "can_submit_requests": c("CUSTOMER_SUBMIT_REQUESTS"),
        "can_attest_e911": c("CUSTOMER_ATTEST_E911"),
        "can_view_requests": c("CUSTOMER_VIEW_REQUESTS"),
        "connection_purposes": [{"value": p, "label": PURPOSE_LABELS[p]} for p in CONNECTION_PURPOSES],
        "contact_roles": [{"value": r, "label": CONTACT_LABELS[r]} for r in CONTACT_ROLES],
        "request_types": [{"value": k, "label": v} for k, v in REQUEST_TYPES.items()
                          if k != "e911_verification"],
    }


# ══════════════════════════════════════════════════════════════════════
# Location context (registry building OR legacy site)
# ══════════════════════════════════════════════════════════════════════
@dataclass
class LocationContext:
    ref: str
    key: str                              # bldg:<id> | site:<site_id>
    mode: str                             # registry | site
    building_id: Optional[int] = None
    site: Any = None                      # primary linked Site (may be None)
    canonical_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    store_number: Optional[str] = None
    site_type: Optional[str] = None
    record: Optional[dict] = None         # registry aggregate (full loads only)
    extra: dict = field(default_factory=dict)

    @property
    def site_id(self) -> Optional[str]:
        return getattr(self.site, "site_id", None)


async def resolve_location_context(db: AsyncSession, tenant_id: str, ref: str, now=None,
                                   *, full: bool = False) -> Optional[LocationContext]:
    """Resolve an opaque location ref to a tenant-scoped context, or None (404).
    ``full`` also loads the registry aggregate / legacy services for rendering."""
    from app.services.customer import portfolio as cportfolio
    from app.services.customer import portfolio_registry_view as prv

    now = now or datetime.now(timezone.utc)
    raw_site = decode_ref("loc", ref)
    if raw_site is not None:
        site = await cportfolio.resolve_site(db, tenant_id, ref)
        if site is None:
            return None
        return LocationContext(
            ref=ref, key=f"site:{site.site_id}", mode="site", site=site,
            canonical_name=site.site_name, address=site.e911_street, city=site.e911_city,
            state=site.e911_state, zip=site.e911_zip)

    raw_b = decode_ref("bldg", ref)
    if raw_b is None or not prv.registry_mode_enabled(tenant_id):
        return None
    try:
        bid = int(raw_b)
    except (TypeError, ValueError):
        return None
    from app.models.portfolio_registry import PortfolioBuilding
    b = (await db.execute(select(PortfolioBuilding).where(
        PortfolioBuilding.id == bid, PortfolioBuilding.tenant_id == tenant_id))).scalar_one_or_none()
    if b is None or not (b.approved or prv._include_pending(tenant_id)):
        return None
    ctx = LocationContext(
        ref=ref, key=f"bldg:{b.id}", mode="registry", building_id=b.id,
        canonical_name=b.canonical_name, address=b.address, city=b.city, state=b.state,
        zip=b.zip, store_number=b.store_number, site_type=b.site_type)
    if full:
        records = await prv.load_customer_buildings(db, tenant_id, now) or []
        ctx.record = next((r for r in records if r["id"] == b.id), None)
        if ctx.record is None:
            return None
    ctx.site = await cportfolio._resolve_building_primary_site(db, tenant_id, ref)
    return ctx


# ══════════════════════════════════════════════════════════════════════
# Audit (append-only; mirrored into the platform ActionAudit log)
# ══════════════════════════════════════════════════════════════════════
def _j(v) -> Optional[str]:
    return None if v is None else json.dumps(v, default=str, sort_keys=True)


def _uj(v):
    if v is None:
        return None
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _record_event(db, user, *, event_type: str, summary: str, origin: str,
                  location_key=None, building_id=None, site_id=None, subject_key=None,
                  request_ref=None, field_name=None, old=None, new=None, now=None) -> None:
    """Stage one immutable activity event + its ActionAudit mirror (caller commits)."""
    now = now or datetime.now(timezone.utc)
    db.add(CustomerActivityEvent(
        tenant_id=user.tenant_id, location_key=location_key, building_id=building_id,
        site_id=site_id, subject_key=subject_key, request_ref=request_ref,
        event_type=event_type, field=field_name, old_value=_j(old), new_value=_j(new),
        summary=summary[:255], origin=origin, actor_email=user.email,
        actor_name=getattr(user, "name", None), actor_role=user.role, occurred_at=now))
    original_tid = getattr(user, "_original_tenant_id", user.tenant_id)
    db.add(ActionAudit(
        audit_id=_uid("AUD"), request_id=_uid("REQ"), tenant_id=user.tenant_id,
        user_email=user.email, requester_name=getattr(user, "name", None), role=user.role,
        action_type=AUDIT_ACTION, site_id=site_id, timestamp=now, result="ok",
        details=json.dumps({"event_type": event_type, "origin": origin,
                            "location_key": location_key, "building_id": building_id,
                            "subject_key": subject_key, "request_ref": request_ref,
                            "field": field_name, "old": old, "new": new}, default=str),
        original_tenant_id=original_tid,
        acting_as_tenant_id=(user.tenant_id if user.tenant_id != original_tid else None)))


# ══════════════════════════════════════════════════════════════════════
# Validation helpers (pure)
# ══════════════════════════════════════════════════════════════════════
def _clean_text(v, limit: int, name: str):
    if v is None:
        return None
    if not isinstance(v, str):
        raise SelfServiceError(422, "invalid_value", f"'{name}' must be text.", [name])
    v = v.strip()
    if len(v) > limit:
        raise SelfServiceError(422, "too_long", f"'{name}' is longer than {limit} characters.", [name])
    return v or None


def _clean_phone(v, name: str):
    if v in (None, ""):
        return None
    digits = re.sub(r"\D", "", str(v))
    if not 7 <= len(digits) <= 15:
        raise SelfServiceError(422, "invalid_phone", f"'{name}' is not a valid phone number.", [name])
    return str(v).strip()[:40]


def _clean_email(v, name: str):
    if v in (None, ""):
        return None
    v = str(v).strip()
    if not _EMAIL.match(v) or len(v) > 255:
        raise SelfServiceError(422, "invalid_email", f"'{name}' is not a valid email address.", [name])
    return v


def clean_contact(v, name: str) -> Optional[dict]:
    """A contact card {name, title, phone, email}; None / {} clears it."""
    if v in (None, {}):
        return None
    if not isinstance(v, dict):
        raise SelfServiceError(422, "invalid_value", f"'{name}' must be a contact.", [name])
    unknown = set(v) - {"name", "title", "phone", "email"}
    if unknown:
        raise SelfServiceError(422, "unknown_field",
                               f"Unsupported contact detail(s): {', '.join(sorted(unknown))}.", [name])
    out = {"name": _clean_text(v.get("name"), 120, f"{name}.name"),
           "title": _clean_text(v.get("title"), 120, f"{name}.title"),
           "phone": _clean_phone(v.get("phone"), f"{name}.phone"),
           "email": _clean_email(v.get("email"), f"{name}.email")}
    out = {k: val for k, val in out.items() if val}
    if out and not (out.get("phone") or out.get("email")):
        raise SelfServiceError(422, "contact_unreachable",
                               f"'{name}' needs a phone number or an email address.", [name])
    return out or None


def _clean_prefs(v) -> Optional[dict]:
    if v in (None, {}):
        return None
    if not isinstance(v, dict):
        raise SelfServiceError(422, "invalid_value", "Notification preferences must be an object.",
                               ["notification_preferences"])
    unknown = set(v) - {"email_recipients", "notify_on"}
    if unknown:
        raise SelfServiceError(422, "unknown_field", "Unsupported notification preference.",
                               ["notification_preferences"])
    recips = v.get("email_recipients") or []
    if not isinstance(recips, list) or len(recips) > 10:
        raise SelfServiceError(422, "invalid_value", "Up to 10 notification email recipients.",
                               ["notification_preferences"])
    events = v.get("notify_on") or []
    if not isinstance(events, list) or any(e not in NOTIFY_EVENTS for e in events):
        raise SelfServiceError(422, "invalid_value", "Unsupported notification event.",
                               ["notification_preferences"])
    return {"email_recipients": [_clean_email(r, "notification_preferences") for r in recips],
            "notify_on": sorted(set(events))}


def _clean_location_value(fname: str, v):
    spec = LOCATION_FIELDS[fname]
    if spec == "prefs":
        return _clean_prefs(v)
    return _clean_text(v, spec, fname)


def _clean_connection_value(fname: str, v):
    spec = CONNECTION_FIELDS[fname]
    if spec == "purpose":
        if v in (None, ""):
            return None
        if v not in CONNECTION_PURPOSES:
            raise SelfServiceError(422, "invalid_purpose",
                                   f"Purpose must be one of: {', '.join(CONNECTION_PURPOSES)}.",
                                   ["purpose"])
        return v
    if spec == "contact":
        return clean_contact(v, "customer_contact")
    return _clean_text(v, spec, fname)


def classify_fields(changes: dict, editable: dict, request_based: dict) -> tuple[dict, dict]:
    """Split a change set into (direct edits, request-based edits).  Refuses the
    WHOLE call when any system-managed or unknown field is present — nothing is
    applied, so a mixed payload can never partially slip a protected write."""
    if not isinstance(changes, dict) or not changes:
        raise SelfServiceError(422, "no_changes", "No changes were provided.")
    system = sorted(k for k in changes if k.lower() in SYSTEM_MANAGED_FIELDS)
    if system:
        raise SelfServiceError(
            403, "system_managed_field",
            "These details are managed by the operations team and can't be changed here: "
            + ", ".join(system) + ". Use Request Service Change to ask for an update.", system)
    unknown = sorted(k for k in changes if k not in editable and k not in request_based)
    if unknown:
        raise SelfServiceError(422, "unknown_field", "Unsupported field(s): " + ", ".join(unknown),
                               unknown)
    direct = {k: v for k, v in changes.items() if k in editable}
    requested = {k: v for k, v in changes.items() if k in request_based}
    return direct, requested


def _check_changes_payload(changes) -> dict:
    changes = changes or {}
    if not isinstance(changes, dict):
        raise SelfServiceError(422, "invalid_value", "Requested changes must be an object.")
    system = sorted(k for k in changes if str(k).lower() in SYSTEM_MANAGED_FIELDS)
    if system:
        # a request may DESCRIBE a need in words, but may not carry system values
        raise SelfServiceError(403, "system_managed_field",
                               "Equipment, SIM and network identifiers are managed by the "
                               "operations team — describe the change in the notes instead.",
                               system)
    if len(json.dumps(changes, default=str)) > _MAX_CHANGES_JSON:
        raise SelfServiceError(422, "too_long", "The request details are too long.")
    return changes


# ══════════════════════════════════════════════════════════════════════
# Overlay (customer-managed fields)
# ══════════════════════════════════════════════════════════════════════
async def _field_rows(db, tenant_id, location_key=None):
    q = select(CustomerManagedField).where(CustomerManagedField.tenant_id == tenant_id)
    if location_key is not None:
        q = q.where(CustomerManagedField.location_key == location_key)
    return (await db.execute(q)).scalars().all()


def overlay_by_subject(rows) -> dict:
    """{location_key: {subject_key: {field: value}}}"""
    out: dict = {}
    for r in rows:
        out.setdefault(r.location_key, {}).setdefault(r.subject_key or "", {})[r.field] = _uj(r.value)
    return out


async def _upsert_field(db, user, ctx: LocationContext, subject_key: str, fname: str,
                        new_value, *, summary: str, now) -> bool:
    """Write one overlay value + an old/new event.  Returns False when unchanged."""
    row = (await db.execute(select(CustomerManagedField).where(
        CustomerManagedField.tenant_id == user.tenant_id,
        CustomerManagedField.location_key == ctx.key,
        CustomerManagedField.subject_key == subject_key,
        CustomerManagedField.field == fname))).scalar_one_or_none()
    old_value = _uj(row.value) if row is not None else None
    if old_value == new_value:
        return False
    if row is None:
        db.add(CustomerManagedField(
            tenant_id=user.tenant_id, location_key=ctx.key, building_id=ctx.building_id,
            site_id=ctx.site_id, subject_key=subject_key, field=fname, value=_j(new_value),
            updated_by=user.email, updated_at=now))
    else:
        row.value = _j(new_value)
        row.updated_by = user.email
        row.updated_at = now
    _record_event(db, user, event_type="field_updated", summary=summary, origin=ORIGIN_CUSTOMER,
                  location_key=ctx.key, building_id=ctx.building_id, site_id=ctx.site_id,
                  subject_key=subject_key or None, field_name=fname, old=old_value, new=new_value,
                  now=now)
    return True


def _current_location_values(ctx: LocationContext) -> dict:
    return {"canonical_name": ctx.canonical_name, "address": ctx.address, "city": ctx.city,
            "state": ctx.state, "zip": ctx.zip, "store_number": ctx.store_number,
            "site_type": ctx.site_type}


async def update_location_profile(db, user, ctx: LocationContext, changes: dict) -> dict:
    """Customer-owned location fields apply directly; identity fields (name /
    address / store #) become ONE location_correction request instead."""
    direct, requested = classify_fields(changes, LOCATION_FIELDS, REQUEST_BASED_LOCATION_FIELDS)
    cleaned = {k: _clean_location_value(k, v) for k, v in direct.items()}   # validate all first
    now = datetime.now(timezone.utc)
    applied = []
    for k, v in cleaned.items():
        if await _upsert_field(db, user, ctx, "", k, v, now=now,
                               summary=f"Updated {LOCATION_FIELD_LABELS[k]}"):
            applied.append(k)
    request = None
    if requested:
        current = _current_location_values(ctx)
        request = await _create_request(
            db, user, ctx, request_type="location_correction", now=now,
            changes={"fields": {k: {"current": current.get(k), "requested": v}
                                for k, v in requested.items()}},
            notes=None)
    await db.commit()
    return {"applied": applied, "requested": sorted(requested),
            "request": serialize_request(request) if request else None}


async def update_contacts(db, user, ctx: LocationContext, contacts: dict) -> dict:
    if not isinstance(contacts, dict) or not contacts:
        raise SelfServiceError(422, "no_changes", "No contact changes were provided.")
    unknown = sorted(set(contacts) - set(CONTACT_ROLES))
    if unknown:
        raise SelfServiceError(422, "unknown_field",
                               "Unsupported contact type(s): " + ", ".join(unknown), unknown)
    cleaned = {role: clean_contact(v, role) for role, v in contacts.items()}
    now = datetime.now(timezone.utc)
    applied = []
    for role, v in cleaned.items():
        verb = "Removed" if v is None else "Updated"
        if await _upsert_field(db, user, ctx, "", f"contact.{role}", v, now=now,
                               summary=f"{verb} {CONTACT_LABELS[role].lower()}"):
            applied.append(role)
    await db.commit()
    return {"applied": applied}


def encode_connection_ref(location_key: str, connection_key: str) -> str:
    return encode_ref("conn", f"{location_key}|{connection_key}")


def decode_connection_ref(ctx: LocationContext, connection_ref: str) -> Optional[str]:
    """The connection key, only if the signed ref was issued for THIS location."""
    raw = decode_ref("conn", connection_ref or "")
    if raw is None or "|" not in raw:
        return None
    loc_key, conn_key = raw.split("|", 1)
    return conn_key if loc_key == ctx.key and conn_key else None


async def update_connection(db, user, ctx: LocationContext, connection_key: str,
                            changes: dict) -> dict:
    direct, requested = classify_fields(changes, CONNECTION_FIELDS, REQUEST_BASED_CONNECTION_FIELDS)
    cleaned = {k: _clean_connection_value(k, v) for k, v in direct.items()}
    now = datetime.now(timezone.utc)
    applied = []
    for k, v in cleaned.items():
        if await _upsert_field(db, user, ctx, connection_key, k, v, now=now,
                               summary=f"Updated {CONNECTION_FIELD_LABELS[k]}"):
            applied.append(k)
    requests = []
    by_type: dict = {}
    for k, v in requested.items():
        by_type.setdefault(REQUEST_BASED_CONNECTION_FIELDS[k], {})[k] = v
    for rtype, fields in sorted(by_type.items()):
        requests.append(await _create_request(
            db, user, ctx, request_type=rtype, connection_key=connection_key, now=now,
            changes={"fields": {k: {"requested": v} for k, v in fields.items()}}, notes=None))
    await db.commit()
    return {"applied": applied, "requested": sorted(requested),
            "requests": [serialize_request(r) for r in requests]}


# ══════════════════════════════════════════════════════════════════════
# Governed requests
# ══════════════════════════════════════════════════════════════════════
async def _create_request(db, user, ctx: LocationContext, *, request_type: str, changes: dict,
                          notes, now, connection_key=None, priority="normal") -> CustomerServiceRequest:
    req = CustomerServiceRequest(
        request_ref=f"CSR-{uuid.uuid4().hex[:12].upper()}", tenant_id=user.tenant_id,
        location_key=ctx.key, building_id=ctx.building_id, site_id=ctx.site_id,
        connection_key=connection_key, request_type=request_type, status="submitted",
        priority=priority, requested_by=user.email, requested_by_name=getattr(user, "name", None),
        requested_at=now, customer_notes=notes, requested_changes=_j(changes or {}))
    db.add(req)
    _record_event(db, user, event_type="request_submitted", origin=ORIGIN_CUSTOMER,
                  summary=f"{REQUEST_TYPES[request_type]} requested", location_key=ctx.key,
                  building_id=ctx.building_id, site_id=ctx.site_id, subject_key=connection_key,
                  request_ref=req.request_ref, new={"status": "submitted",
                                                    "request_type": request_type}, now=now)
    return req


async def submit_request(db, user, ctx: LocationContext, *, request_type: str, notes=None,
                         changes=None, connection_key=None, priority="normal") -> dict:
    if request_type not in REQUEST_TYPES or request_type == "e911_verification":
        raise SelfServiceError(422, "invalid_request_type",
                               "Unsupported request type." if request_type != "e911_verification"
                               else "Use Verify E911 to submit an E911 verification.")
    if priority not in PRIORITIES:
        raise SelfServiceError(422, "invalid_priority", "Priority must be normal, high or urgent.")
    notes = _clean_text(notes, 4000, "notes")
    changes = _check_changes_payload(changes)
    if not notes and not changes:
        raise SelfServiceError(422, "details_required", "Tell us what you need in the notes.")
    now = datetime.now(timezone.utc)
    req = await _create_request(db, user, ctx, request_type=request_type, changes=changes,
                                notes=notes, now=now, connection_key=connection_key,
                                priority=priority)
    await db.commit()
    return serialize_request(req)


async def load_requests(db, tenant_id: str, *, location_key=None, request_type=None,
                        open_only=False) -> list:
    q = select(CustomerServiceRequest).where(CustomerServiceRequest.tenant_id == tenant_id)
    if location_key is not None:
        q = q.where(CustomerServiceRequest.location_key == location_key)
    if request_type is not None:
        q = q.where(CustomerServiceRequest.request_type == request_type)
    rows = (await db.execute(q.order_by(CustomerServiceRequest.id.desc()))).scalars().all()
    if open_only:
        rows = [r for r in rows if r.status not in TERMINAL_STATUSES]
    return rows


async def get_request(db, tenant_id: str, request_ref: str) -> Optional[CustomerServiceRequest]:
    return (await db.execute(select(CustomerServiceRequest).where(
        CustomerServiceRequest.tenant_id == tenant_id,
        CustomerServiceRequest.request_ref == request_ref))).scalar_one_or_none()


async def _transition(db, user, req: CustomerServiceRequest, to_status: str, *, origin: str,
                      notes=None) -> None:
    now = datetime.now(timezone.utc)
    old = req.status
    req.status = to_status
    if origin == ORIGIN_OPERATIONS:
        req.reviewed_by = user.email
        req.reviewed_at = now
        if notes:
            req.resolution_notes = notes
    if to_status == "completed":
        req.completed_at = now
    label = REQUEST_TYPES.get(req.request_type, "Request")
    _record_event(db, user, event_type="request_status_changed", origin=origin,
                  summary=f"{label}: {STATUS_LABELS.get(to_status, to_status).lower()}",
                  location_key=req.location_key, building_id=req.building_id, site_id=req.site_id,
                  subject_key=req.connection_key, request_ref=req.request_ref,
                  field_name="status", old=old, new=to_status, now=now)


async def customer_cancel(db, user, req: CustomerServiceRequest, *, notes=None) -> dict:
    if req.status not in CUSTOMER_CANCELLABLE:
        raise SelfServiceError(409, "not_cancellable",
                               f"A request that is {STATUS_LABELS[req.status].lower()} can't be cancelled.")
    await _transition(db, user, req, "cancelled", origin=ORIGIN_CUSTOMER,
                      notes=_clean_text(notes, 2000, "notes"))
    await db.commit()
    return serialize_request(req)


async def customer_respond(db, user, req: CustomerServiceRequest, *, notes) -> dict:
    """Answer an operations question (waiting_customer -> submitted)."""
    notes = _clean_text(notes, 4000, "notes")
    if req.status != "waiting_customer":
        raise SelfServiceError(409, "not_waiting", "This request isn't waiting on you.")
    if not notes:
        raise SelfServiceError(422, "details_required", "Add your response in the notes.")
    req.customer_notes = ((req.customer_notes + "\n\n") if req.customer_notes else "") + notes
    await _transition(db, user, req, "submitted", origin=ORIGIN_CUSTOMER)
    await db.commit()
    return serialize_request(req)


async def operations_transition(db, user, req: CustomerServiceRequest, to_status: str,
                                *, notes=None) -> dict:
    """Operations-side status change.  Enforces the state machine.  Completing an
    E911 verification request NEVER marks E911 verified — the official record is
    changed only through the existing UPDATE_E911 flow."""
    allowed = OPERATIONS_TRANSITIONS.get(req.status, set())
    if to_status not in allowed:
        raise SelfServiceError(409, "invalid_transition",
                               f"Cannot move a request from '{req.status}' to '{to_status}'.")
    await _transition(db, user, req, to_status, origin=ORIGIN_OPERATIONS,
                      notes=_clean_text(notes, 4000, "notes"))
    await db.commit()
    return serialize_request(req, internal=True)


def serialize_request(r: CustomerServiceRequest, *, internal: bool = False) -> dict:
    out = {
        "request_ref": r.request_ref,
        "request_type": r.request_type,
        "request_label": REQUEST_TYPES.get(r.request_type, "Request"),
        "status": r.status,
        "status_label": STATUS_LABELS.get(r.status, r.status),
        "open": r.status not in TERMINAL_STATUSES,
        "priority": r.priority,
        "requested_by": r.requested_by_name or r.requested_by,
        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
        "customer_notes": r.customer_notes,
        "requested_changes": _uj(r.requested_changes) or {},
        "resolution_notes": r.resolution_notes,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "connection_ref": (encode_connection_ref(r.location_key, r.connection_key)
                           if r.connection_key else None),
    }
    if internal:
        out.update({"tenant_id": r.tenant_id, "location_key": r.location_key,
                    "building_id": r.building_id, "site_id": r.site_id,
                    "connection_key": r.connection_key, "requested_by_email": r.requested_by,
                    "reviewed_by": r.reviewed_by})
    else:
        # the customer sees who acted as a neutral team label, never staff identities
        out["reviewed_by"] = "Operations team" if r.reviewed_at else None
    return out


# ══════════════════════════════════════════════════════════════════════
# E911 self-service (attestation → verification queue; never self-certified)
# ══════════════════════════════════════════════════════════════════════
def e911_state(*, official_verified: bool, has_address: bool,
               latest_request: Optional[CustomerServiceRequest]) -> dict:
    """The customer E911 state.  ``verified`` is reachable ONLY from the official
    record; a customer attestation at most reaches ``customer_submitted``."""
    provenance = None
    if official_verified:
        state = "verified"
        provenance = {"verified_by": "Verification team", "verification_method": "official_record",
                      "source": "Official emergency record", "verification_timestamp": None}
    elif latest_request is None:
        state = "customer_confirmation_required" if has_address else "not_verified"
    else:
        changes = _uj(latest_request.requested_changes) or {}
        has_corrections = bool(changes.get("corrections"))
        s = latest_request.status
        if s == "submitted":
            state = "requires_review" if has_corrections else "customer_submitted"
        elif s in ("under_review", "approved", "in_progress", "completed"):
            state = "requires_review" if (has_corrections and s != "completed") else "verification_pending"
        elif s == "waiting_customer":
            state = "customer_confirmation_required"
        elif s == "rejected":
            state = "failed"
        else:   # cancelled -> as if never submitted
            state = "customer_confirmation_required" if has_address else "not_verified"
        if state != "customer_confirmation_required" and s != "cancelled":
            att = changes.get("attestation") or {}
            provenance = {"attested_by": att.get("attested_by"),
                          "attested_at": att.get("attested_at"),
                          "verification_method": "customer_attestation",
                          "source": "Customer attestation — pending official verification",
                          "request_ref": latest_request.request_ref}
    actionable = state in E911_CUSTOMER_ACTION_STATES
    return {"state": state, "label": E911_STATE_LABELS[state], "verified": state == "verified",
            "customer_action_required": actionable,
            "customer_action": "verify_e911" if actionable else None,
            "reason": E911_STATE_REASONS[state],
            "provenance": provenance}


def _latest_e911_request(requests) -> Optional[CustomerServiceRequest]:
    rs = [r for r in requests if r.request_type == "e911_verification" and r.status != "cancelled"]
    return max(rs, key=lambda r: r.id) if rs else None


def _official_verified(ctx: LocationContext) -> bool:
    if ctx.record is not None:
        return bool(ctx.record.get("e911_verified"))
    return (getattr(ctx.site, "e911_status", "") or "").strip().lower() in _E911_VERIFIED


def _dispatch_address(ctx: LocationContext) -> Optional[str]:
    """The registered dispatch address: the official emergency record on the
    linked site when one exists, else the canonical service address on file."""
    if ctx.record is not None:            # registry mode: the read model's single source
        return ctx.record.get("dispatch_address")
    site = ctx.site
    if site is not None and getattr(site, "e911_street", None):
        street, city, state, zp = site.e911_street, site.e911_city, site.e911_state, site.e911_zip
    else:
        street, city, state, zp = ctx.address, ctx.city, ctx.state, ctx.zip
    parts = [street, city, " ".join(x for x in (state, zp) if x)]
    s = ", ".join(p for p in parts if p)
    return s or None


async def submit_e911_verification(db, user, ctx: LocationContext, body: dict) -> dict:
    """Record the customer's portion of E911 verification.

    The customer reviews the service number + registered dispatch address +
    building, confirms / corrects suite, floor and callback details, and ATTESTS.
    We snapshot the SERVER-shown record (not client content), store the
    attestation with provenance as an ``e911_verification`` request, and feed the
    existing E911 review queue.  The official record is NOT changed and is NOT
    marked verified."""
    if body.get("attest") is not True:
        raise SelfServiceError(422, "attestation_required",
                               "Please confirm that the information is correct to submit.",
                               ["attest"])
    corrections = {
        "address": _clean_text(body.get("corrected_address"), 300, "corrected_address"),
        "suite": _clean_text(body.get("suite"), 60, "suite"),
        "floor": _clean_text(body.get("floor"), 60, "floor"),
        "additional_location": _clean_text(body.get("additional_location"), 300,
                                           "additional_location"),
        "callback_number": _clean_phone(body.get("callback_number"), "callback_number"),
    }
    corrections = {k: v for k, v in corrections.items() if v}
    confirmed = {k: body.get(k) is True for k in ("number_confirmed", "address_confirmed",
                                                  "building_confirmed")}
    if not corrections.get("address") and not confirmed["address_confirmed"]:
        raise SelfServiceError(422, "address_unconfirmed",
                               "Confirm the dispatch address or enter the correct one.",
                               ["address_confirmed"])
    if not confirmed["building_confirmed"]:
        raise SelfServiceError(422, "building_unconfirmed", "Confirm this is the right building.",
                               ["building_confirmed"])
    contact = clean_contact(body.get("contact"), "contact") if body.get("contact") else None
    note = _clean_text(body.get("note"), 2000, "note")
    now = datetime.now(timezone.utc)
    phones = sorted({p for p in ((ctx.record or {}).get("connection_numbers") or [])})
    if ctx.mode == "site" and ctx.site is not None:
        from app.services.customer import portfolio as cportfolio
        eps = await cportfolio.load_e911_endpoints(db, user.tenant_id, ctx.site.site_id)
        phones = sorted({n for n in (pdev.norm_phone(e.get("callback_number")) for e in eps) if n})
    snapshot = {"dispatch_address": _dispatch_address(ctx),
                "location": ctx.canonical_name, "service_numbers": phones}
    changes = {
        "attestation": {"attested_by": getattr(user, "name", None) or user.email,
                        "attested_by_email": user.email, "attested_at": now.isoformat(),
                        "method": "customer_attestation", **confirmed},
        "server_snapshot": snapshot,
        "corrections": corrections,
        "contact": contact,
    }
    req = await _create_request(db, user, ctx, request_type="e911_verification", changes=changes,
                                notes=note, now=now,
                                priority="high" if corrections else "normal")
    # Feed the existing internal E911 review queue for site-backed locations
    # (one verification authority).  That helper commits the whole unit of work.
    if ctx.site is not None:
        from app.services import e911_review
        server_view = {"emergency_dispatch_address": snapshot["dispatch_address"],
                       "emergency_endpoints": [], "verification": {"verified": False}}
        if corrections:
            res = await e911_review.record_correction(
                db, user, ctx.site, snapshot=server_view, note=note or "",
                corrected={"address": corrections.get("address"), "suite": corrections.get("suite"),
                           "floor": corrections.get("floor"), "unit": None,
                           "callback_number": corrections.get("callback_number"),
                           "service_identifier": None})
        else:
            res = await e911_review.record_confirmation(db, user, ctx.site, snapshot=server_view,
                                                        note=note or "")
        changes["e911_review_id"] = res.get("review_id")
        req.requested_changes = _j(changes)
    await db.commit()
    state = e911_state(official_verified=_official_verified(ctx),
                       has_address=bool(snapshot["dispatch_address"]), latest_request=req)
    return {"request": serialize_request(req), "e911": state}


# ══════════════════════════════════════════════════════════════════════
# Activity
# ══════════════════════════════════════════════════════════════════════
def serialize_event(e: CustomerActivityEvent) -> dict:
    by = ("Operations team" if e.origin == ORIGIN_OPERATIONS
          else (e.actor_name or e.actor_email))
    return {"when": e.occurred_at.isoformat() if e.occurred_at else None, "by": by,
            "summary": e.summary, "event_type": e.event_type, "origin": e.origin,
            "request_ref": e.request_ref}


async def load_activity(db, tenant_id: str, *, location_key=None, limit: int = 50) -> list:
    q = select(CustomerActivityEvent).where(CustomerActivityEvent.tenant_id == tenant_id)
    if location_key is not None:
        q = q.where(CustomerActivityEvent.location_key == location_key)
    rows = (await db.execute(q.order_by(CustomerActivityEvent.id.desc()).limit(limit))).scalars().all()
    return [serialize_event(e) for e in rows]


# ══════════════════════════════════════════════════════════════════════
# Connections (customer-meaningful, no carrier internals)
# ══════════════════════════════════════════════════════════════════════
_SERVICE_PURPOSE = {"Fire Alarm": "fire_alarm", "Elevator": "elevator",
                    "Emergency Phone": "emergency_phone", "Emergency Phone Line": "emergency_phone",
                    "Area of Refuge": "emergency_phone", "Burglar Alarm": "security",
                    "Fax Line": "fax"}


def format_phone(p) -> Optional[str]:
    n = pdev.norm_phone(p)
    return f"({n[:3]}) {n[3:6]}-{n[6:]}" if n else (str(p) if p else None)


def build_connections(location_key: str, services: list, extra_numbers: list,
                      overlay: dict, e911: dict, open_requests: list) -> list:
    """Customer connections: one per (service, telephone number), plus any
    registry-known number not yet attached to a monitored service (shown honestly
    as Unknown — never green without evidence)."""
    from app.services.customer import serialize as cs

    open_by_conn: dict = {}
    for r in open_requests:
        if r.connection_key:
            open_by_conn.setdefault(r.connection_key, []).append(r)
    out, seen_numbers = [], set()

    def make(key, service, default_name, number, status, equipment, attention, service_ref=None):
        ov = overlay.get(key, {})
        purpose = ov.get("purpose") or _SERVICE_PURPOSE.get(service, "other")
        pending = open_by_conn.get(key, [])
        action = list(attention or [])
        if e911.get("customer_action_required"):
            action.append("E911 verification needed")
        return {
            "connection_ref": encode_connection_ref(location_key, key),
            "service_ref": service_ref,
            # the Life-Safety Service this connection belongs to; None when the
            # number is known but not yet linked to a monitored service
            "service": service,
            "service_label": service or "Not yet linked to a life-safety service",
            "name": ov.get("friendly_name") or default_name,
            "default_name": default_name,
            "purpose": purpose,
            "purpose_label": PURPOSE_LABELS.get(purpose, "Other"),
            "phone_number": format_phone(number),
            "status": status,
            "e911_state": e911.get("label"),
            "device_association": equipment,
            "last_known_health": status.get("as_of") if status.get("status") != "Unknown" else None,
            "action_required": action,
            "customer_notes": ov.get("customer_notes"),
            "customer_contact": ov.get("customer_contact"),
            "open_requests": [serialize_request(r) for r in pending],
        }

    for svc in services or []:
        raw = decode_ref("svc", svc.get("service_ref") or "") or (svc.get("service_ref") or "")
        numbers = [n for n in (pdev.norm_phone(p) for p in (svc.get("phone_numbers") or [])) if n]
        numbers = list(dict.fromkeys(numbers)) or [None]
        equip = svc.get("equipment") or []
        equipment = (f"{len(equip)} device" + ("" if len(equip) == 1 else "s")) if equip else None
        base = svc.get("name") or svc.get("service") or "Life Safety Service"
        for i, n in enumerate(numbers):
            if n:
                seen_numbers.add(n)
            name = f"{base} Line {i + 1}" if len(numbers) > 1 else base
            out.append(make(f"s:{raw}:{n or '-'}"[:120], svc.get("service") or "Life Safety Service",
                            name, n, svc.get("status") or cs.status_object("Unknown"), equipment,
                            svc.get("attention_items"), service_ref=svc.get("service_ref")))
    for n in extra_numbers or []:
        n = pdev.norm_phone(n)
        if not n or n in seen_numbers:
            continue
        seen_numbers.add(n)
        # A number on file for the building that is not (yet) attached to a
        # monitored service: a CONNECTION, not a second service.  Named neutrally
        # so it never reads as a service of its own.
        status = cs.status_object("Unknown", reason="We're confirming which service this line supports.")
        out.append(make(f"n:{n}", None, "Additional line", n, status, None, None))
    return out


# ══════════════════════════════════════════════════════════════════════
# Location workspace + portfolio Action Center
# ══════════════════════════════════════════════════════════════════════
def _contacts_view(loc_overlay: dict, site) -> dict:
    out = {role: loc_overlay.get(f"contact.{role}") for role in CONTACT_ROLES}
    system = None
    if site is not None and (getattr(site, "poc_name", None) or getattr(site, "poc_phone", None)
                             or getattr(site, "poc_email", None)):
        system = {"name": site.poc_name, "phone": site.poc_phone, "email": site.poc_email}
    return {"contacts": out, "site_contact_on_file": system,
            "labels": CONTACT_LABELS,
            "missing": not any(out.values()) and system is None}


def _profile_view(loc_overlay: dict) -> dict:
    return {k: loc_overlay.get(k) for k in LOCATION_FIELDS}


async def location_workspace(db, user, ctx: LocationContext, now) -> dict:
    """Everything the customer location page needs to ACT: overview, connections,
    contacts, notes, E911 state, open requests, activity, and outstanding actions."""
    from app.services.customer import command_center as cc
    from app.services.customer import portfolio as cportfolio
    from app.services.customer import serialize as cs

    overlay = overlay_by_subject(await _field_rows(db, user.tenant_id, ctx.key)).get(ctx.key, {})
    loc_overlay = overlay.get("", {})
    requests = await load_requests(db, user.tenant_id, location_key=ctx.key)
    open_requests = [r for r in requests if r.status not in TERMINAL_STATUSES]

    if ctx.mode == "registry":
        rec = ctx.record or {}
        building = cs.portfolio_building(rec)
        services = rec.get("services") or []
        extra_numbers = rec.get("connection_numbers") or []
        protection = rec.get("protection") or cs.status_object("Unknown")
        device_count = rec.get("physical_device_count", 0)
        display_default = building["display_name"]
        category = building.get("building_category")
    else:
        services = await cc._build_location_services(db, user.tenant_id, ctx.site, now)
        resolved = await cportfolio.resolve_location(db, user.tenant_id, ctx.ref, now)
        protection = resolved[1] if resolved else cs.status_object("Unknown")
        devices = (resolved[3] if resolved else None) or []
        device_count = len(devices)
        extra_numbers = []
        display_default = ctx.canonical_name
        category = None

    address = _dispatch_address(ctx)
    e911 = e911_state(official_verified=_official_verified(ctx), has_address=bool(address),
                      latest_request=_latest_e911_request(requests))
    connections = build_connections(ctx.key, services, extra_numbers,
                                    {k: v for k, v in overlay.items() if k},
                                    e911, open_requests)
    contacts = _contacts_view(loc_overlay, ctx.site)
    outstanding = _outstanding_actions(protection, e911, contacts["missing"], open_requests)
    return {
        "location": {
            "location_ref": ctx.ref,
            "canonical_name": display_default,
            "display_name": loc_overlay.get("display_name") or display_default,
            "address": address,
            "store_number": ctx.store_number if cs.valid_store_number(ctx.store_number) else None,
            "building_type": category,
            "protection": protection,
            "device_count": device_count,
            # Building → Life-Safety Service → Connection → Device → Carrier:
            # one service may have several connections (lines / numbers), and a
            # connection may exist before it is linked to a service.
            "service_count": len(services),
            "monitored_service_count": sum(1 for s in services
                                           if (s.get("status") or {}).get("status") == "Protected"),
            "operational_state": cs.operational_state(
                (protection or {}).get("status"),
                linked=(ctx.record or {}).get("monitoring_linked", True) if ctx.mode == "registry" else True),
            "connection_count": len(connections),
            "unlinked_connection_count": sum(1 for c in connections if c["service"] is None),
            "outstanding_actions": outstanding,
        },
        "profile": _profile_view(loc_overlay),
        "contacts": contacts,
        "connections": connections,
        "e911": {**e911, "dispatch_address": address,
                 "service_numbers": [c["phone_number"] for c in connections if c["phone_number"]]},
        "requests": [serialize_request(r) for r in requests[:25]],
        "activity": await load_activity(db, user.tenant_id, location_key=ctx.key, limit=30),
        "capabilities": capabilities(user),
    }


def _outstanding_actions(protection, e911, contacts_missing, open_requests) -> list:
    out = []
    if e911.get("customer_action_required"):
        out.append({"action": "verify_e911", "label": "Verify E911",
                    "reason": e911.get("label")})
    if contacts_missing:
        out.append({"action": "update_contacts", "label": "Add contacts",
                    "reason": "No facility or emergency contact on file"})
    for r in open_requests:
        if r.status == "waiting_customer":
            out.append({"action": "respond_request", "label": "Respond to request",
                        "reason": f"{REQUEST_TYPES.get(r.request_type)} is waiting on you",
                        "request_ref": r.request_ref})
    status = (protection or {}).get("status")
    if status in ("Critical", "Attention Needed"):
        out.append({"action": "review_status", "label": "Review status",
                    "reason": (protection or {}).get("reason") or status})
    return out


async def _portfolio_locations(db, tenant_id, now) -> list[dict]:
    """[{ref, key, name, protection, has_address, official_verified, site}] for the
    whole tenant, in whichever mode the customer view is in."""
    from app.services.customer import portfolio as cportfolio
    from app.services.customer import portfolio_registry_view as prv
    from app.services.customer import serialize as cs

    records = await prv.load_customer_buildings(db, tenant_id, now)
    out = []
    if records is not None:
        for r in records:
            b = cs.portfolio_building(r)
            out.append({"ref": r["building_ref"], "key": f"bldg:{r['id']}",
                        "name": b["display_name"], "protection": r.get("protection") or {},
                        "monitoring_linked": bool(r.get("monitoring_linked", True)),
                        "has_address": bool(r.get("dispatch_address")),
                        "official_verified": bool(r.get("e911_verified")), "site": None,
                        "site_contact": False})
        return out
    for site, protection in await cportfolio.load_portfolio(db, tenant_id, now):
        out.append({"ref": encode_ref("loc", site.id), "key": f"site:{site.site_id}",
                    "name": site.site_name, "protection": protection, "monitoring_linked": True,
                    "has_address": bool(site.e911_street),
                    "official_verified": (site.e911_status or "").lower() in _E911_VERIFIED,
                    "site": site,
                    "site_contact": bool(site.poc_name or site.poc_phone or site.poc_email)})
    return out


# Action Center tiers: URGENT (known service problems) · ACTION NEEDED (tasks the
# customer can do now) · IN PROGRESS (True911 / operations own it) ·
# INFORMATIONAL (low-priority portfolio completion) · ACTIVITY (history — things
# that already happened; nothing waits on it, D-028).  Missing contacts are setup,
# never shown at the severity of a service problem.
ACTION_CENTER_TIERS = [
    {"tier": "urgent", "owner": "true911", "lists": ["needs_attention"]},
    {"tier": "action_needed", "owner": "customer",
     "lists": ["awaiting_your_response", "e911_confirmation_required"]},
    {"tier": "in_progress", "owner": "true911",
     "lists": ["e911_not_ready", "being_reconciled", "service_change_requests", "open_problems"]},
    {"tier": "informational", "owner": "customer", "lists": ["missing_contact_information"]},
    {"tier": "activity", "owner": "none", "lists": ["recently_updated"]},
]


async def action_center(db, user, now) -> dict:
    """The portfolio "What do I need to do?" view."""
    locations = await _portfolio_locations(db, user.tenant_id, now)
    overlay = overlay_by_subject(await _field_rows(db, user.tenant_id))
    all_requests = await load_requests(db, user.tenant_id)
    req_by_loc: dict = {}
    for r in all_requests:
        req_by_loc.setdefault(r.location_key, []).append(r)
    names = {loc["key"]: (overlay.get(loc["key"], {}).get("", {}).get("display_name") or loc["name"])
             for loc in locations}
    refs = {loc["key"]: loc["ref"] for loc in locations}

    from app.services.customer import serialize as cs

    needs_attention, e911_confirm, e911_not_ready, missing_contacts = [], [], [], []
    being_reconciled = []
    for loc in locations:
        name, ref = names[loc["key"]], loc["ref"]
        st = (loc["protection"] or {}).get("status")
        op = cs.operational_state(st, linked=loc["monitoring_linked"])
        if op["state"] == "attention_required":       # evidence-backed problems only
            needs_attention.append({"location_ref": ref, "location": name, "status": st,
                                    "label": op["label"], "urgent": op["urgent"],
                                    "reason": (loc["protection"] or {}).get("reason")})
        elif op["state"] == "being_reconciled":       # True911's work, not the customer's
            being_reconciled.append({"location_ref": ref, "location": name,
                                     "label": op["label"], "reason": op["summary"]})
        e = e911_state(official_verified=loc["official_verified"], has_address=loc["has_address"],
                       latest_request=_latest_e911_request(req_by_loc.get(loc["key"], [])))
        row = {"location_ref": ref, "location": name, "state": e["state"], "label": e["label"],
               "reason": e["reason"], "action": e["customer_action"]}
        if e["customer_action_required"]:
            e911_confirm.append(row)          # the customer can act now (Verify E911)
        elif e["state"] == "not_verified":
            e911_not_ready.append(row)        # nothing to confirm yet — informational
        loc_ov = overlay.get(loc["key"], {}).get("", {})
        if not any(loc_ov.get(f"contact.{r}") for r in CONTACT_ROLES) and not loc["site_contact"]:
            missing_contacts.append({"location_ref": ref, "location": name})

    def req_item(r):
        return {**serialize_request(r), "location_ref": refs.get(r.location_key),
                "location": names.get(r.location_key)}
    visible = [r for r in all_requests if r.location_key in refs]
    open_reqs = [r for r in visible if r.status not in TERMINAL_STATUSES]
    # a request waiting on the customer is THEIR action (awaiting_your_response),
    # so it is not also listed as True911's in-progress work
    true911_reqs = [r for r in open_reqs if r.status != "waiting_customer"]
    needs_attention.sort(key=lambda x: 0 if x["status"] == "Critical" else 1)
    return {
        "needs_attention": needs_attention,
        # Actionable confirmations and not-yet-ready records are SEPARATE lists —
        # a record with no dispatch address is never called a "confirmation".
        "e911_confirmation_required": e911_confirm,
        "e911_not_ready": e911_not_ready,
        # combined E911 attention (kept for compatibility; rows carry ``action``)
        "e911_verification_required": e911_confirm + e911_not_ready,
        "missing_contact_information": missing_contacts,
        "awaiting_your_response": [req_item(r) for r in open_reqs if r.status == "waiting_customer"],
        "service_change_requests": [req_item(r) for r in true911_reqs
                                    if r.request_type in CHANGE_REQUEST_TYPES],
        "open_problems": [req_item(r) for r in true911_reqs if r.request_type == "support_request"],
        "being_reconciled": being_reconciled,
        "recently_updated": await load_activity(db, user.tenant_id, limit=10),
        # Who owns what, and how urgent it is (customer trust rule, D-022).  The UI
        # renders these tiers in order; nothing in "operations" is the customer's job.
        "tiers": ACTION_CENTER_TIERS,
        "counts": {"locations": len(locations), "needs_attention": len(needs_attention),
                   "e911_confirmation_required": len(e911_confirm),
                   "e911_not_ready": len(e911_not_ready),
                   "e911_attention": len(e911_confirm) + len(e911_not_ready),
                   "e911_verification_required": len(e911_confirm) + len(e911_not_ready),
                   "missing_contact_information": len(missing_contacts),
                   "open_requests": len(open_reqs),
                   "being_reconciled": len(being_reconciled)},
        "capabilities": capabilities(user),
    }
