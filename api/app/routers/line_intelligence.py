"""
Line Intelligence API endpoints.

All endpoints are gated behind FEATURE_LINE_INTELLIGENCE and require
standard JWT authentication with tenant isolation.

Endpoints:
    GET  /api/line-intelligence/status   — engine status + summary
    GET  /api/line-intelligence/ports    — per-port state list
    GET  /api/line-intelligence/events   — event audit log
    GET  /api/line-intelligence/profiles — available protocol profiles
    POST /api/line-intelligence/classify — submit observation for classification
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.line_intelligence import (
    ClassifyRequest,
    LineIntelligenceEventOut,
    LineIntelligenceStatusOut,
    PortStateOut,
    ProtocolProfileOut,
)
from app.services import line_intelligence_service as li_svc
from app.services.line_intelligence.protocol_profiles import get_all_profiles

router = APIRouter()


def _require_feature() -> None:
    """Raise 404 if Line Intelligence is not enabled."""
    if not li_svc.is_line_intelligence_enabled():
        raise HTTPException(
            status_code=404,
            detail="Line Intelligence is not enabled. "
                   "Set FEATURE_LINE_INTELLIGENCE=true to activate.",
        )


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=LineIntelligenceStatusOut)
async def get_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return Line Intelligence engine status and classification summary."""
    _require_feature()
    return await li_svc.get_status(db, current_user.tenant_id)


# ---------------------------------------------------------------------------
# GET /ports
# ---------------------------------------------------------------------------

@router.get("/ports", response_model=list[PortStateOut])
async def list_ports(
    device_id: str | None = None,
    site_id: str | None = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List per-port intelligence state for the tenant."""
    _require_feature()
    rows = await li_svc.list_port_states(
        db,
        current_user.tenant_id,
        device_id=device_id,
        site_id=site_id,
        limit=limit,
    )
    return [PortStateOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /events
# ---------------------------------------------------------------------------

@router.get("/events", response_model=list[LineIntelligenceEventOut])
async def list_events(
    event_type: str | None = None,
    line_id: str | None = None,
    device_id: str | None = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List line intelligence events (classification, adaptation, failure)."""
    _require_feature()
    rows = await li_svc.list_events(
        db,
        current_user.tenant_id,
        event_type=event_type,
        line_id=line_id,
        device_id=device_id,
        limit=limit,
    )
    return [LineIntelligenceEventOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /profiles
# ---------------------------------------------------------------------------

@router.get("/profiles", response_model=list[ProtocolProfileOut])
async def list_profiles(
    current_user: User = Depends(get_current_user),
):
    """List all available protocol profiles."""
    _require_feature()
    profiles = get_all_profiles()
    return [
        ProtocolProfileOut(
            profile_id=p.profile_id,
            profile_name=p.profile_name,
            line_type=p.line_type.value,
            codec_preference=p.codec_preference.value,
            dtmf_mode=p.dtmf_mode.value,
            jitter_strategy=p.jitter_strategy.value,
            gain_profile=p.gain_profile.value,
            echo_cancellation=p.echo_cancellation.value,
            t38_enabled=p.t38_enabled,
            passthrough_enabled=p.passthrough_enabled,
            silence_suppression=p.silence_suppression,
            vad_enabled=p.vad_enabled,
            notes=p.notes,
        )
        for p in profiles.values()
    ]


# ---------------------------------------------------------------------------
# POST /classify
# ---------------------------------------------------------------------------

@router.post("/classify")
async def classify(
    body: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a line observation for classification.

    Returns the full classification decision including line type,
    confidence, evidence, and assigned protocol profile.
    """
    _require_feature()
    decision = await li_svc.classify_line(
        db,
        tenant_id=current_user.tenant_id,
        line_id=body.line_id,
        device_id=body.device_id,
        site_id=body.site_id,
        port_index=body.port_index,
        dtmf_digits=body.dtmf_digits,
        fax_tone_present=body.fax_tone_present,
        modem_carrier_present=body.modem_carrier_present,
        voice_energy_estimate=body.voice_energy_estimate,
        silence_ratio=body.silence_ratio,
        window_duration_ms=body.window_duration_ms,
        source=body.source,
    )
    return {
        "decision_id": decision.decision_id,
        "line_id": decision.line_id,
        "classification": {
            "line_type": decision.classification.line_type.value,
            "confidence_score": decision.classification.confidence_score,
            "confidence_tier": decision.classification.confidence_tier.value,
            "is_actionable": decision.classification.is_actionable,
            "fallback_applied": decision.classification.fallback_applied,
            "evidence": [e.model_dump() for e in decision.classification.evidence],
        },
        "assigned_profile": {
            "profile_id": decision.assigned_profile.profile_id,
            "profile_name": decision.assigned_profile.profile_name,
            "line_type": decision.assigned_profile.line_type.value,
        },
        "manual_override": decision.manual_override,
        "pipeline_version": decision.pipeline_version,
    }
