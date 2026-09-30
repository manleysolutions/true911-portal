"""RH customer go-live audit — verdict logic + a real-DB fact-gathering run.

The audit's whole purpose is to keep SYSTEM BLOCKERS (Manley must fix before the
invite) apart from CUSTOMER ACTIONS (Judy does after login): E911 confirmation
and missing contacts must never, by themselves, make the verdict BLOCKED.
"""

from __future__ import annotations

import asyncio
import copy

from scripts import rh_customer_go_live_audit as audit
from tests._customer_db import make_db
from tests.test_customer_self_service import RH, seed

ALL_KNOWN = [
    ("Chicago Gallery #147", "147", "Chicago"), ("Austin Gallery #149", "149", "Austin"),
    ("Dallas Gallery #168", "168", "Dallas"), ("Charlotte Gallery #174", "174", "Charlotte"),
    ("Oakbrook Gallery #176", "176", "Oak Brook"), ("Cherry Hill #640", "640", "Cherry Hill"),
    ("Katy Mills #645", "645", "Katy"), ("Irvine #646", "646", "Irvine"),
    ("Boca Raton #654", "654", "Boca Raton"), ("Pembroke #661", "661", "Pembroke Pines"),
    ("Roseville #123", "123", "Roseville"), ("Edina #159", "159", "Edina"),
    ("Raleigh #178", "178", "Raleigh"), ("Dawsonville #604", "604", "Dawsonville"),
    ("Gilbert #642", "642", "Gilbert"), ("San Rafael #656", "656", "San Rafael"),
    ("Princeton Gallery #644", "644", "Princeton"), ("Pleasanton Gallery", None, None),
    ("Hollywood Gallery", None, "Los Angeles"), ("LaSalle Gallery", None, "Chicago IL"),
    ("RH NYC Flagship", None, "New York"), ("Patterson Warehouse", None, "Patterson"),
    ("MDC Distribution Center", None, "Baltimore"), ("Beverly Modern Gallery", None, None),
    ("Linden House Gallery", None, None), ("Soda Grocery Gallery", None, None),
    ("Greenwich Gallery", None, "Greenwich"), ("Richmond Gallery", None, "Richmond"),
    ("Memphis Gallery", None, "Memphis"),
]


def _facts(**over):
    f = {
        "tenant": RH, "as_of": "2026-09-30T00:00:00+00:00",
        "flags": {"customer_api_enabled": True, "customer_preview_enabled": True,
                  "registry_mode_enabled": True, "self_service_enabled": True,
                  "self_service_user_allowlist": [], "dashboard_mode": "registry_mode"},
        "canonical_buildings": len(ALL_KNOWN), "pending_building_rows": 0, "legacy_sites": 42,
        "customer_visible_buildings": len(ALL_KNOWN), "protected_buildings": 29,
        "physical_devices": 40, "device_anchor_mappings": 40, "telephone_numbers": 60,
        "e911_verified": 0, "e911_states": {}, "e911_customer_confirmation": 0,
        "e911_no_address": 0, "pending_reviews": 0, "pending_reviews_by_type": {},
        "open_customer_requests": 0, "requests_waiting_customer": 0,
        "locations_missing_contacts": 0, "unlinked_buildings": [],
        "duplicate_store_numbers": {}, "duplicate_addresses": {}, "invalid_store_numbers": [],
        "buildings": [{"id": i, "canonical_name": n, "store_number": s, "city": c,
                       "address": "3265 Brunswick Pike" if "Princeton" in n else f"{i} Main St"}
                      for i, (n, s, c) in enumerate(ALL_KNOWN)],
    }
    f.update(over)
    return f


def test_clean_portfolio_is_ready():
    rep = audit.evaluate(_facts())
    assert rep["verdict"] == audit.READY, rep
    assert all(status == "OK" for _l, status in rep["known_locations"])


def test_customer_work_is_not_a_blocker():
    rep = audit.evaluate(_facts(e911_customer_confirmation=45, locations_missing_contacts=45,
                                requests_waiting_customer=1))
    assert rep["verdict"] == audit.READY_WITH_CUSTOMER_ACTIONS
    assert rep["system_blockers"] == []
    assert len(rep["customer_actions"]) == 3


def test_flags_and_mode_are_system_blockers():
    f = _facts()
    f["flags"] = {**f["flags"], "self_service_enabled": False, "dashboard_mode": "fallback_mode"}
    rep = audit.evaluate(f)
    assert rep["verdict"] == audit.BLOCKED
    assert any("self-service" in b for b in rep["system_blockers"])
    assert any("fallback_mode" in b for b in rep["system_blockers"])


def test_user_allowlist_is_a_warning_not_a_blocker():
    f = _facts()
    f["flags"] = {**f["flags"], "self_service_user_allowlist": ["rh-test@rh.example"]}
    rep = audit.evaluate(f)
    assert rep["verdict"] == audit.READY and any("allowlist" in w for w in rep["warnings"])


