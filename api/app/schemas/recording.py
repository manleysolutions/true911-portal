from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RecordingOut(BaseModel):
    id: int
    recording_id: str
    tenant_id: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    provider: str
    call_control_id: Optional[str] = None
    cdr_id: Optional[str] = None
    recording_url: Optional[str] = None
    direction: str
    duration_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    caller: Optional[str] = None
    callee: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RecordingCreate(BaseModel):
    recording_id: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    provider: str = "telnyx"
    call_control_id: Optional[str] = None
    cdr_id: Optional[str] = None
    recording_url: Optional[str] = None
    direction: str = "inbound"
    duration_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    caller: Optional[str] = None
    callee: Optional[str] = None
    status: str = "available"
