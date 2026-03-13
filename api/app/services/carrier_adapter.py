"""Carrier adapter service — ingests network-level telemetry from carriers.

Supports T-Mobile, Verizon, AT&T adapters.  Each normalizes carrier-specific
payloads into a common CarrierTelemetry structure that updates device records
and creates network events when thresholds are crossed.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.network_event import NetworkEvent
from app.models.command_telemetry import CommandTelemetry


# ── Signal thresholds ───────────────────────────────────────────────

SIGNAL_DEGRADED_DBM = -100
SIGNAL_CRITICAL_DBM = -110


def _severity_for_signal(dbm: Optional[float]) -> Optional[str]:
    if dbm is None:
        return None
    if dbm <= SIGNAL_CRITICAL_DBM:
        return "critical"
    if dbm <= SIGNAL_DEGRADED_DBM:
        return "warning"
    return None


# ── Common telemetry structure ──────────────────────────────────────

class CarrierTelemetry:
    def __init__(
        self,
        device_id: str,
        carrier: str,
        signal_dbm: Optional[float] = None,
        network_status: Optional[str] = None,
        roaming: Optional[bool] = None,
        data_usage_mb: Optional[float] = None,
        network_tech: Optional[str] = None,
    ):
        self.device_id = device_id
        self.carrier = carrier
        self.signal_dbm = signal_dbm
        self.network_status = network_status
        self.roaming = roaming
        self.data_usage_mb = data_usage_mb
        self.network_tech = network_tech


# ── Carrier adapters ───────────────────────────────────────────────

class BaseCarrierAdapter:
    """Base adapter — override normalize() for carrier-specific formats."""

    carrier_name: str = "generic"

    def normalize(self, raw: dict) -> CarrierTelemetry:
        return CarrierTelemetry(
            device_id=raw.get("device_id", ""),
            carrier=self.carrier_name,
            signal_dbm=raw.get("signal_dbm"),
            network_status=raw.get("network_status"),
            roaming=raw.get("roaming"),
            data_usage_mb=raw.get("data_usage_mb"),
            network_tech=raw.get("network_tech"),
        )


class TMobileAdapter(BaseCarrierAdapter):
    carrier_name = "t-mobile"

    def normalize(self, raw: dict) -> CarrierTelemetry:
        return CarrierTelemetry(
            device_id=raw.get("device_id") or raw.get("imei", ""),
            carrier="t-mobile",
            signal_dbm=raw.get("rssi") or raw.get("signal_dbm"),
            network_status=raw.get("registration_status") or raw.get("network_status"),
            roaming=raw.get("roaming"),
            data_usage_mb=raw.get("data_usage_mb"),
            network_tech=raw.get("rat") or raw.get("network_tech"),
        )


class VerizonAdapter(BaseCarrierAdapter):
    carrier_name = "verizon"

    def normalize(self, raw: dict) -> CarrierTelemetry:
        return CarrierTelemetry(
            device_id=raw.get("device_id") or raw.get("mdn", ""),
            carrier="verizon",
            signal_dbm=raw.get("signal_strength") or raw.get("signal_dbm"),
            network_status=raw.get("connection_status") or raw.get("network_status"),
            roaming=raw.get("is_roaming") or raw.get("roaming"),
            data_usage_mb=raw.get("data_usage_mb"),
            network_tech=raw.get("access_technology") or raw.get("network_tech"),
        )


class ATTAdapter(BaseCarrierAdapter):
    carrier_name = "att"

    def normalize(self, raw: dict) -> CarrierTelemetry:
        return CarrierTelemetry(
            device_id=raw.get("device_id") or raw.get("iccid", ""),
            carrier="att",
            signal_dbm=raw.get("rsrp") or raw.get("signal_dbm"),
            network_status=raw.get("attach_status") or raw.get("network_status"),
            roaming=raw.get("roaming"),
            data_usage_mb=raw.get("usage_mb") or raw.get("data_usage_mb"),
            network_tech=raw.get("bearer") or raw.get("network_tech"),
        )


ADAPTERS = {
    "t-mobile": TMobileAdapter(),
    "verizon": VerizonAdapter(),
    "att": ATTAdapter(),
    "generic": BaseCarrierAdapter(),
}


def get_adapter(carrier: str) -> BaseCarrierAdapter:
    return ADAPTERS.get(carrier.lower().replace(" ", "-").replace("&", ""), ADAPTERS["generic"])


# ── Ingest pipeline ────────────────────────────────────────────────

async def ingest_carrier_telemetry(
    db: AsyncSession,
    tenant_id: str,
    telemetry: CarrierTelemetry,
) -> list[NetworkEvent]:
    """Update device fields and create network events if thresholds crossed."""

    now = datetime.now(timezone.utc)
    events_created: list[NetworkEvent] = []

    # Find device
    q = select(Device).where(
        Device.tenant_id == tenant_id,
        Device.device_id == telemetry.device_id,
    )
    result = await db.execute(q)
    device = result.scalar_one_or_none()
    if not device:
        return events_created

    # Update device carrier fields
    device.carrier = telemetry.carrier
    device.network_status = telemetry.network_status
    device.data_usage_mb = telemetry.data_usage_mb
    device.last_network_event = now
    device.telemetry_source = f"{telemetry.carrier}_carrier"

    # Store telemetry sample
    ct = CommandTelemetry(
        tenant_id=tenant_id,
        device_id=device.device_id,
        site_id=device.site_id,
        signal_strength=telemetry.signal_dbm,
        metadata_json=json.dumps({
            "source": f"{telemetry.carrier}_carrier",
            "carrier": telemetry.carrier,
            "network_status": telemetry.network_status,
            "roaming": telemetry.roaming,
            "data_usage_mb": telemetry.data_usage_mb,
            "network_tech": telemetry.network_tech,
        }),
    )
    db.add(ct)

    # Check for signal degradation
    sig_severity = _severity_for_signal(telemetry.signal_dbm)
    if sig_severity:
        evt = NetworkEvent(
            event_id=f"ne-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            device_id=device.device_id,
            site_id=device.site_id,
            carrier=telemetry.carrier,
            event_type="signal_degradation",
            severity=sig_severity,
            summary=f"Signal at {telemetry.signal_dbm} dBm ({sig_severity})",
            signal_dbm=telemetry.signal_dbm,
            network_status=telemetry.network_status,
        )
        db.add(evt)
        events_created.append(evt)

    # Check for disconnection
    if telemetry.network_status and telemetry.network_status.lower() in (
        "disconnected", "not_registered", "denied", "detached",
    ):
        evt = NetworkEvent(
            event_id=f"ne-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            device_id=device.device_id,
            site_id=device.site_id,
            carrier=telemetry.carrier,
            event_type="device_disconnected",
            severity="critical",
            summary=f"Device disconnected — status: {telemetry.network_status}",
            network_status=telemetry.network_status,
        )
        db.add(evt)
        events_created.append(evt)

    # Check for roaming
    if telemetry.roaming:
        evt = NetworkEvent(
            event_id=f"ne-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            device_id=device.device_id,
            site_id=device.site_id,
            carrier=telemetry.carrier,
            event_type="roaming_detected",
            severity="warning",
            summary=f"Device roaming on {telemetry.carrier}",
            roaming=True,
            network_status=telemetry.network_status,
        )
        db.add(evt)
        events_created.append(evt)

    return events_created
