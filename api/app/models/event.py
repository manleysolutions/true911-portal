from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    # event_type values: device.heartbeat, device.registered, device.offline,
    # line.registered, line.down, e911.updated, e911.validated,
    # alert.triggered, call.started, call.completed, recording.available, system.info
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")  # critical, warning, info
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
