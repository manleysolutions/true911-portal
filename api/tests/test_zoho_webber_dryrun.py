"""Phase 4 — Webber Infra end-to-end dry-run (no DB, no writes).

Exercises the full pipeline (routing -> extract -> normalize -> serialize) via the
importable report builder in scripts/zoho_webber_infra_dryrun.py.  This is the
request's headline case: Zoho shows Webber Infra as "De-activated", which must
normalize to `deactivated` and NOT present as healthy active monitoring, while
nothing is written.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from zoho_webber_infra_dryrun import WEBBER_SAMPLE, build_dryrun_report  # noqa: E402


class TestWebberDryRun:
    def test_deactivated_pipeline(self):
        report = build_dryrun_report(dict(WEBBER_SAMPLE))
        assert report["routing_matched"] is True
        assert report["raw_device_activation_status"] == "De-activated"
        assert report["normalized_lifecycle_state"] == "deactivated"

        row = report["review_row"]
        assert row["subscription_mgmt_id"] == "ZSM-WEBBER-001"
        assert row["account_name"] == "Webber Infra"
        assert row["device_activation_status"] == "De-activated"   # raw preserved
        assert row["lifecycle_state"] == "deactivated"
        assert row["presents_as_active_monitoring"] is False
        assert row["map_status"] == "unmapped"
        assert row["mrc"] == 45.0
        assert row["service_term_ends"] == "2026-12-31"
        # In-memory only — never persisted.
        assert row["id"] is None

    def test_secret_is_redacted(self):
        report = build_dryrun_report(dict(WEBBER_SAMPLE))
        assert report["sanitized_payload"]["auth_token"] == "<redacted>"
        # business fields preserved
        assert report["sanitized_payload"]["Account_Name"] == "Webber Infra"

    def test_active_status_presents_as_active(self):
        payload = dict(WEBBER_SAMPLE, Device_Activation_Status="Active")
        report = build_dryrun_report(payload)
        assert report["normalized_lifecycle_state"] == "active"
        assert report["review_row"]["presents_as_active_monitoring"] is True

    def test_no_normalize_leaves_lifecycle_none(self):
        report = build_dryrun_report(dict(WEBBER_SAMPLE), normalize=False)
        assert report["normalized_lifecycle_state"] is None
        assert report["review_row"]["lifecycle_state"] is None
        # raw status still captured even without normalization
        assert report["review_row"]["device_activation_status"] == "De-activated"

    def test_report_needs_no_database(self):
        # build_dryrun_report takes no session; proving the dry run is pure.
        import inspect
        params = inspect.signature(build_dryrun_report).parameters
        assert "db" not in params and "session" not in params
