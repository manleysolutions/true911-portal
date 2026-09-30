"""Customer Self-Service — the customer-owned operational layer + governed requests.

Three narrowly-scoped, tenant-scoped tables (migration ``053``):

  * ``CustomerServiceRequest``   — a governed request (add / remove / move service,
                                   change number, replace equipment, E911
                                   verification, location correction, problem
                                   report).  A request NEVER changes carrier /
                                   device / network / registry / official-E911
                                   data by itself; operations review and act.
  * ``CustomerManagedField``     — the customer-owned OVERLAY (contacts, notes,
                                   friendly names, connection purpose, notification
                                   preferences).  Lives beside — never inside — the
                                   system records it annotates, so a customer edit
                                   can never overwrite a Site / Device / registry /
                                   E911 value.
  * ``CustomerActivityEvent``    — append-only history of every customer-plane
                                   mutation and request transition (who / what /
                                   when / old / new / location / connection /
                                   origin).  Rows are never updated or deleted.

A location is addressed by ``location_key``: ``bldg:<PortfolioBuilding.id>`` in
registry mode, ``site:<Site.site_id>`` in legacy Site mode — so the same layer
serves both views.  Loose-coupled by string ids (no cross-table FKs), matching the
Portfolio Registry convention.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CustomerServiceRequest(Base):
    """A customer-submitted, operations-governed request."""

    __tablename__ = "customer_service_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_ref: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    location_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    building_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # the connection this request concerns (customer connection key), if any
    connection_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    request_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted", index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")

    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_changes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_customer_requests_tenant_status", "tenant_id", "status"),
        Index("ix_customer_requests_tenant_location", "tenant_id", "location_key"),
    )


class CustomerManagedField(Base):
    """One customer-owned value (the overlay).  ``subject_key`` is ``""`` for a
    location-level field or the connection key for a connection-level field."""

    __tablename__ = "customer_managed_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    location_key: Mapped[str] = mapped_column(String(80), nullable=False)
    building_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subject_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "location_key", "subject_key", "field",
                         name="uq_customer_managed_field"),
        Index("ix_customer_fields_tenant_location", "tenant_id", "location_key"),
    )


class CustomerActivityEvent(Base):
    """Append-only customer-plane history.  Never updated, never deleted."""

    __tablename__ = "customer_activity_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    location_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    building_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subject_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    request_ref: Mapped[Optional[str]] = mapped_column(String(40), index=True, nullable=True)

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    field: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    # customer_portal | operations
    origin: Mapped[str] = mapped_column(String(30), nullable=False)

    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_customer_activity_tenant_location", "tenant_id", "location_key"),
    )
