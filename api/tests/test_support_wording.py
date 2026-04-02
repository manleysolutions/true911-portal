"""Tests for the support wording library, sanitizer, policy engine, and response assembler.

Covers:
  1. Operational status wording
  2. Attention-needed wording
  3. Service-impacted wording
  4. Uncertainty wording
  5. E911 wording
  6. Urgent escalation wording
  7. Sanitizer blocks technical terms
  8. Deterministic fallback for malformed LLM output
  9. Response length stays concise
  10. Subscriber response never includes forbidden phrases
"""

import pytest

from app.services.support.wording import (
    WORDING,
    pick,
    pick_random,
    sanitize_customer_text,
    build_customer_response,
    StructuredCustomerResponse,
    FORBIDDEN_WORDS,
)
from app.services.support.support_policy import evaluate, PolicyDecision
from app.services.support.ai_service import classify_intent


# ═══════════════════════════════════════════════════════════════════
# 1. Operational status wording
# ═══════════════════════════════════════════════════════════════════

class TestOperationalWording:
    def test_operational_response_is_calm(self):
        resp = build_customer_response(
            intent="status_check",
            normalized_status="operational",
        )
        assert "operating normally" in resp.summary or "looks good" in resp.summary or "No active" in resp.summary

    def test_operational_has_no_escalation(self):
        resp = build_customer_response(
            intent="general",
            normalized_status="operational",
            escalation_level="none",
        )
        assert resp.escalation_message == ""

    def test_full_response_is_nonempty(self):
        resp = build_customer_response(intent="general", normalized_status="operational")
        assert len(resp.full_response) > 20


# ═══════════════════════════════════════════════════════════════════
# 2. Attention-needed wording
# ═══════════════════════════════════════════════════════════════════

class TestAttentionNeededWording:
    def test_attention_response_is_non_alarming(self):
        resp = build_customer_response(
            intent="device_offline",
            normalized_status="attention_needed",
        )
        text = resp.full_response.lower()
        assert "may" in text or "temporary" in text
        assert "critical" not in text
        assert "failed" not in text

    def test_voice_issue_uses_specific_summary(self):
        resp = build_customer_response(
            intent="voice_quality",
            normalized_status="attention_needed",
            issue_flags={"voice": True},
        )
        assert "voice" in resp.summary.lower()


# ═══════════════════════════════════════════════════════════════════
# 3. Service-impacted wording
# ═══════════════════════════════════════════════════════════════════

class TestServiceImpactedWording:
    def test_impacted_mentions_impact(self):
        resp = build_customer_response(
            intent="device_offline",
            normalized_status="service_impacted",
            escalation_level="urgent",
        )
        text = resp.full_response.lower()
        assert "impact" in text or "not be working" in text or "affecting service" in text

    def test_impacted_includes_escalation(self):
        resp = build_customer_response(
            intent="device_offline",
            normalized_status="service_impacted",
            escalation_level="urgent",
        )
        assert resp.escalation_message != ""

    def test_impacted_includes_reassurance(self):
        resp = build_customer_response(
            intent="device_offline",
            normalized_status="service_impacted",
        )
        assert resp.reassurance != ""


# ═══════════════════════════════════════════════════════════════════
# 4. Uncertainty wording
# ═══════════════════════════════════════════════════════════════════

class TestUncertaintyWording:
    def test_high_uncertainty_admits_it(self):
        resp = build_customer_response(
            intent="general",
            normalized_status="attention_needed",
            uncertainty_level="high",
        )
        text = resp.full_response.lower()
        assert "not fully certain" in text or "unable to confirm" in text

    def test_high_uncertainty_recommends_support(self):
        resp = build_customer_response(
            intent="device_offline",
            normalized_status="attention_needed",
            uncertainty_level="high",
        )
        text = resp.next_step.lower()
        assert "support" in text or "contact" in text


# ═══════════════════════════════════════════════════════════════════
# 5. E911 wording
# ═══════════════════════════════════════════════════════════════════

class TestE911Wording:
    def test_e911_mentions_location(self):
        resp = build_customer_response(
            intent="compliance",
            normalized_status="operational",
            e911_flag=True,
        )
        assert "location" in resp.summary.lower()

    def test_e911_recommends_support(self):
        resp = build_customer_response(
            intent="compliance",
            normalized_status="operational",
            e911_flag=True,
            escalation_level="none",
        )
        assert "support" in resp.escalation_message.lower() or "emergency" in resp.escalation_message.lower()


