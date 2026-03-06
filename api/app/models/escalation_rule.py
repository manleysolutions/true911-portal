from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EscalationRule(Base):
    __tablename__ = "escalation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(20))
    escalate_after_minutes: Mapped[int] = mapped_column(Integer, server_default="30")
    escalation_target: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notify_channel: Mapped[str] = mapped_column(String(20), server_default="in_app")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Phase 8 columns
    tier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notify_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notify_sms: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    auto_assign_vendor: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
