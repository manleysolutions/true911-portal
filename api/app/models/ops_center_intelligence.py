"""Ops Center Phase 1.5 — operational-intelligence models (foundations).

Additive, currently-inert tables that scaffold richer Tier-1 support:

  * ``OpsEscalationQueue``     — a queued escalation with canonical severity,
                                 derived priority, and assignment lifecycle.
  * ``OpsKnowledgeArticle``    — a support knowledge-base article.
  * ``OpsPlaybook``            — a step-by-step support playbook.
  * ``OpsResolutionPattern``   — a learned (symptom → resolution) pattern.

None of these is wired to a route or the live workflow yet — they exist so a
later phase can build on a stable schema.  Severity/status columns are plain
strings (values from
``app.services.ops_center.intelligence.constants``) per the project's
no-native-PG-enum convention.  Cross-links to sessions/sites/devices are loose
string/UUID references (no FK) to avoid coupling and migration ordering issues.
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OpsEscalationQueue(Base):
    __tablename__ = "ops_escalation_queue"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    # Loose link back to the originating support session (no FK).
    session_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    session_ref: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    issue_category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="moderate", server_default="moderate", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)  # 1 = most urgent
    status: Mapped[str] = mapped_column(String(30), default="queued", server_default="queued", nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    handoff_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    incident_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OpsKnowledgeArticle(Base):
    __tablename__ = "ops_knowledge_articles"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Null tenant_id => global/platform article shared across tenants.
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_ops_knowledge_tenant_slug"),
    )


class OpsPlaybook(Base):
    __tablename__ = "ops_playbooks"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    # Ordered list of step dicts, e.g. [{"order":1,"action":"...","expect":"..."}].
    steps: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_ops_playbook_tenant_slug"),
    )


class OpsResolutionPattern(Base):
    __tablename__ = "ops_resolution_patterns"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    issue_category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    # Normalized symptom signature used to recognize a recurring problem.
    signature: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="candidate", server_default="candidate", nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "issue_category", "signature", name="uq_ops_resolution_signature"),
    )
