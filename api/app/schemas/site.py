from datetime import datetime
from typing import Optional

from pydantic import BaseModel

_SITE_FIELDS = {
    "last_checkin": (Optional[datetime], None),
    "e911_street": (Optional[str], None),
    "e911_city": (Optional[str], None),
    "e911_state": (Optional[str], None),
    "e911_zip": (Optional[str], None),
    "poc_name": (Optional[str], None),
    "poc_phone": (Optional[str], None),
    "poc_email": (Optional[str], None),
    "device_model": (Optional[str], None),
    "device_serial": (Optional[str], None),
    "device_firmware": (Optional[str], None),
    "kit_type": (Optional[str], None),
    "carrier": (Optional[str], None),
    "static_ip": (Optional[str], None),
    "signal_dbm": (Optional[int], None),
    "network_tech": (Optional[str], None),
    "heartbeat_frequency": (Optional[str], None),
    "heartbeat_next_due": (Optional[datetime], None),
    "lat": (Optional[float], None),
    "lng": (Optional[float], None),
    "notes": (Optional[str], None),
    "endpoint_type": (Optional[str], None),
    "service_class": (Optional[str], None),
    "last_device_heartbeat": (Optional[datetime], None),
    "last_portal_sync": (Optional[datetime], None),
    "container_version": (Optional[str], None),
    "firmware_version": (Optional[str], None),
    "csa_model": (Optional[str], None),
    "heartbeat_interval": (Optional[int], None),
    "uptime_percent": (Optional[float], None),
    "update_channel": (Optional[str], None),
}


class SiteOut(BaseModel):
    id: int
    site_id: str
    tenant_id: str
    site_name: str
    customer_name: str
    status: str
    last_checkin: Optional[datetime] = None
    e911_street: Optional[str] = None
    e911_city: Optional[str] = None
    e911_state: Optional[str] = None
    e911_zip: Optional[str] = None
    poc_name: Optional[str] = None
    poc_phone: Optional[str] = None
    poc_email: Optional[str] = None
    device_model: Optional[str] = None
    device_serial: Optional[str] = None
    device_firmware: Optional[str] = None
    kit_type: Optional[str] = None
    carrier: Optional[str] = None
    static_ip: Optional[str] = None
    signal_dbm: Optional[int] = None
    network_tech: Optional[str] = None
    heartbeat_frequency: Optional[str] = None
    heartbeat_next_due: Optional[datetime] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    notes: Optional[str] = None
    endpoint_type: Optional[str] = None
    service_class: Optional[str] = None
    last_device_heartbeat: Optional[datetime] = None
    last_portal_sync: Optional[datetime] = None
    container_version: Optional[str] = None
    firmware_version: Optional[str] = None
    csa_model: Optional[str] = None
    heartbeat_interval: Optional[int] = None
    uptime_percent: Optional[float] = None
    update_channel: Optional[str] = None
    computed_status: Optional[str] = None

    model_config = {"from_attributes": True}


class SiteCreate(BaseModel):
    site_id: str
    site_name: str
    customer_name: str
    status: str
    last_checkin: Optional[datetime] = None
    e911_street: Optional[str] = None
    e911_city: Optional[str] = None
    e911_state: Optional[str] = None
    e911_zip: Optional[str] = None
    poc_name: Optional[str] = None
    poc_phone: Optional[str] = None
    poc_email: Optional[str] = None
    device_model: Optional[str] = None
    device_serial: Optional[str] = None
    device_firmware: Optional[str] = None
    kit_type: Optional[str] = None
    carrier: Optional[str] = None
    static_ip: Optional[str] = None
    signal_dbm: Optional[int] = None
    network_tech: Optional[str] = None
    heartbeat_frequency: Optional[str] = None
    heartbeat_next_due: Optional[datetime] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    notes: Optional[str] = None
    endpoint_type: Optional[str] = None
    service_class: Optional[str] = None
    last_device_heartbeat: Optional[datetime] = None
    last_portal_sync: Optional[datetime] = None
    container_version: Optional[str] = None
    firmware_version: Optional[str] = None
    csa_model: Optional[str] = None
    heartbeat_interval: Optional[int] = None
    uptime_percent: Optional[float] = None
    update_channel: Optional[str] = None


class SiteUpdate(BaseModel):
    site_name: Optional[str] = None
    customer_name: Optional[str] = None
    status: Optional[str] = None
    last_checkin: Optional[datetime] = None
    e911_street: Optional[str] = None
    e911_city: Optional[str] = None
    e911_state: Optional[str] = None
    e911_zip: Optional[str] = None
    poc_name: Optional[str] = None
    poc_phone: Optional[str] = None
    poc_email: Optional[str] = None
    device_model: Optional[str] = None
    device_serial: Optional[str] = None
    device_firmware: Optional[str] = None
    kit_type: Optional[str] = None
    carrier: Optional[str] = None
    static_ip: Optional[str] = None
    signal_dbm: Optional[int] = None
    network_tech: Optional[str] = None
    heartbeat_frequency: Optional[str] = None
    heartbeat_next_due: Optional[datetime] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    notes: Optional[str] = None
    endpoint_type: Optional[str] = None
    service_class: Optional[str] = None
    last_device_heartbeat: Optional[datetime] = None
    last_portal_sync: Optional[datetime] = None
    container_version: Optional[str] = None
    firmware_version: Optional[str] = None
    csa_model: Optional[str] = None
    heartbeat_interval: Optional[int] = None
    uptime_percent: Optional[float] = None
    update_channel: Optional[str] = None
