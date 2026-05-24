"""Provider tests — registry + Anthropic graceful-failure surface.

The orchestrator depends on the provider NEVER raising, so these tests
exist primarily to defend that contract.  We verify graceful failure
without ever making a real network call.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.llm.base import LLMResult
from app.services.llm.providers import AnthropicProvider, get_provider


# ─── Registry ──────────────────────────────────────────────────────


class TestRegistry:
    def test_anthropic_resolves(self):
        p = get_provider("anthropic")
        assert isinstance(p, AnthropicProvider)

    def test_empty_default_resolves_to_anthropic(self):
        p = get_provider("")
        assert isinstance(p, AnthropicProvider)

    def test_unknown_returns_none(self):
        # The orchestrator treats None as "external provider
        # unavailable" → deterministic fallback.  This is what saves
        # us from a typo in LLLM_PROVIDER taking the feature down.
        assert get_provider("does-not-exist") is None
        assert get_provider("BEDROCK_GOVCLOUD") is None  # not registered yet


# ─── AnthropicProvider graceful failure ────────────────────────────


class TestAnthropicProviderFailure:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_error_without_network(self):
        provider = AnthropicProvider()
        with patch("app.services.llm.providers.anthropic_provider.settings.ANTHROPIC_API_KEY", ""):
            result = await provider.generate(
                system_prompt="x",
                user_prompt="y",
                timeout_seconds=5.0,
                model="claude-x",
            )
        assert isinstance(result, LLMResult)
        assert result.status == "error"
        assert "ANTHROPIC_API_KEY not configured" in result.error_summary

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_status(self):
        provider = AnthropicProvider()

        async def _raise_timeout(*args, **kwargs):
            raise httpx.TimeoutException("simulated timeout")

        with patch("app.services.llm.providers.anthropic_provider.settings.ANTHROPIC_API_KEY", "test-key"), \
             patch("httpx.AsyncClient.post", new=_raise_timeout):
            result = await provider.generate(
                system_prompt="x",
                user_prompt="y",
                timeout_seconds=0.1,
                model="claude-x",
            )
        assert result.status == "timeout"
        assert "timeout" in (result.error_summary or "").lower()

    @pytest.mark.asyncio
    async def test_http_error_returns_error_status(self):
        provider = AnthropicProvider()

        async def _raise_http(*args, **kwargs):
            raise httpx.ConnectError("dns failure")

        with patch("app.services.llm.providers.anthropic_provider.settings.ANTHROPIC_API_KEY", "test-key"), \
             patch("httpx.AsyncClient.post", new=_raise_http):
            result = await provider.generate(
                system_prompt="x",
                user_prompt="y",
                timeout_seconds=5.0,
                model="claude-x",
            )
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_bare_exception_caught_and_returned(self):
        """The defensive bare-except clause is intentional.

        If a future httpx change raises something outside HTTPError
        the contract still has to hold — orchestrator must never crash
        because the provider crashed.
        """
        provider = AnthropicProvider()

        async def _raise_bare(*args, **kwargs):
            raise RuntimeError("unexpected")

        with patch("app.services.llm.providers.anthropic_provider.settings.ANTHROPIC_API_KEY", "test-key"), \
             patch("httpx.AsyncClient.post", new=_raise_bare):
            result = await provider.generate(
                system_prompt="x",
                user_prompt="y",
                timeout_seconds=5.0,
                model="claude-x",
            )
        assert result.status == "error"
