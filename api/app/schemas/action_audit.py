from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActionAuditOut(BaseModel):
    id: int
    audit_id: str
    request_id: str
    tenant_id: str
    user_email: str
    requester_name: Optional[str] = None
    role: str
    action_type: str
    site_id: Optional[str] = None
    timestamp: datetime
    result: str
    details: Optional[str] = None

    model_config = {"from_attributes": True}


class ActionAuditCreate(BaseModel):
    audit_id: str
    request_id: str
    user_email: str
    requester_name: Optional[str] = None
    role: str
    action_type: str
    site_id: Optional[str] = None
    timestamp: datetime
    result: str
    details: Optional[str] = None
