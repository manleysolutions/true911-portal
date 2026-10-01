"""Customer trust rule — KNOWN GOOD · KNOWN PROBLEM · UNKNOWN (DECISIONS D-022).

UNKNOWN != FAILED and UNKNOWN != PROTECTED.  A location without a linked
monitoring record is "being reconciled" by True911 — never "unprotected" and
never green.  Only an evidence-backed assurance label yields "monitored" or
"needs attention", and a known problem always wins.  Action-center ownership
keeps True911's work off the customer's to-do list.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.customer import serialize as cs
from app.services.customer import self_service as ss
from tests._customer_db import client_for, make_db, user
from tests.test_customer_self_service import B1, B2, RH, ROUTERS, flags, seed  # noqa: F401


# ── pure mapping ─────────────────────────────────────────────────────
@pytest.mark.parametrize("status,linked,state", [
    ("Protected", True, "monitored"),
    ("Unknown", True, "not_yet_confirmed"),
    ("Pending Install", True, "not_yet_confirmed"),
    ("Inactive", True, "not_yet_confirmed"),
    (None, True, "not_yet_confirmed"),
    ("Unknown", False, "being_reconciled"),
    ("Protected", False, "being_reconciled"),       # never green without a monitoring link
    ("Attention Needed", True, "attention_required"),
    ("Critical", True, "attention_required"),
    ("Critical", False, "attention_required"),      # a known problem always wins
])
def test_operational_state_mapping(status, linked, state):
    op = cs.operational_state(status, linked=linked)
    assert op["state"] == state
    assert op["urgent"] is (status == "Critical")
    evidence = {"monitored": "known_good", "attention_required": "known_problem"}.get(state, "unknown")
    assert op["evidence"] == evidence


def test_unknown_is_never_labelled_failed_or_protected():
    for st in ("being_reconciled", "not_yet_confirmed"):
        label, summary, evidence = cs.OPERATIONAL_STATES[st]
        assert evidence == "unknown"
        for word in ("unprotected", "fail", "offline", "down", "protected"):
            assert word not in (label + " " + summary).lower(), (st, word)


def test_action_center_tiers_assign_ownership():
    tiers = {t["tier"]: t for t in ss.ACTION_CENTER_TIERS}
    assert tiers["urgent"]["lists"] == ["needs_attention"]
    assert "e911_confirmation_required" in tiers["action_needed"]["lists"]
    assert tiers["action_needed"]["owner"] == "customer"
    for k in ("e911_not_ready", "being_reconciled"):
        assert k in tiers["in_progress"]["lists"] and tiers["in_progress"]["owner"] == "true911"
    assert "missing_contact_information" in tiers["informational"]["lists"]
    listed = [k for t in ss.ACTION_CENTER_TIERS for k in t["lists"]]
    assert len(listed) == len(set(listed))                 # each list in exactly one tier


# ── real DB: Chicago linked (monitored), Austin unlinked (being reconciled) ──
def run(scenario):
    async def _go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            state = {"user": user()}
            async with client_for(ROUTERS, Session, state) as c:
                return await scenario(c, Session, state)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


def test_summary_reports_operational_states_not_failures(flags):
    async def sc(c, Session, state):
        s = (await c.get("/api/customer/portfolio/summary")).json()["data"]
        assert s["operational_states"] == {"monitored": 1, "attention_required": 0,
                                           "being_reconciled": 1, "not_yet_confirmed": 0}
        assert s["e911_verified_locations"] == 0
        assert s["devices"] == 2                                      # no KPI regression
        items = (await c.get("/api/customer/locations")).json()["data"]["items"]
        by_ref = {i["building_ref"]: i for i in items}
        assert by_ref[B1]["operational_state"]["label"] == "Monitored"
        assert by_ref[B2]["operational_state"]["label"] == "Monitoring record being confirmed"
        assert by_ref[B2]["monitoring_linked"] is False
        assert "unprotected" not in json.dumps(items).lower()
    run(sc)


def test_action_center_puts_reconciliation_on_true911_not_the_customer(flags):
    async def sc(c, Session, state):
        ac = (await c.get("/api/customer/action-center")).json()["data"]
        assert [x["location_ref"] for x in ac["being_reconciled"]] == [B2]
        assert ac["needs_attention"] == []                           # nothing known broken
        assert ac["counts"]["being_reconciled"] == 1
        assert ac["tiers"] == ss.ACTION_CENTER_TIERS
        # the customer's lists never contain True911's reconciliation work
        customer_lists = [k for t in ac["tiers"] if t["owner"] == "customer" for k in t["lists"]]
        assert "being_reconciled" not in customer_lists and "e911_not_ready" not in customer_lists
    run(sc)


def test_workspace_status_is_evidence_based(flags):
    async def sc(c, Session, state):
        w1 = (await c.get(f"/api/customer/locations/{B1}/workspace")).json()["data"]["location"]
        assert w1["operational_state"]["state"] == "monitored"
        assert w1["monitored_service_count"] == w1["service_count"] == 1
        w2 = (await c.get(f"/api/customer/locations/{B2}/workspace")).json()["data"]["location"]
        assert w2["operational_state"]["state"] == "being_reconciled"
        assert w2["monitored_service_count"] == 0
    run(sc)


def test_legacy_site_summary_carries_the_same_contract(flags):
    flags(registry="false")

    async def sc(c, Session, state):
        s = (await c.get("/api/customer/portfolio/summary")).json()["data"]
        assert s["operational_states"]["monitored"] == 1
        assert s["operational_states"]["being_reconciled"] == 0
        assert "e911_verified_locations" in s
    run(sc)


def test_customer_workflows_and_e911_rules_unchanged(flags):
    async def sc(c, Session, state):
        r = await c.put(f"/api/customer/locations/{B1}/contacts",
                        json={"contacts": {"facility": {"name": "Pat", "phone": "3125550111"}}})
        assert r.status_code == 200
        r = await c.post(f"/api/customer/locations/{B1}/e911/verification",
                         json={"address_confirmed": True, "building_confirmed": True, "attest": True})
        assert r.json()["data"]["e911"]["state"] == "customer_submitted"
        assert r.json()["data"]["e911"]["verified"] is False
        s = (await c.get("/api/customer/portfolio/summary")).json()["data"]
        assert s["e911_verified_locations"] == 0                     # never auto-verified
        act = (await c.get(f"/api/customer/locations/{B1}/activity")).json()["data"]["activity"]
        assert {a["summary"] for a in act} >= {"Updated facility contact", "E911 verification requested"}
    run(sc)