def test_identity_reviews_block_but_new_alias_reviews_warn():
    rep = audit.evaluate(_facts(pending_reviews_by_type={"possible_merge": 1, "unknown_alias": 3}))
    assert rep["verdict"] == audit.BLOCKED
    assert any("possible_merge=1" in b for b in rep["system_blockers"])
    assert any("unknown_alias=3" in w for w in rep["warnings"])


def test_device_kpi_zero_with_mappings_blocks():
    rep = audit.evaluate(_facts(physical_devices=0))
    assert any("Devices KPI" in b for b in rep["system_blockers"])


def test_store_number_on_wrong_location_blocks():
    f = _facts()
    b = copy.deepcopy(f["buildings"])
    b[0]["store_number"] = "999"              # Chicago loses #147 ...
    b[1]["store_number"] = "147"              # ... and Austin carries it
    rep = audit.evaluate(_facts(buildings=b))
    assert rep["verdict"] == audit.BLOCKED
    assert any("#147" in x and "Austin" in x for x in rep["system_blockers"])


def test_duplicate_special_location_blocks_and_missing_one_warns():
    f = _facts()
    b = copy.deepcopy(f["buildings"])
    b.append({"id": 999, "canonical_name": "Beverly Modern Gallery (2)", "store_number": None,
              "city": None, "address": "x"})
    b = [x for x in b if "Greenwich" not in x["canonical_name"]]
    rep = audit.evaluate(_facts(buildings=b))
    assert any("Beverly Modern" in x for x in rep["system_blockers"])
    assert any("Greenwich" in x for x in rep["warnings"])


def test_edina_raleigh_merge_blocks():
    f = _facts()
    b = [x for x in copy.deepcopy(f["buildings"]) if "Raleigh" not in x["canonical_name"]]
    for x in b:
        if x["store_number"] == "159":
            x["canonical_name"] = "Edina / Raleigh Gallery #159"
    rep = audit.evaluate(_facts(buildings=b))
    assert any("Edina #159 and Raleigh #178" in x for x in rep["system_blockers"])


def test_hollywood_zero_and_memphis_duplicates_are_warnings():
    f = _facts()
    b = copy.deepcopy(f["buildings"])
    b.append({"id": 998, "canonical_name": "Memphis Outlet", "store_number": None,
              "city": "Memphis", "address": "y"})
    rep = audit.evaluate(_facts(buildings=b, invalid_store_numbers=[("Hollywood Gallery", "0")]))
    assert rep["verdict"] == audit.READY
    assert any("Hollywood" in w and "'0'" in w for w in rep["warnings"])
    assert any("Memphis" in w for w in rep["warnings"])


def test_gather_on_a_real_db(monkeypatch):
    s = "app.config.settings."
    for k, v in (("FEATURE_CUSTOMER_API", "true"), ("CUSTOMER_API_TENANT_ALLOWLIST", RH),
                 ("FEATURE_CUSTOMER_PREVIEW", "true"), ("CUSTOMER_PREVIEW_TENANT_ALLOWLIST", RH),
                 ("FEATURE_CUSTOMER_PORTFOLIO_REGISTRY", "true"),
                 ("CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST", RH),
                 ("CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS", "false"),
                 ("CUSTOMER_PORTFOLIO_PREVIEW_PENDING", "false"),
                 ("FEATURE_CUSTOMER_SELF_SERVICE", "true"),
                 ("CUSTOMER_SELF_SERVICE_TENANT_ALLOWLIST", RH),
                 ("CUSTOMER_SELF_SERVICE_USER_ALLOWLIST", "")):
        monkeypatch.setattr(s + k, v)

    async def go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            async with Session() as db:
                return await audit.gather(db, RH)
        finally:
            await engine.dispose()
    f = asyncio.run(go())
    assert f["flags"]["dashboard_mode"] == "registry_mode"
    assert f["canonical_buildings"] == 2 and f["customer_visible_buildings"] == 2
    assert f["physical_devices"] == 2 and f["telephone_numbers"] == 2
    assert f["e911_customer_confirmation"] == 2 and f["locations_missing_contacts"] == 2
    assert f["unlinked_buildings"] == ["Austin Gallery #149"]
    rep = audit.evaluate(f)
    # a 2-building fixture is missing most confirmed RH locations (warnings), but
    # E911 confirmation + contacts are CUSTOMER actions, never blockers
    assert rep["verdict"] == audit.READY_WITH_CUSTOMER_ACTIONS, rep["system_blockers"]
    text = audit.render({"facts": f, "report": rep})
    assert "VERDICT: READY_WITH_CUSTOMER_ACTIONS" in text and "Physical devices" in text
