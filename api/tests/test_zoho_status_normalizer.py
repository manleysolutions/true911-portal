"""Phase 2 — Zoho lifecycle status normalizer (pure).

Lifecycle is a separate axis from operational status.  The key requirement:
Zoho "De-activated" maps to ``deactivated`` and never presents as healthy active
monitoring.
"""

from __future__ import annotations

import pytest

from app.services.zoho_status_normalizer import (
    ACTIVE,
    DEACTIVATED,
    PENDING_INSTALL,
    SUSPENDED,
    UNKNOWN,
    normalize_activation_status,
    presents_as_active_monitoring,
)


class TestNormalizeActivationStatus:
    @pytest.mark.parametrize("raw", ["De-activated", "Deactivated", "DEACTIVATED", "de activated", "deactive"])
    def test_zoho_deactivated_maps_to_deactivated(self, raw):
        assert normalize_activation_status(raw) == DEACTIVATED

    @pytest.mark.parametrize("raw,expected", [
        ("Active", ACTIVE),
        ("Activated", ACTIVE),
        ("In Service", ACTIVE),
        ("Suspended", SUSPENDED),
        ("On Hold", SUSPENDED),
        ("Inactive", DEACTIVATED),
        ("Cancelled", DEACTIVATED),
        ("Canceled", DEACTIVATED),
        ("Terminated", DEACTIVATED),
        ("Disconnected", DEACTIVATED),
        ("Pending", PENDING_INSTALL),
        ("Pending Install", PENDING_INSTALL),
        ("Provisioning", PENDING_INSTALL),
        ("New", PENDING_INSTALL),
    ])
    def test_canonical_mappings(self, raw, expected):
        assert normalize_activation_status(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "???", "wat", "foobar"])
    def test_unknown_inputs(self, raw):
        # Never guess active for unmapped/empty input.
        assert normalize_activation_status(raw) == UNKNOWN

    def test_inactive_does_not_fall_through_to_active(self):
        # "inactive" contains the substring "activ" — must NOT become active.
        assert normalize_activation_status("Inactive") == DEACTIVATED

    def test_substring_fallback(self):
        assert normalize_activation_status("Service De-Activated by billing") == DEACTIVATED
        assert normalize_activation_status("currently suspended (non-pay)") == SUSPENDED


class TestPresentsAsActiveMonitoring:
    def test_only_active_presents_as_active(self):
        assert presents_as_active_monitoring(ACTIVE) is True

    @pytest.mark.parametrize("state", [DEACTIVATED, SUSPENDED, PENDING_INSTALL, UNKNOWN, None])
    def test_non_active_states_do_not_present_as_active(self, state):
        assert presents_as_active_monitoring(state) is False
