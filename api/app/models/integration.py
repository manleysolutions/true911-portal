from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Integration(Base):
    """Registry of supported provider integrations (Telnyx, Vola, T-Mobile, etc.)."""
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # telnyx, vola, tmobile
    display_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))  # sip, hardware, carrier
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    docs_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrationAccount(Base):
    """Per-tenant credentials for a provider integration."""
    __tablename__ = "integration_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id"))
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
