"""
Port State — per-FXS-port intelligence state tracking.

Tracks the latest classification, assigned profile, and observation
metadata for each physical port on a device.  Designed for CSA / ATA
edge devices with multiple analog ports (e.g., FlyingVoice 2-port,
Teltonika 4-port).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortState(Base):
    __tablename__ = "port_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    device_id: Mapped[str] = mapped_column(String(50), index=True)
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    port_index: Mapped[int] = mapped_column(Integer, default=0)

    # Current classification
    classified_type: Mapped[str] = mapped_column(String(30), default="unknown")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_tier: Mapped[str] = mapped_column(String(20), default="none")

    # Assigned profile
    profile_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    profile_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Manual override
    manual_override: Mapped[bool] = mapped_column(default=False)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Observation metadata
    last_observation_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    last_observed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Extra
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
