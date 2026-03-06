from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(50))
    condition_json: Mapped[str] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(String(50))
    action_config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fire_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Phase 8 columns
    max_fires_per_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default="10")
    cooldown_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default="15")
    auto_diagnostic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    self_heal_action: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
