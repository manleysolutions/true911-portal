"""Support orchestrator — coordinates diagnostics, policy, wording, AI, and escalation.

Flow:
  1. Classify user intent
  2. Run diagnostics if relevant
  3. Policy engine evaluates status/uncertainty/escalation
  4. Wording layer builds approved response (deterministic)
  5. LLM may enhance (if configured), but wording layer validates
  6. Final response is always sanitized through approved wording
  7. Persist transcript + structured summary
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import (
    SupportSession, SupportMessage, SupportDiagnostic, SupportAISummary,
)
from .diagnostics import run_diagnostics
from .ai_service import generate_response, classify_intent
from .support_policy import evaluate as evaluate_policy
from .wording import build_customer_response, sanitize_customer_text, pick

logger = logging.getLogger("true911.support.orchestrator")


async def create_session(
    db: AsyncSession,
    tenant_id: str,
    user_id: UUID,
    site_id: int | None = None,
    device_id: int | None = None,
    initial_message: str | None = None,
) -> tuple[SupportSession, SupportMessage | None]:
    """Create a new support session and optionally process an initial message."""

    session = SupportSession(
        tenant_id=tenant_id,
        user_id=user_id,
        site_id=site_id,
        device_id=device_id,
        status="active",
    )
    db.add(session)
    await db.flush()

    # Use approved greeting from wording library
    greeting_text = pick("greetings", "default")
    greeting = SupportMessage(
        session_id=session.id,
        role="assistant",
        content=greeting_text,
    )
    db.add(greeting)
    session.message_count = 1

    assistant_msg = None
    if initial_message:
        assistant_msg = await process_message(db, session, initial_message)

    await db.commit()
    await db.refresh(session)
    return session, assistant_msg


async def process_message(
    db: AsyncSession,
    session: SupportSession,
    user_content: str,
) -> SupportMessage:
    """Process a user message through the full pipeline:
    intent → diagnostics → policy → wording → AI → sanitize → persist.
    """

    # 1. Save user message
    user_msg = SupportMessage(
        session_id=session.id,
        role="user",
        content=user_content,
    )
    db.add(user_msg)
    session.message_count += 1

    # 2. Classify intent
    intent = classify_intent(user_content)

    # 3. Run diagnostics if relevant
    diagnostics = None
    if intent in ("device_offline", "status_check", "voice_quality", "compliance"):
        diagnostics = await _run_and_store_diagnostics(
            db, session,
            checks=_checks_for_intent(intent),
        )

    # 4. Generate response (policy + wording + optional LLM)
    # The generate_response function now internally:
    #   - evaluates policy
    #   - builds deterministic wording
    #   - calls LLM if configured
    #   - validates and sanitizes output
    history = await _get_conversation_history(db, session.id)
    ai_response = await generate_response(
        user_message=user_content,
        conversation_history=history,
        diagnostics=diagnostics,
        intent=intent,
    )

    # 5. Final sanitization (defense-in-depth)
    customer_text = sanitize_customer_text(
        ai_response.get("customer_response", pick("fallbacks", "generic"))
    )

    # 6. Apply safety rules (life-safety escalation override)
    ai_response = _apply_safety_rules(ai_response, diagnostics)

    # 7. Persist assistant message
    assistant_msg = SupportMessage(
        session_id=session.id,
        role="assistant",
        content=customer_text,
        structured_response=ai_response,
    )
    db.add(assistant_msg)
    session.message_count += 1

    # 8. Update session metadata
    if ai_response.get("issue_category") and not session.issue_category:
        session.issue_category = ai_response["issue_category"]

    # 9. Update AI summary
    await _update_ai_summary(db, session.id, ai_response, diagnostics)

    await db.flush()
    return assistant_msg


async def run_system_test(
    db: AsyncSession,
    session: SupportSession,
) -> tuple[list[dict], SupportMessage]:
    """Run full diagnostics and return customer-friendly summary."""

    diagnostics = await _run_and_store_diagnostics(db, session, checks=None)

    # Evaluate policy for overall status
    policy = evaluate_policy(diagnostics=diagnostics)

    # Use wording library for the summary
    if policy.normalized_status == "operational":
        summary_text = pick("system_test", "result_healthy")
    elif policy.normalized_status == "attention_needed":
        summary_text = pick("system_test", "result_attention")
        summary_text += " " + pick("guidance", "offer_followup")
    else:
        summary_text = pick("system_test", "result_impacted")
        from .wording import pick_random
        summary_text += " " + pick_random("escalation", "recommend")

    summary_text = sanitize_customer_text(summary_text)

    msg = SupportMessage(
        session_id=session.id,
        role="assistant",
        content=summary_text,
        structured_response={
            "has_issues": policy.normalized_status != "operational",
            "normalized_status": policy.normalized_status,
        },
    )
    db.add(msg)
    session.message_count += 1

    await db.flush()
    return diagnostics, msg


# ── Internal helpers ────────────────────────────────────────────

async def _run_and_store_diagnostics(
    db: AsyncSession,
    session: SupportSession,
    checks: list[str] | None = None,
) -> list[dict]:
    """Run diagnostics and persist results."""
    results = await run_diagnostics(
        db,
        tenant_id=session.tenant_id,
        checks=checks,
        device_id=session.device_id,
        site_id=session.site_id,
    )

    for r in results:
        diag = SupportDiagnostic(
            session_id=session.id,
            tenant_id=session.tenant_id,
            check_type=r["check_type"],
            status=r["status"],
            severity=r["severity"],
            confidence=r["confidence"],
            customer_safe_summary=r["customer_safe_summary"],
            internal_summary=r["internal_summary"],
            raw_payload=r.get("raw_payload"),
        )
        db.add(diag)

    return results


def _checks_for_intent(intent: str) -> list[str]:
    """Map intent to relevant diagnostic checks."""
    mapping = {
        "device_offline": ["heartbeat", "device_status", "ata_reachability", "incidents"],
        "status_check": ["heartbeat", "device_status", "telemetry"],
        "voice_quality": ["sip_registration", "device_status", "telemetry"],
        "compliance": ["e911"],
    }
    return mapping.get(intent, ["heartbeat", "device_status"])


def _apply_safety_rules(ai_response: dict, diagnostics: list[dict] | None) -> dict:
    """Life-safety escalation override — policy has already set this, but defense-in-depth."""
    if diagnostics:
        has_critical = any(d.get("severity") == "critical" for d in diagnostics)
        if has_critical and not ai_response.get("escalate"):
            ai_response["escalate"] = True
            reason = ai_response.get("escalation_reason", "")
            ai_response["escalation_reason"] = (
                f"{reason} [Safety override: critical diagnostic]"
            ).strip()

    if not ai_response.get("customer_response"):
        ai_response["customer_response"] = pick("fallbacks", "generic")

    return ai_response


async def _get_conversation_history(db: AsyncSession, session_id: UUID) -> list[dict]:
    result = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.session_id == session_id)
        .order_by(SupportMessage.created_at.asc())
        .limit(20)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]


async def _update_ai_summary(
    db: AsyncSession,
    session_id: UUID,
    ai_response: dict,
    diagnostics: list[dict] | None,
):
    result = await db.execute(
        select(SupportAISummary).where(SupportAISummary.session_id == session_id)
    )
    summary = result.scalar_one_or_none()

    diag_summary = None
    if diagnostics:
        diag_summary = {d["check_type"]: d["status"] for d in diagnostics}

    if summary:
        summary.issue_category = ai_response.get("issue_category") or summary.issue_category
        summary.probable_cause = ai_response.get("probable_cause") or summary.probable_cause
        summary.confidence = ai_response.get("confidence", summary.confidence)
        summary.diagnostics_run = diag_summary or summary.diagnostics_run
        summary.recommended_actions = ai_response.get("recommended_actions") or summary.recommended_actions
        summary.escalated = ai_response.get("escalate", summary.escalated)
    else:
        summary = SupportAISummary(
            session_id=session_id,
            issue_category=ai_response.get("issue_category"),
            probable_cause=ai_response.get("probable_cause"),
            confidence=ai_response.get("confidence", 0.0),
            diagnostics_run=diag_summary,
            recommended_actions=ai_response.get("recommended_actions"),
            escalated=ai_response.get("escalate", False),
        )
        db.add(summary)
