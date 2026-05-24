"""Anthropic Claude provider — the only provider in Phase 1.

Uses httpx directly (no SDK dependency added) to match the existing
``app.services.support.ai_service._call_anthropic`` pattern.  When the
API key is unset, ``generate()`` returns ``status='error'`` immediately
without making a network call — the caller treats that as deterministic
fallback territory.

This provider:

  * Honors the timeout from the caller exactly (httpx.AsyncClient(timeout=...)).
  * Never raises — every exception path returns an LLMResult with a
    non-sensitive ``error_summary``.
  * Records usage tokens from the response when available; otherwise
    leaves them as None and lets the orchestrator decide how to charge
    the budget.
  * Posts to /v1/messages with ``anthropic-version: 2023-06-01`` — the
    same header used by the support assistant integration.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import settings
from app.services.llm.base import LLMProvider, LLMResult

logger = logging.getLogger("true911.llm.anthropic")


_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float,
        model: str,
        max_tokens: int = 1024,
    ) -> LLMResult:
        api_key = settings.ANTHROPIC_API_KEY.strip()
        if not api_key:
            # No key — record as 'error' so the orchestrator falls back
            # to deterministic without recording tokens against the cap.
            return LLMResult(
                status="error",
                model=model,
                error_summary="ANTHROPIC_API_KEY not configured",
            )

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(_API_URL, headers=headers, json=body)
        except httpx.TimeoutException:
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "Anthropic timeout after %dms (limit %.2fs)", elapsed, timeout_seconds
            )
            return LLMResult(
                status="timeout",
                latency_ms=elapsed,
                model=model,
                error_summary=f"provider timeout after {timeout_seconds}s",
            )
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.warning("Anthropic HTTP error: %s: %s", type(exc).__name__, exc)
            return LLMResult(
                status="error",
                latency_ms=elapsed,
                model=model,
                error_summary=f"http error: {type(exc).__name__}",
            )
        except Exception as exc:  # noqa: BLE001 — defensive: never raise
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.exception("Anthropic unexpected exception")
            return LLMResult(
                status="error",
                latency_ms=elapsed,
                model=model,
                error_summary=f"unexpected: {type(exc).__name__}",
            )

        elapsed = int((time.perf_counter() - start) * 1000)

        if resp.status_code >= 400:
            # Surface the HTTP status without echoing the response body
            # (which could include hints about the API key or org).
            logger.warning("Anthropic returned %d", resp.status_code)
            return LLMResult(
                status="error",
                latency_ms=elapsed,
                model=model,
                error_summary=f"provider returned HTTP {resp.status_code}",
            )

        try:
            data: dict[str, Any] = resp.json()
        except ValueError:
            return LLMResult(
                status="invalid_output",
                latency_ms=elapsed,
                model=model,
                error_summary="provider response was not JSON",
            )

        # Extract text — Anthropic returns content as a list of blocks.
        try:
            text = data["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return LLMResult(
                status="invalid_output",
                latency_ms=elapsed,
                model=model,
                error_summary="provider response missing content[0].text",
            )

        usage = data.get("usage") or {}
        return LLMResult(
            status="ok",
            raw_text=text or "",
            tokens_in=int(usage.get("input_tokens")) if usage.get("input_tokens") is not None else None,
            tokens_out=int(usage.get("output_tokens")) if usage.get("output_tokens") is not None else None,
            latency_ms=elapsed,
            model=data.get("model") or model,
        )
