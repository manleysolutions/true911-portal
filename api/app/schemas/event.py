from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EventOut(BaseModel):
    id: int
    event_id: str
    tenant_id: str
    event_type: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    severity: str
    message: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EventCreate(BaseModel):
    event_id: str
    event_type: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    severity: str = "info"
    message: Optional[str] = None
    metadata_json: Optional[dict] = None
