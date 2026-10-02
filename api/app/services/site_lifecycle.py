"""Site lifecycle vocabulary for PLANNED vs operational sites (CT-1, D-034 proposed).

Registration conversion creates a PLANNED portfolio, never an operational one:

    ASSESSMENT ≠ DEPLOYMENT · CUSTOMER CREATED ≠ CONNECTED
    ADDRESS PROVIDED ≠ E911 VERIFIED · SERVICE REQUESTED ≠ INSTALLED
    PHONE PROVIDED ≠ VERIFIED CONNECTION · DEVICE REQUESTED ≠ DEVICE PRESENT

Values reuse the existing vocabularies: "Pending Install" is the assurance
label for not-yet-deployed sites, "pending" is a non-live onboarding value the
assurance engine already treats as Pending Install, and "unverified" is the
existing address-enrichment E911 status that keeps a row in review queues.
"""

from __future__ import annotations

from typing import Optional

# Site.status for a site that exists on paper but has no installed equipment.
SITE_STATUS_PENDING_INSTALL = "Pending Install"
PLANNED_SITE_STATUSES = frozenset({SITE_STATUS_PENDING_INSTALL})

# Site.onboarding_status for a planned site (not in the engine's _LIVE_ONBOARDING).
ONBOARDING_PENDING = "pending"

# E911 state for a prospect-provided address: on file, not verified, needs confirming.
E911_STATUS_UNVERIFIED = "unverified"
ADDRESS_SOURCE_REGISTRATION = "registration"

# Onboarding values an operator may set through the internal site API — the
# vocabulary already in use across importers, provisioning and the engine.
ONBOARDING_STATUSES = (
    "pending", "onboarding", "in_progress",                       # not live
    "active", "complete", "completed", "operational", "accepted", "done",   # live
    "retired",
)


def is_planned_site(status: Optional[str]) -> bool:
    """True for a site that conversion (or an operator) marked as planned."""
    return (status or "").strip() in PLANNED_SITE_STATUSES
