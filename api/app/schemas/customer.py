from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CustomerCreate(BaseModel):
    name: str
    billing_email: Optional[str] = None
    billing_phone: Optional[str] = None
    billing_address: Optional[str] = None
    status: str = "active"


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    billing_email: Optional[str] = None
    billing_phone: Optional[str] = None
    billing_address: Optional[str] = None
    status: Optional[str] = None


class CustomerOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    billing_email: Optional[str] = None
    billing_phone: Optional[str] = None
    billing_address: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
