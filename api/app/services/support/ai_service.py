"""AI layer for the support assistant.

Uses the wording library as the source of truth for customer tone.
The LLM may assist with phrasing but output is always validated
against approved wording and sanitized before delivery.

Flow:
  1. Policy engine determines status/uncertainty/escalation
  2. Wording layer builds a deterministic preferred response
  3. LLM is called (if configured) with constrained prompt
  4. LLM output is sanitized and validated
  5. If LLM output is weak/malformed, deterministic response is used instead
"""

from __future__ import annotations

import json
import logging

from app.config import settings

from .wording import (
    build_customer_response,
    sanitize_customer_text,
    pick_random,
    StructuredCustomerResponse,
)
from .support_policy import PolicyDecision, evaluate as evaluate_policy
from .prompt_templates import build_support_prompt, build_diagnostics_summary

logger = logging.getLogger("true911.support.ai")


async def generate_response(
    user_message: str,
    conversation_history: list[dict],
    diagnostics: list[dict] | None = None,
    intent: str = "general",
) -> dict:
    """Generate an AI response with approved wording enforcement.

    Returns structured dict matching AIStructuredResponse schema.
    The customer_response field is always sanitized and drawn from
    approved wording — even when an LLM is used.
    """

    # 1. Policy evaluation
    policy = evaluate_policy(diagnostics=diagnostics, intent=intent)

    # 2. Build deterministic response (always available as fallback)
    deterministic = build_customer_response(
        intent=intent,
        normalized_status=policy.normalized_status,
        issue_flags=policy.issue_flags,
        uncertainty_level=policy.uncertainty_level,
        escalation_level=policy.escalation_level,
        e911_flag=policy.issue_flags.get("e911", False),
    )

    # 3. Try LLM if configured
    anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            llm_response = await _call_anthropic(
                user_message=user_message,
                conversation_history=conversation_history,
                diagnostics=diagnostics,
                intent=intent,
                policy=policy,
                api_key=anthropic_key,
            )

            # 4. Validate and sanitize LLM output
            validated = _validate_llm_output(llm_response, deterministic, policy)
            return validated

        except Exception:
            logger.exception("LLM call failed, using deterministic response")

    # 5. Fallback: pure deterministic response
    return _build_deterministic_output(intent, policy, deterministic, diagnostics)


def _build_deterministic_output(
    intent: str,
    policy: PolicyDecision,
    response: StructuredCustomerResponse,
    diagnostics: list[dict] | None,
) -> dict:
    """Build a full structured output dict from the deterministic wording layer."""

    # Map escalation level to escalate flag
    escalate = policy.escalation_level in ("recommend", "urgent")

    # Build recommended actions
    actions = _recommended_actions_for_intent(intent, policy)

    return {
        "issue_category": _category_for_intent(intent, policy),
        "probable_cause": _internal_probable_cause(diagnostics, policy),
        "customer_response": response.full_response,
        "recommended_actions": actions,
        "escalate": escalate,
        "escalation_reason": _escalation_reason(policy) if escalate else "",
        "confidence": _confidence_from_policy(policy),
    }


def _validate_llm_output(
    llm_response: dict,
    deterministic: StructuredCustomerResponse,
    policy: PolicyDecision,
) -> dict:
    """Validate LLM output. Sanitize customer_response. Fall back to deterministic if weak."""

    # Must have customer_response
    customer_text = llm_response.get("customer_response", "")
    if not customer_text or len(customer_text) < 10:
        logger.warning("LLM output missing customer_response, using deterministic")
        llm_response["customer_response"] = deterministic.full_response
    else:
        # Sanitize whatever the LLM produced
        llm_response["customer_response"] = sanitize_customer_text(customer_text)

    # Enforce escalation policy — LLM cannot override urgent escalation
    if policy.escalation_level == "urgent":
        llm_response["escalate"] = True
        if not llm_response.get("escalation_reason"):
            llm_response["escalation_reason"] = _escalation_reason(policy)

    # Ensure required fields exist
    llm_response.setdefault("issue_category", "general")
    llm_response.setdefault("probable_cause", "")
    llm_response.setdefault("recommended_actions", [])
    llm_response.setdefault("escalate", False)
    llm_response.setdefault("escalation_reason", "")
    llm_response.setdefault("confidence", 0.5)

    return llm_response


