"""Output validator and PII sanitizer for LLLM responses.

Every byte the provider returns passes through here before it reaches
the audit log or the response.  The guarantee is:

  * The text is below the configured length cap.
  * No E.164 phone number, ICCID, MSISDN, IPv4 address, or email
    survives in the ``customer_safe_summary`` field.
  * No prompt-injection success markers appear in the output (we treat
    those as evidence the model was successfully attacked).
  * Confidence is clamped to [0.0, 1.0]; values below
    ``MIN_CONFIDENCE`` cause the deterministic fallback to be returned
    instead.

The deterministic builder's own output is also passed through here so
both paths are subject to the same contract — this guards against a
future change adding raw fields to the rules-based path.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("true911.llm.validator")


# Length caps — generous for the internal-only Phase 1 surface, but
# bounded enough that a runaway model can't fill the response with
# megabytes of text.
MAX_FIELD_CHARS = 800
MAX_TOTAL_CHARS = 4000
# Below this confidence we return the deterministic fallback even if
# the LLM produced a syntactically valid response.  Audit decision.
MIN_CONFIDENCE = 0.50


# Regexes for PII redaction.  Kept conservative — we'd rather over-redact
# in customer_safe_summary than leak.  internal_summary is allowed to
# retain device identifiers because the audience is the operator.
#
# Order matters: ICCID runs FIRST (most specific, 19-20 digits starting
# with '89') so phone/MSISDN regexes don't carve off a 10-digit prefix.
# Phone regexes require either a '+' prefix OR formatting separators so
# they don't fire on the 10-digit head of a raw ICCID/MSISDN run.
_PII_PATTERNS = (
    # 19-20 digit ICCID — must run before phone/MSISDN.
    (re.compile(r"\b89\d{17,18}\b"), "[REDACTED-ICCID]"),
    # International phone (must have + prefix).
    (
        re.compile(r"\+\d{1,3}[\s\-.]?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"),
        "[REDACTED-PHONE]",
    ),
    # Domestic phone (must have separators between all three parts).
    (
        re.compile(r"(?:\(\d{3}\)|\d{3})[\s\-.]\d{3}[\s\-.]\d{4}"),
        "[REDACTED-PHONE]",
    ),
    # MSISDN-style 10-15 digit run — catches anything else (raw cellular
    # numbers without separators).  Runs after phone so formatted phones
    # are already gone.
    (re.compile(r"\b\d{10,15}\b"), "[REDACTED-MSISDN]"),
    # IPv4
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED-IP]"),
    # Email
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED-EMAIL]"),
)

# Common prompt-injection success markers — strings a successful
# injection might emit.  Presence in output means the model was
# tricked and we should not surface its response.
_INJECTION_MARKERS = (
    re.compile(r"\bIGNORE\s+(PREVIOUS|ABOVE)\s+INSTRUCTIONS\b", re.IGNORECASE),
    re.compile(r"\bI\s+AM\s+NOW\s+IN\s+ADMIN\s+MODE\b", re.IGNORECASE),
    re.compile(r"\bSYSTEM\s+PROMPT\s*[:=]", re.IGNORECASE),
    re.compile(r"\bJWT_SECRET\b"),
    re.compile(r"\bANTHROPIC_API_KEY\b"),
    re.compile(r"\bDATABASE_URL\b"),
)


# ─── Public API ────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Outcome of validating a raw provider response."""

    accepted: bool
    # The cleaned payload — same keys as HealthSummaryResponse, only
    # populated when ``accepted`` is True.
    payload: Optional[dict] = None
    # Human-readable reason; recorded on the audit row when rejected.
    reject_reason: Optional[str] = None


def redact_pii(text: str) -> str:
    """Strip phone/ICCID/MSISDN/IP/email from a string.

    Pass a string through this exactly once.  The replacement markers
    look like ``[REDACTED-PHONE]`` so an operator scanning the audit
    log can see WHERE redaction happened.
    """
    if not text:
        return text
    out = text
    for pattern, replacement in _PII_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def enforce_length(text: str, max_chars: int = MAX_FIELD_CHARS) -> str:
    """Truncate to ``max_chars`` with a trailing ellipsis if needed."""
    if not text or len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def looks_like_injection(text: str) -> bool:
    """True if the text contains a known prompt-injection success marker."""
    if not text:
        return False
    return any(p.search(text) for p in _INJECTION_MARKERS)


