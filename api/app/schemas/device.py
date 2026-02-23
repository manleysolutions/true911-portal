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
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None
    provision_code: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    heartbeat_interval: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None
    provision_code: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    heartbeat_interval: Optional[int] = None
    notes: Optional[str] = None


class DeviceHeartbeatRequest(BaseModel):
    """Payload from a device checking in."""
    firmware_version: Optional[str] = None
    container_version: Optional[str] = None
