"""Map reason codes to a single customer-friendly recommended action.

Generic and vendor-neutral — the same wording applies to any hardware class.
"""

from __future__ import annotations

from app.services.device_health.reason_codes import ReasonCode, primary_reason


_ACTIONS: dict[ReasonCode, str] = {
    ReasonCode.OK: "No action needed.",
    ReasonCode.DEVICE_OFFLINE: (
        "Device is not checking in. Verify on-site power and the cellular / "
        "network connection."
    ),
    ReasonCode.NO_RECENT_HEARTBEAT: (
        "Device has not reported in yet. Confirm installation is complete and "
        "the device is powered on."
    ),
    ReasonCode.SIM_INACTIVE: (
        "The SIM is not active. Check the carrier activation status for this line."
    ),
    ReasonCode.SIP_UNREGISTERED: (
        "The voice line is not registered. Check SIP credentials / registration."
    ),
    ReasonCode.VOLTE_NOT_READY: (
        "VoLTE is not ready on this line. Confirm carrier VoLTE provisioning."
    ),
    ReasonCode.NO_RECENT_CALL_ACTIVITY: (
        "No recent call activity. An optional test call is recommended to "
        "confirm the voice path."
    ),
    ReasonCode.VENDOR_API_UNAVAILABLE: (
        "Vendor status could not be retrieved right now. Status will refresh on "
        "the next sync."
    ),
    ReasonCode.MISSING_CREDENTIALS: (
        "Live vendor status is not yet enabled (credentials not configured). "
        "Showing last-known platform status."
    ),
    ReasonCode.DEVICE_NOT_FOUND: (
        "Device was not found in the vendor system. Verify it is provisioned "
        "with the vendor."
    ),
    ReasonCode.CONFIG_MISMATCH: (
        "Device / SIM mapping looks inconsistent. Review the device record."
    ),
}


def recommend(reasons: list[ReasonCode]) -> str:
    """Return one recommended action for the most actionable reason."""
    return _ACTIONS.get(primary_reason(reasons), _ACTIONS[ReasonCode.OK])
