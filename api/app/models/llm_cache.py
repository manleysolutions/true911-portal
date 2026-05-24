"""LLLM Phase 1 — Postgres-backed summary cache.

Bounds cost and rate by reusing a summary when the underlying telemetry
hasn't changed.  The cache key includes ``data_fingerprint`` — a hash
over the inputs the summary was built from (most recent heartbeat
timestamps, the open-incident id list, telemetry rollup hash, etc.) —
so a fresh summary is generated automatically the moment any input
changes, even if the TTL hasn't expired.

A row whose ``expires_at`` is in the past is treated as a miss; a
background tidy is not required for correctness but keeps the table
small.
"""

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class LLMSummaryCache(Base):
    __tablename__ = "llm_summary_cache"

    # cache_key = sha256(tenant_id|scope|scope_id|data_fingerprint|prompt_template_version)
    # — fits 64 hex chars, padded to 128 for safety.
    cache_key = Column(String(128), primary_key=True)

    tenant_id = Column(String(100), nullable=False, index=True)
    scope = Column(String(20), nullable=False)
    scope_id = Column(String(100), nullable=True)
    data_fingerprint = Column(String(64), nullable=False)

    # The full summary payload — same shape the router returns.
    payload = Column(JSONB, nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
