from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ExternalCustomerMap(Base):
    """Maps an external CRM/billing account ID to a True911 customer."""
    __tablename__ = "external_customer_map"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(50))  # zoho, qb
    external_account_id: Mapped[str] = mapped_column(String(255))
    true911_customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
