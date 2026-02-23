from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TelemetryEventOut(BaseModel):
    id: int
    event_id: str
    site_id: str
    tenant_id: str
    timestamp: datetime
    category: str
    severity: str
    message: str
    raw_json: Optional[str] = None

    model_config = {"from_attributes": True}


class TelemetryEventCreate(BaseModel):
    event_id: str
    site_id: str
    timestamp: datetime
    category: str
    severity: str
    message: str
    raw_json: Optional[str] = None
