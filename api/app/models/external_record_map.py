from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ExternalRecordMap(Base):
    """Additive, generic mapping of an external CRM record to True911 entities.

    Broader than ``external_customer_map`` / ``external_subscription_map`` (which
    are billing-specific and left untouched): this maps ANY Zoho module record
    (Accounts, Contacts, Subscription_Mgmt) to whichever True911 entities apply.

    Every link column is nullable — a row can start fully ``unmapped`` and gain
    links only as the read-only review surface CONFIRMS them.  Nothing here
    overwrites or deletes existing True911 data; the link columns store the
    string business IDs (site_id / device_id / line_id), mirroring how
    ``lines`` already references sites/devices, plus int FKs for customer /
    subscription where those are the natural key.
    """
    __tablename__ = "external_record_map"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(50), default="zoho_crm")  # zoho_crm, qb
    module: Mapped[str] = mapped_column(String(100))  # Accounts, Contacts, Subscription_Mgmt
    external_record_id: Mapped[str] = mapped_column(String(255))

    # Optional True911 links — populated only as mapping is confirmed.
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id"), nullable=True
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )
    linked_tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # unmapped | suggested | confirmed.  NEVER auto-set to confirmed.
    map_status: Mapped[str] = mapped_column(String(30), default="unmapped")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # The unique constraint below is backed by its own index, covering lookups
    # by (source, module, external_record_id).  Only the org_id filter needs an
    # extra index (declared inline above).
    __table_args__ = (
        UniqueConstraint(
            "source", "module", "external_record_id",
            name="uq_external_record_map_identity",
        ),
    )
