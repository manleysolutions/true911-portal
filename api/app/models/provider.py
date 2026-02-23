from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    provider_type: Mapped[str] = mapped_column(String(50))  # telnyx, tmobile, napco, bandwidth, verizon, teal
    display_name: Mapped[str] = mapped_column(String(255))
    api_key_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # reference only, NOT the key
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
