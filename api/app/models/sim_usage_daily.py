from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SimUsageDaily(Base):
    """Daily data usage aggregates per SIM — populated by polling jobs."""
    __tablename__ = "sim_usage_daily"

    id: Mapped[int] = mapped_column(primary_key=True)
    sim_id: Mapped[int] = mapped_column(ForeignKey("sims.id"), index=True)
    usage_date: Mapped[date] = mapped_column(Date, index=True)
    bytes_up: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_down: Mapped[int] = mapped_column(BigInteger, default=0)
    sms_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
