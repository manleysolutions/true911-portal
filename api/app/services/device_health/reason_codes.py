"""Generic, hardware-agnostic reason codes.

These explain *why* a device is not simply "Online".  They are deliberately
vendor-neutral so the same code means the same thing for a Vola LM150, an
MS130v4, or an Inseego+Cisco ATA.  Vendor-specific detail (e.g. a Vola task
error, a T-Mobile SubscriberInquiry status string) belongs in
``VendorStatus.raw_payload`` / metadata, never here.
"""

from __future__ import annotations

from enum import Enum


class ReasonCode(str, Enum):
    """Why a device is in its current normalized status."""

    OK = "OK"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    SIM_INACTIVE = "SIM_INACTIVE"
    SIP_UNREGISTERED = "SIP_UNREGISTERED"
    VOLTE_NOT_READY = "VOLTE_NOT_READY"
    NO_RECENT_HEARTBEAT = "NO_RECENT_HEARTBEAT"
    NO_RECENT_CALL_ACTIVITY = "NO_RECENT_CALL_ACTIVITY"
    VENDOR_API_UNAVAILABLE = "VENDOR_API_UNAVAILABLE"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    CONFIG_MISMATCH = "CONFIG_MISMATCH"


# Ordering used to pick the single "primary" reason that drives the
# recommended action.  Earlier = more urgent / more actionable.
PRIMARY_ORDER: tuple[ReasonCode, ...] = (
    ReasonCode.DEVICE_OFFLINE,
    ReasonCode.NO_RECENT_HEARTBEAT,
    ReasonCode.SIM_INACTIVE,
    ReasonCode.SIP_UNREGISTERED,
    ReasonCode.VOLTE_NOT_READY,
    ReasonCode.DEVICE_NOT_FOUND,
    ReasonCode.CONFIG_MISMATCH,
    ReasonCode.VENDOR_API_UNAVAILABLE,
    ReasonCode.MISSING_CREDENTIALS,
    ReasonCode.NO_RECENT_CALL_ACTIVITY,
    ReasonCode.OK,
)


def primary_reason(reasons: list[ReasonCode]) -> ReasonCode:
    """Pick the most actionable reason from a list (OK if empty)."""
    if not reasons:
        return ReasonCode.OK
    for code in PRIMARY_ORDER:
        if code in reasons:
            return code
    return reasons[0]
