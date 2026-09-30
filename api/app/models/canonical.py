"""Canonical Life-Safety Service & Connection model (DECISIONS D-023).

    PortfolioBuilding
      -> LifeSafetyService        the protected life-safety function
          -> LifeSafetyConnection a REQUIRED communications path of the service
              -> CommunicationsAsset (via ConnectionAssetLink)
                                   the identifiers / equipment that carry it

SERVICE != CONNECTION != ASSET.  Cardinality is a domain rule, applied only to
CONFIRMED (or operator-approved) services: ELEVATOR and EMERGENCY_PHONE require
1 connection, FACP requires 2.  A connection row states what the service
REQUIRES; the assets linked to it (and, later, their observed state) say
whether each required path is provisioned or impaired.

Three independent axes on every service / asset — never collapsed:
  * ``confidence`` — how strong the evidence is (CONFIRMED / PROBABLE /
    UNRESOLVED).  Evidence never promotes itself.
  * ``approval``   — the operator's decision (NONE / APPROVED / REJECTED).
    Operator decisions override automated reconciliation.
  * ``lifecycle``  — CURRENT / DECOMMISSIONED / REPLACED / SUSPENDED /
    HISTORICAL / UNKNOWN, with a preserved reason and history.

Provenance: every projected fact has ``canonical_evidence`` rows (source
ZOHO / TRUE911 / NAPCO / GENESIS / REGISTRY / OPERATOR).  Operator ground truth
is an append-only, supersedable ``operator_decisions`` ledger.

Additive and inert: written only by the reconciliation writer under an explicit
``--apply``; nothing customer-facing reads these tables in PR #186a.  E911 is a
separate axis and is never touched.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProjectionRun(Base):
    """One reconciliation run (dry-run runs are reported, not stored)."""

    __tablename__ = "projection_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)          # APPLY
    run_by: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # per-source retrieval metadata: {"zoho": {"status", "retrieved_at", ...}, ...}
    sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # JSON
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommunicationsAsset(Base):
    __tablename__ = "communications_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(120), nullable=False)
    display_value: Mapped[str] = mapped_column(String(120), nullable=False)  # masked for SIM/IMEI
    carrier: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    lifecycle_reason: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    lifecycle_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_asset_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lifecycle_event_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    building_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    placement_confidence: Mapped[str] = mapped_column(String(20), nullable=False,
                                                      default="UNRESOLVED")
    placement_basis: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    last_projection_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "asset_type", "normalized_value",
                         name="uq_comm_asset_identity"),
    )


class LifeSafetyService(Base):
    __tablename__ = "life_safety_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    building_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    service_key: Mapped[str] = mapped_column(String(160), nullable=False)
    service_type: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="UNRESOLVED")
    approval: Mapped[str] = mapped_column(String(20), nullable=False, default="NONE")
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    lifecycle_reason: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    source_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legacy_service_unit_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_projection_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "building_id", "service_key",
                         name="uq_ls_service_key"),
        Index("ix_ls_services_tenant_building", "tenant_id", "building_id"),
    )


class LifeSafetyConnection(Base):
    """A REQUIRED communications path of a confirmed / approved service."""

    __tablename__ = "life_safety_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    connection_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # REQUIRED while the service is confirmed/approved + current; NOT_REQUIRED after
    requirement: Mapped[str] = mapped_column(String(20), nullable=False, default="REQUIRED")
    # ASSET_LINKED / NO_ASSET_LINKED - observed operational state is a later axis
    provisioning: Mapped[str] = mapped_column(String(20), nullable=False,
                                              default="NO_ASSET_LINKED")
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="CONFIRMED")
    last_projection_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("service_id", "ordinal", name="uq_ls_connection_ordinal"),
    )


class ConnectionAssetLink(Base):
    __tablename__ = "connection_asset_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    connection_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    asset_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    relationship: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("connection_id", "asset_id", "relationship",
                         name="uq_conn_asset_link"),
    )


class AssetLifecycleEvent(Base):
    """A lifecycle event covering one or more assets (e.g. a carrier migration
    replacing six lines with seven).  Assets point here via
    ``lifecycle_event_id``; the event itself comes from an operator decision."""

    __tablename__ = "asset_lifecycle_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    building_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="OPERATOR")
    operator_decision_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True,
                                                                nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CanonicalEvidence(Base):
    """Append-only provenance for services, assets, placements and lifecycle."""

    __tablename__ = "canonical_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    projection_run_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # JSON, masked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_canon_evidence_subject", "tenant_id", "subject_type", "subject_key"),
    )


class OperatorDecision(Base):
    """Durable, auditable, reversible operator ground truth.  Never updated in
    place except to record that a newer decision superseded it."""

    __tablename__ = "operator_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    decision_type: Mapped[str] = mapped_column(String(40), nullable=False)
    decision_key: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)              # JSON
    previous_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_state: Mapped[str] = mapped_column(Text, nullable=False)            # JSON
    effective_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="OPERATOR")
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    superseded_by_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    superseded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_operator_decisions_active", "tenant_id", "decision_key",
              "superseded_by_id"),
    )
