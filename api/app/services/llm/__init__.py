"""LLLM (Localized LLM) service package — Phase 1 MVP.

Public surface in Phase 1:

  * :func:`generate_health_summary` — the orchestrator (wired in a
    later commit; not yet exported).

Everything in this package is no-op when ``settings.FEATURE_LLLM`` is
not ``"true"``.  The router refuses to even import this package's
orchestrator unless the flag is set, so this directory existing on
disk is benign by itself.
"""
