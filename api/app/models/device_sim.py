from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeviceSim(Base):
    """Maps a SIM to a device slot. Only one active assignment per SIM and per slot."""
    __tablename__ = "device_sims"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    sim_id: Mapped[int] = mapped_column(ForeignKey("sims.id"), index=True)
    slot: Mapped[int] = mapped_column(Integer, default=1)  # 1 = primary, 2 = secondary
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unassigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
