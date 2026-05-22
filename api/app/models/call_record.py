from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CallRecord(Base):
    """Call detail record (CDR) — one row per call.

    Stores call history for managed POTS replacement deployments so a
    call can be associated with the tenant / customer / site / device /
    line it belongs to, and a customer-facing call history can be
    rendered.

    Linkage follows the platform convention: ``tenant_id`` / ``site_id``
    / ``device_id`` / ``line_id`` are indexed string business keys
    (matching the ``recordings`` and ``events`` tables).  ``customer_id``
    is a real FK to ``customers.id`` (matching ``lines.customer_id``), so
    a CDR can be FK-joined to a customer.

    The table is populated by provider ingestion (Telnyx) — see Phase 3.
    """

    __tablename__ = "call_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # internal business key
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    provider: Mapped[str] = mapped_column(String(50), default="telnyx")  # telnyx, tmobile, other
    direction: Mapped[str] = mapped_column(String(20), default="inbound")  # inbound, outbound
    from_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    did: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # Red Tag Line DID involved

    status: Mapped[str] = mapped_column(String(30), default="completed")  # completed, no-answer, busy, failed, canceled
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # provider-billed cost, if available
    recording_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # links to recordings.recording_id
    telnyx_call_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    telnyx_cdr_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # raw provider extras

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_call_records_tenant_started", "tenant_id", "started_at"),
    )
