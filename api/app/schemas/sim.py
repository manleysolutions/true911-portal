from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SimOut(BaseModel):
    id: int
    tenant_id: str
    iccid: str
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    carrier: str
    status: str
    plan: Optional[str] = None
    apn: Optional[str] = None
    provider_sim_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SimCreate(BaseModel):
    iccid: str
    carrier: str
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    status: str = "inventory"
    plan: Optional[str] = None
    apn: Optional[str] = None
    provider_sim_id: Optional[str] = None
    notes: Optional[str] = None


class SimUpdate(BaseModel):
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    carrier: Optional[str] = None
    status: Optional[str] = None
    plan: Optional[str] = None
    apn: Optional[str] = None
    provider_sim_id: Optional[str] = None
    notes: Optional[str] = None


class SimAssign(BaseModel):
    device_id: int
    slot: int = 1


class SimActionOut(BaseModel):
    sim_id: int
    action: str
    job_id: Optional[int] = None
    message: str
