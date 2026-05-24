"""Orchestrator — the single entry point a router uses.

Composes the building blocks from the rest of the package into the
"policy → deterministic → optional provider → validate → fallback"
flow that the audit doc specifies and that
``app.services.support.ai_service`` already proves works in production.

Flow per request:

  1. Build :class:`SummaryContext` via :class:`LLLMContext` — the
     ONLY place a SQL query for an AI summary is issued.
  2. Build the deterministic payload from the context.  This is the
     floor: every code path below this point either returns this
     payload or a validator-approved variation of it.
  3. Compute cache key from (tenant, scope, scope_id, data_fingerprint,
     template_version).  If cached and fresh, return it.
  4. Check feature flag (FEATURE_LLLM) + external-egress flag
     (LLLM_ALLOW_EXTERNAL) + provider availability.  Any 'no' →
     return deterministic with ``deterministic_fallback=True``.
  5. Check per-tenant daily token quota.  Out of budget →
     return deterministic with ``deterministic_fallback=True`` and
     status='blocked' on the audit row.
  6. Call the provider with the configured timeout.  Bad result →
     return deterministic with ``deterministic_fallback=True``.
  7. Validate the provider output.  Failure → return deterministic.
  8. Cache the accepted payload, write the audit row, return.

Every path writes ONE row to ``llm_audit_log``.  Every path is
guaranteed to return a valid HealthSummaryResponse shape.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm_audit import LLMAuditLog
from app.models.user import User
from app.services.llm import cache as cache_mod
from app.services.llm import quota as quota_mod
from app.services.llm.context import (
    LLLMContext,
    fingerprint_inputs_for_fleet,
    fingerprint_inputs_for_site,
)
from app.services.llm.deterministic import (
    SummaryContext,
    build_deterministic_summary,
)
from app.services.llm.prompts import load_template, template_version
from app.services.llm.providers import get_provider
from app.services.llm.validator import validate_provider_output

logger = logging.getLogger("true911.llm.orchestrator")


def _new_audit_id() -> str:
    return f"ai-{uuid.uuid4().hex[:12]}"


def _wrap_response(
    *,
    audit_id: str,
    ctx: SummaryContext,
    deterministic: dict,
    chosen: dict,
    deterministic_fallback: bool,
    model: str,
    source: str,  # "cache" | "fresh" | "fallback"
) -> dict:
    """Combine the chosen payload with the response envelope."""
    return {
        "summary_id": audit_id,
        "scope": ctx.scope,
        "scope_id": ctx.scope_id,
        "current_status": chosen["current_status"],
        "likely_issue": chosen.get("likely_issue"),
        "recommended_next_step": chosen["recommended_next_step"],
        "confidence": chosen.get("confidence", deterministic.get("confidence", 0.5)),
        # sources_used always comes from the deterministic payload —
        # i.e. from what the context loader actually read.  The provider
        # never gets to invent this.
        "sources_used": list(deterministic.get("sources_used", [])),
        "customer_safe_summary": chosen.get("customer_safe_summary"),
        "internal_summary": chosen["internal_summary"],
        "generated_at": chosen.get("generated_at") or deterministic["generated_at"],
        "model": model,
        "deterministic_fallback": deterministic_fallback,
        "source": source,
    }


async def _persist_audit(
    db: AsyncSession,
    *,
    audit_id: str,
    user: User,
    ctx: SummaryContext,
    payload: dict,
    model: str,
    status: str,
    error_summary: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[int] = None,
    template_v: str = "",
) -> None:
    """Add one row to llm_audit_log.  Caller commits."""
    original_tenant = getattr(user, "_original_tenant_id", user.tenant_id)
    is_impersonating = bool(getattr(user, "_is_impersonating", False))
    db.add(
        LLMAuditLog(
            audit_id=audit_id,
            user_id=str(user.id),
            user_email=user.email,
            user_role=user.role,
            effective_tenant_id=user.tenant_id,
            original_tenant_id=original_tenant,
            is_impersonating=is_impersonating,
            scope=ctx.scope,
            scope_id=ctx.scope_id,
            model=model,
            prompt_template_version=template_v,
            sources_used=list(ctx.sources_used),
            summary_text=payload["internal_summary"],
            customer_safe_summary=payload.get("customer_safe_summary"),
            internal_summary=payload["internal_summary"],
            confidence=payload.get("confidence"),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            status=status,
            error_summary=error_summary,
        )
    )


def _build_provider_prompt(
    ctx: SummaryContext, deterministic: dict, template_name: str
) -> tuple[str, str]:
    """Render the prompt template for one scope.

    Returns ``(system_prompt, user_prompt)``.  Phase 1 puts the entire
    template into the system_prompt and uses a fixed user prompt
    ("Produce the summary now.") so the model has a clear pivot.
    """
    template = load_template(template_name, "v1")

    # Structured context — counts only, no PII
    if ctx.scope == "fleet":
        ctx_payload = {
            "scope": "fleet",
            "tenant_id": ctx.tenant_id,
            "fleet": {
                "total_sites": ctx.fleet.total_sites,
                "connected_sites": ctx.fleet.connected_sites,
                "sites_needing_attention": ctx.fleet.sites_needing_attention,
                "active_incidents": ctx.fleet.active_incidents,
                "critical_incidents": ctx.fleet.critical_incidents,
                "stale_devices": ctx.fleet.stale_devices,
            },
            "open_incident_count": len(ctx.incidents),
        }
    else:
        site = ctx.site
        ctx_payload = {
            "scope": "site",
            "tenant_id": ctx.tenant_id,
            "scope_id": ctx.scope_id,
            "site_present": site is not None,
            "site": (
                {
                    "site_name": site.site_name,
                    "needs_attention": site.needs_attention,
                    "active_incidents": site.active_incidents,
                    "critical_incidents": site.critical_incidents,
                    "stale_devices": site.stale_devices,
                    "last_heartbeat_seconds_ago": site.last_heartbeat_seconds_ago,
                    "connection_status": site.connection_status,
                }
                if site is not None
                else None
            ),
            "open_incident_count": len(ctx.incidents),
        }

    # Incident summaries are operator-entered free text — UNTRUSTED.
    # The template wraps them in <untrusted_data> and instructs the
    # model never to follow instructions inside.  We still pass them
    # through json.dumps so any embedded quotes can't break the block.
    incident_summaries = [
        {
            "incident_id": i.incident_id,
            "severity": i.severity,
            "opened_minutes_ago": i.opened_minutes_ago,
            "summary": i.summary,  # untrusted by contract
        }
        for i in ctx.incidents
    ]

    system_prompt = template.replace(
        "{{ CONTEXT_JSON }}", json.dumps(ctx_payload, indent=2, default=str)
    ).replace(
        "{{ INCIDENT_SUMMARIES }}", json.dumps(incident_summaries, indent=2, default=str)
    )
    user_prompt = "Produce the JSON object now."
    return system_prompt, user_prompt


# ─── Public entry point ────────────────────────────────────────────


async def generate_health_summary(
    *,
    db: AsyncSession,
    user: User,
    scope: str,
    scope_id: Optional[str] = None,
    force_refresh: bool = False,
) -> dict:
    """Generate (or fetch cached) AI Health Summary for the caller's tenant.

    The returned dict matches :class:`app.schemas.llm.HealthSummaryResponse`.
    The function NEVER raises an upstream error — every failure path
    returns a deterministic summary with ``deterministic_fallback=True``
    and an audit row that records what went wrong.

    Tenant isolation is structural: the only SQL queries issued live
    in :class:`LLLMContext`, which filters every query on
    ``user.tenant_id``.
    """
    audit_id = _new_audit_id()
    model = settings.LLLM_DEFAULT_MODEL

    # 1) Build tenant-scoped context
    loader = LLLMContext(user=user, db=db)
    if scope == "site" and scope_id:
        ctx = await loader.load_site(scope_id)
        template_name = "site_health"
        fingerprint_dict = fingerprint_inputs_for_site(ctx)
    else:
        # default to fleet for any unrecognized scope, matching the
        # schema default and saving a 422 on a typo
        scope = "fleet"
        ctx = await loader.load_fleet()
        template_name = "fleet_health"
        fingerprint_dict = fingerprint_inputs_for_fleet(ctx)
    template_v = template_version(template_name)

    # 2) Deterministic floor — always built first
    deterministic = build_deterministic_summary(ctx)

    # 3) Cache lookup (skip on force_refresh)
    fingerprint = cache_mod.compute_data_fingerprint(fingerprint_dict)
    cache_key = cache_mod.compute_cache_key(
        tenant_id=ctx.tenant_id,
        scope=ctx.scope,
        scope_id=ctx.scope_id,
        data_fingerprint=fingerprint,
        prompt_template_version=template_v,
    )
    if not force_refresh:
        cached = await cache_mod.get_cached(db, cache_key)
        if cached is not None:
            # Stamp a fresh summary_id so each call still gets a unique
            # row in the audit log, but the payload itself is reused.
            payload = dict(cached)
            payload["summary_id"] = audit_id
            payload["source"] = "cache"
            await _persist_audit(
                db,
                audit_id=audit_id,
                user=user,
                ctx=ctx,
                payload=payload,
                model=payload.get("model", model),
                status="ok",
                template_v=template_v,
            )
            await db.commit()
            return payload

    # 4) Feature-flag / egress / provider availability gate
    flag_on = settings.FEATURE_LLLM.lower() == "true"
    egress_on = settings.LLLM_ALLOW_EXTERNAL.lower() == "true"
    provider = get_provider(settings.LLLM_PROVIDER) if (flag_on and egress_on) else None

    if not flag_on or not egress_on or provider is None:
        # Deterministic-only path
        payload = _wrap_response(
            audit_id=audit_id,
            ctx=ctx,
            deterministic=deterministic,
            chosen=deterministic,
            deterministic_fallback=True,
            model="deterministic",
            source="fallback",
        )
        await _persist_audit(
            db,
            audit_id=audit_id,
            user=user,
            ctx=ctx,
            payload=payload,
            model="deterministic",
            status="fallback",
            error_summary=(
                "feature flag off" if not flag_on
                else "egress disabled" if not egress_on
                else f"unknown provider '{settings.LLLM_PROVIDER}'"
            ),
            template_v=template_v,
        )
        await db.commit()
        return payload

    # 5) Quota check
    if not await quota_mod.has_budget(db, ctx.tenant_id):
        payload = _wrap_response(
            audit_id=audit_id,
            ctx=ctx,
            deterministic=deterministic,
            chosen=deterministic,
            deterministic_fallback=True,
            model="deterministic",
            source="fallback",
        )
        await _persist_audit(
            db,
            audit_id=audit_id,
            user=user,
            ctx=ctx,
            payload=payload,
            model="deterministic",
            status="blocked",
            error_summary="daily token cap exceeded",
            template_v=template_v,
        )
        await db.commit()
        return payload

    # 6) Provider call
    system_prompt, user_prompt = _build_provider_prompt(ctx, deterministic, template_name)
    result = await provider.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_seconds=settings.LLLM_PROVIDER_TIMEOUT_SECONDS,
        model=model,
    )

    if result.status != "ok" or not result.raw_text:
        payload = _wrap_response(
            audit_id=audit_id,
            ctx=ctx,
            deterministic=deterministic,
            chosen=deterministic,
            deterministic_fallback=True,
            model=result.model or model,
            source="fallback",
        )
        await _persist_audit(
            db,
            audit_id=audit_id,
            user=user,
            ctx=ctx,
            payload=payload,
            model=result.model or model,
            status="fallback",
            error_summary=result.error_summary or f"provider status: {result.status}",
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=result.latency_ms,
            template_v=template_v,
        )
        await db.commit()
        return payload

    # 7) Validate
    validation = validate_provider_output(result.raw_text, deterministic)
    if not validation.accepted or validation.payload is None:
        payload = _wrap_response(
            audit_id=audit_id,
            ctx=ctx,
            deterministic=deterministic,
            chosen=deterministic,
            deterministic_fallback=True,
            model=result.model or model,
            source="fallback",
        )
        await _persist_audit(
            db,
            audit_id=audit_id,
            user=user,
            ctx=ctx,
            payload=payload,
            model=result.model or model,
            status="fallback",
            error_summary=validation.reject_reason or "validator rejected output",
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=result.latency_ms,
            template_v=template_v,
        )
        await db.commit()
        return payload

    # 8) Accepted — cache + audit + return
    payload = _wrap_response(
        audit_id=audit_id,
        ctx=ctx,
        deterministic=deterministic,
        chosen=validation.payload,
        deterministic_fallback=False,
        model=result.model or model,
        source="fresh",
    )
    await cache_mod.store(
        db,
        cache_key=cache_key,
        tenant_id=ctx.tenant_id,
        scope=ctx.scope,
        scope_id=ctx.scope_id,
        data_fingerprint=fingerprint,
        payload=payload,
    )
    await _persist_audit(
        db,
        audit_id=audit_id,
        user=user,
        ctx=ctx,
        payload=payload,
        model=result.model or model,
        status="ok",
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        latency_ms=result.latency_ms,
        template_v=template_v,
    )
    await db.commit()
    return payload
