from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SimEvent(Base):
    """Immutable log of SIM lifecycle events (activate, suspend, etc.)."""
    __tablename__ = "sim_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    sim_id: Mapped[int] = mapped_column(ForeignKey("sims.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))  # activate, suspend, resume, terminate, plan_change
    status_before: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status_after: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    initiated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
