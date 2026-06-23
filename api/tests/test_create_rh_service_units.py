"""P3 — RH service-unit creation tool tests (pure decision surface).

Covers the planner, confidence, normalization, status derivation, the apply gate
(incl. the Stuart-approval gate), and the rollback planner — without exercising
any real DB write (the tool is dry-run-first and this PR never runs DRY_RUN=false).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import create_rh_service_units as m
from app.services.assurance.signals import AssuranceLabel  # noqa: F401 (kept for parity)

T = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


def _dev(did="RH-DEV-1", site_id="RH-BOS-1", model="LM150 Elevator", device_type=None,
         last_heartbeat=None, heartbeat_interval=300, with_id=True, site_name="RH Boston"):
    d = {"device_id": did, "site_id": site_id, "model": model, "device_type": device_type,
         "last_heartbeat": last_heartbeat, "heartbeat_interval": heartbeat_interval,
         "site_name": site_name}
    if with_id:
        d["iccid"] = "8901240000000000001"
    return d


def _devices(*devs):
    return {d["device_id"]: d for d in devs}


# ── Inference + normalization ────────────────────────────────────────
def test_infer_normalization_to_canonical():
    assert m.infer_canonical_unit(_dev(model="LM150 Elevator"))[0] == "elevator_phone"
    assert m.infer_canonical_unit(_dev(model="Napco Fire Radio"))[0] == "fire_alarm"
    assert m.infer_canonical_unit(_dev(model="Burglar Alarm Panel"))[0] == "fire_alarm"
    assert m.infer_canonical_unit(_dev(model="Lobby Call Box"))[0] == "emergency_call_station"
    assert m.infer_canonical_unit(_dev(model="Fax machine"))[0] == "fax_line"
    assert m.infer_canonical_unit(_dev(model="Cisco ATA"))[0] == "voice_line"
    # strong cue -> 0.9; analog -> 0.6; default -> 0.3
    assert m.infer_canonical_unit(_dev(model="LM150 Elevator"))[1] == 0.9
    assert m.infer_canonical_unit(_dev(model="analog POTS"))[1] == 0.6
    assert m.infer_canonical_unit(_dev(model="Mystery Box"))[1] == 0.3


def test_score_confidence_signals():
    assert m.score_confidence(0.9, location_present=True, has_identifier=True) == 0.95
    assert m.score_confidence(0.9, location_present=False, has_identifier=False) == 0.4  # cap
    assert m.score_confidence(0.3, location_present=False, has_identifier=True, override=0.8) == 0.8


def test_derive_status_no_false_green():
    assert m.derive_status(_dev(last_heartbeat=None)) == "pending_install"
    assert m.derive_status(_dev(last_heartbeat=datetime.now(timezone.utc))) == "active"
    assert m.derive_status(_dev(last_heartbeat=datetime(2020, 1, 1, tzinfo=timezone.utc))) == "pending_install"


# ── Planner ──────────────────────────────────────────────────────────
def _row(did="RH-DEV-1", unit_type="elevator_phone", confirmed=True, **kw):
    r = {"device_id": did, "unit_type": unit_type, "confirmed": confirmed}
    r.update(kw)
    return r


def test_plan_creates_confirmed_unit():
    plan = m.plan_service_units([_row(location_description="Elevator #1")],
                                _devices(_dev()), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert plan.safe and len(plan.creates) == 1
    c = plan.creates[0]
    assert c["unit_id"] == "SU-RH-DEV-1" and c["unit_type"] == "elevator_phone"
    assert c["site_id"] == "RH-BOS-1" and c["status"] == "pending_install"
    assert c["compliance_status"] == "unknown"


def test_plan_refuses_unknown_field():
    plan = m.plan_service_units([_row(bogus="x")], _devices(_dev()), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not plan.safe and plan.creates == []


def test_plan_refuses_non_canonical_type():
    plan = m.plan_service_units([_row(unit_type="fire_alarm_line")], _devices(_dev()),
                                {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not plan.safe and any("not canonical" in r for r in plan.refusals)


def test_plan_refuses_unconfirmed():
    plan = m.plan_service_units([_row(confirmed=False)], _devices(_dev()),
                                {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not plan.safe and any("not confirmed" in r for r in plan.refusals)


def test_plan_refuses_unknown_device_and_site():
    p1 = m.plan_service_units([_row(did="GHOST")], _devices(_dev()), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not p1.safe and any("not found" in r for r in p1.refusals)
    p2 = m.plan_service_units([_row()], _devices(_dev(site_id="NOPE")), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not p2.safe and any("unresolved" in r for r in p2.refusals)


def test_plan_duplicate_device_id_refused():
    plan = m.plan_service_units([_row(), _row()], _devices(_dev()), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not plan.safe and any("duplicate" in r for r in plan.refusals)


def test_plan_idempotent_noop_for_covered_device():
    plan = m.plan_service_units([_row()], _devices(_dev()), {"RH-BOS-1"}, {"RH-DEV-1"}, min_confidence=0.5)
    assert plan.safe and plan.creates == [] and plan.noops == ["RH-DEV-1"]


def test_plan_all_or_nothing():
    good, bad = _row(did="RH-DEV-1"), _row(did="RH-DEV-2", bogus="x")
    plan = m.plan_service_units([good, bad],
                                _devices(_dev("RH-DEV-1"), _dev("RH-DEV-2")),
                                {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not plan.safe and plan.creates == []  # one refusal => nothing created


def test_plan_confidence_floor_and_override():
    dev = _dev(model="Mystery Box", with_id=False)  # default type, no identifier -> conf 0.3
    refused = m.plan_service_units([_row(unit_type="voice_line")], _devices(dev),
                                   {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert not refused.safe and any("confidence" in r for r in refused.refusals)
    ok = m.plan_service_units([_row(unit_type="voice_line", confidence_override=0.8)],
                              _devices(dev), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert ok.safe and ok.creates[0]["confidence"] == 0.8


def test_plan_status_active_when_fresh():
    dev = _dev(last_heartbeat=datetime.now(timezone.utc))
    plan = m.plan_service_units([_row()], _devices(dev), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert plan.creates[0]["status"] == "active"


# ── Apply gate (Stuart approval) ─────────────────────────────────────
def _good_plan():
    return m.plan_service_units([_row()], _devices(_dev()), {"RH-BOS-1"}, set(), min_confidence=0.5)


def test_apply_gate():
    plan = _good_plan()
    assert m.apply_allowed(True, "stuart@x", plan) == (False, "dry-run")
    assert m.apply_allowed(False, "", plan) == (False, "approval-required")   # Stuart gate
    assert m.apply_allowed(False, "stuart@x", plan) == (True, "apply")
    bad = m.plan_service_units([_row(bogus="x")], _devices(_dev()), {"RH-BOS-1"}, set(), min_confidence=0.5)
    assert m.apply_allowed(False, "stuart@x", bad) == (False, "refused")
    empty = m.plan_service_units([_row()], _devices(_dev()), {"RH-BOS-1"}, {"RH-DEV-1"}, min_confidence=0.5)
    assert m.apply_allowed(False, "stuart@x", empty) == (False, "nothing-to-create")


def test_build_unit_meta():
    c = _good_plan().creates[0]
    meta = m.build_unit_meta(c, batch_id="su-1", actor="a", approver="stuart@x", now_iso="2026-07-15T08:00:00Z")
    assert meta["source"] == m.SOURCE and meta["batch_id"] == "su-1"
    assert meta["approved_by"] == "stuart@x" and meta["confidence"] == c["confidence"]


# ── Rollback planner ─────────────────────────────────────────────────
def _unit(unit_id="SU-1", batch="b1", status="active", created=T, updated=T,
          rolled=False, source=m.SOURCE):
    meta = {"source": source, "batch_id": batch}
    if rolled:
        meta["rolled_back_at"] = "2026-07-16"
        status = "decommissioned"
    return SimpleNamespace(unit_id=unit_id, site_id="S", device_id="D", status=status,
                           created_at=created, updated_at=updated, meta=meta)


def test_rollback_selects_batch_no_drift():
    units = [_unit("SU-1", batch="b1"), _unit("SU-2", batch="b1"),
             _unit("SU-9", batch="other")]
    rp = m.plan_rollback(units, batch_id="b1")
    assert rp.safe and {u.unit_id for u in rp.to_reverse} == {"SU-1", "SU-2"}


def test_rollback_drift_guard_refuses_all():
    units = [_unit("SU-1", batch="b1"),
             _unit("SU-2", batch="b1", updated=T + timedelta(seconds=30))]  # human-edited
    rp = m.plan_rollback(units, batch_id="b1")
    assert not rp.safe and rp.to_reverse == []  # all-or-nothing


def test_rollback_idempotent_skips_already_rolled():
    rp = m.plan_rollback([_unit("SU-1", batch="b1", rolled=True)], batch_id="b1")
    assert rp.safe and rp.to_reverse == [] and rp.skipped_already == ["SU-1"]


def test_rollback_ignores_foreign_source():
    rp = m.plan_rollback([_unit("SU-1", batch="b1", source="someone_else")], batch_id="b1")
    assert rp.safe and rp.to_reverse == []
