"""LLLM (Localized LLM) service package — Phase 1 MVP.

Public surface:

  * :func:`generate_health_summary` — the orchestrator.  Always
    returns a HealthSummaryResponse-shaped dict; never raises.

Everything in this package is no-op when ``settings.FEATURE_LLLM`` is
not ``"true"``.  The orchestrator additionally checks
``LLLM_ALLOW_EXTERNAL`` before any provider call, so the worst-case
behavior with bad config is "always returns the deterministic
summary" rather than "leaks data" or "crashes".
"""

from app.services.llm.orchestrator import generate_health_summary

__all__ = ["generate_health_summary"]
