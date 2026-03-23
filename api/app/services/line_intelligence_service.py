"""
Line Intelligence platform service — bridges the engine to True911.

Handles:
- Tenant-scoped classification requests
- Event logging to the line_intelligence_events table
- Port state tracking in the port_states table
- Feature flag gating

This service does NOT import any hardware or SIP dependencies.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.line_intelligence_event import LineIntelligenceEvent
from app.models.port_state import PortState
from app.services.line_intelligence import (
    LineIntelligenceSession,
    LineType,
    Observation,
    SessionDecision,
)
from app.services.line_intelligence.models import DtmfEvent

logger = logging.getLogger("true911.line_intelligence")


# ---------------------------------------------------------------------------
# Feature flag helper
# ---------------------------------------------------------------------------

def is_line_intelligence_enabled() -> bool:
    """Check whether the FEATURE_LINE_INTELLIGENCE flag is on."""
    return getattr(settings, "FEATURE_LINE_INTELLIGENCE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

async def classify_line(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_id: str,
    device_id: Optional[str] = None,
    site_id: Optional[str] = None,
    port_index: int = 0,
    dtmf_digits: str = "",
    fax_tone_present: bool = False,
    modem_carrier_present: bool = False,
    voice_energy_estimate: float = 0.0,
    silence_ratio: float = 0.0,
    window_duration_ms: int = 5000,
    source: str = "api",
) -> SessionDecision:
    """
    Run the Line Intelligence pipeline and persist results.

    1. Build an Observation from the provided signals
    2. Run detection → classification → profile assignment
    3. Log a LineIntelligenceEvent
    4. Upsert PortState for this device/port
    5. Return the SessionDecision
    """
    # Build observation
    observation_id = f"obs-{uuid.uuid4().hex[:12]}"
    dtmf_events = [
        DtmfEvent(digit=d, timestamp_ms=i * 100, duration_ms=50)
        for i, d in enumerate(dtmf_digits)
    ]
    observation = Observation(
        observation_id=observation_id,
        line_id=line_id,
        tenant_id=tenant_id,
        site_id=site_id,
        device_id=device_id,
        dtmf_events=dtmf_events,
        fax_tone_present=fax_tone_present,
        modem_carrier_present=modem_carrier_present,
        voice_energy_estimate=voice_energy_estimate,
        silence_ratio=silence_ratio,
        window_duration_ms=window_duration_ms,
        source=source,
    )

    # Run pipeline
    session = LineIntelligenceSession()
    decision = session.process(observation)

    # Log event
    cls = decision.classification
    event_type = "li.override" if decision.manual_override else (
        "li.fallback" if cls.fallback_applied else "li.classification"
    )
    await _log_event(
        db,
        tenant_id=tenant_id,
        event_type=event_type,
        line_id=line_id,
        device_id=device_id,
        site_id=site_id,
        port_index=port_index,
        classified_type=cls.line_type.value,
        confidence_score=cls.confidence_score,
        confidence_tier=cls.confidence_tier.value,
        profile_id=decision.assigned_profile.profile_id,
        message=f"Classified as {cls.line_type.value} "
                f"(confidence={cls.confidence_score:.2f})",
        metadata={
            "observation_id": observation_id,
            "decision_id": decision.decision_id,
            "evidence": [e.model_dump() for e in cls.evidence],
            "source": source,
        },
    )

    # Upsert port state
    await _upsert_port_state(
        db,
        tenant_id=tenant_id,
        device_id=device_id or line_id,
        line_id=line_id,
        site_id=site_id,
        port_index=port_index,
        decision=decision,
        observation_id=observation_id,
    )

    await db.commit()
    return decision


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

async def get_status(db: AsyncSession, tenant_id: str) -> dict:
    """Return a summary status for the tenant's line intelligence."""
    port_count = await db.scalar(
        select(func.count()).select_from(PortState).where(
            PortState.tenant_id == tenant_id
        )
    ) or 0

    event_count = await db.scalar(
        select(func.count()).select_from(LineIntelligenceEvent).where(
            LineIntelligenceEvent.tenant_id == tenant_id
        )
    ) or 0

    # Classification breakdown from port_states
    rows = (await db.execute(
        select(PortState.classified_type, func.count())
        .where(PortState.tenant_id == tenant_id)
        .group_by(PortState.classified_type)
    )).all()
    summary = {r[0]: r[1] for r in rows}

    return {
        "enabled": is_line_intelligence_enabled(),
        "pipeline_version": "1.0.0",
        "total_ports_tracked": port_count,
        "total_events": event_count,
        "classification_summary": summary,
    }


