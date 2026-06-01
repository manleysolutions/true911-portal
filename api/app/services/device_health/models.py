"""Normalized data shapes for the device-health layer.

``VendorStatus``  — what a single vendor adapter returns for one device.
``DeviceHealth``  — the unified, hardware-agnostic per-device health view that
                    every API / portal surface consumes.

Both are plain dataclasses (no ORM, no I/O) so they are trivially testable and
serialisable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.services.device_health.reason_codes import ReasonCode
from app.services.device_health.status import NormalizedStatus


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


@dataclass
class VendorStatus:
    """One vendor adapter's normalized answer for one device.

    Vendor-specific detail is confined to ``raw_payload`` / ``metadata``.
    """

    vendor: str                                   # vola | tmobile | telnyx | inseego | cisco_ata | ms130 | ...
    device_identifier: str = ""                   # what we looked up by (serial / imei / msisdn / iccid)
    device_type: Optional[str] = None
    connection_type: Optional[str] = None
    voice_type: Optional[str] = None
    raw_status: Optional[str] = None              # vendor's own status string, verbatim
    normalized_status: NormalizedStatus = NormalizedStatus.UNKNOWN
    last_seen: Optional[datetime] = None
    signal_strength: Optional[float] = None
    sim_status: Optional[str] = None
    sip_status: Optional[str] = None
    volte_status: Optional[str] = None
    static_ip: Optional[str] = None
    firmware: Optional[str] = None
    usage: Optional[dict] = None                  # {data_mb, voice_minutes, ...}
    reason_codes: list[ReasonCode] = field(default_factory=list)
    raw_payload: Optional[dict] = None            # stored only in IntegrationPayload / metadata
    available: bool = True                        # adapter reached the vendor (creds present, no error)
    error: Optional[str] = None

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "vendor": self.vendor,
            "device_identifier": self.device_identifier,
            "device_type": self.device_type,
            "connection_type": self.connection_type,
            "voice_type": self.voice_type,
            "raw_status": self.raw_status,
            "normalized_status": self.normalized_status.value,
            "last_seen": _iso(self.last_seen),
            "signal_strength": self.signal_strength,
            "sim_status": self.sim_status,
            "sip_status": self.sip_status,
            "volte_status": self.volte_status,
            "static_ip": self.static_ip,
            "firmware": self.firmware,
            "usage": self.usage,
            "reason_codes": [r.value for r in self.reason_codes],
            "available": self.available,
            "error": self.error,
        }
        if include_raw:
            d["raw_payload"] = self.raw_payload
        return d


@dataclass
class DeviceHealth:
    """Unified per-device health — the single object every surface renders."""

    # ── Identity / context ──────────────────────────────────────────
    tenant_id: str
    device_id: str
    device_name: Optional[str] = None             # friendly name (service unit or model)
    model: Optional[str] = None
    device_type: Optional[str] = None
    manufacturer: Optional[str] = None
    serial_number: Optional[str] = None
    imei: Optional[str] = None
    iccid: Optional[str] = None
    msisdn: Optional[str] = None
    carrier: Optional[str] = None

    site_id: Optional[str] = None
    site_name: Optional[str] = None
    service_unit_id: Optional[str] = None
    service_unit_name: Optional[str] = None       # "Elevator 1"

    connection_type: str = "unknown"
    voice_type: str = "unknown"

    # ── Health ──────────────────────────────────────────────────────
    canonical_state: str = "unknown"
    status: NormalizedStatus = NormalizedStatus.UNKNOWN
    reason_codes: list[ReasonCode] = field(default_factory=list)
    recommended_action: str = ""

    # ── Supporting signals (read from DB, no live vendor call) ──────
    last_check_in: Optional[datetime] = None      # most recent liveness across channels
    last_call_activity: Optional[datetime] = None
    last_callback_received: Optional[datetime] = None   # Device.last_network_event
    last_sync_time: Optional[datetime] = None           # Device.vola_last_sync
    firmware: Optional[str] = None
    signal_dbm: Optional[float] = None
    sim_status: Optional[str] = None
    sip_status: Optional[str] = None
    volte_status: Optional[str] = None
    static_ip: Optional[str] = None

    vendor_links: dict[str, Any] = field(default_factory=dict)   # {vola_org_id, zoho_account_id, ...}
    vendors: list[VendorStatus] = field(default_factory=list)    # populated by sync enrichment, optional

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "model": self.model,
            "device_type": self.device_type,
            "manufacturer": self.manufacturer,
            "serial_number": self.serial_number,
            "imei": self.imei,
            "iccid": self.iccid,
            "msisdn": self.msisdn,
            "carrier": self.carrier,
            "site_id": self.site_id,
            "site_name": self.site_name,
            "service_unit_id": self.service_unit_id,
            "service_unit_name": self.service_unit_name,
            "connection_type": self.connection_type,
            "voice_type": self.voice_type,
            "canonical_state": self.canonical_state,
            "status": self.status.value,
            "reason_codes": [r.value for r in self.reason_codes],
            "recommended_action": self.recommended_action,
            "last_check_in": _iso(self.last_check_in),
            "last_call_activity": _iso(self.last_call_activity),
            "last_callback_received": _iso(self.last_callback_received),
            "last_sync_time": _iso(self.last_sync_time),
            "firmware": self.firmware,
            "signal_dbm": self.signal_dbm,
            "sim_status": self.sim_status,
            "sip_status": self.sip_status,
            "volte_status": self.volte_status,
            "static_ip": self.static_ip,
            "vendor_links": self.vendor_links,
            "vendors": [v.to_dict() for v in self.vendors],
        }

    def to_customer_view(self) -> dict[str, Any]:
        """The simple-language shape for the customer portal.

        Property / Elevator-Fire-Line / Device / Carrier / Voice Path /
        Status / Last Check-In / Last Call / Recommended Action.
        """
        _VOICE_LABEL = {
            "volte": "VoLTE", "sip": "SIP", "analog": "Analog",
            "sip_over_lte": "SIP over LTE", "unknown": "—",
        }
        return {
            "property": self.site_name,
            "unit": self.service_unit_name,           # Elevator / Fire Alarm / Line
            "device": self.device_name or self.model,
            "carrier": (self.carrier or "—"),
            "voice_path": _VOICE_LABEL.get(self.voice_type, self.voice_type or "—"),
            "status": self.status.value,
            "last_check_in": _iso(self.last_check_in),
            "last_call": _iso(self.last_call_activity),
            "recommended_action": self.recommended_action,
        }
