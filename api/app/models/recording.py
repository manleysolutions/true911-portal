from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50))  # telnyx, tmobile, other
    call_control_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cdr_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    recording_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), default="inbound")  # inbound, outbound
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    caller: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    callee: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="available")  # available, pending, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
