"""Tests for the support escalation service — deduplication, Zoho integration, sanitization."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.services.support.escalation import (
    _compute_dedupe_key,
    _build_ticket_subject,
    _build_handoff_summary,
    _recommend_followup,
    _determine_escalation_level,
    _zoho_category,
    DEDUPE_WINDOWS,
)
from app.schemas.support import SupportEscalationCustomerOut


# ═══════════════════════════════════════════════════════════════════
# Dedupe key tests
# ═══════════════════════════════════════════════════════════════════

class TestDedupeKey:
    def test_same_inputs_produce_same_key(self):
        k1 = _compute_dedupe_key("tenant1", 5, 10, "device_offline")
        k2 = _compute_dedupe_key("tenant1", 5, 10, "device_offline")
        assert k1 == k2

    def test_different_tenant_produces_different_key(self):
        k1 = _compute_dedupe_key("tenant1", 5, 10, "device_offline")
        k2 = _compute_dedupe_key("tenant2", 5, 10, "device_offline")
        assert k1 != k2

    def test_different_site_produces_different_key(self):
        k1 = _compute_dedupe_key("tenant1", 5, 10, "device_offline")
        k2 = _compute_dedupe_key("tenant1", 6, 10, "device_offline")
        assert k1 != k2

    def test_different_category_produces_different_key(self):
        k1 = _compute_dedupe_key("tenant1", 5, 10, "device_offline")
        k2 = _compute_dedupe_key("tenant1", 5, 10, "voice_quality")
        assert k1 != k2

    def test_none_values_handled(self):
        k = _compute_dedupe_key("tenant1", None, None, None)
        assert isinstance(k, str)
        assert len(k) == 32

    def test_key_is_fixed_length(self):
        k = _compute_dedupe_key("tenant1", 5, 10, "device_offline")
        assert len(k) == 32


# ═══════════════════════════════════════════════════════════════════
# Dedupe window tests
# ═══════════════════════════════════════════════════════════════════

class TestDedupeWindows:
    def test_urgent_window_is_30_minutes(self):
        assert DEDUPE_WINDOWS["urgent"] == timedelta(minutes=30)

    def test_standard_window_is_4_hours(self):
        assert DEDUPE_WINDOWS["recommend"] == timedelta(hours=4)
        assert DEDUPE_WINDOWS["offer"] == timedelta(hours=4)

    def test_default_window_is_24_hours(self):
        assert DEDUPE_WINDOWS["none"] == timedelta(hours=24)


# ═══════════════════════════════════════════════════════════════════
# Ticket subject tests
# ═══════════════════════════════════════════════════════════════════

class TestTicketSubject:
    def test_basic_subject_format(self):
        subject = _build_ticket_subject("device_offline", "acme", 5, 10)
        assert subject == "True911 | Device Offline | Site 5 | Device 10"

    def test_voice_quality_label(self):
        subject = _build_ticket_subject("voice_quality", "acme", 3, None)
        assert "Voice Service" in subject

    def test_compliance_label(self):
        subject = _build_ticket_subject("compliance", "acme", 1, None)
        assert "E911 Compliance" in subject

    def test_no_site_or_device_uses_tenant(self):
        subject = _build_ticket_subject("general", "acme", None, None)
        assert "Tenant acme" in subject

    def test_unknown_category_uses_default(self):
        subject = _build_ticket_subject("something_weird", "t1", 1, 2)
        assert "Support Request" in subject


# ═══════════════════════════════════════════════════════════════════
# Ticket description tests
# ═══════════════════════════════════════════════════════════════════

class TestTicketDescription:
    def test_description_has_required_sections(self):
        desc = _build_handoff_summary(
            tenant_id="acme",
            site_id=5,
            device_id=10,
            reason="Device not responding",
            probable_cause="Heartbeat timeout",
            issue_category="device_offline",
            diagnostics_checked={
                "heartbeat": {"status": "critical", "severity": "critical", "summary": "No response"},
            },
            transcript_excerpt="[USER] My phone is dead",
            additional_notes="Customer is upset",
        )
        assert "SUMMARY" in desc
        assert "SERVICE CONTEXT" in desc
        assert "SYSTEM ASSESSMENT" in desc
        assert "CHECKS COMPLETED" in desc
        assert "CONVERSATION" in desc
        assert "RECOMMENDED NEXT STEP" in desc
        assert "Device not responding" in desc
        assert "Tenant: acme" in desc

    def test_description_is_readable_not_json(self):
        desc = _build_handoff_summary(
            tenant_id="t1", site_id=1, device_id=2,
            reason="Test", probable_cause=None, issue_category=None,
            diagnostics_checked={}, transcript_excerpt="",
            additional_notes=None,
        )
        assert "{" not in desc or "===" in desc  # not raw JSON
        assert "Tenant: t1" in desc


# ═══════════════════════════════════════════════════════════════════
# Escalation level tests
# ═══════════════════════════════════════════════════════════════════

class TestEscalationLevel:
    def test_critical_diagnostic_returns_urgent(self):
        class MockDiag:
            severity = "critical"
        level = _determine_escalation_level([MockDiag()], None)
        assert level == "urgent"

    def test_warning_diagnostic_returns_offer(self):
        class MockDiag:
            severity = "warning"
        level = _determine_escalation_level([MockDiag()], None)
        assert level == "offer"

    def test_no_diagnostics_returns_offer(self):
        level = _determine_escalation_level([], None)
        assert level == "offer"


# ═══════════════════════════════════════════════════════════════════
# Subscriber sanitization tests
# ═══════════════════════════════════════════════════════════════════

class TestSubscriberSanitization:
    def test_customer_response_has_no_zoho_id(self):
        resp = SupportEscalationCustomerOut(
            id=uuid4(),
            session_id=uuid4(),
            status="submitted",
            message="Your support request has been submitted.",
            created_at=datetime.now(timezone.utc),
        )
        d = resp.model_dump()
        assert "zoho" not in str(d).lower()
        assert "ticket_id" not in str(d)
        assert "dedupe" not in str(d)

    def test_customer_status_is_always_submitted(self):
        resp = SupportEscalationCustomerOut(
            id=uuid4(),
            session_id=uuid4(),
            status="submitted",
            message="Test",
            created_at=datetime.now(timezone.utc),
        )
        assert resp.status == "submitted"


# ═══════════════════════════════════════════════════════════════════
# Zoho category mapping tests
# ═══════════════════════════════════════════════════════════════════

class TestZohoCategory:
    def test_device_offline(self):
        assert _zoho_category("device_offline") == "Device Issue"

    def test_voice_quality(self):
        assert _zoho_category("voice_quality") == "Voice Issue"

    def test_compliance(self):
        assert _zoho_category("compliance") == "E911/Compliance"

    def test_unknown_returns_default(self):
        assert _zoho_category("something") == "Support Escalation"
        assert _zoho_category(None) == "Support Escalation"


# ═══════════════════════════════════════════════════════════════════
# Recommended followup tests
# ═══════════════════════════════════════════════════════════════════

class TestRecommendedFollowup:
    def test_heartbeat_critical_suggests_power_check(self):
        result = _recommend_followup(
            {"heartbeat": {"status": "critical", "severity": "critical", "summary": ""}},
            None,
        )
        assert "power" in result.lower() or "connectivity" in result.lower()

    def test_e911_warning_suggests_address_update(self):
        result = _recommend_followup(
            {"e911": {"status": "warning", "severity": "warning", "summary": ""}},
            None,
        )
        assert "address" in result.lower() or "E911" in result

    def test_no_diagnostics_suggests_full_suite(self):
        result = _recommend_followup({}, None)
        assert "diagnostic" in result.lower() or "full" in result.lower()
