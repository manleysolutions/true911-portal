from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    rule_name: Mapped[str] = mapped_column(String(255))
    rule_type: Mapped[str] = mapped_column(String(100))
    threshold_value: Mapped[float] = mapped_column(Float)
    threshold_unit: Mapped[str] = mapped_column(String(50))
    scope: Mapped[str] = mapped_column(String(100))
    channels: Mapped[list] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    escalation_steps: Mapped[list] = mapped_column(JSONB, default=list)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
