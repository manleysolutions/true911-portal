from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LineOut(BaseModel):
    id: int
    line_id: str
    tenant_id: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    provider: str
    did: Optional[str] = None
    sip_uri: Optional[str] = None
    protocol: str
    status: str
    e911_status: str
    e911_street: Optional[str] = None
    e911_city: Optional[str] = None
    e911_state: Optional[str] = None
    e911_zip: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LineCreate(BaseModel):
    line_id: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    provider: str = "telnyx"
    did: Optional[str] = None
    sip_uri: Optional[str] = None
    protocol: str = "SIP"
    status: str = "provisioning"
    e911_status: str = "none"
    e911_street: Optional[str] = None
    e911_city: Optional[str] = None
    e911_state: Optional[str] = None
    e911_zip: Optional[str] = None
    notes: Optional[str] = None


class LineUpdate(BaseModel):
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    provider: Optional[str] = None
    did: Optional[str] = None
    sip_uri: Optional[str] = None
    protocol: Optional[str] = None
    status: Optional[str] = None
    e911_status: Optional[str] = None
    e911_street: Optional[str] = None
    e911_city: Optional[str] = None
    e911_state: Optional[str] = None
    e911_zip: Optional[str] = None
    notes: Optional[str] = None
