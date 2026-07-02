"""RH registry approval script — plan builder (pure) + apply (fake session).

Pins the operator decision table (merges / exclusions / canonical overrides /
keep-separate), the confidence + limit filters, collision-safe aliases/mappings, and
that --apply writes ONLY the registry via the approval workflow (never Site/Device/
E911/Zoho/Napco/Genesis).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.models.portfolio_registry import PortfolioReviewItem
from scripts import rh_registry_approve_from_review as ap


def _cand(canonical, store=None, sources=("zoho",), devices=None, conf=100.0, source_names=None,
          site_id=None):
    return {"canonical_name": canonical, "store_number": store, "site_type": "gallery",
            "building_category": "Retail",
            "address": {"street": "1 Main", "city": "Town", "state": "ST", "zip": "00000"},
            "source_names": source_names or {"zoho": [canonical]}, "devices": devices or [],
            "e911": {"site_id": site_id}, "sources": list(sources), "source_confidence": conf}


def _item(rid, canonical, store=None, **kw):
    cand = _cand(canonical, store=store, **kw)
    return SimpleNamespace(id=rid, review_type="new_building", payload=json.dumps(cand),
                           candidate_name=canonical, store_number=store)


def _plan(items, *, decisions=True, only_high=False, limit=None):
    parsed = [ap.parse_review_item(it) for it in items]
    return ap.build_plan(parsed, apply_decisions=decisions, only_high=only_high, limit=limit)


# ── decision table: merges + canonical overrides ────────────────────
def test_merges_and_canonical_overrides():
    plan = _plan([
        _item(1, "RH Hollywood CA - Elevator", source_names={"genesis": ["RH Hollywood CA - Elevator"]}),
        _item(2, "Restoration Hardware #146 Hollywood", store="146"),
        _item(3, "Restoration hardware 147 Chicago", store="147"),
        _item(4, "RH #147 Chicago Gallery", store="147"),
    ])
    by_name = {s["canonical_name"]: s for s in plan["creates"]}
    assert "Hollywood Gallery" in by_name and "Chicago Gallery #147" in by_name
    assert by_name["Hollywood Gallery"]["review_ids"] == [1, 2]        # merged
    assert by_name["Hollywood Gallery"]["store_number"] == "146"       # store adopted on merge
    assert by_name["Chicago Gallery #147"]["review_ids"] == [3, 4]
    assert len(plan["merged"]) == 2


def test_special_location_canonicals_and_site_types():
    plan = _plan([
        _item(1, "Restoration Hardware - MDC"),
        _item(2, "Restoration Hardware - Patterson Warehouse"),
        _item(3, "Restoration Hardware #RHNYC"),
        _item(4, "Restoration Hardware - Lindern House"),
        _item(5, "Restoration Hardware - Soda Grocery"),
    ])
    m = {s["canonical_name"]: s for s in plan["creates"]}
    assert m["MDC Distribution Center"]["site_type"] == "distribution_center"
    assert m["Patterson Warehouse"]["site_type"] == "warehouse"
    assert "RH NYC Flagship" in m and "Linden House Gallery" in m and "Soda Grocery Gallery" in m


def test_memphis_flagged_for_research():
    plan = _plan([_item(1, "Restoration Hardware Memphis")])
    memphis = plan["creates"][0]
    assert memphis["canonical_name"] == "Memphis Gallery" and "research" in (memphis["note"] or "")


# ── exclusions ───────────────────────────────────────────────────────
def test_parent_account_excluded():
    plan = _plan([_item(1, "Restoration Hardware (main account)"),
                  _item(2, "Restoration Hardware")])   # bare brand, no store -> parent
    assert plan["creates"] == []
    assert len(plan["excluded"]) == 2


def test_parent_exclusion_does_not_eat_real_stores():
    plan = _plan([_item(1, "Restoration Hardware #632 Vero Beach", store="632")])
    assert len(plan["creates"]) == 1 and plan["excluded"] == []


# ── keep-separate guard ──────────────────────────────────────────────
def test_edina_and_raleigh_stay_separate():
    plan = _plan([_item(1, "Restoration Hardware #159 Edina", store="159"),
                  _item(2, "Restoration Hardware #178 Raleigh", store="178")])
    stores = {s["store_number"] for s in plan["creates"]}
    assert stores == {"159", "178"} and len(plan["creates"]) == 2   # never fused


def test_princeton_brunswick_pike_merges_to_644():
    plan = _plan([_item(1, "Restoration Hardware 3265 Brunswick Pike", store="644"),
                  _item(2, "Restoration Hardware Princeton Outlet", store="644")])
    assert len(plan["creates"]) == 1
    assert plan["creates"][0]["canonical_name"] == "Princeton Gallery #644"


# ── confidence + limit filters ───────────────────────────────────────
def test_only_high_confidence_skips_low_non_decisions():
    items = [_item(1, "Restoration Hardware #632 Vero Beach", store="632", conf=55.0),  # low, no decision
             _item(2, "Restoration Hardware - MDC", conf=40.0)]                          # low but a decision
    plan = _plan(items, only_high=True)
    names = {s["canonical_name"] for s in plan["creates"]}
    assert "MDC Distribution Center" in names                 # decision approved regardless
    assert not any("Vero Beach" in n for n in names)          # low-confidence non-decision skipped
    assert any("high-confidence" in s["reason"] for s in plan["skipped"])


def test_limit_caps_building_count():
    items = [_item(i, f"Restoration Hardware #{140+i} City{i}", store=str(140 + i)) for i in range(5)]
    plan = _plan(items, decisions=False, limit=2)
    assert len(plan["creates"]) == 2
    assert any(s["reason"] == "over --limit" for s in plan["skipped"])


# ── aliases + device mappings (collision-safe) ──────────────────────
def test_aliases_and_device_mappings_extracted():
    dev = {"radio_number": "RAD1", "iccid": "IC1", "imei": None, "msisdn": "3125550100",
           "starlink_id": None, "serial": None}
    plan = _plan([_item(1, "Restoration Hardware #147 Chicago", store="147", devices=[dev],
                        source_names={"zoho": ["Restoration Hardware #147 Chicago"],
                                      "napco": ["RH 147 Chicago Alarm"]}, site_id="RH-147")])
    s = plan["creates"][0]
    kinds = {m["kind"] for m in s["device_mappings"]}
    assert {"napco_radio", "iccid", "genesis_msisdn", "phone", "true911_device", "zoho_account"} <= kinds
    assert "restorationhardware" not in {ap.norm_alias(a) for a in s["aliases"]}   # brand-only skipped


def test_alias_and_mapping_collisions_deduped_across_buildings():
    # same ICCID appears on two candidates -> mapping kept once (uq-safe)
    dev = {"radio_number": None, "iccid": "SHARED", "imei": None, "msisdn": None,
           "starlink_id": None, "serial": None}
    plan = _plan([_item(1, "Restoration Hardware #140 A", store="140", devices=[dev]),
                  _item(2, "Restoration Hardware #141 B", store="141", devices=[dev])],
                 decisions=False)
    all_maps = [m for s in plan["creates"] for m in s["device_mappings"] if m["kind"] == "iccid"]
    assert len(all_maps) == 1                                 # deduped globally


def test_unparseable_payload_is_unresolved():
    bad = SimpleNamespace(id=9, review_type="new_building", payload="{not json",
                          candidate_name="x", store_number=None)
    plan = ap.build_plan([ap.parse_review_item(bad)], apply_decisions=True, only_high=False)
    assert len(plan["unresolved"]) == 1 and plan["creates"] == []


# ── apply writes ONLY the registry (fake session) ───────────────────
class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, exec_batches=None):
        self.added = []
        self.commits = 0
        self._exec = list(exec_batches or [])
        self._next = 1

    def add(self, o):
        self.added.append(o)

    async def flush(self):
        for o in self.added:
            if getattr(o, "id", None) is None:
                o.id = self._next
                self._next += 1

    async def commit(self):
        self.commits += 1

    async def execute(self, stmt):
        # 1st execute: _decide_review(primary) → [r1]; 2nd: merged-extra lookup → [r2]
        return _Result(self._exec.pop(0) if self._exec else [])


def test_apply_creates_building_and_decides_reviews():
    r1 = PortfolioReviewItem(tenant_id="rh", review_type="new_building", status="pending",
                             signature="s1")
    r1.id = 1
    r2 = PortfolioReviewItem(tenant_id="rh", review_type="new_building", status="pending",
                             signature="s2")
    r2.id = 2
    db = _FakeDB(exec_batches=[[r1], [r2]])   # decide(primary=r1), then merged-extra lookup r2
    plan = {"creates": [{"canonical_name": "Chicago Gallery #147", "store_number": "147",
                         "site_type": "gallery", "address": "1 Main", "city": "Chicago",
                         "state": "IL", "zip": "60601", "aliases": ["RH 147 Chicago"],
                         "device_mappings": [{"kind": "iccid", "value": "IC1", "source": "vendor"}],
                         "review_ids": [1, 2], "note": None}]}
    created = asyncio.run(ap.apply_plan(db, "rh", plan, approved_by="ops@x"))
    assert created[0]["building_id"] == 1 and created[0]["merged_reviews"] == 2
    kinds = {type(o).__name__ for o in db.added}
    assert {"PortfolioBuilding", "PortfolioAlias", "PortfolioDeviceMapping"} <= kinds
    bldg = next(o for o in db.added if type(o).__name__ == "PortfolioBuilding")
    assert bldg.approved is True and bldg.approved_by == "ops@x"
    # the merged extra review item was decided -> approved
    assert r2.status == "approved" and r2.suggested_building_id == 1
