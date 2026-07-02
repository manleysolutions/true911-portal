"""Portfolio Registry — reconcile (pure) + approval workflow (fake-session).

No DB fixture exists in this project, so these follow the established pattern:
pure-function tests for ``reconcile`` (mapping order + every review type) and a
small in-memory AsyncSession substitute for the load / approval writers.  Verifies
approved mappings win before heuristics and that the registry is written ONLY
through the explicit approval workflow.
"""

from __future__ import annotations

import asyncio

from app.models.portfolio_registry import PortfolioReviewItem
from app.services import portfolio_registry as reg


# ── helpers to build a registry snapshot ─────────────────────────────
def _building(id, store=None, name="RH", street=None, city=None, state=None, approved=True):
    return {"id": id, "canonical_name": name, "store_number": store, "site_type": "store",
            "status": "active", "address": street, "city": city, "state": state, "zip": None,
            "approved": approved}


def _alias(bid, alias):
    return {"building_id": bid, "alias": alias, "alias_normalized": reg.norm_alias(alias),
            "source": "operator", "confidence": 100, "active": True}


def _map(bid, kind, value):
    vn = reg.norm_id(value) if kind != "zoho_account" else reg.norm_alias(value)
    return {"building_id": bid, "kind": kind, "value": value, "value_normalized": vn,
            "source": "test", "confidence": 100, "active": True}


def _registry(buildings=(), aliases=(), mappings=(), reviews=()):
    return {"tenant": "rh", "buildings": list(buildings), "aliases": list(aliases),
            "device_mappings": list(mappings), "review_items": list(reviews)}


def _cand(name="RH #177 Jacksonville", store="177", street=None, city=None, state=None,
          devices=None, site_id=None, zoho_names=None):
    return {"canonical_name": name, "store_number": store,
            "address": {"street": street, "city": city, "state": state, "zip": None},
            "devices": devices or [], "e911": {"site_id": site_id},
            "source_names": {"zoho": zoho_names or []}, "source_confidence": 100,
            "sources": ["zoho"]}


def _dev(**kw):
    base = {"radio_number": None, "imei": None, "iccid": None, "msisdn": None, "serial": None}
    base.update(kw)
    return base


# ── normalization ────────────────────────────────────────────────────
def test_normalizers():
    assert reg.norm_alias("Restoration Hardware #177!") == "restorationhardware177"
    assert reg.norm_id(" 89-01:26 ") == "890126"
    assert reg.norm_addr("10300 Southside Blvd", "Jacksonville", "FL") == "10300 southside blvd jacksonville fl"


# ── reconcile: empty registry -> new building ────────────────────────
def test_reconcile_empty_registry_new_building():
    out = reg.reconcile([_cand()], _registry())
    assert out["stats"]["resolved"] == 0
    assert out["review_items"][0]["review_type"] == reg.RT_NEW_BUILDING
    assert out["stats"]["review_by_type"] == {reg.RT_NEW_BUILDING: 1}


# ── reconcile: mapping order (approved mappings BEFORE heuristics) ────
def test_reconcile_device_mapping_wins():
    registry = _registry(
        buildings=[_building(1, store="999", name="Other")],   # store# would NOT match cand 177
        mappings=[_map(1, "napco_radio", "RAD177")])
    cand = _cand(store=None, devices=[_dev(radio_number="RAD177")])
    out = reg.reconcile([cand], registry)
    assert out["resolved"][0]["building_id"] == 1 and out["resolved"][0]["method"] == "device"


def test_reconcile_alias_mapping():
    registry = _registry(buildings=[_building(2, store=None, name="RH MDC")],
                         aliases=[_alias(2, "Restoration Hardware - MDC")])
    cand = _cand(name="Restoration Hardware - MDC", store=None)
    out = reg.reconcile([cand], registry)
    assert out["resolved"][0]["building_id"] == 2 and out["resolved"][0]["method"] == "alias"


def test_reconcile_store_number_mapping():
    registry = _registry(buildings=[_building(3, store="177")])
    out = reg.reconcile([_cand(name="Zzz", store="177")], registry)
    assert out["resolved"][0]["building_id"] == 3 and out["resolved"][0]["method"] == "store_number"


def test_reconcile_address_mapping():
    registry = _registry(buildings=[_building(4, store=None, street="10300 Southside Blvd",
                                              city="Jacksonville", state="FL")])
    cand = _cand(name="Zzz", store=None, street="10300 Southside Blvd", city="Jacksonville", state="FL")
    out = reg.reconcile([cand], registry)
    assert out["resolved"][0]["building_id"] == 4 and out["resolved"][0]["method"] == "address"


# ── reconcile: review types ──────────────────────────────────────────
def test_reconcile_possible_merge():
    # device maps to bld 1, store# maps to bld 2 -> ambiguous / possible merge
    registry = _registry(buildings=[_building(1, store=None), _building(2, store="177")],
                         mappings=[_map(1, "iccid", "ICX")])
    cand = _cand(store="177", devices=[_dev(iccid="ICX")])
    out = reg.reconcile([cand], registry)
    assert any(r["review_type"] == reg.RT_POSSIBLE_MERGE for r in out["review_items"])


def test_reconcile_duplicate_building():
    registry = _registry(buildings=[_building(1, store="177"), _building(2, store="177")])
    out = reg.reconcile([], registry)
    assert any(r["review_type"] == reg.RT_DUPLICATE_BUILDING for r in out["review_items"])


