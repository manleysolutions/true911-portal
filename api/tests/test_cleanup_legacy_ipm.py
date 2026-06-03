"""Tests for the pure legacy-tenant cleanup planner (refusal gates)."""

from __future__ import annotations

from app.cleanup_legacy_ipm_tenant import plan_cleanup

CLEAN_COUNTS = {"service_units": 0, "devices": 0, "sims": 0, "users": 0,
                "registrations": 0, "subscriptions": 0}


def _scenario(**over):
    base = dict(
        tenant_id="ipm",
        customers=[{"id": 81, "name": "Integrity Property Management", "zoho": None},
                   {"id": 82, "name": "Integrity Property Management", "zoho": None}],
        sites=[{"site_id": "TIFFANY-GARDENS-EAST", "site_name": "Tiffany Gardens East"},
               {"site_id": "TIFFANY-GARDENS-NORTH", "site_name": "Tiffany Gardens North"}],
        counts=dict(CLEAN_COUNTS),
        external_references={81: [], 82: []},
    )
    base.update(over)
    return base


def test_clean_scenario_is_safe():
    plan = plan_cleanup(**_scenario())
    assert plan.safe is True and not plan.refusals
    assert {c["id"] for c in plan.archive_customers} == {81, 82}
    assert {s["site_id"] for s in plan.archive_sites} == {"TIFFANY-GARDENS-EAST", "TIFFANY-GARDENS-NORTH"}
    assert plan.retire_tenant == "ipm"


def test_refuses_when_operational_records_remain():
    for kind in ("service_units", "devices", "sims", "users", "registrations", "subscriptions"):
        counts = dict(CLEAN_COUNTS, **{kind: 1})
        plan = plan_cleanup(**_scenario(counts=counts))
        assert plan.safe is False
        assert any(kind in r for r in plan.refusals)
        assert plan.retire_tenant is None


def test_refuses_on_unexpected_site():
    plan = plan_cleanup(**_scenario(sites=[
        {"site_id": "TIFFANY-GARDENS-EAST", "site_name": "Tiffany Gardens East"},
        {"site_id": "SOME-OTHER-LIVE-SITE", "site_name": "Mystery"},
    ]))
    assert plan.safe is False
    assert any("unexpected site 'SOME-OTHER-LIVE-SITE'" in r for r in plan.refusals)


def test_refuses_customer_with_zoho_id():
    plan = plan_cleanup(**_scenario(customers=[
        {"id": 81, "name": "Integrity Property Management", "zoho": "999"},
        {"id": 82, "name": "Integrity Property Management", "zoho": None},
    ], external_references={81: [], 82: []}))
    assert plan.safe is False
    assert any("Zoho id 999" in r for r in plan.refusals)


def test_refuses_customer_with_unexpected_name():
    plan = plan_cleanup(**_scenario(customers=[
        {"id": 81, "name": "A Totally Different Company", "zoho": None},
        {"id": 82, "name": "Integrity Property Management", "zoho": None},
    ], external_references={81: [], 82: []}))
    assert plan.safe is False
    assert any("not a known duplicate" in r for r in plan.refusals)


def test_refuses_when_customer_still_referenced():
    plan = plan_cleanup(**_scenario(external_references={
        81: ["site:IPM-BELLE-TERRE(tenant integrity-pm)"],  # live reference
        82: [],
    }))
    assert plan.safe is False
    assert any("still referenced by" in r and "#81" in r for r in plan.refusals)
