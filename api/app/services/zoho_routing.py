"""Configurable routing for inbound Zoho webhook events — pure, no I/O.

The Zoho webhook field mapping is NOT finalized, so routing is intentionally
data-driven: a payload is classified as a Subscription_Mgmt (lifecycle) event
when its ``module`` is in ``ZOHO_SUBSCRIPTION_MODULES`` **or** its ``event_type``
is in ``ZOHO_SUBSCRIPTION_EVENT_TYPES`` (both comma-separated, case-insensitive).
Either signal alone is sufficient, so Zoho workflows can evolve to send either
field without a code change — operators adjust the env vars (Render) instead.
"""

from __future__ import annotations

from typing import Any


def _csv_set(value: str | None) -> set[str]:
    """Parse a comma-separated config string into a lowercased, trimmed set."""
    if not value:
        return set()
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def is_zoho_subscription_event(payload: dict[str, Any], settings: Any) -> bool:
    """Return True if the payload should route to the subscription lifecycle ingest.

    Matches on EITHER:
      * ``payload['module']``     ∈ ZOHO_SUBSCRIPTION_MODULES, or
      * ``payload['event_type']`` ∈ ZOHO_SUBSCRIPTION_EVENT_TYPES.

    Both comparisons are case-insensitive and ignore surrounding whitespace.
    An empty configured set never matches (so a blank EVENT_TYPES config does
    not accidentally match blank/absent event_type values).
    """
    if not isinstance(payload, dict):
        return False

    modules = _csv_set(getattr(settings, "ZOHO_SUBSCRIPTION_MODULES", ""))
    event_types = _csv_set(getattr(settings, "ZOHO_SUBSCRIPTION_EVENT_TYPES", ""))

    module = str(payload.get("module") or "").strip().lower()
    event_type = str(payload.get("event_type") or "").strip().lower()

    if module and module in modules:
        return True
    if event_type and event_type in event_types:
        return True
    return False
