from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CommandTelemetry(Base):
    __tablename__ = "command_telemetry"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    device_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    signal_strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    battery_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default="0")
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
