"""Unit tests for app.services.llm.deterministic.

This module is the SAFE OUTPUT.  Every test here defends the property
'no LLM, no provider key, no network → still produces a useful summary'.
"""

from __future__ import annotations

import pytest

from app.services.llm.deterministic import (
    FleetSnapshot,
    IncidentSnapshot,
    SiteSnapshot,
    SummaryContext,
    build_deterministic_summary,
)


# ─── Fleet scope ───────────────────────────────────────────────────


class TestFleetScope:
    def test_zero_sites_produces_useful_message(self):
        ctx = SummaryContext(
            scope="fleet",
            tenant_id="t1",
            fleet=FleetSnapshot(total_sites=0),
            sources_used=["sites:tenant=t1"],
        )
        out = build_deterministic_summary(ctx)
        assert "No sites" in out["current_status"]
        assert out["recommended_next_step"]
        assert 0.0 <= out["confidence"] <= 1.0

    def test_healthy_fleet_summary(self):
        ctx = SummaryContext(
            scope="fleet",
            tenant_id="t1",
            fleet=FleetSnapshot(
                total_sites=20, connected_sites=20, active_incidents=0
            ),
        )
        out = build_deterministic_summary(ctx)
        assert "20 of 20" in out["current_status"]
        assert "100%" in out["current_status"]
        assert out["likely_issue"] is None
        assert "monitoring" in out["recommended_next_step"].lower()

    def test_critical_incident_surfaced(self):
        ctx = SummaryContext(
            scope="fleet",
            tenant_id="t1",
            fleet=FleetSnapshot(
                total_sites=10,
                connected_sites=9,
                active_incidents=3,
                critical_incidents=1,
                sites_needing_attention=2,
            ),
        )
        out = build_deterministic_summary(ctx)
        assert "1 critical incident" in out["likely_issue"]
        assert "Triage critical" in out["recommended_next_step"]

    def test_stale_devices_surfaced_when_no_incidents(self):
        ctx = SummaryContext(
            scope="fleet",
            tenant_id="t1",
            fleet=FleetSnapshot(
                total_sites=10,
                connected_sites=8,
                stale_devices=5,
                active_incidents=0,
                critical_incidents=0,
            ),
        )
        out = build_deterministic_summary(ctx)
        assert "5 device" in out["likely_issue"]
        assert "stale" in out["recommended_next_step"].lower() or "heartbeat" in out["recommended_next_step"].lower()


# ─── Site scope ────────────────────────────────────────────────────


class TestSiteScope:
    def test_site_not_found_reports_clearly(self):
        ctx = SummaryContext(scope="site", scope_id="missing", site=None)
        out = build_deterministic_summary(ctx)
        assert "not found" in out["current_status"].lower()
        assert out["confidence"] < 0.5

    def test_healthy_site_summary(self):
        site = SiteSnapshot(
            site_id="s1",
            site_name="Tampa Courthouse",
            last_heartbeat_seconds_ago=45,
            connection_status="connected",
        )
        ctx = SummaryContext(scope="site", scope_id="s1", site=site)
        out = build_deterministic_summary(ctx)
        assert "Tampa Courthouse" in out["current_status"]
        assert "45s ago" in out["current_status"]
        assert out["likely_issue"] is None

    def test_site_with_critical_incident(self):
        site = SiteSnapshot(
            site_id="s1",
            site_name="Tampa Courthouse",
            last_heartbeat_seconds_ago=20,
            critical_incidents=1,
            active_incidents=1,
            connection_status="connected",
        )
        ctx = SummaryContext(scope="site", scope_id="s1", site=site)
        out = build_deterministic_summary(ctx)
        assert "critical" in out["likely_issue"].lower()
        assert "acknowledge" in out["recommended_next_step"].lower()

    def test_site_with_never_reported_device(self):
        site = SiteSnapshot(
            site_id="s1",
            site_name="New Site",
            last_heartbeat_seconds_ago=None,
            connection_status="stale",
        )
        ctx = SummaryContext(scope="site", scope_id="s1", site=site)
        out = build_deterministic_summary(ctx)
        assert "has not reported" in out["current_status"]

    def test_recent_incident_surfaced_when_no_counters_set(self):
        site = SiteSnapshot(
            site_id="s1",
            site_name="Site One",
            last_heartbeat_seconds_ago=60,
            connection_status="connected",
        )
        incident = IncidentSnapshot(
            incident_id="INC-1",
            severity="warning",
            summary="SIP registration intermittent",
            opened_minutes_ago=15,
            site_id="s1",
        )
        ctx = SummaryContext(
            scope="site", scope_id="s1", site=site, incidents=[incident]
        )
        out = build_deterministic_summary(ctx)
        assert "SIP registration intermittent" in out["likely_issue"]


# ─── Response shape contract ───────────────────────────────────────


class TestResponseShape:
    @pytest.mark.parametrize(
        "ctx",
        [
            SummaryContext(scope="fleet", tenant_id="t", fleet=FleetSnapshot()),
            SummaryContext(scope="site", scope_id="s1", site=None),
            SummaryContext(scope="device", scope_id="d1"),
        ],
    )
    def test_every_path_returns_required_keys(self, ctx):
        out = build_deterministic_summary(ctx)
        required = {
            "current_status",
            "likely_issue",
            "recommended_next_step",
            "confidence",
            "sources_used",
            "customer_safe_summary",
            "internal_summary",
            "generated_at",
        }
        assert required.issubset(set(out.keys()))
        assert 0.0 <= out["confidence"] <= 1.0
        # customer_safe_summary is Phase 1 reserved → always None
        assert out["customer_safe_summary"] is None
