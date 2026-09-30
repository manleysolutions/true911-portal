"""Versioned source-status -> lifecycle interpretation (D-024).

Each source has ONE versioned map.  Only statuses whose meaning is documented
for that source are mapped; every other value - including an empty status -
interprets as UNKNOWN.  An unknown status is NEVER treated as active.  The raw
value is always stored beside the interpretation, with the rule that produced
it, so a later map version can re-interpret history.

Lifecycle is currentness only.  ACTIVE never implies healthy, monitored or
E911-verified (separate axes, D-006).
"""

from __future__ import annotations

import re

from app.services.canonical import vocab as V

NAPCO = "NAPCO"
T_MOBILE = "T_MOBILE"
VERIZON = "VERIZON"
RED_POCKET = "RED_POCKET"
SOURCE_SYSTEMS = (NAPCO, T_MOBILE, VERIZON, RED_POCKET)

_C, _S, _D = V.CURRENT, V.SUSPENDED, V.DECOMMISSIONED

STATUS_MAPS: dict[str, tuple[str, dict[str, str]]] = {
    # NAPCO StarLink RadioList "SIMStatus" (observed values: Active / Suspend / Terminate)
    NAPCO: ("napco.simstatus.v1", {
        "active": _C,
        "suspend": _S, "suspended": _S,
        "terminate": _D, "terminated": _D,
    }),
    # T-Mobile / Infatrac (Genesis) subscriber status
    T_MOBILE: ("tmobile.infatrac.v1", {
        "active": _C, "activated": _C,
        "suspend": _S, "suspended": _S,
        "deactivated": _D, "deactive": _D, "cancelled": _D, "canceled": _D,
        "terminated": _D, "disconnected": _D,
    }),
    # Verizon ThingSpace subscription state.  Connection words ("connected") are
    # activity, not lifecycle, and pre-activation states are not current.
    VERIZON: ("verizon.thingspace.v1", {
        "active": _C, "activated": _C,
        "suspend": _S, "suspended": _S,
        "deactive": _D, "deactivated": _D, "terminated": _D,
    }),
    # Red Pocket - PROVISIONAL until a production export is reviewed.  "expired"
    # is deliberately unmapped (plan lapse is not proof of decommissioning).
    RED_POCKET: ("redpocket.v0-provisional", {
        "active": _C,
        "suspend": _S, "suspended": _S,
        "cancelled": _D, "canceled": _D, "deactivated": _D, "terminated": _D,
    }),
}


def normalize_status(raw) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(raw or "").lower())).strip()


def interpret(source_system: str, raw) -> tuple[str, str]:
    """-> (lifecycle, rule).  Unmapped / empty -> UNKNOWN."""
    version, table = STATUS_MAPS[source_system]
    key = normalize_status(raw)
    if key and key in table:
        return table[key], ("%s:%s->%s" % (version, key, table[key]))[:120]
    return V.UNKNOWN, ("%s:unmapped(%s)->UNKNOWN" % (version, key or "<empty>"))[:120]


def map_version(source_system: str) -> str:
    return STATUS_MAPS[source_system][0]
