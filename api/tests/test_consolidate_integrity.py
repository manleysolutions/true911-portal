"""Tests for the pure Integrity consolidation planner (no DB)."""

from __future__ import annotations

from app.consolidate_integrity_tenants import normalize_name, plan_consolidation


def _scenario(**over):
    base = dict(
        source_sites=[
            {"site_id": "TIFFANY-GARDENS-EAST", "site_name": "Tiffany Gardens East",
             "e911_street": "100 East Rd", "e911_city": "Sunrise", "e911_state": "FL", "e911_zip": "33351"},
            {"site_id": "TIFFANY-GARDENS-NORTH", "site_name": "Tiffany Gardens North",
             "e911_street": "", "e911_city": "", "e911_state": "", "e911_zip": ""},
        ],
        survivor_sites=[
            {"site_id": "IPM-BELLE-TERRE", "site_name": "Belle Terre at Sunrise",
             "e911_street": "7800 W Oakland Park Blvd", "e911_city": "Sunrise", "e911_state": "FL", "e911_zip": "33351"},
            {"site_id": "IPM-TIFFANY-EAST", "site_name": "Tiffany Gardens East",
             "e911_street": "", "e911_city": "", "e911_state": "", "e911_zip": ""},
            {"site_id": "IPM-TIFFANY-NORTH", "site_name": "Tiffany Gardens North",
             "e911_street": "", "e911_city": "", "e911_state": "", "e911_zip": ""},
            {"site_id": "IPM-POMPANO", "site_name": "The Pointe of Pompano Beach Condo Association"},
        ],
        source_units_by_site={
            "TIFFANY-GARDENS-EAST": [{"unit_id": "TGE-1", "unit_name": "Elevator 1", "unit_type": "elevator_phone"},
                                     {"unit_id": "TGE-2", "unit_name": "Elevator 2", "unit_type": "elevator_phone"}],
            "TIFFANY-GARDENS-NORTH": [{"unit_id": "TGN-1", "unit_name": "Elevator 1", "unit_type": "elevator_phone"},
                                      {"unit_id": "TGN-2", "unit_name": "Elevator 2", "unit_type": "elevator_phone"}],
        },
        survivor_unit_types_by_site={"IPM-BELLE-TERRE": {"elevator_phone"}},  # survivor Tiffany sites have none
        source_customers=[{"id": 81, "name": "Integrity Property Management", "zoho": None},
                          {"id": 82, "name": "Integrity Property Management", "zoho": None}],
        survivor_customers=[{"id": 83, "name": "Integrity Property Management", "zoho": "337391000069074135"}],
        source_subscriptions=[{"id": 7, "status": "inactive"}],
    )
    base.update(over)
    return base


def test_normalize_name_matches_slug_variants():
    assert normalize_name("Tiffany Gardens East") == normalize_name("tiffany gardens east")
    assert normalize_name("Tiffany Gardens East") != normalize_name("Tiffany Gardens North")


def test_moves_all_four_units_to_matching_survivor_sites():
    plan = plan_consolidation(**_scenario())
    moved = {(m["unit_id"], m["to_site"]) for m in plan.move_units}
    assert moved == {
        ("TGE-1", "IPM-TIFFANY-EAST"), ("TGE-2", "IPM-TIFFANY-EAST"),
        ("TGN-1", "IPM-TIFFANY-NORTH"), ("TGN-2", "IPM-TIFFANY-NORTH"),
    }
    assert all(m["to_tenant"] == "integrity-pm" for m in plan.move_units)


def test_merges_e911_only_into_blank_survivor():
    plan = plan_consolidation(**_scenario())
    # East has an address on the source and blanks on the survivor → fill.
    east = [m for m in plan.merge_site_e911 if m["survivor_site_id"] == "IPM-TIFFANY-EAST"]
    assert len(east) == 1
    assert east[0]["fields"]["e911_street"] == "100 East Rd"
    # North is blank on both → nothing to merge.
    assert not any(m["survivor_site_id"] == "IPM-TIFFANY-NORTH" for m in plan.merge_site_e911)


def test_flags_duplicate_sites_for_archive_not_move():
    plan = plan_consolidation(**_scenario())
    archived = {a["site_id"] for a in plan.archive_sites}
    assert archived == {"TIFFANY-GARDENS-EAST", "TIFFANY-GARDENS-NORTH"}
    assert plan.move_sites == []  # both had a survivor match → not moved


def test_flags_duplicate_customers_and_repoints_subscription():
    plan = plan_consolidation(**_scenario())
    assert {c["id"] for c in plan.archive_customers} == {81, 82}
    assert all("canonical customer id=83" in c["reason"] for c in plan.archive_customers)
    assert len(plan.repoint_subscriptions) == 1
    rp = plan.repoint_subscriptions[0]
    assert rp["to_customer_id"] == 83 and rp["to_tenant"] == "integrity-pm" and rp["status"] == "inactive"


def test_discards_unit_when_survivor_site_already_has_type():
    sc = _scenario(survivor_unit_types_by_site={
        "IPM-BELLE-TERRE": {"elevator_phone"},
        "IPM-TIFFANY-EAST": {"elevator_phone"},  # already has an elevator unit
    })
    plan = plan_consolidation(**sc)
    discarded = {d["unit_id"] for d in plan.discard_units}
    assert discarded == {"TGE-1", "TGE-2"}            # East units are duplicates → discard
    assert {m["unit_id"] for m in plan.move_units} == {"TGN-1", "TGN-2"}  # North still moves


def test_protected_belle_terre_source_site_is_skipped():
    sc = _scenario(source_sites=[
        {"site_id": "IPM-BELLE-TERRE", "site_name": "Belle Terre at Sunrise"},
    ], source_units_by_site={})
    plan = plan_consolidation(**sc)
    assert any(s["id"] == "IPM-BELLE-TERRE" and "protected" in s["reason"] for s in plan.skipped)
    assert plan.move_units == [] and plan.archive_sites == []


def test_unique_source_site_is_moved():
    sc = _scenario(
        source_sites=[{"site_id": "IPM-ONLY-HERE", "site_name": "Unique Place"}],
        source_units_by_site={},
    )
    plan = plan_consolidation(**sc)
    assert len(plan.move_sites) == 1
    assert plan.move_sites[0]["site_id"] == "IPM-ONLY-HERE"
    assert plan.move_sites[0]["to_customer_id"] == 83  # canonical
