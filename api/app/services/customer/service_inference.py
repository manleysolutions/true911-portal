"""Life Safety Service inference — turn equipment into business services.

The customer reasons in **services** (Fire Alarm, Elevator, Area of Refuge,
Emergency Phone, BDA/DAS, Generator Monitoring, Mass Notification, Burglar Alarm)
— never in device models. This engine groups equipment (devices/lines, optionally
anchored by a ServiceUnit) into first-class services and classifies each by type
with a confidence, from real signals only (model, device/equipment type, notes,
manufacturer, carrier, line label, ServiceUnit). Manual overrides win.

PURE + deterministic: no DB, no I/O, no fabrication.  "unknown" is a real outcome
(a service we can't classify) and lowers confidence — it is never invented.
"""

from __future__ import annotations

from typing import Iterable, Optional

# The Life-Safety service catalog (Phase 1).  These are the ONLY service types.
SERVICE_TYPES = (
    "Fire Alarm", "Elevator", "Area of Refuge", "Emergency Phone",
    "BDA/DAS", "Generator Monitoring", "Mass Notification", "Burglar Alarm",
    "Life Safety Service",  # generic fallback — an unclassified service
)

CONFIDENCE_ORDER = {"Confirmed": 3, "High": 2, "Medium": 1, "Low": 0}

# ActionAudit.action_type used to persist + log a manual classification override
# (Phase 8).  Overrides live as append-only audit records — logging is inherent.
OVERRIDE_ACTION = "service_classification_override"
OVERRIDE_OPERATIONS = ("approve", "override", "merge", "split")

# Ordered classification rules (first match wins).  Each rule: (patterns,
# service_type, confidence).  Patterns are lowercase substrings matched against a
# combined haystack of the equipment's signals.  Specific model/keyword matches
# are High; generic keywords are Medium.  Order matters — most specific first.
_RULES: tuple = (
    (("area of refuge", "refuge", "aor"), "Area of Refuge", "High"),
    (("elevator", "elev ", " elev", "lula", "lm150", "elevator phone"), "Elevator", "High"),
    (("fire alarm", "facp", "fire panel", "fire comm", "ms130", "smoke"), "Fire Alarm", "High"),
    (("generator", "genset", "gen-mon", "generator monitor"), "Generator Monitoring", "High"),
    (("bda", "das", "ercs", "signal booster", "public safety das", "public-safety"), "BDA/DAS", "High"),
    (("mass notification", "mass-notification", "mns", "paging", "intercom", "annunciat"), "Mass Notification", "High"),
    (("burglar", "intrusion", "security alarm", "burg "), "Burglar Alarm", "High"),
    (("emergency phone", "call station", "call box", "callbox", "blue light",
      "help phone", "area phone", "emergency call"), "Emergency Phone", "High"),
    # Weaker/generic signals — Medium confidence.
    (("fire",), "Fire Alarm", "Medium"),
    (("alarm",), "Burglar Alarm", "Medium"),
    (("phone", "voice", "pots", "ata", "did"), "Emergency Phone", "Medium"),
)


def _haystack(item: dict) -> str:
    parts = [
        item.get("model"), item.get("device_type"), item.get("manufacturer"),
        item.get("carrier"), item.get("notes"), item.get("line_label"),
        item.get("unit_type"), item.get("unit_name"), item.get("where"),
    ]
    # underscores/hyphens -> spaces so enum values (e.g. "emergency_call_station",
    # "area_of_refuge", "fire_alarm") match the space-separated keyword rules.
    return " ".join(str(p) for p in parts if p).lower().replace("_", " ").replace("-", " ")


def classify(item: dict) -> tuple[str, str, str]:
    """Classify one equipment item -> (service_type, confidence, source).

    Priority: an explicit ServiceUnit type is Confirmed; otherwise the rules
    engine infers from real signals; no signal -> generic 'Life Safety Service'
    at Low confidence (an honest 'we don't know yet', never fabricated)."""
    # Explicit ServiceUnit type is authoritative (Confirmed).
    from app.services.customer.serialize import SERVICE_CATALOG
    ut = (item.get("unit_type") or "").strip().lower()
    if ut and ut in SERVICE_CATALOG and SERVICE_CATALOG[ut] != "Life Safety Service":
        return SERVICE_CATALOG[ut], "Confirmed", "service_unit"

    hay = _haystack(item)
    if hay:
        for patterns, service_type, confidence in _RULES:
            if any(p in hay for p in patterns):
                return service_type, confidence, "inferred"
    return "Life Safety Service", "Low", "unclassified"


def _group_key(service_type: str, item: dict) -> str:
    where = (item.get("where") or item.get("floor") or "").strip().lower()
    return f"{service_type}|{where}"


def infer_services(equipment: Iterable[dict], *,
                   overrides: Optional[dict] = None,
                   empty_units: Optional[Iterable[dict]] = None) -> list[dict]:
    """Group equipment into Life-Safety services (Phase 1/2).

    ``equipment``: dicts with device_id + classification signals (model,
    device_type, manufacturer, carrier, notes, line_label, unit_type, unit_name,
    where, floor, phone_number, status).
    ``overrides``: {device_id: service_type} — a manual operations override wins
    (Confirmed).
    ``empty_units``: ServiceUnits with no device (still surfaced as services with
    0 equipment so nothing is lost).

    Returns a list of service dicts: {service_type, confidence, source, where,
    floor, equipment[], phone_numbers[], device_ids[]}. One service may contain
    multiple devices (e.g. a Fire Alarm panel + communicator)."""
    overrides = overrides or {}
    services: dict[str, dict] = {}

    def _svc(service_type: str, item: dict, confidence: str, source: str) -> dict:
        key = _group_key(service_type, item)
        svc = services.get(key)
        if svc is None:
            svc = {
                "key": key,
                "service_type": service_type, "confidence": confidence, "source": source,
                "where": item.get("where"), "floor": item.get("floor"),
                "equipment": [], "phone_numbers": [], "device_ids": [],
            }
            services[key] = svc
        else:
            # keep the strongest confidence seen in the group
            if CONFIDENCE_ORDER.get(confidence, 0) > CONFIDENCE_ORDER.get(svc["confidence"], 0):
                svc["confidence"] = confidence
        return svc

    for item in equipment:
        did = item.get("device_id")
        if did and did in overrides:
            service_type, confidence, source = overrides[did], "Confirmed", "override"
        else:
            service_type, confidence, source = classify(item)
        svc = _svc(service_type, item, confidence, source)
        svc["equipment"].append(item)
        if did:
            svc["device_ids"].append(did)
        pn = item.get("phone_number")
        if pn and pn not in svc["phone_numbers"]:
            svc["phone_numbers"].append(pn)

    # ServiceUnits with no device -> services with 0 equipment (nothing lost).
    for u in (empty_units or []):
        stype, conf, src = classify({"unit_type": u.get("unit_type"), "unit_name": u.get("unit_name")})
        key = _group_key(stype, u)
        if key not in services:
            services[key] = {
                "key": key,
                "service_type": stype, "confidence": conf if src == "service_unit" else "Low",
                "source": src, "where": u.get("where"), "floor": u.get("floor"),
                "equipment": [], "phone_numbers": [], "device_ids": [],
            }

    # Stable order: Confirmed/High first, then by service type.
    return sorted(services.values(),
                  key=lambda s: (-CONFIDENCE_ORDER.get(s["confidence"], 0), s["service_type"], s.get("where") or ""))
