"""Approved wording library and response assembler for customer-facing support.

This module is the single source of truth for customer tone. Every phrase
shown to a subscriber must originate from or be validated against this library.

The LLM may assist with phrasing, but the wording layer has final say.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════
# WORDING LIBRARY
# ═══════════════════════════════════════════════════════════════════

WORDING: dict[str, dict] = {
    "greetings": {
        "default": [
            "Hi, I'm here to help. I can check your system, run a quick test, or connect you with support.",
        ],
        "attention": [
            "Hi, I'm here to help. I'm seeing that your system may need attention — I can run a quick check or connect you with support.",
        ],
    },

    "acknowledgements": {
        "checking": [
            "I'm checking that now.",
            "Let me take a look.",
            "I'm reviewing your system.",
        ],
        "can_help": [
            "I can help with that.",
            "I'm here to help.",
        ],
    },

    "status": {
        "operational": [
            "Your system appears to be operating normally.",
            "Everything looks good right now.",
            "No active service issue is currently detected.",
        ],
        "attention_needed": [
            "Your system may need attention.",
            "A temporary issue may be affecting service.",
            "Something may be impacting your system, but it may resolve on its own.",
        ],
        "service_impacted": [
            "Your service may currently be impacted.",
            "We're seeing signs that your service may not be working as expected.",
            "This may be affecting service availability.",
        ],
    },

    "diagnostic_summaries": {
        "device_online_voice_issue": [
            "Your device appears to be online, but the voice connection may need attention.",
        ],
        "connectivity_issue": [
            "It looks like there may be a connectivity issue affecting your system.",
        ],
        "intermittent_issue": [
            "Your system may be experiencing a temporary interruption.",
        ],
        "uncertain": [
            "I'm not able to fully confirm the current status right now.",
        ],
    },

    "system_test": {
        "running": "Running a quick system check now.",
        "step_device": "Checking device status…",
        "step_connection": "Checking connection…",
        "step_service": "Checking service availability…",
        "result_healthy": "Your device appears to be operating normally.",
        "result_attention": "Your system may need attention.",
        "result_impacted": "We could not confirm normal service.",
    },

    "guidance": {
        "offer_test": [
            "Would you like me to run a quick test?",
            "You can run a system check to confirm everything is working.",
        ],
        "check_power": [
            "You may want to confirm the device has power.",
        ],
        "try_test": [
            "You can try a quick system test to gather more information.",
        ],
        "offer_followup": [
            "If the issue continues, I can connect you with support.",
            "This may resolve on its own, but I can help you check further.",
        ],
    },

    "escalation": {
        "offer": [
            "If you'd like, I can connect you with support.",
            "I can send this to a support specialist for review.",
        ],
        "recommend": [
            "I recommend contacting support to take a closer look.",
            "This may require assistance from our support team.",
        ],
        "urgent": [
            "Because this may affect service availability, I recommend contacting support now.",
            "This may impact critical service. I recommend requesting support immediately.",
        ],
    },

    "human_support": {
        "offer": "I can send your request to a support specialist.",
        "submitted": "Your support request has been submitted.",
        "context_included": "We've included the checks already completed so you don't need to repeat them.",
        "followup": "Our team will review this and follow up as soon as possible.",
    },

    "uncertainty": {
        "low": [
            "I'm not fully certain about the cause, but I can help you check further.",
            "I'm unable to confirm all details right now.",
        ],
        "recommend_support": [
            "I recommend contacting support to ensure everything is working correctly.",
        ],
    },

    "e911": {
        "needs_update": [
            "Your location information may need to be updated.",
        ],
        "guide": [
            "I can help guide you through updating your location details.",
        ],
        "recommend_support": [
            "This is important for emergency services. I recommend contacting support to update it.",
        ],
    },

    "reassurance": {
        "here_to_help": [
            "I'm here to help.",
            "You're in the right place to get this checked.",
        ],
        "will_resolve": [
            "We'll make sure this gets resolved.",
        ],
        "next_steps": [
            "I can guide you through the next steps.",
        ],
    },

    "fallbacks": {
        "generic": [
            "I'm here to help with your system. I can check status, run a test, or connect you with support.",
        ],
        "error": [
            "I wasn't able to process that right now. You can try again or request human support.",
        ],
    },
}


def pick(category: str, subcategory: str, index: int = 0) -> str:
    """Pick an approved phrase. Returns first match or empty string."""
    cat = WORDING.get(category, {})
    val = cat.get(subcategory)
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list) and val:
        return val[min(index, len(val) - 1)]
    return ""


def pick_random(category: str, subcategory: str) -> str:
    """Pick a random approved phrase from the specified category."""
    cat = WORDING.get(category, {})
    val = cat.get(subcategory)
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list) and val:
        return random.choice(val)
    return ""


# ═══════════════════════════════════════════════════════════════════
# SANITIZER
# ═══════════════════════════════════════════════════════════════════

# Targeted replacements: match whole phrases or technical terms.
# Each tuple is (pattern, replacement). Patterns are checked case-insensitively.
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    ("sip registration failed", "voice connection may need attention"),
    ("sip registration", "voice connection"),
    ("registration failure", "connection issue"),
    ("heartbeat missed", "device may not be responding"),
    ("heartbeat timeout", "device may not be responding"),
    ("heartbeat exception", "device may not be responding"),
    ("ata unreachable", "device may not be reachable"),
    ("ata offline", "device may not be reachable"),
    ("ata observer fault", "device may need attention"),
    ("telemetry stale", "status may not be up to date"),
    ("critical incident detected", "a potential issue has been identified"),
    ("critical incident", "potential issue"),
    ("transport instability", "connection issue"),
    ("carrier failure", "service interruption"),
    ("provider failure", "service interruption"),
    ("stack trace", ""),
    ("traceback", ""),
    ("exception:", "issue:"),
]

# Individual technical terms that should never appear in customer text.
FORBIDDEN_WORDS: set[str] = {
    "sip", "ata", "telemetry", "heartbeat", "payload", "traceback",
    "stacktrace", "debug", "raw_payload", "internal_summary",
}


def sanitize_customer_text(text: str) -> str:
    """Remove or replace technical/internal language from customer-facing text.

    Uses targeted phrase replacement — not naive substring matching that
    would break normal prose (e.g. "assist" contains "sip" but is fine).
    """
    if not text:
        return text

    result = text

    # Phase 1: Replace known technical phrases (case-insensitive)
    for pattern, replacement in FORBIDDEN_PATTERNS:
        # Use word-boundary-aware replacement to avoid breaking normal words
        import re
        result = re.sub(
            r'\b' + re.escape(pattern) + r'\b',
            replacement,
            result,
            flags=re.IGNORECASE,
        )

    # Phase 2: Check for standalone forbidden technical terms
    # Only flag words that appear as standalone tokens, not inside other words
    for word in FORBIDDEN_WORDS:
        import re
        # Match the word as a standalone token (not part of "assist", "simple", etc.)
        if re.search(r'\b' + re.escape(word) + r'\b', result, re.IGNORECASE):
            # Replace with a generic safe term
            result = re.sub(
                r'\b' + re.escape(word) + r'\b',
                _safe_replacement(word),
                result,
                flags=re.IGNORECASE,
            )

    # Phase 3: Strip confidence percentages (e.g. "confidence: 85%", "0.85 confidence")
    import re
    result = re.sub(r'\b(?:confidence[:\s]+)?\d+(?:\.\d+)?%?\s*(?:confidence)?\b', '', result, flags=re.IGNORECASE)

    # Clean up double spaces
    result = " ".join(result.split())
    return result.strip()


def _safe_replacement(word: str) -> str:
    """Map a forbidden technical term to a safe alternative."""
    replacements = {
        "sip": "voice service",
        "ata": "device",
        "telemetry": "system data",
        "heartbeat": "check-in",
        "payload": "data",
        "traceback": "",
        "stacktrace": "",
        "debug": "",
        "raw_payload": "",
        "internal_summary": "",
    }
    return replacements.get(word.lower(), "")


# ═══════════════════════════════════════════════════════════════════
# RESPONSE ASSEMBLER
# ═══════════════════════════════════════════════════════════════════

@dataclass
class StructuredCustomerResponse:
    """Assembled customer-facing response with named sections."""
    acknowledgement: str = ""
    summary: str = ""
    next_step: str = ""
    escalation_message: str = ""
    reassurance: str = ""

    @property
    def full_response(self) -> str:
        """Assemble into a concise 2–4 sentence response."""
        parts = [p for p in [
            self.acknowledgement,
            self.summary,
            self.next_step,
            self.escalation_message,
            self.reassurance,
        ] if p]
        return " ".join(parts)


def build_customer_response(
    intent: str,
    normalized_status: str,
    issue_flags: dict | None = None,
    uncertainty_level: str = "low",
    escalation_level: str = "none",
    e911_flag: bool = False,
    context: dict | None = None,
) -> StructuredCustomerResponse:
    """Build an approved customer response from structured policy inputs.

    Args:
        intent: device_offline | voice_quality | compliance | status_check | escalation_request | general
        normalized_status: operational | attention_needed | service_impacted
        issue_flags: dict with keys like "voice", "connectivity", "device" (True/False)
        uncertainty_level: low | medium | high
        escalation_level: none | offer | recommend | urgent
        e911_flag: True if E911 issue detected
        context: optional extra context
    """
    flags = issue_flags or {}
    resp = StructuredCustomerResponse()

    # 1. Acknowledgement
    if intent == "escalation_request":
        resp.acknowledgement = pick("human_support", "offer")
    elif intent in ("device_offline", "voice_quality"):
        resp.acknowledgement = pick_random("acknowledgements", "checking")
    else:
        resp.acknowledgement = pick_random("acknowledgements", "can_help")

    # 2. Summary — what is known
    if e911_flag:
        resp.summary = pick_random("e911", "needs_update")
    elif normalized_status == "operational":
        resp.summary = pick_random("status", "operational")
    elif normalized_status == "attention_needed":
        # Pick a more specific summary if we know the issue type
        if flags.get("voice"):
            resp.summary = pick("diagnostic_summaries", "device_online_voice_issue")
        elif flags.get("connectivity"):
            resp.summary = pick("diagnostic_summaries", "connectivity_issue")
        else:
            resp.summary = pick_random("status", "attention_needed")
    elif normalized_status == "service_impacted":
        resp.summary = pick_random("status", "service_impacted")
    else:
        resp.summary = pick_random("status", "operational")

    # Handle high uncertainty — override summary
    if uncertainty_level == "high":
        resp.summary = pick_random("uncertainty", "low")

    # 3. Next step
    if intent == "escalation_request":
        resp.next_step = ""  # Escalation message handles this
    elif e911_flag:
        resp.next_step = pick_random("e911", "guide")
    elif normalized_status == "operational":
        resp.next_step = pick_random("guidance", "offer_test")
    elif uncertainty_level == "high":
        resp.next_step = pick_random("uncertainty", "recommend_support")
    else:
        resp.next_step = pick_random("guidance", "offer_followup")

    # 4. Escalation message
    if escalation_level == "urgent":
        resp.escalation_message = pick_random("escalation", "urgent")
    elif escalation_level == "recommend":
        resp.escalation_message = pick_random("escalation", "recommend")
    elif escalation_level == "offer":
        resp.escalation_message = pick_random("escalation", "offer")
    # 'none' → no escalation message

    # E911 always recommends support
    if e911_flag and escalation_level == "none":
        resp.escalation_message = pick_random("e911", "recommend_support")

    # 5. Reassurance (only when issue detected, keep it brief)
    if normalized_status in ("attention_needed", "service_impacted"):
        resp.reassurance = pick_random("reassurance", "will_resolve")
    elif intent == "escalation_request":
        resp.reassurance = ""

    # Sanitize the assembled response
    resp.acknowledgement = sanitize_customer_text(resp.acknowledgement)
    resp.summary = sanitize_customer_text(resp.summary)
    resp.next_step = sanitize_customer_text(resp.next_step)
    resp.escalation_message = sanitize_customer_text(resp.escalation_message)
    resp.reassurance = sanitize_customer_text(resp.reassurance)

    return resp
