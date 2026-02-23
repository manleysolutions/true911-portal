from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class E911ChangeLogOut(BaseModel):
    id: int
    log_id: str
    site_id: str
    tenant_id: str
    requested_by: str
    requester_name: str
    requested_at: datetime
    old_street: Optional[str] = None
    old_city: Optional[str] = None
    old_state: Optional[str] = None
    old_zip: Optional[str] = None
    new_street: str
    new_city: str
    new_state: str
    new_zip: str
    reason: Optional[str] = None
    status: str
    applied_at: Optional[datetime] = None
    correlation_id: Optional[str] = None

    model_config = {"from_attributes": True}


class E911ChangeLogCreate(BaseModel):
    log_id: str
    site_id: str
    requested_by: str
    requester_name: str
    requested_at: datetime
    old_street: Optional[str] = None
    old_city: Optional[str] = None
    old_state: Optional[str] = None
    old_zip: Optional[str] = None
    new_street: str
    new_city: str
    new_state: str
    new_zip: str
    reason: Optional[str] = None
    status: str = "applied"
    applied_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
