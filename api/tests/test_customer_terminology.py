"""Customer-facing terminology & ownership (D-028).

Presentation-only rules — no data, E911, registry or RBAC behaviour is touched:
  * internal review / research flags in a record name never reach a customer name,
    and a replacement name is never invented;
  * real customer names ("Edmonton Gallery #505") are unchanged;
  * the UNKNOWN monitoring state names True911 as the owner and claims neither
    monitored nor failed;
  * Recent activity is history in its own tier, not portfolio setup.
"""
from __future__ import annotations

import pytest

from app.services.customer import self_service as ss
from app.services.customer import serialize as cs


@pytest.mark.parametrize("canonical,store,city,site_type,expected", [
    ("RESEARCH REQUIRED Gallery #653", "653", None, "gallery", "Gallery #653"),
    ("Research required: Gallery #653", "653", None, "gallery", "Gallery #653"),
    ("[Needs review] Boston Gallery", None, None, "gallery", "Boston Gallery"),
    ("RESEARCH REQUIRED", "653", None, "gallery", "Gallery #653"),
    ("RESEARCH REQUIRED", None, None, None, "Location"),          # nothing invented
])
def test_internal_markers_never_reach_a_customer_name(canonical, store, city, site_type, expected):
    name = cs.building_display_name(canonical, store, city, site_type)
    assert name == expected
    assert "research" not in name.lower() and "review" not in name.lower()


@pytest.mark.parametrize("canonical,store,city,site_type,expected", [
    ("Edmonton Gallery #505", "505", "Edmonton", "gallery", "Edmonton Gallery #505"),
    ("Dallas Gallery #168", "168", "Dallas", "gallery", "Dallas Gallery #168"),
    ("RH Linden House", None, None, "special", "Linden House Gallery"),
    ("Review Hall Gallery", None, None, "gallery", "Review Hall Gallery"),   # a real word stays
])
def test_real_customer_names_are_unchanged(canonical, store, city, site_type, expected):
    assert cs.building_display_name(canonical, store, city, site_type) == expected


def test_strip_internal_markers_never_invents_a_name():
    assert cs.strip_internal_markers("RESEARCH REQUIRED") == ""
    assert cs.strip_internal_markers(None) == ""
    assert cs.strip_internal_markers("Lincoln Elementary School") == "Lincoln Elementary School"


def test_monitoring_confirmation_assigns_work_to_true911_without_claiming_a_status():
    label, summary, evidence = cs.OPERATIONAL_STATES["being_reconciled"]
    assert evidence == "unknown"
    text = f"{label} {summary}".lower()
    assert "true911" in text and "no action is needed from you" in text
    for word in ("reconcil", "monitored", "working", "fail", "offline", "down", "protected"):
        assert word not in label.lower(), word
    for word in ("reconcil", "fail", "offline", "down", "unprotected"):
        assert word not in text, word
    op = cs.operational_state("Protected", linked=False)       # never green without a link
    assert op["state"] == "being_reconciled" and op["label"] == label


def test_recent_activity_is_history_not_setup():
    tiers = {t["tier"]: t for t in ss.ACTION_CENTER_TIERS}
    assert tiers["activity"] == {"tier": "activity", "owner": "none", "lists": ["recently_updated"]}
    assert "recently_updated" not in tiers["informational"]["lists"]
    listed = [k for t in ss.ACTION_CENTER_TIERS for k in t["lists"]]
    assert len(listed) == len(set(listed))
