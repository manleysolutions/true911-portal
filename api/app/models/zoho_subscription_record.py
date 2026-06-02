from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ZohoSubscriptionRecord(Base):
    """Shadow/staging mirror of a Zoho CRM Subscription_Mgmt record.

    This is the source-of-truth MIRROR for LIFECYCLE status — populated from the
    Zoho webhook behind ``FEATURE_ZOHO_SUBSCRIPTION_INGEST``.  It NEVER overwrites
    ``sites`` / ``devices`` / ``lines``; it is read by the read-only review
    surface and, in a later explicitly-gated phase, promoted to an additive
    ``lifecycle_status`` column.

    Lifecycle (Active / Suspended / Deactivated / Pending Install) is a SEPARATE
    axis from operational status (Online / Offline / Attention), which stays
    owned by True911 telemetry.  ``device_activation_status`` holds Zoho's raw
    commercial string verbatim; ``lifecycle_state`` holds the normalized value
    (NULL until the normalizer runs).
    """
    __tablename__ = "zoho_subscription_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    # org_id is the leading column of uq_zoho_subscription_records_identity, so
    # org-scoped queries are already index-covered — no standalone index needed.
    org_id: Mapped[str] = mapped_column(String(100))

    # Zoho "Subscription Mgmt ID" — natural key for idempotent upsert.
    subscription_mgmt_id: Mapped[str] = mapped_column(String(255), index=True)

    # ── Persisted Zoho subscription fields (task 3) ──────────────────────
    account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    facility_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    msisdn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    # Raw Zoho "Device Activation Status" string, stored verbatim (e.g. "De-activated").
    device_activation_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    connection_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subscription_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mrc: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # Monthly Recurring Charge
    service_term_ends: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Normalized lifecycle state (Phase 2) ─────────────────────────────
    # active | suspended | deactivated | pending_install | unknown.  NULL until
    # FEATURE_ZOHO_STATUS_NORMALIZER populates it.
    lifecycle_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # ── Linkage / audit ──────────────────────────────────────────────────
    external_record_map_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("external_record_map.id"), nullable=True
    )
    last_event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("integration_events.id"), nullable=True
    )
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # sanitized payload snapshot

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id", "subscription_mgmt_id",
            name="uq_zoho_subscription_records_identity",
        ),
    )
