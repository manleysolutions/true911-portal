"""Tests for the RH E911 verification planner (pure, no DB)."""

from __future__ import annotations

from app.verify_rh_e911 import plan_e911_verification


def _site(sid, *, status="active", e911_status="provided",
          street="1 Main St", city="Tampa", state="FL", zip_="33601"):
    return {"site_id": sid, "status": status, "e911_status": e911_status,
            "e911_street": street, "e911_city": city, "e911_state": state, "e911_zip": zip_}


def test_validates_eligible_complete_address():
    sites = [_site("RH-1"), _site("RH-2")]
    plan = plan_e911_verification(["RH-1"], sites)
    assert plan.safe is True
    assert [s["site_id"] for s in plan.to_validate] == ["RH-1"]
    assert plan.refusals == []
    # RH-2 was eligible but not named
    assert "RH-2" in plan.not_requested_eligible


def test_refuses_batch_on_missing_address_parts():
    sites = [_site("RH-1"), _site("RH-BAD", zip_="", state="")]
    plan = plan_e911_verification(["RH-1", "RH-BAD"], sites)
    assert plan.safe is False
    assert plan.to_validate == []                      # whole batch refused
    assert any("RH-BAD" in r and "incomplete" in r for r in plan.refusals)
    assert any("zip" in r for r in plan.refusals)


def test_refuses_unknown_site():
    plan = plan_e911_verification(["NOPE"], [_site("RH-1")])
    assert plan.safe is False
    assert any("NOPE" in r and "not found" in r for r in plan.refusals)


def test_already_verified_is_noop_not_refusal():
    sites = [_site("RH-1", e911_status="validated")]
    plan = plan_e911_verification(["RH-1"], sites)
    assert plan.safe is True                            # not a refusal
    assert plan.to_validate == []
    assert plan.already_verified == ["RH-1"]


def test_mixed_already_and_eligible():
    sites = [_site("RH-1", e911_status="validated"), _site("RH-2", e911_status="provided")]
    plan = plan_e911_verification(["RH-1", "RH-2"], sites)
    assert plan.safe is True
    assert [s["site_id"] for s in plan.to_validate] == ["RH-2"]
    assert plan.already_verified == ["RH-1"]


def test_empty_request_lists_eligible_only():
    sites = [_site("RH-1"), _site("RH-2", e911_status="validated")]
    plan = plan_e911_verification([], sites)
    assert plan.to_validate == [] and plan.refusals == []
    assert plan.not_requested_eligible == ["RH-1"]     # only the unverified-complete one


def test_whitespace_in_requested_is_trimmed():
    plan = plan_e911_verification([" RH-1 ", ""], [_site("RH-1")])
    assert [s["site_id"] for s in plan.to_validate] == ["RH-1"]
