from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CommandActivity(Base):
    __tablename__ = "command_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    activity_type: Mapped[str] = mapped_column(String(50))
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    incident_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
