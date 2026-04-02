"""Prompt template builder for the support LLM.

Constructs constrained prompts that:
- include diagnostic context
- specify allowed/forbidden wording categories
- enforce structured JSON output
- bias toward approved phrasing
"""

from __future__ import annotations

from .wording import WORDING, pick_random


def build_support_prompt(
    diagnostics_summary: str,
    conversation_history: str,
    intent: str = "general",
    normalized_status: str = "operational",
    escalation_level: str = "none",
    affected_service: str = "unknown",
    life_safety_sensitive: bool = True,
) -> str:
    """Build the full system prompt for the LLM."""

    # Gather approved phrasing examples for this context
    status_key = {
        "operational": "operational",
        "attention_needed": "attention_needed",
        "service_impacted": "service_impacted",
    }.get(normalized_status, "operational")

    approved_status = WORDING["status"].get(status_key, [])
    approved_escalation = WORDING["escalation"].get(escalation_level, []) if escalation_level != "none" else []
    approved_guidance = []
    for subcat in WORDING.get("guidance", {}).values():
        if isinstance(subcat, list):
            approved_guidance.extend(subcat[:2])

    # Build the approved wording block
    wording_block = "APPROVED STATUS PHRASES:\n"
    for phrase in approved_status:
        wording_block += f'  - "{phrase}"\n'
    if approved_escalation:
        wording_block += "APPROVED ESCALATION PHRASES:\n"
        for phrase in approved_escalation:
            wording_block += f'  - "{phrase}"\n'
    if approved_guidance:
        wording_block += "APPROVED GUIDANCE PHRASES:\n"
        for phrase in approved_guidance[:4]:
            wording_block += f'  - "{phrase}"\n'

    # Life-safety instruction
    safety_instruction = ""
    if life_safety_sensitive:
        safety_instruction = (
            "\nLIFE-SAFETY NOTE: These devices may serve elevators, fire panels, or emergency phones. "
            "When in doubt, recommend escalation to human support. Never downplay potential issues."
        )

    return f"""\
You are the True911+ Support Assistant helping customers with life-safety \
communication devices (elevator phones, fire panels, emergency phones).

RULES — MANDATORY:
1. Use calm, plain, non-alarming language. No technical jargon.
2. Never mention: SIP, ATA, telemetry, heartbeat, payload, stack trace, \
carrier failure, provider failure, debug, confidence percentages.
3. Never fabricate device status. Only state what diagnostics confirm.
4. Never expose internal incident IDs, error codes, or raw diagnostic output.
5. Keep responses to 2–4 sentences maximum.
6. Prefer the approved phrasing below over your own wording.
7. If uncertain about status, say so honestly and offer escalation.
8. If diagnostics show a critical issue, recommend contacting support.
{safety_instruction}

{wording_block}
FORBIDDEN TERMS (never use in customer_response):
  SIP, ATA, telemetry, heartbeat, payload, traceback, stacktrace, debug, \
  registration failure, transport instability, carrier failure, provider failure, \
  critical incident detected, confidence percentages (e.g. "85%", "0.7")

CURRENT CONTEXT:
  Intent: {intent}
  System Status: {normalized_status}
  Affected Service: {affected_service}
  Escalation Level: {escalation_level}

DIAGNOSTIC SUMMARY:
{diagnostics_summary}

CONVERSATION:
{conversation_history}

Respond with ONLY valid JSON matching this exact structure:
{{
  "issue_category": "connectivity | device_offline | voice_quality | compliance | general | escalation_request",
  "probable_cause": "brief technical cause (admin-only, not shown to customer)",
  "customer_response": "the message shown to the customer — use approved phrasing",
  "recommended_actions": ["array of plain-language action strings for the customer"],
  "escalate": {"true" if escalation_level in ("recommend", "urgent") else "false"},
  "escalation_reason": "why escalation is needed (admin-only)",
  "confidence": 0.0
}}"""


def build_diagnostics_summary(diagnostics: list[dict] | None) -> str:
    """Format diagnostics for prompt inclusion — using customer-safe summaries only."""
    if not diagnostics:
        return "No diagnostics have been run yet."

    lines = []
    for d in diagnostics:
        status = d.get("status", "unknown")
        summary = d.get("customer_safe_summary", "Check pending")
        check = d.get("check_type", "unknown")
        # Map check_type to customer-friendly label
        label = {
            "heartbeat": "Device responsiveness",
            "device_status": "Device status",
            "sip_registration": "Voice service",
            "telemetry": "System data",
            "ata_reachability": "Device reachability",
            "incidents": "Active issues",
            "e911": "E911 compliance",
            "zoho_ticket": "Support tickets",
        }.get(check, check)
        lines.append(f"- {label}: {status.upper()} — {summary}")

    return "\n".join(lines)