async def list_port_states(
    db: AsyncSession,
    tenant_id: str,
    *,
    device_id: Optional[str] = None,
    site_id: Optional[str] = None,
    limit: int = 100,
) -> list[PortState]:
    """List port states for a tenant, with optional filters."""
    q = select(PortState).where(PortState.tenant_id == tenant_id)
    if device_id:
        q = q.where(PortState.device_id == device_id)
    if site_id:
        q = q.where(PortState.site_id == site_id)
    q = q.order_by(PortState.updated_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def list_events(
    db: AsyncSession,
    tenant_id: str,
    *,
    event_type: Optional[str] = None,
    line_id: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 100,
) -> list[LineIntelligenceEvent]:
    """List line intelligence events for a tenant."""
    q = select(LineIntelligenceEvent).where(
        LineIntelligenceEvent.tenant_id == tenant_id
    )
    if event_type:
        q = q.where(LineIntelligenceEvent.event_type == event_type)
    if line_id:
        q = q.where(LineIntelligenceEvent.line_id == line_id)
    if device_id:
        q = q.where(LineIntelligenceEvent.device_id == device_id)
    q = q.order_by(LineIntelligenceEvent.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _log_event(
    db: AsyncSession,
    *,
    tenant_id: str,
    event_type: str,
    line_id: Optional[str],
    device_id: Optional[str],
    site_id: Optional[str],
    port_index: Optional[int],
    classified_type: Optional[str],
    confidence_score: Optional[float],
    confidence_tier: Optional[str],
    profile_id: Optional[str],
    message: Optional[str],
    severity: str = "info",
    metadata: Optional[dict] = None,
) -> None:
    """Insert an immutable line intelligence event."""
    event = LineIntelligenceEvent(
        event_id=f"li-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        event_type=event_type,
        line_id=line_id,
        device_id=device_id,
        site_id=site_id,
        port_index=port_index,
        classified_type=classified_type,
        confidence_score=confidence_score,
        confidence_tier=confidence_tier,
        profile_id=profile_id,
        severity=severity,
        message=message,
        metadata_json=metadata,
    )
    db.add(event)


async def _upsert_port_state(
    db: AsyncSession,
    *,
    tenant_id: str,
    device_id: str,
    line_id: Optional[str],
    site_id: Optional[str],
    port_index: int,
    decision: SessionDecision,
    observation_id: str,
) -> None:
    """Create or update the port state row for this device/port."""
    q = select(PortState).where(
        PortState.tenant_id == tenant_id,
        PortState.device_id == device_id,
        PortState.port_index == port_index,
    )
    result = await db.execute(q)
    ps = result.scalar_one_or_none()

    cls = decision.classification
    now = datetime.now(timezone.utc)

    if ps is None:
        ps = PortState(
            tenant_id=tenant_id,
            device_id=device_id,
            line_id=line_id,
            site_id=site_id,
            port_index=port_index,
            classified_type=cls.line_type.value,
            confidence_score=cls.confidence_score,
            confidence_tier=cls.confidence_tier.value,
            profile_id=decision.assigned_profile.profile_id,
            profile_name=decision.assigned_profile.profile_name,
            manual_override=decision.manual_override,
            override_reason=decision.override_reason,
            last_observation_id=observation_id,
            observation_count=1,
            last_observed_at=now,
        )
        db.add(ps)
    else:
        ps.classified_type = cls.line_type.value
        ps.confidence_score = cls.confidence_score
        ps.confidence_tier = cls.confidence_tier.value
        ps.profile_id = decision.assigned_profile.profile_id
        ps.profile_name = decision.assigned_profile.profile_name
        ps.manual_override = decision.manual_override
        ps.override_reason = decision.override_reason
        ps.last_observation_id = observation_id
        ps.observation_count = (ps.observation_count or 0) + 1
        ps.last_observed_at = now
        if line_id:
            ps.line_id = line_id
        if site_id:
            ps.site_id = site_id
