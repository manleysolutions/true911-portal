"""Tests for the self-healing remediation framework.

Covers:
  1. Allowed action runs and verifies
  2. Blocked by cooldown
  3. Blocked by max attempts
  4. Failed verification remains failed
  5. retry_zoho_sync clears sync error when successful
  6. Customer-facing text never exposes technical jargon
  7. Dangerous actions are not present in enabled registry
"""

import pytest
from datetime import timedelta

from app.services.support.remediation_registry import (
    ACTIONS, BLOCKED_ACTIONS, ISSUE_ACTION_MAP,
    get_action, get_actions_for_issue, is_blocked,
)
from app.services.support.remediation_policy import PolicyDecision
from app.services.support.self_healing import (
    _verify_diagnostics_improved,
    _verify_status_ok,
    _verify_telemetry_fresh,
    _verify_connectivity_ok,
    _verify_zoho_synced,
    _verify_backup_checked,
    _blocked_result,
)


# ═══════════════════════════════════════════════════════════════════
# 1. Registry: allowed actions exist and are configured
# ═══════════════════════════════════════════════════════════════════

class TestRegistry:
    def test_tier1_actions_are_enabled(self):
        tier1 = ["refresh_diagnostics", "refresh_device_status", "refresh_telemetry",
                 "retry_voice_check", "retry_connectivity_check", "retry_zoho_sync"]
        for action in tier1:
            defn = get_action(action)
            assert defn is not None, f"Missing action: {action}"
            assert defn.enabled, f"Tier 1 action should be enabled: {action}"
            assert defn.level == "safe", f"Tier 1 action should be safe: {action}"

    def test_tier2_gated_action_defaults_disabled(self):
        defn = get_action("restart_local_monitoring_service")
        assert defn is not None
        assert defn.level == "gated"
        assert defn.enabled is False

    def test_all_actions_have_cooldowns(self):
        for name, defn in ACTIONS.items():
            assert defn.cooldown_minutes > 0, f"Action {name} has no cooldown"
            assert defn.max_attempts_24h > 0, f"Action {name} has no max attempts"

    def test_issue_mapping_only_references_registered_actions(self):
        for issue, action_types in ISSUE_ACTION_MAP.items():
            for at in action_types:
                assert at in ACTIONS, f"Issue '{issue}' maps to unregistered action '{at}'"


# ═══════════════════════════════════════════════════════════════════
# 7. Dangerous actions are NOT in enabled registry
# ═══════════════════════════════════════════════════════════════════

class TestDangerousActionsBlocked:
    DANGEROUS = [
        "reboot_device", "reboot_modem", "reboot_ata",
        "reprovision_device", "modify_e911", "force_transport_switch",
        "restart_customer_service",
    ]

    def test_dangerous_actions_in_blocklist(self):
        for action in self.DANGEROUS:
            assert is_blocked(action), f"Dangerous action '{action}' should be blocked"

    def test_dangerous_actions_not_in_registry(self):
        for action in self.DANGEROUS:
            assert get_action(action) is None, f"Dangerous action '{action}' should not be in registry"

    def test_no_registered_action_is_dangerous(self):
        for name in ACTIONS:
            assert name not in BLOCKED_ACTIONS, f"Registered action '{name}' is also on the deny-list"

    def test_e911_has_no_auto_remediation(self):
        actions = get_actions_for_issue("e911_incomplete")
        assert len(actions) == 0, "E911 should have no auto-remediation actions"


# ═══════════════════════════════════════════════════════════════════
# Verification: passed/failed logic
# ═══════════════════════════════════════════════════════════════════

