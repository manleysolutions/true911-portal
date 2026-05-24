"""Pydantic schemas for LLLM Phase 1.

The output schema deliberately mirrors ``SupportAISummary`` so an
operator who is already familiar with the support feature can read
LLLM output without translation.  See ``docs/AI_OPERATIONAL_SAFETY.md``
for the full output contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Scope = Literal["fleet", "site", "device"]


class HealthSummaryRequest(BaseModel):
    """Query-shape for ``GET /api/llm/health-summary``.

    Not used as a request body — present so the OpenAPI schema names
    the parameters and tests can validate ``scope_id`` requirements.
    """

    scope: Scope = "fleet"
    scope_id: Optional[str] = None
    # When true, bypass the cache and force a fresh generation.  Subject
    # to the daily token cap.  Equivalent to calling
    # ``POST /api/llm/health-summary/refresh``.
    force_refresh: bool = False


class HealthSummaryResponse(BaseModel):
    """The audit-row-shaped payload returned to the UI.

    A response with ``deterministic_fallback=true`` is fully valid and
    actionable — it means the LLM was unavailable / timed out / failed
    validation and the deterministic summary built from the same input
    data is being returned instead.  The UI should render it identically.
    """

    summary_id: str = Field(..., description="Public audit-row id, format ai-<uuid12>")
    scope: Scope
    scope_id: Optional[str] = None

    current_status: str
    likely_issue: Optional[str] = None
    recommended_next_step: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Structured list of "<table>:<key>" references — the data this
    # summary was built from.  Never includes the actual values.
    sources_used: List[str]

    # Two-track audience.  ``customer_safe_summary`` has PII stripped
    # and approved-wording-style sanitation applied; ``internal_summary``
    # may reference device identifiers.  Phase 1 only returns
    # internal_summary populated; customer_safe_summary is reserved
    # for Phase 3 customer-visible drafts.
    customer_safe_summary: Optional[str] = None
    internal_summary: str

    generated_at: datetime
    model: str
    deterministic_fallback: bool = False
    # Source of the response: "cache" | "fresh" | "fallback"
    source: Literal["cache", "fresh", "fallback"]


class FeatureFlagsResponse(BaseModel):
    """Shape of the existing ``GET /api/config/features`` endpoint after
    Phase 1 adds its ``lllm`` key.  Kept as a schema so the UI client
    has something to import even though the route returns a plain dict.
    """

    samantha: bool
    line_intelligence: bool
    lllm: bool
