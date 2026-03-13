from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ServiceUnitOut(BaseModel):
    id: int
    tenant_id: str
    site_id: str
    unit_id: str
    unit_name: str
    unit_type: str
    location_description: Optional[str] = None
    floor: Optional[str] = None
    install_type: Optional[str] = None
    # Capabilities
    voice_supported: bool = True
    video_supported: bool = False
    text_supported: bool = False
    visual_messaging_supported: bool = False
    onsite_takeover_supported: bool = False
    backup_power_supported: bool = False
    monitoring_station_type: Optional[str] = None
    # Compliance
    compliance_status: Optional[str] = None
    compliance_notes: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    governing_code_edition: Optional[str] = None
    compliance_last_reviewed_at: Optional[datetime] = None
    # Video readiness
    camera_present: bool = False
    video_stream_url: Optional[str] = None
    video_transport_type: Optional[str] = None
    video_encryption: Optional[str] = None
    video_retained: bool = False
    video_operator_visible: bool = False
    # Linkage
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    sim_id: Optional[int] = None
    # Status
    status: str = "active"
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ServiceUnitCreate(BaseModel):
    site_id: str
    unit_id: str
    unit_name: str
    unit_type: str
    location_description: Optional[str] = None
    floor: Optional[str] = None
    install_type: Optional[str] = None
    # Capabilities
    voice_supported: bool = True
    video_supported: bool = False
    text_supported: bool = False
    visual_messaging_supported: bool = False
    onsite_takeover_supported: bool = False
    backup_power_supported: bool = False
    monitoring_station_type: Optional[str] = None
    # Compliance
    jurisdiction_code: Optional[str] = None
    governing_code_edition: Optional[str] = None
    compliance_notes: Optional[str] = None
    # Video readiness
    camera_present: bool = False
    video_transport_type: Optional[str] = None
    # Linkage
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    sim_id: Optional[int] = None
    notes: Optional[str] = None


class ServiceUnitUpdate(BaseModel):
    unit_name: Optional[str] = None
    unit_type: Optional[str] = None
    location_description: Optional[str] = None
    floor: Optional[str] = None
    install_type: Optional[str] = None
    voice_supported: Optional[bool] = None
    video_supported: Optional[bool] = None
    text_supported: Optional[bool] = None
    visual_messaging_supported: Optional[bool] = None
    onsite_takeover_supported: Optional[bool] = None
    backup_power_supported: Optional[bool] = None
    monitoring_station_type: Optional[str] = None
    compliance_status: Optional[str] = None
    compliance_notes: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    governing_code_edition: Optional[str] = None
    camera_present: Optional[bool] = None
    video_stream_url: Optional[str] = None
    video_transport_type: Optional[str] = None
    video_encryption: Optional[str] = None
    video_retained: Optional[bool] = None
    video_operator_visible: Optional[bool] = None
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    sim_id: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None
