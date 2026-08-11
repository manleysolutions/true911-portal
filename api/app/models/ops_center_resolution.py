"""Ops Center Phase 1.6 — Resolution Intelligence models (foundations).

Additive, currently-inert tables that persist the structured operational
knowledge library used by Manley technicians / NOC / carrier-support /
installers / customer-support for life-safety communications:

  * ``OpsKnownIssue``         — a known issue (symptoms, probable causes) per
                                vendor / carrier / hardware model.
  * ``OpsDiagnosticWorkflow`` — an ordered troubleshooting sequence for an issue.
  * ``OpsResolutionWorkflow`` — the actual fix procedure for an issue.
  * ``OpsResolutionOutcome``  — what actually happened (resolved / escalated /
                                vendor-issue / …) with a confidence score.

The knowledge tables (issue / diagnostic / resolution) are GLOBAL shared
operational knowledge — NOT customer data — so they carry no ``tenant_id``.
``OpsResolutionOutcome`` records a real engagement result and so carries an
OPTIONAL ``tenant_id`` (+ ``session_ref``) for tenant-scoped traceability,
honoring tenant isolation without coupling the library to a tenant.

Severity/status/outcome columns are plain ``String`` (values from
``app.services.ops_center.resolution_intelligence.constants`` /
``...intelligence.constants.IncidentSeverity``) per the no-native-PG-enum
convention.  Cross-links are loose UUID/string references (no FK).  Each
knowledge row has a stable ``code`` so seeding is idempotent.

Nothing reads these at runtime yet; the whole module stays behind
``FEATURE_OPS_CENTER`` (default off).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OpsKnownIssue(Base):
    __tablename__ = "ops_known_issues"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(60), index=True, nullable=False)  # domain
    severity: Mapped[str] = mapped_column(String(20), default="moderate", server_default="moderate", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    symptoms: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)         # list[str]
    probable_causes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # list[str]
    vendor: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    carrier: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    hardware_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    escalation_queue: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OpsDiagnosticWorkflow(Base):
    __tablename__ = "ops_diagnostic_workflows"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Loose link to the known issue (by code + optional id) — no FK.
    issue_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    issue_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    ordered_steps: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)     # list[{order,action,expect}]
    expected_results: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # list[str]
    failure_paths: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)     # list[{when,do,escalate_to}]
    escalation_queue: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OpsResolutionWorkflow(Base):
    __tablename__ = "ops_resolution_workflows"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    issue_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolution_steps: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # list[{order,action}]
    estimated_time_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    escalation_trigger: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # list[str]
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OpsResolutionOutcome(Base):
    __tablename__ = "ops_resolution_outcomes"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Optional tenant scope — an outcome may be tied to a real customer
    # engagement (tenant isolation honored; the knowledge library itself is global).
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    issue_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    issue_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    workflow_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    workflow_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    session_ref: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    outcome_type: Mapped[str] = mapped_column(String(40), nullable=False)  # resolved | partially_resolved | escalated | vendor_issue | carrier_issue | customer_issue | hardware_failure
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
