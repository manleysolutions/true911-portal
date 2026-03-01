"""Tests for reconciliation mismatch detection logic.

Tests the core comparison algorithms without requiring a database.
"""

import pytest


# ── Inline the detection logic for unit testing ──────────────────

DEPLOYED_STATUSES = {"active", "provisioning"}
ACTIVE_SUB_STATUSES = {"active", "trialing"}


def detect_mismatches(subscriptions, lines_by_sub, lines_without_sub):
    """Pure-function version of the reconciliation mismatch detection.

    Args:
        subscriptions: list of dicts with {id, customer_id, customer_name, plan_name, status, qty_lines}
        lines_by_sub: dict mapping subscription_id -> count of deployed lines
        lines_without_sub: count of deployed lines with no subscription_id
    Returns:
        list of mismatch dicts
    """
    mismatches = []

    for sub in subscriptions:
        deployed = lines_by_sub.get(sub["id"], 0)
        billed = sub["qty_lines"]
        is_active = sub["status"] in ACTIVE_SUB_STATUSES

        if is_active and billed > deployed:
            mismatches.append({
                "type": "billed_gt_deployed",
                "customer": sub["customer_name"],
                "subscription_id": sub["id"],
                "billed": billed,
                "deployed": deployed,
            })
        elif is_active and deployed > billed:
            mismatches.append({
                "type": "deployed_gt_billed",
                "customer": sub["customer_name"],
                "subscription_id": sub["id"],
                "billed": billed,
                "deployed": deployed,
            })

        if is_active and deployed == 0 and billed > 0:
            mismatches.append({
                "type": "active_sub_no_lines",
                "customer": sub["customer_name"],
                "subscription_id": sub["id"],
                "billed": billed,
            })

    if lines_without_sub > 0:
        mismatches.append({
            "type": "unlinked_deployed_lines",
            "count": lines_without_sub,
        })

    return mismatches


# ── Tests ────────────────────────────────────────────────────────

class TestReconciliationMismatches:
    def test_perfect_match_no_mismatches(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Acme", "plan_name": "Pro", "status": "active", "qty_lines": 3}]
        lines = {1: 3}
        result = detect_mismatches(subs, lines, 0)
        assert len(result) == 0

    def test_billed_greater_than_deployed(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Acme", "plan_name": "Pro", "status": "active", "qty_lines": 5}]
        lines = {1: 2}
        result = detect_mismatches(subs, lines, 0)
        types = [m["type"] for m in result]
        assert "billed_gt_deployed" in types
        match = next(m for m in result if m["type"] == "billed_gt_deployed")
        assert match["billed"] == 5
        assert match["deployed"] == 2

    def test_deployed_greater_than_billed(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Acme", "plan_name": "Pro", "status": "active", "qty_lines": 2}]
        lines = {1: 5}
        result = detect_mismatches(subs, lines, 0)
        types = [m["type"] for m in result]
        assert "deployed_gt_billed" in types
        match = next(m for m in result if m["type"] == "deployed_gt_billed")
        assert match["deployed"] == 5
        assert match["billed"] == 2

    def test_active_subscription_no_lines(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Acme", "plan_name": "Pro", "status": "active", "qty_lines": 3}]
        lines = {}  # no deployed lines
        result = detect_mismatches(subs, lines, 0)
        types = [m["type"] for m in result]
        assert "active_sub_no_lines" in types
        assert "billed_gt_deployed" in types

    def test_cancelled_subscription_ignored(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Acme", "plan_name": "Pro", "status": "cancelled", "qty_lines": 5}]
        lines = {1: 0}
        result = detect_mismatches(subs, lines, 0)
        assert len(result) == 0

    def test_unlinked_deployed_lines(self):
        subs = []
        result = detect_mismatches(subs, {}, 7)
        assert len(result) == 1
        assert result[0]["type"] == "unlinked_deployed_lines"
        assert result[0]["count"] == 7

    def test_zero_unlinked_no_mismatch(self):
        subs = []
        result = detect_mismatches(subs, {}, 0)
        assert len(result) == 0

    def test_multiple_subscriptions_mixed(self):
        subs = [
            {"id": 1, "customer_id": 1, "customer_name": "Acme", "plan_name": "Pro", "status": "active", "qty_lines": 3},
            {"id": 2, "customer_id": 2, "customer_name": "Beta", "plan_name": "Basic", "status": "active", "qty_lines": 2},
            {"id": 3, "customer_id": 3, "customer_name": "Gamma", "plan_name": "Enterprise", "status": "active", "qty_lines": 10},
        ]
        lines = {1: 3, 2: 5, 3: 10}  # Acme OK, Beta over-deployed, Gamma OK
        result = detect_mismatches(subs, lines, 0)
        assert len(result) == 1
        assert result[0]["type"] == "deployed_gt_billed"
        assert result[0]["customer"] == "Beta"

    def test_trialing_subscription_is_active(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Trial Co", "plan_name": "Trial", "status": "trialing", "qty_lines": 2}]
        lines = {1: 0}
        result = detect_mismatches(subs, lines, 0)
        types = [m["type"] for m in result]
        assert "active_sub_no_lines" in types

    def test_expired_subscription_ignored(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Old Co", "plan_name": "Legacy", "status": "expired", "qty_lines": 10}]
        lines = {}
        result = detect_mismatches(subs, lines, 0)
        assert len(result) == 0

    def test_zero_billed_zero_deployed_no_mismatch(self):
        subs = [{"id": 1, "customer_id": 1, "customer_name": "Free", "plan_name": "Free", "status": "active", "qty_lines": 0}]
        lines = {1: 0}
        result = detect_mismatches(subs, lines, 0)
        assert len(result) == 0
