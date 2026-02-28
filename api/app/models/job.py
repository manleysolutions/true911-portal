from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Job(Base):
    """Async job tracking — mirrors RQ job state in the database for visibility."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(100), index=True)  # sim.activate, webhook.telnyx, etc.
    queue: Mapped[str] = mapped_column(String(50), default="default")  # default, provisioning, polling
    status: Mapped[str] = mapped_column(String(30), default="queued")  # queued, running, completed, failed
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
