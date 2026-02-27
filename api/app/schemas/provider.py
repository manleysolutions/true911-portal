from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProviderOut(BaseModel):
    id: int
    provider_id: str
    tenant_id: str
    provider_type: str
    display_name: str
    api_key_ref: Optional[str] = None
    enabled: bool
    config_json: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProviderCreate(BaseModel):
    provider_id: str
    provider_type: str
    display_name: str
    api_key_ref: Optional[str] = None
    enabled: bool = False
    config_json: Optional[dict] = None


class ProviderUpdate(BaseModel):
    provider_type: Optional[str] = None
    display_name: Optional[str] = None
    api_key_ref: Optional[str] = None
    enabled: Optional[bool] = None
    config_json: Optional[dict] = None
