from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IntegrationPayload(Base):
    """Raw webhook/API payloads persisted for audit and replay."""
    __tablename__ = "integration_payloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    payload_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)  # telnyx, vola, tmobile
    direction: Mapped[str] = mapped_column(String(10))  # inbound (webhook), outbound (api call)
    headers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    body: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    raw_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
