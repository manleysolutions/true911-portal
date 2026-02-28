from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IntegrationStatus(Base):
    """Tracks the last-known sync status between a resource and a provider."""
    __tablename__ = "integration_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id"))
    resource_type: Mapped[str] = mapped_column(String(50))  # sim, device, line
    resource_id: Mapped[str] = mapped_column(String(100), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50))  # synced, pending, error
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
