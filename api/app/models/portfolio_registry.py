"""Portfolio Registry — the permanent, approved source of truth for buildings.

The Portfolio Fusion Engine used to *rediscover* the portfolio on every run.  These
tables make the portfolio **persistent**: incoming Zoho / Napco / Genesis / True911
data is reconciled against an operator-**approved** registry instead of being
re-clustered from scratch.  Approved mappings are permanent and are consulted BEFORE
any heuristic on future runs.

Tables (all tenant-scoped, loose-coupled by string ids — no cross-table FKs except
within this module):

  * ``PortfolioBuilding``       — one canonical building (the Digital Twin spine).
  * ``PortfolioAlias``          — an approved alias/label that resolves to a building.
  * ``PortfolioDeviceMapping``  — an approved identifier→building mapping
                                  (Napco radio / Genesis MSISDN / ICCID / IMEI /
                                  phone / True911 device / Zoho account).
  * ``PortfolioReviewItem``     — the review queue.  Nothing enters the registry
                                  without an explicit approval that clears a review
                                  item; the Fusion run itself NEVER writes here.

Writes to any of these happen ONLY through the explicit approval workflow in
``app.services.portfolio_registry`` — a plain Fusion run is read-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortfolioBuilding(Base):
    """A canonical building in the approved Portfolio Registry — the permanent
    identity that every customer Digital Twin is built on."""

    __tablename__ = "portfolio_buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    store_number: Mapped[Optional[str]] = mapped_column(String(30), index=True, nullable=True)
    site_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # lifecycle: active | inactive | decommissioned | pending
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zip: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Approval gate — a building is only authoritative once approved.
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_portfolio_buildings_tenant_store", "tenant_id", "store_number"),
    )


class PortfolioAlias(Base):
    """An alias/label that resolves to a ``PortfolioBuilding`` (approved)."""

    __tablename__ = "portfolio_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    building_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    # normalized form used for matching (lower-cased, alnum-collapsed)
    alias_normalized: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # zoho|napco|genesis|true911|operator
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "alias_normalized", name="uq_portfolio_alias_norm"),
    )


class PortfolioDeviceMapping(Base):
    """An approved identifier → building mapping.  ``kind`` is one of:
    napco_radio | genesis_msisdn | iccid | imei | phone | true911_device |
    zoho_account.  ``value_normalized`` is the join key used at reconcile time."""

    __tablename__ = "portfolio_device_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    building_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    value_normalized: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "value_normalized", name="uq_portfolio_devmap"),
    )


class PortfolioReviewItem(Base):
    """The review queue.  A Fusion run proposes review items when incoming data does
    not map to the approved registry; an operator approves or rejects them.  Types:
    new_building | possible_merge | duplicate_building | address_conflict |
    device_conflict | unknown_alias.  Status: pending | approved | rejected."""

    __tablename__ = "portfolio_review_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    review_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    # a stable signature so re-runs don't duplicate an open/decided item
    signature: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # candidate identity (from the fusion run) + optional suggested existing building
    candidate_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    store_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    suggested_building_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON snapshot of the candidate

    decided_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "signature", name="uq_portfolio_review_sig"),
        Index("ix_portfolio_review_tenant_status", "tenant_id", "status"),
    )
