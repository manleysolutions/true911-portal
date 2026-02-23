from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Line(Base):
    __tablename__ = "lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50))  # telnyx, tmobile, bandwidth, other
    did: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # phone number / DID
    sip_uri: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    protocol: Mapped[str] = mapped_column(String(20), default="SIP")  # SIP, POTS, cellular
    status: Mapped[str] = mapped_column(String(30), default="provisioning")  # active, provisioning, suspended, disconnected
    e911_status: Mapped[str] = mapped_column(String(20), default="none")  # pending, validated, failed, none
    e911_street: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    e911_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    e911_state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    e911_zip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
