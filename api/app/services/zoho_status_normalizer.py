"""Normalize Zoho activation/subscription status into a canonical LIFECYCLE state.

Pure, no I/O.  Lifecycle is a SEPARATE axis from operational status (Online /
Offline / Attention), which stays owned by True911 telemetry.  This maps Zoho's
free-text commercial status (e.g. "De-activated") to a small canonical
vocabulary used by the staging records and, later, the gated promotion.

Canonical lifecycle states:
    active           — in service / billing active
    suspended        — temporarily on hold
    deactivated      — cancelled / terminated / inactive
    pending_install  — ordered / provisioning / awaiting activation
    unknown          — unmapped or empty (never assumed active)

IMPORTANT: ``deactivated`` / ``suspended`` / ``pending_install`` / ``unknown``
must NEVER present as healthy active monitoring.  ``presents_as_active_monitoring``
encodes that rule for downstream consumers (alerting/UI/promotion).
"""

from __future__ import annotations

import re
from typing import Optional

ACTIVE = "active"
SUSPENDED = "suspended"
DEACTIVATED = "deactivated"
PENDING_INSTALL = "pending_install"
UNKNOWN = "unknown"

CANONICAL_STATES = frozenset({ACTIVE, SUSPENDED, DEACTIVATED, PENDING_INSTALL, UNKNOWN})

_NON_ALNUM = re.compile(r"[^a-z0-9]")

# Exact normalized matches (lowercased, non-alphanumerics stripped).
_EXACT = {
    "active": ACTIVE,
    "activated": ACTIVE,
    "inservice": ACTIVE,
    "connected": ACTIVE,
    "suspended": SUSPENDED,
    "suspend": SUSPENDED,
    "onhold": SUSPENDED,
    "hold": SUSPENDED,
    "paused": SUSPENDED,
    "deactivated": DEACTIVATED,
    "deactive": DEACTIVATED,
    "inactive": DEACTIVATED,
    "cancelled": DEACTIVATED,
    "canceled": DEACTIVATED,
    "terminated": DEACTIVATED,
    "disconnected": DEACTIVATED,
    "closed": DEACTIVATED,
    "pending": PENDING_INSTALL,
    "pendinginstall": PENDING_INSTALL,
    "pendingactivation": PENDING_INSTALL,
    "new": PENDING_INSTALL,
    "provisioning": PENDING_INSTALL,
    "ordered": PENDING_INSTALL,
}

# Ordered substring fallback.  Deactivated / suspended / pending are checked
# BEFORE active so that "inactive" / "deactivated" never fall through to the
# "activ" rule.
_ORDERED = (
    ("deactiv", DEACTIVATED),
    ("inactiv", DEACTIVATED),
    ("cancel", DEACTIVATED),
    ("terminat", DEACTIVATED),
    ("disconnect", DEACTIVATED),
    ("suspend", SUSPENDED),
    ("hold", SUSPENDED),
    ("paus", SUSPENDED),
    ("pending", PENDING_INSTALL),
    ("provision", PENDING_INSTALL),
    ("activ", ACTIVE),
    ("inservice", ACTIVE),
    ("connect", ACTIVE),
)


def _norm(value: str) -> str:
    return _NON_ALNUM.sub("", str(value).lower())


def normalize_activation_status(raw: Optional[str]) -> str:
    """Map a raw Zoho status string to a canonical lifecycle state.

    Returns ``unknown`` for ``None`` / empty / unrecognized input — we never
    guess ``active``.
    """
    if raw is None:
        return UNKNOWN
    norm = _norm(raw)
    if not norm:
        return UNKNOWN
    if norm in _EXACT:
        return _EXACT[norm]
    for token, state in _ORDERED:
        if token in norm:
            return state
    return UNKNOWN


def presents_as_active_monitoring(state: Optional[str]) -> bool:
    """True only for the canonical ``active`` state.

    Deactivated / suspended / pending_install / unknown all return False so a
    deactivated subscription is never shown as healthy active monitoring.
    """
    return state == ACTIVE
