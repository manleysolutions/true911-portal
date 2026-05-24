"""LLM provider abstraction — the swap point for future providers.

Phase 1 ships only :class:`AnthropicProvider`.  The interface is
designed so adding Ollama, llama.cpp, vLLM, Azure OpenAI Gov, or AWS
Bedrock GovCloud later means writing one new file in
``app/services/llm/providers/`` and one entry in the registry — no
orchestrator or router change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional


ProviderStatus = Literal["ok", "timeout", "error", "invalid_output"]


@dataclass
class LLMResult:
    """The single return shape every provider must produce.

    The text is intentionally NOT pre-parsed — the validator owns parsing
    so every provider is held to the same contract.  Token counts are
    best-effort; ``None`` is allowed if the provider doesn't report them
    (used for self-hosted backends).
    """

    status: ProviderStatus
    raw_text: str = ""
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: int = 0
    model: str = ""
    error_summary: Optional[str] = None


class LLMProvider(ABC):
    """Abstract base for every LLM provider.

    Implementations MUST:

      * Respect the timeout passed to ``generate()``.  A hung provider
        kills the user-facing request — return an LLMResult with
        ``status='timeout'`` instead of raising.
      * Never raise on network errors.  Catch and return
        ``status='error'`` with a non-sensitive ``error_summary``.
        Stack traces are logged; they do NOT travel into the response.
      * Treat the system prompt as the trust boundary — anything the
        caller passes in ``untrusted_context`` was already wrapped in
        ``<untrusted_data>...</untrusted_data>`` blocks by the prompt
        builder, but providers MUST NOT echo those blocks back into the
        system prompt slot of any nested call.
    """

    name: str = "unknown"

    @abstractmethod
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float,
        model: str,
        max_tokens: int = 1024,
    ) -> LLMResult:
        """Call the underlying model.  Never raises."""
        raise NotImplementedError
