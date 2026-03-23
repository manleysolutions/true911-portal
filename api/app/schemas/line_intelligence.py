"""Pydantic schemas for Line Intelligence API endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class LineIntelligenceStatusOut(BaseModel):
    """GET /api/line-intelligence/status response."""

    enabled: bool
    pipeline_version: str
    total_ports_tracked: int
    total_events: int
    classification_summary: dict[str, int]  # line_type → count


class PortStateOut(BaseModel):
    """Single port state in list responses."""

    id: int
    tenant_id: str
    device_id: str
    line_id: Optional[str] = None
    site_id: Optional[str] = None
    port_index: int
    classified_type: str
    confidence_score: float
    confidence_tier: str
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    manual_override: bool = False
    override_reason: Optional[str] = None
    observation_count: int = 0
    last_observed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LineIntelligenceEventOut(BaseModel):
    """Single event in list responses."""

    id: int
    event_id: str
    tenant_id: str
    event_type: str
    line_id: Optional[str] = None
    device_id: Optional[str] = None
    site_id: Optional[str] = None
    port_index: Optional[int] = None
    classified_type: Optional[str] = None
    confidence_score: Optional[float] = None
    confidence_tier: Optional[str] = None
    profile_id: Optional[str] = None
    severity: str = "info"
    message: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProtocolProfileOut(BaseModel):
    """Protocol profile summary for API responses."""

    profile_id: str
    profile_name: str
    line_type: str
    codec_preference: str
    dtmf_mode: str
    jitter_strategy: str
    gain_profile: str
    echo_cancellation: str
    t38_enabled: bool
    passthrough_enabled: bool
    silence_suppression: bool
    vad_enabled: bool
    notes: list[str] = []


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ClassifyRequest(BaseModel):
    """POST /api/line-intelligence/classify — submit an observation."""

    line_id: str
    device_id: Optional[str] = None
    site_id: Optional[str] = None
    port_index: int = 0

    # Signal inputs (normalized)
    dtmf_digits: str = ""
    fax_tone_present: bool = False
    modem_carrier_present: bool = False
    voice_energy_estimate: float = 0.0
    silence_ratio: float = 0.0
    window_duration_ms: int = 5000
    source: str = "api"