def test_reconcile_address_conflict():
    registry = _registry(buildings=[_building(5, store="177", street="1 Old St", city="Jax", state="FL")])
    cand = _cand(store="177", street="999 New Rd", city="Jax", state="FL")
    out = reg.reconcile([cand], registry)
    assert any(r["review_type"] == reg.RT_ADDRESS_CONFLICT for r in out["review_items"])


def test_reconcile_device_conflict():
    # candidate resolves by store# to bld 1, but its radio is approved-mapped to bld 2
    registry = _registry(buildings=[_building(1, store="177"), _building(2, store="888")],
                         mappings=[_map(2, "napco_radio", "RADX")])
    cand = _cand(store="177", devices=[_dev(radio_number="RADX")])
    out = reg.reconcile([cand], registry)
    assert any(r["review_type"] in (reg.RT_DEVICE_CONFLICT, reg.RT_POSSIBLE_MERGE)
               for r in out["review_items"])


def test_reconcile_unknown_alias():
    # resolves by store#, but the label is not an approved alias -> suggest adding it
    registry = _registry(buildings=[_building(6, store="177", name="RH #177")])
    cand = _cand(name="RH Jax Downtown", store="177")
    out = reg.reconcile([cand], registry)
    assert any(r["review_type"] == reg.RT_UNKNOWN_ALIAS for r in out["review_items"])
    assert out["resolved"][0]["method"] == "store_number"


def test_reconcile_stats_shape():
    registry = _registry(buildings=[_building(1, store="177")],
                         aliases=[_alias(1, "RH #177")], mappings=[_map(1, "iccid", "IC")],
                         reviews=[{"status": "rejected"}, {"status": "pending"}])
    out = reg.reconcile([_cand(store="177", name="RH #177")], registry)
    st = out["stats"]
    assert st["portfolio_buildings"] == 1 and st["approved_buildings"] == 1
    assert st["known_aliases"] == 1 and st["approved_mappings"] == 1
    assert st["rejected_suggestions"] == 1


# ── approval workflow (fake AsyncSession) — the ONLY registry writers ─
class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self_inner):
                return list(rows)
        return _S()

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, exec_batches=None):
        self.added = []
        self.committed = False
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
        self.committed = True

    async def execute(self, stmt):
        return _Result(self._exec.pop(0) if self._exec else [])


def test_approve_new_building_writes_registry_and_decides_review():
    review = PortfolioReviewItem(tenant_id="rh", review_type=reg.RT_NEW_BUILDING,
                                 status="pending", signature="sig1")
    review.id = 7
    db = _FakeDB(exec_batches=[[review]])       # _decide_review lookup returns this row
    out = asyncio.run(reg.approve_new_building(
        db, "rh", approved_by="ops@x", canonical_name="RH #177 Jacksonville", store_number="177",
        site_type="store", address="10300 Southside Blvd", city="Jacksonville", state="FL",
        aliases=["Restoration Hardware #177 Jacksonville"],
        device_mappings=[{"kind": "napco_radio", "value": "RAD177", "source": "napco"},
                         {"kind": "iccid", "value": "ICRH177", "source": "zoho"}],
        review_item_id=7))
    assert db.committed and out["building_id"] == 1
    kinds = {type(o).__name__ for o in db.added}
    assert {"PortfolioBuilding", "PortfolioAlias", "PortfolioDeviceMapping"} <= kinds
    bldg = next(o for o in db.added if type(o).__name__ == "PortfolioBuilding")
    assert bldg.approved is True and bldg.approved_by == "ops@x"
    assert review.status == "approved" and review.decided_by == "ops@x"


def test_reject_review_item_sets_status():
    review = PortfolioReviewItem(tenant_id="rh", review_type=reg.RT_NEW_BUILDING,
                                 status="pending", signature="sig2")
    review.id = 8
    db = _FakeDB(exec_batches=[[review]])
    asyncio.run(reg.reject_review_item(db, "rh", 8, rejected_by="ops@x"))
    assert review.status == "rejected" and db.committed


def test_sync_review_queue_dedups_by_signature():
    existing = PortfolioReviewItem(tenant_id="rh", review_type=reg.RT_NEW_BUILDING,
                                   status="pending", signature="dup")
    db = _FakeDB(exec_batches=[[existing]])
    items = [{"review_type": reg.RT_NEW_BUILDING, "signature": "dup", "detail": "x"},
             {"review_type": reg.RT_NEW_BUILDING, "signature": "fresh", "detail": "y",
              "candidate": {"canonical_name": "RH #1"}}]
    out = asyncio.run(reg.sync_review_queue(db, "rh", items))
    assert out["added"] == 1 and out["skipped"] == 1        # only the fresh one written


def test_load_registry_shape():
    from app.models.portfolio_registry import (
        PortfolioAlias,
        PortfolioBuilding,
        PortfolioDeviceMapping,
    )
    b = PortfolioBuilding(tenant_id="rh", canonical_name="RH #177", store_number="177",
                          status="active", approved=True)
    b.id = 1
    a = PortfolioAlias(tenant_id="rh", building_id=1, alias="RH 177",
                       alias_normalized="rh177", active=True, confidence=100)
    m = PortfolioDeviceMapping(tenant_id="rh", building_id=1, kind="iccid", value="IC",
                               value_normalized="IC", active=True, confidence=100)
    db = _FakeDB(exec_batches=[[b], [a], [m], []])          # buildings, aliases, mappings, reviews
    snap = asyncio.run(reg.load_registry(db, "rh"))
    assert snap["buildings"][0]["approved"] is True and snap["buildings"][0]["store_number"] == "177"
    assert snap["aliases"][0]["alias_normalized"] == "rh177"
    assert snap["device_mappings"][0]["kind"] == "iccid"
