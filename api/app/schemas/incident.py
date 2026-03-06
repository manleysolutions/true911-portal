from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class IncidentOut(BaseModel):
    id: int
    incident_id: str
    tenant_id: str
    site_id: str
    opened_at: datetime
    severity: str
    status: str
    summary: str
    ack_by: Optional[str] = None
    ack_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    assigned_to: Optional[str] = None
    created_by: Optional[str] = None
    incident_type: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    location_detail: Optional[str] = None
    recommended_actions_json: Optional[str] = None
    metadata_json: Optional[str] = None

    model_config = {"from_attributes": True}


class IncidentCreate(BaseModel):
    incident_id: str
    site_id: str
    opened_at: datetime
    severity: str
    status: str = "open"
    summary: str
    assigned_to: Optional[str] = None
    created_by: Optional[str] = None
    incident_type: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    location_detail: Optional[str] = None
    recommended_actions_json: Optional[str] = None
    metadata_json: Optional[str] = None


class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    ack_by: Optional[str] = None
    ack_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    assigned_to: Optional[str] = None
    incident_type: Optional[str] = None
    description: Optional[str] = None
    location_detail: Optional[str] = None
    recommended_actions_json: Optional[str] = None
    metadata_json: Optional[str] = None


class IncidentCloseRequest(BaseModel):
    resolution_notes: Optional[str] = None
