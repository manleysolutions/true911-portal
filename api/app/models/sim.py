from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Sim(Base):
    """SIM card inventory — tracks ICCID, MSISDN, IMSI and lifecycle state."""
    __tablename__ = "sims"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    iccid: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    msisdn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    imsi: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    carrier: Mapped[str] = mapped_column(String(50))  # tmobile, telnyx, verizon, att, teal
    status: Mapped[str] = mapped_column(String(30), default="inventory")  # inventory, active, suspended, terminated
    plan: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    apn: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provider_sim_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
