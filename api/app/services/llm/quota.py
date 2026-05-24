"""Per-tenant daily token cap for the LLLM provider.

Sums ``tokens_in + tokens_out`` from ``llm_audit_log`` for the effective
tenant over the current UTC day.  When the configured cap is 0 the
cap is treated as unlimited (NOT recommended in production); the
default per the Phase 1 plan is 100,000 tokens/tenant/day.

The check is a soft pre-flight gate: a request is allowed if the
caller has at least ``estimated_call_tokens`` budget remaining.  The
actual usage is recorded post-call on the audit row, so two near-
simultaneous calls could both pass the gate and slightly overshoot.
That's acceptable — the cap is a budget control, not a hard rate limit.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm_audit import LLMAuditLog


# Conservative default for "how many tokens might one call burn".  Used
# as the pre-flight floor when the caller doesn't provide an estimate.
DEFAULT_ESTIMATED_CALL_TOKENS = 2000


def _today_start_utc() -> datetime:
    """Start of the current UTC day."""
    now = datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


async def tokens_used_today(db: AsyncSession, tenant_id: str) -> int:
    """Sum of tokens_in + tokens_out for ``tenant_id`` since UTC midnight.

    Counts every audit row regardless of ``status`` — fallback /
    blocked / error rows may have non-zero tokens too if the provider
    was reached.
    """
    in_sum = func.coalesce(func.sum(LLMAuditLog.tokens_in), 0)
    out_sum = func.coalesce(func.sum(LLMAuditLog.tokens_out), 0)
    stmt = select((in_sum + out_sum).label("total")).where(
        LLMAuditLog.effective_tenant_id == tenant_id,
        LLMAuditLog.created_at >= _today_start_utc(),
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def has_budget(
    db: AsyncSession,
    tenant_id: str,
    estimated_call_tokens: int = DEFAULT_ESTIMATED_CALL_TOKENS,
) -> bool:
    """Whether ``tenant_id`` has at least ``estimated_call_tokens`` left today.

    Returns True when the configured cap is 0 (unlimited) regardless of
    current usage.  Negative cap values are treated as 0 (unlimited)
    rather than erroring — operator misconfiguration shouldn't take
    the feature down.
    """
    cap = settings.LLLM_DAILY_TOKEN_CAP_PER_TENANT
    if cap <= 0:
        return True
    used = await tokens_used_today(db, tenant_id)
    return (cap - used) >= max(1, estimated_call_tokens)


async def remaining_budget(db: AsyncSession, tenant_id: str) -> Optional[int]:
    """How many tokens ``tenant_id`` may still use today.

    Returns ``None`` when the cap is unlimited (cap <= 0), otherwise a
    non-negative int.  Useful for surfacing budget state on responses
    or in operator dashboards (post Phase 1).
    """
    cap = settings.LLLM_DAILY_TOKEN_CAP_PER_TENANT
    if cap <= 0:
        return None
    used = await tokens_used_today(db, tenant_id)
    return max(0, cap - used)