async def _call_anthropic(
    user_message: str,
    conversation_history: list[dict],
    diagnostics: list[dict] | None,
    intent: str,
    policy: PolicyDecision,
    api_key: str,
) -> dict:
    """Call Claude API with constrained prompt."""
    import httpx

    # Build prompt using templates
    diag_summary = build_diagnostics_summary(diagnostics)
    conv_lines = []
    for msg in conversation_history[-10:]:
        conv_lines.append(f"{msg['role'].upper()}: {msg['content']}")
    conv_lines.append(f"USER: {user_message}")
    conv_text = "\n".join(conv_lines)

    system_prompt = build_support_prompt(
        diagnostics_summary=diag_summary,
        conversation_history=conv_text,
        intent=intent,
        normalized_status=policy.normalized_status,
        escalation_level=policy.escalation_level,
        affected_service=policy.affected_service,
        life_safety_sensitive=policy.life_safety_sensitive,
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
        )
        resp.raise_for_status()
        data = resp.json()

    text = data["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON, wrapping as customer_response")
        return {"customer_response": text}


def classify_intent(message: str) -> str:
    """Quick intent classification — used for routing before diagnostics."""
    msg_lower = message.lower()
    if any(w in msg_lower for w in ["offline", "down", "not working", "dead", "no dial tone", "no connection"]):
        return "device_offline"
    if any(w in msg_lower for w in ["e911", "911", "compliance", "kari", "baum", "address", "location"]):
        return "compliance"
    if any(w in msg_lower for w in ["voice", "call", "audio", "static", "echo", "quality"]):
        return "voice_quality"
    if any(w in msg_lower for w in ["help", "human", "agent", "talk", "call me", "ticket", "person"]):
        return "escalation_request"
    if any(w in msg_lower for w in ["test", "check", "status", "how is", "working"]):
        return "status_check"
    return "general"


# ── Helpers ─────────────────────────────────────────────────────

def _category_for_intent(intent: str, policy: PolicyDecision) -> str:
    mapping = {
        "device_offline": "device_offline",
        "voice_quality": "voice_quality",
        "compliance": "compliance",
        "escalation_request": "escalation_request",
        "status_check": "general",
    }
    return mapping.get(intent, "general")


def _recommended_actions_for_intent(intent: str, policy: PolicyDecision) -> list[str]:
    actions = []
    if policy.normalized_status == "operational":
        actions.append("Run a system test to confirm everything is working")
    elif policy.normalized_status == "attention_needed":
        actions.append("Run a system test for more details")
        actions.append("Contact support if the issue persists")
    elif policy.normalized_status == "service_impacted":
        actions.append("Contact support for immediate assistance")

    if policy.issue_flags.get("e911"):
        actions.append("Update your E911 location information")

    if not actions:
        actions.append("Run a system test")
        actions.append("Contact support if you need help")

    return actions


def _internal_probable_cause(diagnostics: list[dict] | None, policy: PolicyDecision) -> str:
    """Build admin-only probable cause string from diagnostics."""
    if not diagnostics:
        return ""
    failing = [d for d in diagnostics if d.get("status") in ("warning", "critical")]
    if not failing:
        return "All diagnostics passed"
    parts = [f"{d['check_type']}={d['status']}" for d in failing]
    return f"Failing checks: {', '.join(parts)}. Affected: {policy.affected_service}"


def _escalation_reason(policy: PolicyDecision) -> str:
    reasons = []
    if policy.normalized_status == "service_impacted":
        reasons.append("service impact detected")
    if policy.life_safety_sensitive:
        reasons.append("life-safety device")
    if policy.uncertainty_level == "high":
        reasons.append("high uncertainty")
    return f"Auto-escalation: {', '.join(reasons)}" if reasons else "Policy-driven escalation"


def _confidence_from_policy(policy: PolicyDecision) -> float:
    mapping = {"low": 0.85, "medium": 0.6, "high": 0.35}
    return mapping.get(policy.uncertainty_level, 0.6)
