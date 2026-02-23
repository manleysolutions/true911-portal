from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class E911ChangeLog(Base):
    __tablename__ = "e911_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    requested_by: Mapped[str] = mapped_column(String(255))
    requester_name: Mapped[str] = mapped_column(String(255))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    old_street: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    old_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    old_zip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    new_street: Mapped[str] = mapped_column(String(500))
    new_city: Mapped[str] = mapped_column(String(100))
    new_state: Mapped[str] = mapped_column(String(10))
    new_zip: Mapped[str] = mapped_column(String(20))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50))
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
