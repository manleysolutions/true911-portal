from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CallRecordOut(BaseModel):
    id: int
    call_id: str
    tenant_id: str
    customer_id: Optional[int] = None
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    provider: str
    direction: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    did: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    cost: Optional[float] = None
    recording_id: Optional[str] = None
    telnyx_call_id: Optional[str] = None
    telnyx_cdr_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