# ═══════════════════════════════════════════════════════════════════
# 6. Urgent escalation wording
# ═══════════════════════════════════════════════════════════════════

class TestUrgentEscalation:
    def test_urgent_uses_strong_language(self):
        resp = build_customer_response(
            intent="device_offline",
            normalized_status="service_impacted",
            escalation_level="urgent",
        )
        text = resp.escalation_message.lower()
        assert "recommend" in text
        assert "now" in text or "immediately" in text

    def test_offer_is_softer(self):
        resp = build_customer_response(
            intent="general",
            normalized_status="attention_needed",
            escalation_level="offer",
        )
        text = resp.escalation_message.lower()
        assert "if you" in text or "i can" in text


# ═══════════════════════════════════════════════════════════════════
# 7. Sanitizer blocks technical terms
# ═══════════════════════════════════════════════════════════════════

class TestSanitizer:
    def test_blocks_sip_registration_failed(self):
        result = sanitize_customer_text("SIP registration failed due to transport instability")
        assert "sip" not in result.lower()
        assert "registration failed" not in result.lower()
        assert "transport instability" not in result.lower()

    def test_blocks_heartbeat_missed(self):
        result = sanitize_customer_text("Heartbeat missed for device 42")
        assert "heartbeat" not in result.lower()
        assert "may not be responding" in result.lower()

    def test_blocks_ata_unreachable(self):
        result = sanitize_customer_text("ATA unreachable on port 5060")
        assert "ata" not in result.lower()

    def test_blocks_telemetry_stale(self):
        result = sanitize_customer_text("Telemetry stale for 3 hours")
        assert "telemetry" not in result.lower()

    def test_blocks_critical_incident_detected(self):
        result = sanitize_customer_text("Critical incident detected in zone 3")
        assert "critical incident detected" not in result.lower()

    def test_blocks_confidence_percentages(self):
        result = sanitize_customer_text("Device status confidence: 85%")
        assert "85%" not in result
        assert "confidence" not in result.lower()

    def test_preserves_normal_prose(self):
        normal = "Your device appears to be operating normally."
        result = sanitize_customer_text(normal)
        assert result == normal

    def test_does_not_break_assist(self):
        """'assist' contains 'sip' as a substring — must not be corrupted."""
        text = "I can assist you with that."
        result = sanitize_customer_text(text)
        assert "assist" in result

    def test_does_not_break_simple(self):
        """'simple' contains no forbidden terms — must remain intact."""
        text = "This is a simple check."
        result = sanitize_customer_text(text)
        assert "simple" in result


# ═══════════════════════════════════════════════════════════════════
# 8. Deterministic fallback for malformed LLM output
# ═══════════════════════════════════════════════════════════════════

class TestDeterministicFallback:
    def test_fallback_produces_valid_response(self):
        resp = build_customer_response(
            intent="general",
            normalized_status="operational",
        )
        assert isinstance(resp, StructuredCustomerResponse)
        assert len(resp.full_response) > 0
        assert resp.acknowledgement != ""
        assert resp.summary != ""

    def test_all_intents_produce_responses(self):
        for intent in ["device_offline", "voice_quality", "compliance",
                       "escalation_request", "status_check", "general"]:
            resp = build_customer_response(
                intent=intent,
                normalized_status="attention_needed",
            )
            assert len(resp.full_response) > 10, f"Empty response for intent={intent}"


# ═══════════════════════════════════════════════════════════════════
# 9. Response length stays concise
# ═══════════════════════════════════════════════════════════════════

class TestResponseLength:
    def test_response_under_500_chars(self):
        """Customer responses should be 2-4 sentences, well under 500 chars."""
        for status in ["operational", "attention_needed", "service_impacted"]:
            resp = build_customer_response(
                intent="device_offline",
                normalized_status=status,
                escalation_level="offer",
            )
            assert len(resp.full_response) < 500, (
                f"Response too long for status={status}: {len(resp.full_response)} chars"
            )

    def test_response_has_reasonable_sentence_count(self):
        resp = build_customer_response(
            intent="general",
            normalized_status="operational",
        )
        sentences = [s.strip() for s in resp.full_response.split(".") if s.strip()]
        assert 1 <= len(sentences) <= 6


# ═══════════════════════════════════════════════════════════════════
# 10. Subscriber response never includes forbidden phrases
# ═══════════════════════════════════════════════════════════════════

