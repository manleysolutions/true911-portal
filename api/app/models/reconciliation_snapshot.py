from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReconciliationSnapshot(Base):
    """Point-in-time reconciliation result comparing deployed vs billed vs subscriptions."""
    __tablename__ = "reconciliation_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(String(100), index=True)
    total_customers: Mapped[int] = mapped_column(Integer, default=0)
    total_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    total_billed_lines: Mapped[int] = mapped_column(Integer, default=0)
    total_deployed_lines: Mapped[int] = mapped_column(Integer, default=0)
    mismatches_count: Mapped[int] = mapped_column(Integer, default=0)
    results_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
