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
    "Attention Needed": "Manley Solutions is reviewing this location.",
    "Critical": "Manley Solutions has been alerted and is addressing this.",
    "Pending Install": "Installation and testing are in progress.",
    "Inactive": "No action needed — service is inactive.",
    "Unknown": "Manley Solutions is confirming this location's status.",
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
        "by": getattr(log, "requester_name", None) or "Manley",
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
