from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Subscription(Base):
    """Billing subscription — synced from Zoho/QB, linked to a customer."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, paused, cancelled, expired
    mrr: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # monthly recurring revenue
    qty_lines: Mapped[int] = mapped_column(Integer, default=0)  # billed line count
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    renewal_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    external_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    external_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # zoho, qb
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
