from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActionAudit(Base):
    __tablename__ = "action_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    request_id: Mapped[str] = mapped_column(String(50), index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    user_email: Mapped[str] = mapped_column(String(255))
    requester_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50))
    action_type: Mapped[str] = mapped_column(String(50))
    site_id: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[str] = mapped_column(String(20))
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
