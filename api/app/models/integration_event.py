from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IntegrationEvent(Base):
    """Inbound webhook events from Zoho CRM, QuickBooks, etc.

    Every webhook delivery is persisted here for audit and replay.
    Idempotency is enforced via unique constraint on (source, idempotency_key).
    """
    __tablename__ = "integration_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)  # zoho, qb
    event_type: Mapped[str] = mapped_column(String(100), index=True)  # customer_upsert, subscription_upsert, ...
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(30), default="received")  # received, processing, processed, failed, needs_mapping
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
