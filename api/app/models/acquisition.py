"""Acquisition records — the durable system of record for public leads (D-031).

One row per accepted public submission: a quote request, a request for a
Life-Safety Assessment, or a self-service assessment (the /register wizard, whose
full payload stays in the ``registrations`` staging tables and is linked here by
``registration_ref``).

ACQUISITION state only.  Nothing here says anything is deployed, monitored,
connected or E911-verified: prospect-provided information is intent, not
operational truth (D-032).  Notification and CRM sync are downstream side
effects recorded on the row; they never decide whether the lead exists.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Record kinds (what the prospect submitted).
KINDS = ("quote_request", "assessment_request", "assessment")
# Acquisition lifecycle — deliberately separate from any deployment status.
STATUSES = ("inquiry", "assessment_draft", "assessment_submitted", "under_review",
            "qualified", "converted", "closed")
# Outcome of the post-persistence internal notification.
NOTIFICATION_STATES = ("pending", "sent", "failed", "not_configured")


class AcquisitionRecord(Base):
    __tablename__ = "acquisition_records"
    __table_args__ = (
        UniqueConstraint("record_ref", name="uq_acquisition_records_record_ref"),
        UniqueConstraint("idempotency_key", name="uq_acquisition_records_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    record_ref: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    company: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    num_locations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    service_interests: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON list (allow-listed)
    needs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)               # JSON list (allow-listed)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    registration_ref: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)

    # Provenance (normalized + length-capped; never trusted for security decisions).
    entry_point: Mapped[str] = mapped_column(String(40), nullable=False)
    landing_path: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    referrer: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    initial_cta: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Retry safety: a resubmission with the same key returns the same record.
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)

    notification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    notification_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notification_error: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
