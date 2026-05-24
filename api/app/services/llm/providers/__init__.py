"""Provider implementations for LLLM.

Phase 1: only Anthropic.  Future entries:

  * ollama_provider          (self-hosted, local)
  * llamacpp_provider        (self-hosted, local)
  * vllm_provider            (self-hosted, GPU)
  * azure_openai_gov_provider (cloud, GovCloud)
  * bedrock_govcloud_provider (cloud, GovCloud)

See :mod:`app.services.llm.base` for the interface contract.
"""

from __future__ import annotations

from typing import Optional

from app.services.llm.base import LLMProvider
from app.services.llm.providers.anthropic_provider import AnthropicProvider


_REGISTRY: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "": AnthropicProvider,  # default when LLLM_PROVIDER is unset
}


def get_provider(name: str) -> Optional[LLMProvider]:
    """Resolve a provider by name.

    Returns ``None`` when the name is unrecognized — callers MUST handle
    that as "external provider unavailable" (deterministic fallback)
    rather than raising, so a typo in ``LLLM_PROVIDER`` doesn't take
    the feature down.
    """
    cls = _REGISTRY.get((name or "").lower())
    if cls is None:
        return None
    return cls()


__all__ = ["AnthropicProvider", "get_provider"]
