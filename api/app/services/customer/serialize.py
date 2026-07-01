"""Customer-safe serializer — the single enforcement point for the data boundary.

ALLOW-LIST, not deny-list: every mapper emits ONLY the named customer fields it
reads off a model.  A new/unmapped model column is therefore invisible by
default and can never leak.  See docs/CUSTOMER_DATA_BOUNDARY.md.

Rules baked in here (not left to callers):
  * No green without evidence (CONSTITUTION §4.6) — `status_object` recodes a
    "Protected" with no evidence/as_of to "Unknown".
  * Separate axes (D-006) — operational protection, E911 verification, and
    billing are distinct outputs; no mapper reads another axis.
  * No jargon (§7) — raw model/identifier/telecom fields are never read.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.services.customer.refs import encode_ref

# The only status vocabulary a customer ever sees (DECISIONS D-005).
SIX_LABELS = {
    "Protected", "Attention Needed", "Critical",
    "Pending Install", "Inactive", "Unknown",
}
_E911_VERIFIED = {"validated", "verified"}


# ── Shared objects ───────────────────────────────────────────────────
def evidence_object(last_checked, signals: Iterable[str], source: str = "monitoring") -> dict:
    return {"last_checked": last_checked, "signals": list(signals), "source": source}


def status_object(label: str, *, as_of=None, reason: Optional[str] = None,
                  evidence: Optional[dict] = None) -> dict:
    """Build a StatusObject, enforcing the no-false-green invariant.

    A "Protected" label requires a populated evidence object AND an as_of
    timestamp; otherwise it is recoded to "Unknown".  Any label outside the
    six-label vocabulary becomes "Unknown".
    """
    if label not in SIX_LABELS:
        label = "Unknown"
    if label == "Protected" and (not evidence or not as_of):
        label = "Unknown"
        reason = reason or "Status cannot be confirmed yet"
        evidence = None

    out: dict = {"status": label, "as_of": as_of}
    if label == "Protected":
        out["evidence"] = evidence
    else:
        out["reason"] = reason
    return out


def error_object(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


# ── Derivation helpers ───────────────────────────────────────────────
_EQUIPMENT_LABELS = {
    "elevator_phone": "Elevator phone unit",
    "fire_alarm": "Fire alarm communicator",
    "emergency_call_station": "Emergency call station",
    "voice_line": "Emergency voice line",
    "fax_line": "Fax line unit",
}
_SERVICE_LABELS = {
    "elevator_phone": "Elevator emergency phone",
    "fire_alarm": "Fire alarm line",
    "emergency_call_station": "Emergency call station",
    "voice_line": "Emergency voice line",
    "fax_line": "Fax line",
    "other": "Emergency service",
}

# Enterprise Life-Safety service catalog — the customer-facing SERVICE the
# equipment supports (Command Center vocabulary).  Kept SEPARATE from the legacy
# _SERVICE_LABELS (whose exact strings existing tests/clients depend on) so this
# is purely additive.  Customers reason about services, never device models.
SERVICE_CATALOG = {
    "fire_alarm": "Fire Alarm",
    "fire_alarm_line": "Fire Alarm",
    "elevator_phone": "Elevator",
    "elevator": "Elevator",
    "area_of_refuge": "Area of Refuge",
    "refuge": "Area of Refuge",
    "burglar_alarm": "Burglar Alarm",
    "intrusion": "Burglar Alarm",
    "emergency_call_station": "Emergency Phone",
    "emergency_phone": "Emergency Phone",
    "emergency_voice_line": "Emergency Phone",
    "voice_line": "Emergency Phone Line",
    "bda_das": "BDA/DAS",
    "das": "BDA/DAS",
    "bda": "BDA/DAS",
    "generator": "Generator Monitoring",
    "generator_monitoring": "Generator Monitoring",
    "fax_line": "Fax Line",
    "other": "Life Safety Service",
}


def enterprise_service_label(unit_type) -> str:
    """Customer-facing Life-Safety service name (Command Center catalog).
    Falls back to a generic, non-jargon label — never a raw device model."""
    return SERVICE_CATALOG.get((unit_type or "").lower(), "Life Safety Service")


def service_card(*, service_ref, service_type: str, status: dict, name=None,
                 where=None, floor=None, equipment=None, confidence: str = "Low",
                 carrier=None, phone_numbers=None, last_test=None,
                 last_inspection=None, attention_items=None) -> dict:
    """A Life-Safety Service card sourced from the inference engine (Phase 6/7) —
    a first-class service that may or may not have an explicit ServiceUnit.  Same
    customer-safe shape as ``service_with_equipment`` plus a ``confidence`` (how
    sure we are of the classification) and the ``service`` type.  Additive; no
    device jargon; nothing fabricated (last_test/inspection null until real)."""
    equip = equipment or []
    return {
        "service_ref": service_ref,
        "service": service_type,
        "name": name,
        "where": where,
        "floor": floor,
        "status": status,
        "confidence": confidence,
        "equipment": equip,
        "equipment_count": len(equip),
        "carrier": carrier_label(carrier),
        "phone_numbers": phone_numbers or [],
        "last_test": _iso(last_test) if hasattr(last_test, "isoformat") else last_test,
        "last_inspection": _iso(last_inspection) if hasattr(last_inspection, "isoformat") else last_inspection,
        "attention_items": attention_items or [],
    }


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _address(site) -> Optional[str]:
    parts = [site.e911_street, site.e911_city, site.e911_state, site.e911_zip]
    if not all(parts):
        return None
    return f"{site.e911_street}, {site.e911_city}, {site.e911_state} {site.e911_zip}"


def e911_state_label(site) -> str:
    """Plain-language emergency-address state (E911 axis only)."""
    present = all([site.e911_street, site.e911_city, site.e911_state, site.e911_zip])
    if not present:
        return "Setup needed"
    if (site.e911_status or "").lower() in _E911_VERIFIED:
        return "Verified"
    return "Not yet verified"


# ── Entity mappers (allow-list) ──────────────────────────────────────
def _map_point(site) -> Optional[dict]:
    """A map pin {lat, lng} when the site has valid coordinates, else None.
    Coordinates are exposed ONLY as an aggregate map pin (never a raw field) —
    see CUSTOMER_DATA_BOUNDARY.md §2."""
    lat, lng = getattr(site, "lat", None), getattr(site, "lng", None)
    if lat is None or lng is None:
        return None
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0) or (lat == 0.0 and lng == 0.0):
        return None
    return {"lat": lat, "lng": lng}


def location_summary(site, *, protection: dict) -> dict:
    """List-level Location (no street in list view)."""
    return {
        "location_ref": encode_ref("loc", site.id),
        "location": site.site_name,
        "building_type": site.building_type,
        "city": site.e911_city,
        "state": site.e911_state,
        "protection": protection,
        "emergency_address_state": e911_state_label(site),
        "map_point": _map_point(site),
    }


def equipment_from_device(device, *, protection: dict, preview: bool = False) -> dict:
    """Device -> 'equipment health'.  Reads NO identifier/telecom/firmware
    field — those are never customer-visible (§7).

    ``preview`` (RH go-live login preview) presents health as "Online" before
    live telemetry is connected.  It does NOT read or mutate ``device.status``;
    the raw row is untouched and internal views still see the real state.
    ``last_seen`` is NOT fabricated — it stays null until a real heartbeat
    exists.  See ``services.customer.preview``."""
    online = preview or (device.status or "").lower() == "active"
    return {
        "equipment": _EQUIPMENT_LABELS.get((device.device_type or "").lower(), "Monitored device"),
        "health": "Online" if online else "Offline",
        "last_seen": _iso(device.last_heartbeat),
        "in_service_since": _iso(device.activated_at),
        "protection": protection,
    }


def service_from_unit(unit, *, protection: dict, equipment: Optional[dict] = None) -> dict:
    caps = []
    if getattr(unit, "voice_supported", False):
        caps.append("Voice")
    if getattr(unit, "video_supported", False):
        caps.append("Video")
    if getattr(unit, "text_supported", False):
        caps.append("Text")
    out = {
        "service_ref": encode_ref("svc", unit.id),
        "service": _SERVICE_LABELS.get((unit.unit_type or "").lower(), "Emergency service"),
        "name": unit.unit_name,
        "where": unit.location_description,
        "floor": unit.floor,
        "can_call_for_help": caps,
        "compliance": {
            "state": (unit.compliance_status or "unknown").replace("_", " ").title(),
            "governing_code": unit.governing_code_edition,
            "disclaimer": "Operational guidance, not legal advice.",
        },
        "protection": protection,
    }
    if equipment is not None:
        out["equipment"] = equipment
    return out


def e911_endpoint_item(unit, *, callback_number: Optional[str] = None) -> dict:
    """One emergency endpoint (per ServiceUnit) for the E911 record — the
    life-safety detail a customer must be able to verify: where it is
    (unit/suite/floor), what kind of line it is (service type), and the
    callback number / BTN / elevator/FACP line identifier.

    Every value comes from REAL stored data (never fabricated).  Fields are
    emitted "where applicable" — a null/absent value is dropped so the customer
    never sees a fabricated placeholder.  ``callback_number`` is resolved by the
    caller from the linked device/line (real stored number)."""
    out: dict = {
        "service_type": _SERVICE_LABELS.get((unit.unit_type or "").lower(), "Emergency service"),
    }
    where = unit.location_description or None
    if where:
        out["where"] = where
    if unit.floor:
        out["floor"] = unit.floor
    if callback_number:
        out["callback_number"] = callback_number
    return out


def e911_summary(site, *, history: Optional[list] = None,
                 endpoints: Optional[list] = None) -> dict:
    """Emergency-address axis ONLY — never returns device/operational health.

    ``endpoints`` is the per-service emergency-line detail (where / service type
    / callback number), built from real stored data by the composition layer.
    The ``verified`` flag is derived strictly from the stored ``e911_status``
    and is true ONLY when the underlying record is actually verified."""
    verified = (site.e911_status or "").lower() in _E911_VERIFIED
    active = (site.status or "").lower() == "active"
    return {
        "location": site.site_name,
        "emergency_dispatch_address": _address(site),
        "verification": {
            "state": e911_state_label(site),
            "verified": verified,
            "is_critical": active and not verified,
        },
        "confirmation_required": bool(site.e911_confirmation_required),
        "emergency_endpoints": endpoints or [],
        "address_history": history or [],
        "customer_actions": ["Request an address correction"],
    }


def billing_from_subscription(sub) -> dict:
    """Read-only billing visibility.  Reads NO external-system id / msisdn /
    raw payload — only plan, monthly cost, count, dates, status."""
    mrr = getattr(sub, "mrr", None)
    return {
        "plan": sub.plan_name,
        "monthly_cost": float(mrr) if mrr is not None else None,
        "services_covered": getattr(sub, "qty_lines", None),
        "status": {"active": "Active", "paused": "Paused",
                   "cancelled": "Ended", "expired": "Ended"}.get(
                       (sub.status or "").lower(), "Unknown"),
        "renews_on": _iso(getattr(sub, "renewal_date", None)),
        "active_since": _iso(getattr(sub, "start_date", None)),
    }


def support_diagnostic_safe(diag) -> dict:
    """Customer-safe diagnostic — emits ONLY customer_safe_summary, never
    internal_summary / raw_payload / check_type / confidence."""
    return {
        "result": {"ok": "OK", "warning": "Needs attention",
                   "critical": "Needs attention", "unknown": "Checking"}.get(
                       (diag.status or "").lower(), "Checking"),
        "detail": diag.customer_safe_summary,
    }


def support_message_safe(msg) -> Optional[dict]:
    """Customer-safe message.  Drops `system` role messages entirely."""
    role = (msg.role or "").lower()
    if role not in ("user", "assistant"):
        return None
    return {
        "from": "you" if role == "user" else "True911",
        "text": msg.content,
        "at": _iso(msg.created_at),
    }


def support_case_summary(session, *, messages=None, diagnostics=None) -> dict:
    status_map = {"active": "Open", "escalated": "In progress (with our team)",
                  "resolved": "Resolved"}
    out = {
        "case_ref": encode_ref("case", str(session.id)),
        "status": status_map.get((session.status or "").lower(), "Open"),
        "subject": (session.issue_category or "Support request").replace("_", " ").title(),
        "opened": _iso(session.created_at),
        "resolution": session.resolution_summary,
    }
    if messages is not None:
        out["messages"] = [m for m in (support_message_safe(x) for x in messages) if m]
    if diagnostics is not None:
        out["checks"] = [support_diagnostic_safe(d) for d in diagnostics]
    return out


# ── PR-C2: dashboard + location-detail composition (allow-list) ──────
_CUSTOMER_ACTION = {
    "Protected": "No action needed.",
    "Attention Needed": "This location is under review.",
    "Critical": "This location has been flagged and is being addressed.",
    "Pending Install": "Installation and testing are in progress.",
    "Inactive": "No action needed — service is inactive.",
    "Unknown": "This location's status is being confirmed.",
}
_CUSTOMER_SUMMARY = {
    "Attention Needed": "We're reviewing an item at this location.",
    "Critical": "This location needs attention.",
    "Pending Install": "This location is being set up.",
    "Inactive": "Service at this location is not currently active.",
    "Unknown": "We're confirming this location's status.",
}


def location_device(device, *, protection: dict, preview: bool = False,
                    identifier: Optional[str] = None) -> dict:
    """A customer-safe device entry for the location detail: friendly equipment
    label, optional model, health (preview-aware), in-service date, and an
    optional line/callback/elevator/FACP identifier.  Reads NO serial / ICCID /
    IMEI / firmware / carrier / IP (§7 jargon veto).  Nothing is fabricated —
    optional fields are omitted when the underlying value is absent."""
    online = preview or (device.status or "").lower() == "active"
    out: dict = {
        "equipment": _EQUIPMENT_LABELS.get((device.device_type or "").lower(), "Monitored device"),
        "health": "Online" if online else "Offline",
        "in_service_since": _iso(getattr(device, "activated_at", None)),
        "protection": protection,
    }
    model = getattr(device, "model", None)
    if model:
        out["model"] = model
    if identifier:
        out["identifier"] = identifier
    return out


def location_detail(site, *, protection: dict, services: Optional[list] = None,
                    devices: Optional[list] = None) -> dict:
    """Detail-level Location.  Adds service_address + site_contact to the
    summary fields, plus a minimal services[] preview (PR-C3) and a customer-safe
    devices[] list.  Still stops short of the full E911 object (its own
    read-only endpoint)."""
    return {
        "location_ref": encode_ref("loc", site.id),
        "location": site.site_name,
        "building_type": site.building_type,
        "service_address": _address(site),
        "protection": protection,
        "emergency_address_state": e911_state_label(site),
        "site_contact": {
            "name": site.poc_name,
            "phone": site.poc_phone,
            "email": site.poc_email,
            "editable": False,
        },
        "services": services or [],
        "devices": devices or [],
    }


def service_preview(unit, *, protection: dict) -> dict:
    """Minimal service card for the location detail (PR-C3): ref + label +
    where + protection.  Full service detail is a separate endpoint."""
    return {
        "service_ref": encode_ref("svc", unit.id),
        "label": _SERVICE_LABELS.get((unit.unit_type or "").lower(), "Emergency service"),
        "where": unit.location_description,
        "protection": protection,
    }


def e911_history_item(log) -> dict:
    """Customer-safe E911 change-log entry — when / change / by / state only.
    Drops the requester email and correlation id."""
    when = getattr(log, "applied_at", None) or getattr(log, "requested_at", None)
    verified = (log.status or "").lower() in {"validated", "verified", "applied"}
    return {
        "when": when.date().isoformat() if when else None,
        "change": "Address verified" if verified else "Address updated",
        "by": getattr(log, "requester_name", None) or "Verification team",
        "state": log.status,
    }


def attention_item(site, *, protection: dict) -> dict:
    status = protection.get("status", "Unknown")
    return {
        "location_ref": encode_ref("loc", site.id),
        "location": site.site_name,
        "status": status,
        "reason": protection.get("reason") or _CUSTOMER_SUMMARY.get(status, ""),
        "action": _CUSTOMER_ACTION.get(status, ""),
    }


def portfolio_counts(labels: Iterable[str]) -> dict:
    key = {"Protected": "protected", "Attention Needed": "attention_needed",
           "Critical": "critical", "Pending Install": "pending_install",
           "Inactive": "inactive", "Unknown": "unknown"}
    counts = {"total": 0, "protected": 0, "attention_needed": 0, "critical": 0,
              "pending_install": 0, "inactive": 0, "unknown": 0}
    for lbl in labels:
        counts["total"] += 1
        counts[key.get(lbl, "unknown")] += 1
    return counts


def headline(counts: dict, as_of: Optional[str] = None) -> str:
    total = counts.get("total", 0)
    if total == 0:
        return "No locations yet — setup in progress"
    base = f"{counts.get('protected', 0)} of {total} locations Protected"
    return f"{base} (as of {as_of})" if as_of else base


# ══════════════════════════════════════════════════════════════════════
# Customer Command Center serializers (additive — Phase 1/4/6/8).
# Pure allow-list mappers: they read ONLY customer-safe fields and never
# fabricate.  Aggregation/DB loading lives in command_center.py.
# ══════════════════════════════════════════════════════════════════════

# Coarse US region from a two-letter state — a DERIVED grouping (not a raw
# field), used for the location Overview "Region".  Unknown state -> None.
_US_REGIONS = {
    "Northeast": {"CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"},
    "Midwest": {"IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"},
    "South": {"DE", "FL", "GA", "MD", "NC", "SC", "VA", "DC", "WV", "AL", "KY", "MS",
              "TN", "AR", "LA", "OK", "TX"},
    "West": {"AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"},
}


def us_region(state) -> Optional[str]:
    st = (state or "").strip().upper()
    for region, members in _US_REGIONS.items():
        if st in members:
            return region
    return None


# Customer-facing carrier/network name (a network provider name is customer-safe;
# carrier *credentials* / account ids are NOT and are never emitted — §8).
_CARRIER_LABELS = {
    "tmobile": "T-Mobile", "t-mobile": "T-Mobile", "att": "AT&T", "at&t": "AT&T",
    "verizon": "Verizon", "telnyx": "Telnyx", "bandwidth": "Bandwidth",
    "inseego": "Inseego", "starlink": "Starlink",
}


def carrier_label(raw) -> Optional[str]:
    """A friendly network/carrier NAME for display, or None. Never an account id."""
    if not raw:
        return None
    return _CARRIER_LABELS.get(str(raw).strip().lower(), str(raw).strip())


def service_with_equipment(unit, *, status: dict, equipment: Optional[list] = None,
                           carrier: Optional[str] = None, phone_numbers: Optional[list] = None,
                           last_test=None, last_inspection=None,
                           attention_items: Optional[list] = None) -> dict:
    """A Life-Safety Service card (Digital Twin): the enterprise service name, where
    it is, its customer-safe status, the equipment that supports it (grouped
    beneath), and service-level facts — equipment count, carrier (name only),
    telephone numbers, last test / last inspection, and attention items.

    All optional fields are additive and omitted-or-null when unknown; nothing is
    fabricated (last_test / last_inspection are null until a real source exists)."""
    equip = equipment or []
    return {
        "service_ref": encode_ref("svc", unit.id),
        "service": enterprise_service_label(unit.unit_type),
        "name": unit.unit_name,
        "where": unit.location_description,
        "floor": unit.floor,
        "status": status,
        "equipment": equip,
        "equipment_count": len(equip),
        "carrier": carrier_label(carrier),
        "phone_numbers": phone_numbers or [],
        "last_test": _iso(last_test) if hasattr(last_test, "isoformat") else last_test,
        "last_inspection": _iso(last_inspection) if hasattr(last_inspection, "isoformat") else last_inspection,
        "attention_items": attention_items or [],
    }


_TIMELINE_LABEL = {
    "validated": "Emergency address verified",
    "verified": "Emergency address verified",
    "applied": "Emergency address updated",
    "pending": "Emergency address submitted",
}


def timeline_item(log) -> dict:
    """Customer-safe activity entry (real data only — no fabricated events).
    Sourced from the E911 change log; the ``kind`` lets the UI theme it."""
    when = getattr(log, "applied_at", None) or getattr(log, "requested_at", None)
    st = (log.status or "").lower()
    verified = st in {"validated", "verified"}
    return {
        "when": when.date().isoformat() if when else None,
        "kind": "e911_verified" if verified else "e911_update",
        "title": _TIMELINE_LABEL.get(st, "Emergency address updated"),
        "by": getattr(log, "requester_name", None) or "Verification team",
    }


def _pct(part, whole) -> Optional[float]:
    """Percentage 0-100, or None (unknown) when there is nothing to measure."""
    if not whole:
        return None
    return round(100.0 * part / whole, 1)


# Health-score component weights (sum need not be 100; normalized over KNOWN
# components).  Unknown components lower CONFIDENCE, never the score.
_HEALTH_WEIGHTS = {
    "e911_verified": 30,
    "service_coverage": 25,
    "telemetry": 20,
    "alarm_testing": 15,
    "carrier": 10,
}
_HEALTH_LABELS = {
    "e911_verified": "E911 verification",
    "service_coverage": "Service coverage",
    "telemetry": "Live telemetry",
    "alarm_testing": "Alarm testing",
    "carrier": "Carrier health",
}


def health_score(components: dict) -> dict:
    """Enterprise Portfolio Health.  ``components`` maps a component key to a
    0-100 value OR None (unknown).  The score is the weighted average over the
    KNOWN components; confidence is the share of total weight that is known.
    Unknown inputs reduce confidence — nothing is fabricated (Phase 6)."""
    known_weight = 0.0
    weighted_sum = 0.0
    out_components = []
    for key, weight in _HEALTH_WEIGHTS.items():
        value = components.get(key)
        known = value is not None
        if known:
            known_weight += weight
            weighted_sum += weight * float(value)
        out_components.append({
            "key": key, "label": _HEALTH_LABELS[key], "weight": weight,
            "value": (round(float(value), 1) if known else None), "known": known,
        })
    score = round(weighted_sum / known_weight, 1) if known_weight else None
    total_weight = sum(_HEALTH_WEIGHTS.values())
    confidence = round(100.0 * known_weight / total_weight, 1) if total_weight else 0.0
    if score is None:
        grade = "Unknown"
    elif score >= 90:
        grade = "Excellent"
    elif score >= 75:
        grade = "Good"
    elif score >= 50:
        grade = "Fair"
    else:
        grade = "Needs attention"
    return {"score": score, "confidence": confidence, "grade": grade,
            "components": out_components}


def portfolio_summary(*, company, counts, services, protected_services,
                      devices, phone_numbers, e911_verified, e911_with_address,
                      health, recent_activity, upcoming_maintenance, as_of) -> dict:
    """Executive portfolio metrics (Command Center header).  All values are
    aggregates over customer-safe data; no raw operational field is exposed."""
    total = counts.get("total", 0)
    return {
        "portfolio_name": company,
        "as_of": as_of,
        "locations_total": total,
        "locations_protected": counts.get("protected", 0),
        "sites_requiring_attention": counts.get("attention_needed", 0),
        "critical_sites": counts.get("critical", 0),
        "life_safety_services": services,
        "protected_services": protected_services,
        "devices": devices,
        "total_phone_numbers": phone_numbers,
        "e911_verification_pct": _pct(e911_verified, e911_with_address or total),
        "service_availability_pct": _pct(protected_services, services),
        "monthly_health_score": health,
        "recent_activity": recent_activity or [],
        "upcoming_maintenance": upcoming_maintenance or [],
    }


# ══════════════════════════════════════════════════════════════════════
# Location Digital Twin serializers (additive — Phase 1/3/4/5/7).
# Placeholders return honest empty sets with a category/type scaffold so the
# UI + API are future-ready; real data (contacts, E911 activity) is emitted
# as-is.  No fabrication, no internal/sensitive fields.
# ══════════════════════════════════════════════════════════════════════

# The vocabulary of activity a location timeline can carry.  Real events are
# emitted only when a source exists; the schema is ready for the rest.
TIMELINE_KINDS = (
    "installation", "alarm_test", "carrier_migration", "firmware_update",
    "technician_visit", "customer_note", "inspection", "e911_verified",
    "e911_update", "ai_event",
)

# Document categories a location can hold (storage is future — see Phase 3).
DOCUMENT_CATEGORIES = (
    "permit", "floor_plan", "inspection_report", "photo", "carrier_paperwork",
    "service_contract", "e911_documentation",
)

# Inspection kinds a location record can carry (real data only when present).
INSPECTION_KINDS = ("fire_alarm", "elevator", "sprinkler", "generator", "annual", "other")


def timeline_entry(*, kind: str, when=None, title: str, by: str = "Verification team",
                   detail: Optional[str] = None) -> dict:
    """Generic customer-safe timeline entry for any real event source (additive).
    ``kind`` outside TIMELINE_KINDS is coerced to a neutral 'activity'."""
    k = kind if kind in TIMELINE_KINDS else "activity"
    when_out = when.isoformat()[:10] if hasattr(when, "isoformat") else when
    out = {"kind": k, "when": when_out, "title": title, "by": by}
    if detail:
        out["detail"] = detail
    return out


def location_contacts(site) -> dict:
    """Customer-safe site contacts (their own contact info).  No internal owners."""
    contacts = []
    if site.poc_name or site.poc_phone or site.poc_email:
        contacts.append({
            "role": "Site contact", "name": site.poc_name,
            "phone": site.poc_phone, "email": site.poc_email,
        })
    return {"contacts": contacts, "support": "Support team"}


def documents_placeholder() -> dict:
    """Location documents — future storage (Phase 3).  Honest empty set + the
    categories the record will hold."""
    return {"categories": list(DOCUMENT_CATEGORIES), "items": [], "available": False}


def photos_placeholder() -> dict:
    return {"items": [], "available": False}


def inspections_placeholder(items: Optional[list] = None) -> dict:
    """Inspection history — real entries only (none today -> empty), plus the
    inspection kinds the record supports."""
    return {"kinds": list(INSPECTION_KINDS), "items": items or [], "available": bool(items)}


# ══════════════════════════════════════════════════════════════════════
# Building Workspace: separated health + Digital Twin maturity (Phase 4/7).
# All additive, pure, no fabrication.  Unknown factors lower confidence.
# ══════════════════════════════════════════════════════════════════════
_HEALTH_FACTOR_WEIGHTS = {
    "operational_health": 40,
    "digital_twin_completeness": 25,
    "compliance": 20,
    "documentation": 15,
}
_HEALTH_FACTOR_LABELS = {
    "operational_health": "Operational Health",
    "digital_twin_completeness": "Digital Twin Completeness",
    "compliance": "Compliance",
    "documentation": "Documentation",
}


def separated_health(*, operational=None, completeness=None, compliance=None,
                     documentation=None) -> dict:
    """Building health split into its contributing factors, with the composite
    shown alongside — the UI explains the factors BEFORE the composite (Phase 4).
    Each factor is 0-100 or None (unknown); unknown lowers confidence, never
    fabricated."""
    values = {"operational_health": operational, "digital_twin_completeness": completeness,
              "compliance": compliance, "documentation": documentation}
    known_w = sum(_HEALTH_FACTOR_WEIGHTS[k] for k, v in values.items() if v is not None)
    total_w = sum(_HEALTH_FACTOR_WEIGHTS.values())
    composite = (round(sum(_HEALTH_FACTOR_WEIGHTS[k] * float(v)
                           for k, v in values.items() if v is not None) / known_w, 1)
                 if known_w else None)
    return {
        "composite": composite,
        "confidence": round(100.0 * known_w / total_w, 1) if total_w else 0.0,
        "factors": [{
            "key": k, "label": _HEALTH_FACTOR_LABELS[k], "weight": _HEALTH_FACTOR_WEIGHTS[k],
            "value": (round(float(values[k]), 1) if values[k] is not None else None),
            "known": values[k] is not None,
        } for k in _HEALTH_FACTOR_WEIGHTS],
    }


MATURITY_DIMENSIONS = (
    "documentation", "contacts", "procedures", "testing", "compliance", "photos", "e911",
)
_MATURITY_LABELS = {
    "documentation": "Documentation", "contacts": "Site contacts",
    "procedures": "Emergency procedures", "testing": "Testing records",
    "compliance": "Compliance", "photos": "Photos", "e911": "E911 verified",
}
_MATURITY_TIERS = ((7, "Platinum"), (5, "Gold"), (3, "Silver"), (1, "Bronze"), (0, "Bronze"))


def building_maturity(signals: dict) -> dict:
    """Digital Twin maturity — Bronze / Silver / Gold / Platinum — from how many of
    the seven dimensions are present.  Signals are booleans; missing = not met
    (honest — nothing fabricated).  A customer improves their tier by contributing."""
    dims = [{"key": d, "label": _MATURITY_LABELS[d], "met": bool(signals.get(d))}
            for d in MATURITY_DIMENSIONS]
    met = sum(1 for d in dims if d["met"])
    tier = next(t for threshold, t in _MATURITY_TIERS if met >= threshold)
    return {
        "tier": tier, "met": met, "total": len(MATURITY_DIMENSIONS),
        "score": round(100.0 * met / len(MATURITY_DIMENSIONS), 1),
        "dimensions": dims,
        "next_steps": [d["label"] for d in dims if not d["met"]][:4],
    }
