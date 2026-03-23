"""
Line Intelligence Engine — Data models.

All models are plain Pydantic v2 models (no ORM dependency).
Persistence is handled separately via the persistence abstraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .constants import (
    CodecPreference,
    Confidence,
    DtmfMode,
    EchoCancellation,
    GainProfile,
    JitterStrategy,
    LineType,
)


# ---------------------------------------------------------------------------
# Observation — normalized input from hardware / integration layer
# ---------------------------------------------------------------------------

class DtmfEvent(BaseModel):
    """A single DTMF digit detection event."""

    digit: str = Field(..., max_length=1, description="Detected digit (0-9, A-D, *, #)")
    timestamp_ms: int = Field(..., ge=0, description="Milliseconds since observation window start")
    duration_ms: int = Field(0, ge=0, description="Tone duration in milliseconds")
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class Observation(BaseModel):
    """
    Normalized observation snapshot from a line or port.

    Produced by hardware adapters, SIP monitors, or manual test rigs.
    The detection/classification pipeline consumes these — never raw hardware.
    """

    observation_id: str = Field(..., description="Unique ID for this observation")
    line_id: str = Field(..., description="Identifier of the line/port being observed")
    tenant_id: str = Field(..., description="Tenant scope")
    site_id: Optional[str] = Field(None, description="Optional site association")
    device_id: Optional[str] = Field(None, description="Optional device association")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Detection signals
    dtmf_events: list[DtmfEvent] = Field(default_factory=list)
    fax_tone_present: bool = Field(False)
    modem_carrier_present: bool = Field(False)
    voice_energy_estimate: float = Field(0.0, ge=0.0, le=1.0,
                                         description="Normalized 0-1 voice energy")
    silence_ratio: float = Field(0.0, ge=0.0, le=1.0,
                                 description="Fraction of window that is silence")

    # Timing
    window_duration_ms: int = Field(5000, ge=0,
                                    description="Observation window length in ms")
    capture_start: Optional[datetime] = None
    capture_end: Optional[datetime] = None

    # Metadata
    source: str = Field("unknown", description="Source adapter or integration name")
    raw_metadata: dict = Field(default_factory=dict,
                               description="Pass-through metadata from source")


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    """A single piece of evidence supporting a classification."""

    signal: str = Field(..., description="Signal name (e.g. 'dtmf_pattern')")
    value: str = Field(..., description="Observed value or description")
    weight: float = Field(0.0, description="Contribution to confidence score")


class ClassificationResult(BaseModel):
    """Output of the classifier for a single observation or session."""

    line_type: LineType = LineType.UNKNOWN
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    confidence_tier: Confidence = Confidence.NONE
    evidence: list[EvidenceItem] = Field(default_factory=list)
    recommended_profile_id: Optional[str] = None
    is_actionable: bool = Field(False,
                                description="True if confidence meets threshold for action")
    fallback_applied: bool = Field(False,
                                   description="True if a safe fallback was used")
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol profile
# ---------------------------------------------------------------------------

class RetryStrategy(BaseModel):
    """Retry / failover configuration for a protocol profile."""

    max_retries: int = Field(3, ge=0)
    backoff_seconds: float = Field(2.0, ge=0.0)
    failover_codec: Optional[CodecPreference] = None


class ProtocolProfile(BaseModel):
    """
    Optimal protocol settings for a classified line type.

    These map to ATA / SIP gateway parameters that can later be pushed
    via TR-069 (VOLA) or similar.
    """

    profile_id: str
    profile_name: str
    line_type: LineType
    codec_preference: CodecPreference = CodecPreference.G711_ULAW
    dtmf_mode: DtmfMode = DtmfMode.RFC2833
    jitter_strategy: JitterStrategy = JitterStrategy.ADAPTIVE
    gain_profile: GainProfile = GainProfile.DEFAULT
    echo_cancellation: EchoCancellation = EchoCancellation.ENABLED
    retry_strategy: RetryStrategy = Field(default_factory=RetryStrategy)
    t38_enabled: bool = Field(False, description="Enable T.38 fax relay")
    passthrough_enabled: bool = Field(False, description="Enable codec passthrough")
    silence_suppression: bool = Field(True)
    vad_enabled: bool = Field(True, description="Voice activity detection")
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Session decision — full pipeline output
# ---------------------------------------------------------------------------

class SessionDecision(BaseModel):
    """
    Complete output of a Line Intelligence session.

    Captures the full pipeline: observation → detection → classification
    → profile assignment → decision.
    """

    decision_id: str
    line_id: str
    tenant_id: str
    observation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    classification: ClassificationResult
    assigned_profile: ProtocolProfile
    manual_override: bool = Field(False,
                                  description="True if a human override was applied")
    override_reason: Optional[str] = None
    pipeline_version: str = Field("1.0.0")
