from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HardwareModelOut(BaseModel):
    id: str
    manufacturer: str
    model_name: str
    device_type: str
    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class HardwareModelCreate(BaseModel):
    id: str
    manufacturer: str
    model_name: str
    device_type: str
    is_active: bool = True


class HardwareModelUpdate(BaseModel):
    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    device_type: Optional[str] = None
    is_active: Optional[bool] = None
