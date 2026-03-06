from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CommandNotification(Base):
    __tablename__ = "command_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    channel: Mapped[str] = mapped_column(String(20), server_default="in_app")
    severity: Mapped[str] = mapped_column(String(20), server_default="info")
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    incident_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_user: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, server_default="false")
    read_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
