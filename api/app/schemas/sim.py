from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SimOut(BaseModel):
    id: int
    tenant_id: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    iccid: str
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    imei: Optional[str] = None
    carrier: str
    status: str
    activation_status: Optional[str] = None
    network_status: Optional[str] = None
    plan: Optional[str] = None
    apn: Optional[str] = None
    provider_sim_id: Optional[str] = None
    carrier_label: Optional[str] = None
    data_source: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    inferred_lat: Optional[float] = None
    inferred_lng: Optional[float] = None
    inferred_location_source: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SimCreate(BaseModel):
    iccid: str
    carrier: str
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    imei: Optional[str] = None
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    status: str = "inventory"
    plan: Optional[str] = None
    apn: Optional[str] = None
    provider_sim_id: Optional[str] = None
    notes: Optional[str] = None


class SimUpdate(BaseModel):
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    imei: Optional[str] = None
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    carrier: Optional[str] = None
    status: Optional[str] = None
    plan: Optional[str] = None
    apn: Optional[str] = None
    provider_sim_id: Optional[str] = None
    notes: Optional[str] = None


class SimAssign(BaseModel):
    device_id: int
    slot: int = 1


class SimBulkSiteAssign(BaseModel):
    sim_ids: list[int]
    site_id: str


class SimActionOut(BaseModel):
    sim_id: int
    action: str
    job_id: Optional[int] = None
    message: str
