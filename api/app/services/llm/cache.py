"""Postgres-backed summary cache.

Cache key is a sha256 over ``tenant_id | scope | scope_id |
data_fingerprint | prompt_template_version``.  ``data_fingerprint`` is
itself a hash of the underlying input data — so the moment ANY input
changes (most recent heartbeat timestamp, the set of open incidents,
the telemetry rollup), the cache key changes too and a fresh summary
is generated.  This makes the cache a free win when nothing has
changed and invisible otherwise.

TTL is a backstop, not the primary invalidation mechanism — even when
inputs haven't changed, an entry older than ``settings.LLLM_CACHE_TTL_SECONDS``
is treated as a miss so an operator can force-refresh by waiting.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm_cache import LLMSummaryCache


def _stable_dump(obj: Any) -> str:
    """JSON dump with sorted keys so the fingerprint is order-independent."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_data_fingerprint(parts: dict) -> str:
    """Hash the input dict.

    ``parts`` should contain ONLY the values that, if they change, mean
    the summary should change.  Stable IDs are better than raw values.
    Example for fleet scope:

        {
          "open_incident_ids": ["INC-1", "INC-2"],
          "last_telemetry_at": "2026-05-23T12:00:00Z",
          "site_count": 25,
          ...
        }
    """
    digest = hashlib.sha256(_stable_dump(parts).encode("utf-8")).hexdigest()
    return digest


def compute_cache_key(
    tenant_id: str,
    scope: str,
    scope_id: Optional[str],
    data_fingerprint: str,
    prompt_template_version: str,
) -> str:
    """Build the primary key for ``llm_summary_cache``."""
    raw = f"{tenant_id}|{scope}|{scope_id or ''}|{data_fingerprint}|{prompt_template_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_cached(db: AsyncSession, cache_key: str) -> Optional[dict]:
    """Return the cached payload if present AND not expired, else None.

    An expired row is left in place; the next ``store()`` call will
    overwrite it.  This avoids issuing a DELETE on every miss.
    """
    stmt = select(LLMSummaryCache).where(LLMSummaryCache.cache_key == cache_key)
    result = await db.execute(stmt)
    row: Optional[LLMSummaryCache] = result.scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        return None
    return row.payload


async def store(
    db: AsyncSession,
    *,
    cache_key: str,
    tenant_id: str,
    scope: str,
    scope_id: Optional[str],
    data_fingerprint: str,
    payload: dict,
    ttl_seconds: Optional[int] = None,
) -> None:
    """Upsert a payload.  Caller is responsible for ``db.commit()``.

    Uses Postgres ON CONFLICT DO UPDATE so re-storing the same key
    refreshes the TTL and overwrites the payload.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.LLLM_CACHE_TTL_SECONDS
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    stmt = pg_insert(LLMSummaryCache).values(
        cache_key=cache_key,
        tenant_id=tenant_id,
        scope=scope,
        scope_id=scope_id,
        data_fingerprint=data_fingerprint,
        payload=payload,
        expires_at=expires_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["cache_key"],
        set_={
            "tenant_id": stmt.excluded.tenant_id,
            "scope": stmt.excluded.scope,
            "scope_id": stmt.excluded.scope_id,
            "data_fingerprint": stmt.excluded.data_fingerprint,
            "payload": stmt.excluded.payload,
            "expires_at": stmt.excluded.expires_at,
        },
    )
    await db.execute(stmt)


async def purge_expired(db: AsyncSession) -> int:
    """Delete every cache row whose TTL has passed.

    Not called automatically anywhere — provided so an operator
    (or a future RQ tidy job) can keep the table small.  Returns the
    number of rows deleted.  Caller commits.
    """
    now = datetime.now(timezone.utc)
    stmt = delete(LLMSummaryCache).where(LLMSummaryCache.expires_at <= now)
    result = await db.execute(stmt)
    return result.rowcount or 0
