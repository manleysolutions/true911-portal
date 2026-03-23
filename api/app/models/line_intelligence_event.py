"""
Line Intelligence event log — immutable audit trail.

Records classification decisions, profile assignments, adaptation
triggers, and failures from the Line Intelligence Engine.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LineIntelligenceEvent(Base):
    __tablename__ = "line_intelligence_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    # event_type values:
    #   li.classification       — line type determined
    #   li.profile_assigned     — protocol profile applied
    #   li.adaptation           — profile adapted after re-observation
    #   li.override             — manual operator override
    #   li.fallback             — safe fallback used (low confidence)
    #   li.failure              — pipeline error
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    port_index: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Classification output
    classified_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    profile_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