def validate_provider_output(
    raw_text: str,
    deterministic_payload: dict,
) -> ValidationResult:
    """Parse, sanitize, and validate a raw provider response.

    The provider is asked to return strict JSON matching
    ``HealthSummaryResponse``.  This function:

      1. Strips a leading ``\\`\\`\\`json`` code fence if present (some
         providers wrap responses).
      2. Parses as JSON; rejects on parse failure.
      3. Pulls each known field, enforcing per-field length caps.
      4. Redacts PII from ``customer_safe_summary`` if populated.
      5. Scans every text field for injection markers; rejects on hit.
      6. Clamps and threshold-checks confidence.
      7. Fills ``sources_used`` from the deterministic payload — the
         provider is NOT allowed to invent source references, because
         that's the audit-row evidence trail.

    ``deterministic_payload`` is the floor — the validator never returns
    a payload that omits a field the deterministic builder produced.
    """
    if not raw_text or not raw_text.strip():
        return ValidationResult(False, reject_reason="empty provider response")

    cleaned = raw_text.strip()
    # Strip leading/trailing ```json``` code fences.
    if cleaned.startswith("```"):
        # Remove first ``` line and trailing ``` line.
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        data: Any = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("LLM output rejected: JSON parse failed (len=%d)", len(raw_text))
        return ValidationResult(False, reject_reason="provider returned non-JSON")

    if not isinstance(data, dict):
        return ValidationResult(False, reject_reason="provider response was not a JSON object")

    # Total payload size guardrail
    if len(cleaned) > MAX_TOTAL_CHARS:
        return ValidationResult(False, reject_reason=f"response exceeded {MAX_TOTAL_CHARS} chars")

    # Pull known fields with deterministic fallback per-field
    current_status = enforce_length(
        str(data.get("current_status") or deterministic_payload.get("current_status") or "").strip()
    )
    likely_issue_raw = data.get("likely_issue")
    likely_issue = enforce_length(str(likely_issue_raw).strip()) if likely_issue_raw else deterministic_payload.get("likely_issue")
    recommended_next_step = enforce_length(
        str(data.get("recommended_next_step") or deterministic_payload.get("recommended_next_step") or "").strip()
    )
    internal_summary = enforce_length(
        str(data.get("internal_summary") or deterministic_payload.get("internal_summary") or "").strip(),
        max_chars=MAX_TOTAL_CHARS,
    )

    # Injection check — applies to every text field
    for label, val in (
        ("current_status", current_status),
        ("likely_issue", likely_issue or ""),
        ("recommended_next_step", recommended_next_step),
        ("internal_summary", internal_summary),
    ):
        if looks_like_injection(val):
            logger.warning("LLM output rejected: injection marker in %s", label)
            return ValidationResult(
                False, reject_reason=f"injection marker detected in {label}"
            )

    # customer_safe_summary — Phase 1 keeps this null, but if a future
    # provider returns it we MUST run it through PII redaction.
    cs_raw = data.get("customer_safe_summary")
    customer_safe_summary = redact_pii(enforce_length(str(cs_raw).strip())) if cs_raw else None

    # Confidence clamp + threshold
    try:
        confidence = float(data.get("confidence", deterministic_payload.get("confidence", 0.5)))
    except (TypeError, ValueError):
        confidence = float(deterministic_payload.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))
    if confidence < MIN_CONFIDENCE:
        return ValidationResult(
            False,
            reject_reason=f"confidence {confidence:.2f} below threshold {MIN_CONFIDENCE}",
        )

    payload = {
        "current_status": current_status,
        "likely_issue": likely_issue,
        "recommended_next_step": recommended_next_step,
        "confidence": confidence,
        # NEVER trust provider's source list — use the one the context
        # loader actually built.  This is the audit-row evidence trail.
        "sources_used": deterministic_payload.get("sources_used", []),
        "customer_safe_summary": customer_safe_summary,
        "internal_summary": internal_summary,
        "generated_at": deterministic_payload.get("generated_at"),
    }
    return ValidationResult(True, payload=payload)
