from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CommandIncidentTransition(BaseModel):
    """Body for incident status transitions."""
    resolution_notes: Optional[str] = None
    assigned_to: Optional[str] = None


class CommandIncidentCreate(BaseModel):
    """Create a new command incident."""
    site_id: str
    summary: str
    severity: str = "warning"
    incident_type: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    location_detail: Optional[str] = None
    assigned_to: Optional[str] = None
    recommended_actions_json: Optional[str] = None
    metadata_json: Optional[str] = None


class CommandActivityOut(BaseModel):
    id: int
    tenant_id: str
    activity_type: str
    site_id: Optional[str] = None
    incident_id: Optional[str] = None
    actor: Optional[str] = None
    summary: str
    detail: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
