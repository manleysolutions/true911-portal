"""Policy engine — determines status classification, uncertainty, and escalation level.

Sits between raw diagnostics and the wording layer. Produces structured values
that drive wording selection without exposing diagnostic internals.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PolicyDecision:
    """Structured policy output that drives wording selection."""
    normalized_status: str  # operational | attention_needed | service_impacted
    uncertainty_level: str  # low | medium | high
    escalation_level: str   # none | offer | recommend | urgent
    affected_service: str   # voice | connectivity | device | config | e911 | unknown
    life_safety_sensitive: bool
    issue_flags: dict       # {voice: bool, connectivity: bool, device: bool, e911: bool}


def evaluate(
    diagnostics: list[dict] | None = None,
    intent: str = "general",
    ai_response: dict | None = None,
) -> PolicyDecision:
    """Evaluate diagnostics and intent to produce a policy decision.

    This is the single place where raw diagnostic states are mapped
    to customer-facing classification levels.
    """
    diags = diagnostics or []
    ai = ai_response or {}

    # ── Classify status ──
    has_critical = any(d.get("severity") == "critical" or d.get("status") == "critical" for d in diags)
    has_warning = any(d.get("severity") == "warning" or d.get("status") == "warning" for d in diags)
    has_unknown = any(d.get("status") == "unknown" for d in diags)

    if has_critical:
        normalized_status = "service_impacted"
    elif has_warning:
        normalized_status = "attention_needed"
    else:
        normalized_status = "operational"

    # ── Identify affected service ──
    issue_flags = {"voice": False, "connectivity": False, "device": False, "e911": False}
    affected_service = "unknown"

    for d in diags:
        ct = d.get("check_type", "")
        is_bad = d.get("status") in ("warning", "critical")
        if ct == "sip_registration" and is_bad:
            issue_flags["voice"] = True
            affected_service = "voice"
        elif ct in ("heartbeat", "ata_reachability") and is_bad:
            issue_flags["connectivity"] = True
            affected_service = "connectivity"
        elif ct == "device_status" and is_bad:
            issue_flags["device"] = True
            affected_service = "device"
        elif ct == "e911" and is_bad:
            issue_flags["e911"] = True
            affected_service = "e911"

    if intent == "compliance":
        affected_service = "e911"
        issue_flags["e911"] = True
    elif intent == "voice_quality":
        affected_service = "voice"
        issue_flags["voice"] = True

    # ── Uncertainty level ──
    if not diags:
        uncertainty_level = "medium"
    elif has_unknown and not has_critical and not has_warning:
        uncertainty_level = "high"
    else:
        # Average confidence from diagnostics
        confidences = [d.get("confidence", 1.0) for d in diags]
        avg_conf = sum(confidences) / len(confidences) if confidences else 1.0
        if avg_conf < 0.4:
            uncertainty_level = "high"
        elif avg_conf < 0.7:
            uncertainty_level = "medium"
        else:
            uncertainty_level = "low"

    # ── Escalation level ──
    # Life-safety sensitive: elevator phones, fire panels, emergency phones
    # We treat all True911 devices as potentially life-safety by default
    life_safety_sensitive = True

    ai_wants_escalation = ai.get("escalate", False)
    ai_confidence = ai.get("confidence", 0.5)

    if has_critical:
        # Critical + life-safety → always urgent
        escalation_level = "urgent"
    elif has_critical and not life_safety_sensitive:
        escalation_level = "recommend"
    elif ai_wants_escalation:
        escalation_level = "recommend"
    elif has_warning and uncertainty_level == "high":
        escalation_level = "recommend"
    elif has_warning:
        escalation_level = "offer"
    elif uncertainty_level == "high":
        escalation_level = "offer"
    elif intent == "escalation_request":
        escalation_level = "offer"
    else:
        escalation_level = "none"

    return PolicyDecision(
        normalized_status=normalized_status,
        uncertainty_level=uncertainty_level,
        escalation_level=escalation_level,
        affected_service=affected_service,
        life_safety_sensitive=life_safety_sensitive,
        issue_flags=issue_flags,
    )