class TestNoForbiddenPhrases:
    """Run all possible combinations and verify no forbidden terms leak."""

    INTENTS = ["device_offline", "voice_quality", "compliance",
               "escalation_request", "status_check", "general"]
    STATUSES = ["operational", "attention_needed", "service_impacted"]
    ESCALATIONS = ["none", "offer", "recommend", "urgent"]

    def test_no_forbidden_words_in_any_combination(self):
        import re
        for intent in self.INTENTS:
            for status in self.STATUSES:
                for esc in self.ESCALATIONS:
                    resp = build_customer_response(
                        intent=intent,
                        normalized_status=status,
                        escalation_level=esc,
                    )
                    text = resp.full_response.lower()
                    for word in ["sip", "ata", "telemetry", "heartbeat",
                                 "payload", "traceback", "stacktrace", "debug"]:
                        # Use word boundary check to avoid false positives
                        assert not re.search(r'\b' + re.escape(word) + r'\b', text), (
                            f"Forbidden word '{word}' found in response for "
                            f"intent={intent} status={status} esc={esc}: {resp.full_response}"
                        )


# ═══════════════════════════════════════════════════════════════════
# Policy engine tests
# ═══════════════════════════════════════════════════════════════════

class TestPolicyEngine:
    def test_no_diagnostics_returns_medium_uncertainty(self):
        policy = evaluate(diagnostics=None, intent="general")
        assert policy.uncertainty_level == "medium"
        assert policy.normalized_status == "operational"

    def test_critical_diagnostic_returns_impacted(self):
        diags = [{"severity": "critical", "status": "critical", "check_type": "heartbeat", "confidence": 0.9}]
        policy = evaluate(diagnostics=diags)
        assert policy.normalized_status == "service_impacted"
        assert policy.escalation_level == "urgent"

    def test_warning_diagnostic_returns_attention(self):
        diags = [{"severity": "warning", "status": "warning", "check_type": "device_status", "confidence": 0.8}]
        policy = evaluate(diagnostics=diags)
        assert policy.normalized_status == "attention_needed"
        assert policy.escalation_level == "offer"

    def test_compliance_intent_flags_e911(self):
        policy = evaluate(diagnostics=None, intent="compliance")
        assert policy.issue_flags["e911"] is True
        assert policy.affected_service == "e911"

    def test_life_safety_always_true(self):
        policy = evaluate(diagnostics=None)
        assert policy.life_safety_sensitive is True


# ═══════════════════════════════════════════════════════════════════
# Intent classification tests
# ═══════════════════════════════════════════════════════════════════

class TestIntentClassification:
    def test_offline_keywords(self):
        assert classify_intent("My phone is not working") == "device_offline"
        assert classify_intent("device is down") == "device_offline"
        assert classify_intent("no dial tone") == "device_offline"

    def test_compliance_keywords(self):
        assert classify_intent("E911 address update") == "compliance"
        assert classify_intent("Kari's Law question") == "compliance"

    def test_voice_keywords(self):
        assert classify_intent("bad audio quality") == "voice_quality"
        assert classify_intent("call has static") == "voice_quality"

    def test_escalation_keywords(self):
        assert classify_intent("talk to a person") == "escalation_request"
        assert classify_intent("I need human help") == "escalation_request"

    def test_status_keywords(self):
        assert classify_intent("check my system status") == "status_check"

    def test_general_fallback(self):
        assert classify_intent("hello there") == "general"


# ═══════════════════════════════════════════════════════════════════
# Wording library structure tests
# ═══════════════════════════════════════════════════════════════════

class TestWordingLibrary:
    def test_all_categories_exist(self):
        required = ["greetings", "acknowledgements", "status", "diagnostic_summaries",
                     "system_test", "guidance", "escalation", "human_support",
                     "uncertainty", "e911", "reassurance", "fallbacks"]
        for cat in required:
            assert cat in WORDING, f"Missing wording category: {cat}"

    def test_status_has_three_levels(self):
        assert "operational" in WORDING["status"]
        assert "attention_needed" in WORDING["status"]
        assert "service_impacted" in WORDING["status"]

    def test_escalation_has_three_levels(self):
        assert "offer" in WORDING["escalation"]
        assert "recommend" in WORDING["escalation"]
        assert "urgent" in WORDING["escalation"]

    def test_pick_returns_string(self):
        result = pick("greetings", "default")
        assert isinstance(result, str)
        assert len(result) > 10

    def test_pick_random_returns_from_list(self):
        result = pick_random("status", "operational")
        assert result in WORDING["status"]["operational"]

    def test_pick_missing_returns_empty(self):
        result = pick("nonexistent", "category")
        assert result == ""