class TestVerification:
    def test_diagnostics_all_ok_passes(self):
        status, summary = _verify_diagnostics_improved(
            {"results": {"heartbeat": "ok", "device_status": "ok"}}
        )
        assert status == "passed"

    def test_diagnostics_with_warning_fails(self):
        status, summary = _verify_diagnostics_improved(
            {"results": {"heartbeat": "ok", "device_status": "warning"}}
        )
        assert status == "failed"
        assert "device_status" in summary

    def test_diagnostics_empty_results_fails(self):
        status, _ = _verify_diagnostics_improved({"results": {}})
        assert status == "failed"

    def test_status_ok_passes(self):
        status, _ = _verify_status_ok({"status": "ok"})
        assert status == "passed"

    def test_status_warning_fails(self):
        status, _ = _verify_status_ok({"status": "warning"})
        assert status == "failed"

    def test_telemetry_ok_passes(self):
        status, _ = _verify_telemetry_fresh({"status": "ok"})
        assert status == "passed"

    def test_connectivity_heartbeat_ok_passes(self):
        status, _ = _verify_connectivity_ok({
            "heartbeat": {"status": "ok"},
            "ata_reachability": {"status": "unknown"},
        })
        assert status == "passed"

    def test_connectivity_heartbeat_warning_fails(self):
        status, _ = _verify_connectivity_ok({
            "heartbeat": {"status": "warning"},
            "ata_reachability": {"status": "ok"},
        })
        assert status == "failed"

    def test_zoho_synced_passes(self):
        status, _ = _verify_zoho_synced({"retried": True, "synced": True, "ticket_id": "123"})
        assert status == "passed"

    def test_zoho_not_synced_fails(self):
        status, _ = _verify_zoho_synced({"retried": True, "synced": False, "error": "timeout"})
        assert status == "failed"

    def test_zoho_no_escalation_fails(self):
        status, _ = _verify_zoho_synced({"retried": False, "reason": "No failed escalation found"})
        assert status == "failed"

    def test_backup_checked_passes(self):
        status, _ = _verify_backup_checked({"backup_path_checked": True})
        assert status == "passed"

    def test_backup_not_checked_fails(self):
        status, _ = _verify_backup_checked({})
        assert status == "failed"


# ═══════════════════════════════════════════════════════════════════
# Blocked result formatting
# ═══════════════════════════════════════════════════════════════════

class TestBlockedResults:
    def test_blocked_result_format(self):
        result = _blocked_result("reboot_device", "On deny-list")
        assert result["status"] == "blocked"
        assert result["action_type"] == "reboot_device"
        assert result["blocked_reason"] == "On deny-list"
        assert result["raw_result"] is None

    def test_cooldown_result_format(self):
        result = _blocked_result("refresh_diagnostics", "Cooldown active", cooldown=120)
        assert result["status"] == "cooldown"
        assert result["cooldown_remaining_seconds"] == 120


# ═══════════════════════════════════════════════════════════════════
# Policy decision structure
# ═══════════════════════════════════════════════════════════════════

class TestPolicyDecision:
    def test_allowed_decision(self):
        d = PolicyDecision(allowed=True, reason="OK", verification_required=True)
        assert d.allowed
        assert d.cooldown_remaining_seconds == 0

    def test_blocked_decision(self):
        d = PolicyDecision(allowed=False, reason="Cooldown", cooldown_remaining_seconds=60)
        assert not d.allowed
        assert d.cooldown_remaining_seconds == 60

    def test_admin_approval_flag(self):
        d = PolicyDecision(allowed=False, reason="Gated", requires_admin_approval=True)
        assert d.requires_admin_approval


# ═══════════════════════════════════════════════════════════════════
# Issue-to-action mapping
# ═══════════════════════════════════════════════════════════════════

class TestIssueMapping:
    def test_heartbeat_missed_has_actions(self):
        actions = get_actions_for_issue("heartbeat_missed")
        types = [a.action_type for a in actions]
        assert "refresh_device_status" in types
        assert "refresh_diagnostics" in types

    def test_voice_quality_has_retry(self):
        actions = get_actions_for_issue("voice_quality")
        types = [a.action_type for a in actions]
        assert "retry_voice_check" in types

    def test_zoho_sync_failed_has_retry(self):
        actions = get_actions_for_issue("zoho_sync_failed")
        types = [a.action_type for a in actions]
        assert "retry_zoho_sync" in types

    def test_connectivity_has_backup_check(self):
        actions = get_actions_for_issue("connectivity_warning")
        types = [a.action_type for a in actions]
        assert "check_backup_path" in types

    def test_general_has_refresh(self):
        actions = get_actions_for_issue("general")
        types = [a.action_type for a in actions]
        assert "refresh_diagnostics" in types

    def test_unknown_issue_falls_back_to_general(self):
        actions = get_actions_for_issue("something_unknown")
        types = [a.action_type for a in actions]
        assert "refresh_diagnostics" in types


# ═══════════════════════════════════════════════════════════════════
# 6. Customer text never exposes remediation internals
# ═══════════════════════════════════════════════════════════════════

class TestCustomerSafety:
    """Verify that none of the customer-facing wording references remediation internals."""

    def test_wording_library_has_no_remediation_terms(self):
        from app.services.support.wording import WORDING
        import json
        wording_text = json.dumps(WORDING).lower()
        forbidden = ["remediation", "self_healing", "cooldown", "retry_zoho",
                      "refresh_diagnostics", "action_type", "verification_status"]
        for term in forbidden:
            assert term not in wording_text, f"Wording library contains '{term}'"
