from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DeviceOut(BaseModel):
    id: int
    device_id: str
    tenant_id: str
    site_id: Optional[str] = None
    status: str
    device_type: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    imei: Optional[str] = None
    iccid: Optional[str] = None
    msisdn: Optional[str] = None
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None
    provision_code: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    heartbeat_interval: Optional[int] = None
    notes: Optional[str] = None
    has_api_key: bool = False
    claimed_at: Optional[datetime] = None
    claimed_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    computed_status: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceCreate(BaseModel):
    device_id: str
    site_id: Optional[str] = None
    status: str = "provisioning"
    device_type: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    imei: Optional[str] = None
    iccid: Optional[str] = None
    msisdn: Optional[str] = None
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None
    provision_code: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    heartbeat_interval: Optional[int] = None
    notes: Optional[str] = None


class DeviceUpdate(BaseModel):
    site_id: Optional[str] = None
    status: Optional[str] = None
    device_type: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    imei: Optional[str] = None
    iccid: Optional[str] = None
    msisdn: Optional[str] = None
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None
    provision_code: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    heartbeat_interval: Optional[int] = None
    notes: Optional[str] = None


class DeviceHeartbeatRequest(BaseModel):
    """Payload from a device checking in (JWT-authenticated admin endpoint)."""
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None


class DeviceCreateOut(DeviceOut):
    """Returned only from POST /devices — includes the one-time raw API key."""
    api_key: Optional[str] = None


class DeviceKeyOut(BaseModel):
    """Returned from rotate-key — one-time raw key display."""
    device_id: str
    api_key: str


class DeviceTokenHeartbeatRequest(BaseModel):
    """Payload for the unauthenticated device-token heartbeat.

    ``device_id`` is required.  All other fields are passed through to
    the vendor adapter for normalization, so the schema accepts extras.
    """
    device_id: str
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None
    signal_dbm: Optional[int] = None
    ip_address: Optional[str] = None

    model_config = {"extra": "allow"}


class DeviceTokenHeartbeatResponse(BaseModel):
    ok: bool = True
    device_id: str
    next_heartbeat_seconds: int
