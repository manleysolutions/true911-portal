"""Provisioning Queue — tracks unlinked infrastructure awaiting site assignment.

Each queue item represents a SIM, device, or line that needs operator review
to be properly linked into the site hierarchy.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProvisioningQueueItem(Base):
    __tablename__ = "provisioning_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)

    # ── What is this item? ───────────────────────────────────────
    item_type: Mapped[str] = mapped_column(String(30), index=True)
    # sim | device | line
    item_id: Mapped[int] = mapped_column(Integer, index=True)  # FK to sims.id, devices.id, or lines.id
    external_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # human-readable ref: ICCID for SIM, device_id for device, DID for line

    # ── Source ───────────────────────────────────────────────────
    source_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # verizon | tmobile | att | telnyx | manual
    source_sync_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Current linkage snapshot ─────────────────────────────────
    current_site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    current_device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ── Suggestions ──────────────────────────────────────────────
    suggested_tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    suggested_site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    suggested_site_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    suggested_device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    suggested_unit_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    suggestion_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 0.0 – 1.0;  None = no suggestion generated
    suggestion_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Missing data flags ───────────────────────────────────────
    missing_e911: Mapped[bool] = mapped_column(default=False, server_default="false")
    missing_site: Mapped[bool] = mapped_column(default=True, server_default="true")
    missing_customer: Mapped[bool] = mapped_column(default=False, server_default="false")
    needs_compliance_review: Mapped[bool] = mapped_column(default=False, server_default="false")

    # ── Status ───────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(30), default="new", server_default="new", index=True)
    # new | suggested | needs_review | approved | linked | ignored

    # ── Resolution ───────────────────────────────────────────────
    resolved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ── Metadata ─────────────────────────────────────────────────
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
