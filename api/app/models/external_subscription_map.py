from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ExternalSubscriptionMap(Base):
    """Maps an external billing subscription ID to a True911 subscription."""
    __tablename__ = "external_subscription_map"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(50))  # zoho, qb
    external_subscription_id: Mapped[str] = mapped_column(String(255))
    true911_subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
