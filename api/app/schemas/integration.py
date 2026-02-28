from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class IntegrationOut(BaseModel):
    id: int
    slug: str
    display_name: str
    category: str
    base_url: Optional[str] = None
    docs_url: Optional[str] = None
    enabled: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IntegrationAccountOut(BaseModel):
    id: int
    tenant_id: str
    integration_id: int
    label: Optional[str] = None
    config: Optional[dict] = None
    enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IntegrationAccountCreate(BaseModel):
    integration_id: int
    label: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    config: Optional[dict] = None
    enabled: bool = True


class IntegrationAccountUpdate(BaseModel):
    label: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None
