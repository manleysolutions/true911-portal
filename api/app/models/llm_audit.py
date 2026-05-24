"""LLLM Phase 1 — audit log of every AI Health Summary generation.

One row is written per call to ``GET /api/llm/health-summary``, whether
the provider was actually invoked or the deterministic fallback was
used.  The row records WHAT was asked, WHO asked it, WHICH tenant it
ran against (with impersonation context preserved), WHICH model was
used, and the GENERATED SUMMARY — but never the raw prompt or the raw
customer fields that fed it.  ``sources_used`` is a structured JSONB
list of references (``"sites:site-abc"``, ``"command_telemetry:last_25"``)
so an operator can reconstruct what data flowed in without the data
itself being persisted in the audit row.

This is the single source of truth for AI activity and is what the
governance review in ``docs/AI_OPERATIONAL_SAFETY.md`` is auditing.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class LLMAuditLog(Base):
    __tablename__ = "llm_audit_log"

    id = Column(BigInteger, primary_key=True)
    # Public-style ID — format ``ai-<uuid12>``.  Mirrors the pattern used
    # by AuditLogEntry.entry_id so an operator can correlate.
    audit_id = Column(String(50), unique=True, nullable=False, index=True)

    # WHO — stored as plain strings (not FK) so an audit row survives a
    # later user deletion / role rename.  The router populates both.
    user_id = Column(String(64), nullable=False)
    user_email = Column(String(255), nullable=True)
    user_role = Column(String(50), nullable=True)

    # WHICH tenant the call effectively ran against (post-impersonation)
    # and which tenant the underlying user actually belongs to.  These
    # only differ for SuperAdmin acting-as.  Recorded separately because
    # the governance question "did a SuperAdmin look at tenant X" needs
    # both halves to answer.
    effective_tenant_id = Column(String(100), nullable=False, index=True)
    original_tenant_id = Column(String(100), nullable=False)
    is_impersonating = Column(Boolean, nullable=False, default=False)

    # WHAT was requested
    scope = Column(String(20), nullable=False)  # fleet | site | device
    scope_id = Column(String(100), nullable=True)

    # WHICH model + prompt template
    model = Column(String(100), nullable=False)
    prompt_template_version = Column(String(50), nullable=False)

    # WHICH data fed the summary — list of "<table>:<key>" strings.
    # The actual values are NOT stored here.
    sources_used = Column(JSONB, nullable=False)

    # The generated artifacts
    summary_text = Column(Text, nullable=False)
    customer_safe_summary = Column(Text, nullable=True)
    internal_summary = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)

    # Operational metadata
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    # ok | fallback | blocked | error.  ``fallback`` means the provider
    # was unavailable / timed out / produced invalid output and the
    # deterministic summary was returned instead.  ``blocked`` means a
    # quota or feature-flag check stopped the call before dispatch.
    status = Column(String(20), nullable=False)
    error_summary = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
