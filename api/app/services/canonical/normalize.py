"""Identifier / label normalisation for canonical reconciliation (pure).

Classification is by EXPLICIT label only: a number is never given a service
type from its digits, and an equipment-level type is never propagated to the
individual numbers of a multi-number device.
"""

from __future__ import annotations

import re

from app.services.canonical import vocab as V


def mask(value) -> str:
    """Last four characters only - for SIM / IMEI / radio ids in any output."""
    v = str(value or "")
    return ("***" + v[-4:]) if len(v) > 4 else v


def n10(value) -> str | None:
    """A NANP telephone number as 10 digits, or None."""
    d = re.sub(r"\D", "", str(value or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else None


def nid(value) -> str:
    """An equipment identifier (NAPCO id / ICCID / IMEI / serial), upper-alnum."""
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


# A StarLink / NAPCO communicator radio number is short (observed 6-8 chars;
# synthetic test ids like "NAP-0001").  Values with these shapes are other
# equipment identifiers and must never become a radio identity:
#   * ICCID  - 19/20 digits starting 89;
#   * IMEI   - 15 digits;
#   * device serials (e.g. MS130 "2023010100000027"-style) - 13+ characters.
RADIO_ID_MAX_LEN = 12
RADIO_ID_MIN_LEN = 4


def radio_id(value) -> str | None:
    """A communicator radio identity, or None when the value cannot be one.

    Generic shape rule (no per-customer special cases): too long to be a radio
    number (serials, IMEIs, ICCIDs), too short, or a 10/11-digit NANP telephone
    number -> None.  Only call this on values from an explicitly radio-typed
    field; shape alone never makes a value a radio identity."""
    v = nid(value)
    if not (RADIO_ID_MIN_LEN <= len(v) <= RADIO_ID_MAX_LEN):
        return None
    if v.isdigit() and n10(v):          # a telephone number typed into a radio field
        return None
    return v


# Device SKU / commercial plan descriptors ("SLELTE - Fire (Dual Line)",
# "SLEMAXVI-FIRE (Dual Line 5G)", "Verizon LTE Unlimited Service Pack 3").  They
# describe hardware or billing - several were applied by mass update - never the
# life-safety function, so a value that looks like one is not service evidence.
_SKU_RE = re.compile(
    r"(?i)\bsle(?:lte|max)\w*|\bsl[ef]-|\bms\s*130|\(\s*(?:dual|single)\s+(?:line|path)"
    r"|\bdual\s+(?:line|path)\b|\bsingle\s+line\b|\bservice\s+pack\b|\bunlimited\b")


def is_sku_label(text) -> bool:
    """True when a label value is a device SKU / plan descriptor, not a
    statement of the service the line or radio provides."""
    return bool(_SKU_RE.search(str(text or "")))


def nalias(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def naddr(street, city, state) -> str:
    t = "%s %s %s" % (street or "", city or "", state or "")
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def words(text) -> str:
    return " %s " % re.sub(r"[^a-z0-9]+", " ", str(text or "").lower())


def store_number(name) -> str | None:
    """Store number from a label ("RH Chicago #147", "Restoration Hardware-150",
    "RH 147").  Returned without leading zeros; None when absent."""
    n = str(name or "")
    m = re.search(r"#\s*0*(\d{1,4})\b", n)
    if m:
        return m.group(1)
    m = re.search(r"(?:hardware|hdwr)\s*[-–]\s*0*(\d{2,4})\b", n, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\brh\b[\s\-#]*0*(\d{1,4})\b", n.lower())
    return m.group(1) if m else None


_ELEV = (" elevator", " elev ", " lift ", " lula")
_EPH = (" emergency phone", " call box", " callbox", " call station", " refuge",
        " blue light", " help phone", " emergency call", " area of refuge")
_FACP = (" fire", " facp ", " alarm panel", " alarm control", " fire panel")
_SECURITY = (" burglar", " intrusion", " security")
_NON_LIFE_SAFETY = (" fax", " pos ", " internet", " data ", " modem", " router",
                    " gate ", " door", " desk", " office", " admin",
                    " business line", " main line", " voicemail")


def classify_label(text) -> tuple[str | None, str | None]:
    """Explicit label -> (category, strength).  ``strength`` is "explicit" or
    "generic-alarm".  (None, None) when the label names no service."""
    t = words(text)
    if not t.strip():
        return None, None
    if any(w in t for w in _ELEV):
        return V.ELEVATOR, "explicit"
    if any(w in t for w in _EPH):
        return V.EMERGENCY_PHONE, "explicit"
    if any(w in t for w in _FACP):
        return V.FACP, "explicit"
    if any(w in t for w in _SECURITY):
        return V.OTHER, "explicit"
    if " alarm" in t:
        return V.FACP, "generic-alarm"
    if any(w in t for w in _NON_LIFE_SAFETY):
        return V.OTHER, "explicit"
    return None, None


_INACTIVE = ("de-activ", "deactiv", "cancel", "terminat", "disconn", "inactive",
             "decommission", "retired")


def source_lifecycle(status) -> tuple[str, str] | None:
    """Lifecycle implied by a source status string, or None when it says nothing.
    Suspension is kept distinct from decommissioning."""
    s = str(status or "").strip().lower()
    if not s:
        return None
    if "suspend" in s:
        return V.SUSPENDED, V.REASON_SOURCE_SUSPENDED
    if any(w in s for w in _INACTIVE):
        return V.DECOMMISSIONED, V.REASON_SOURCE_DEACTIVATED
    if "activ" in s or s in ("live", "in service", "provisioned"):
        return V.CURRENT, V.REASON_SOURCE_ACTIVE
    return None


def is_inactive(status) -> bool:
    lc = source_lifecycle(status)
    return bool(lc and lc[0] in V.NOT_CURRENT)
