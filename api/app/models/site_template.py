from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SiteTemplate(Base):
    __tablename__ = "site_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("tenants.tenant_id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    building_type: Mapped[str] = mapped_column(String(100))
    systems_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_tasks_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    monitoring_rules_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    readiness_weights_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_global: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
