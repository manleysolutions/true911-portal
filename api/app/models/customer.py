from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    """Billing customer / account — synced from Zoho CRM or manual entry."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    customer_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    billing_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    billing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")

    # ── Zoho CRM linkage ─────────────────────────────────────────
    zoho_account_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    zoho_contact_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zoho_deal_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zoho_sync_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # synced | error | pending
    zoho_last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Onboarding ───────────────────────────────────────────────
    onboarding_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="pending")
    # pending | in_progress | complete | on_hold

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
