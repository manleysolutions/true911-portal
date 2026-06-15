"""Tests for the pure Identity Audit aggregation (Phase 0 / PR-1b1).

Builds synthetic datasets via the loader's pure ``build_dataset`` and asserts the
aggregated report. No DB, no I/O.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.identity.audit import run_identity_audit
from app.services.identity.loader import build_dataset

AT = "2026-06-14T00:00:00+00:00"


def _row(**kw):
    return SimpleNamespace(**kw)


def _device(device_id, **kw):
    base = dict(tenant_id="t1", site_id=None, iccid=None, imei=None, msisdn=None,
                carrier=None, identifier_type=None, status="active",
                serial_number=None, sim_id=None)
    base.update(kw)
    return _row(device_id=device_id, **base)


def _site(site_id, *, customer_id=1, addr=True, status="validated", confirm=False):
    return _row(site_id=site_id, tenant_id="t1", customer_id=customer_id,
                e911_street=("1 Main" if addr else None), e911_city="T",
                e911_state="FL", e911_zip="33000", e911_status=status,
                e911_confirmation_required=confirm)


def _customer(cid=1):
    return _row(id=cid, tenant_id="t1")


def _sim(iccid, **kw):
    base = dict(msisdn=None, imei=None, device_id=None, site_id=None, customer_id=None, carrier="t")
    base.update(kw)
    return _row(iccid=iccid, **base)


def test_audit_counts_resolved_orphan_ambiguous():
    devices = [
        # resolved by ICCID, full chain
        _device("d-ok", site_id="S1", iccid="ICCID-1", carrier="t", identifier_type="cellular"),
        # orphan: no site
        _device("d-orphan", iccid="ICCID-2", carrier="t", identifier_type="cellular"),
        # ambiguous: MSISDN -> 2 sims
        _device("d-amb", site_id="S1", msisdn="+1700", carrier="t", identifier_type="cellular"),
    ]
    sims = [
        _sim("ICCID-1", site_id="S1", customer_id=1),
        _sim("ICCID-2", customer_id=1),
        _sim("ICCID-3", msisdn="+1700"),
        _sim("ICCID-4", msisdn="+1700"),
    ]
    ds = build_dataset(devices, sims, [_site("S1")], [_customer(1)], [], [])
    rep = run_identity_audit(ds, generated_at=AT, tenant_id="t1")

    assert rep["totals"]["devices_total"] == 3
    assert rep["totals"]["resolved"] == 1
    assert rep["totals"]["orphan"] == 1
    assert rep["totals"]["ambiguous"] == 1
    assert rep["totals"]["resolution_rate"] == round(1 / 3, 4)
    assert rep["read_only"] is True
    assert rep["scope"]["tenant_id"] == "t1"


def test_audit_gaps_and_sim_quality():
    devices = [_device("d-orphan", iccid="GHOST", carrier="t", identifier_type="cellular")]
    sims = [
        _sim("ICCID-A", msisdn="+1700"),          # unassigned (no device_id)
        _sim("ICCID-B", msisdn="+1700"),          # duplicate msisdn
        _sim("ICCID-C", device_id="d-x"),         # assigned
    ]
    ds = build_dataset(devices, sims, [], [], [], [])
    rep = run_identity_audit(ds, generated_at=AT)

    assert rep["gaps"]["orphan_devices"] == 1
    assert rep["gaps"]["missing_site"] == 1
    assert rep["gaps"]["unmatched_iccid"] == 1     # GHOST iccid not in sims
    assert rep["gaps"]["unassigned_sims"] == 2
    assert rep["gaps"]["duplicate_msisdn"] == 1    # +1700 on two sims
    assert rep["gaps"]["duplicate_iccid"] == 0     # all distinct


def test_audit_e911_three_dimensions():
    sites = [
        _site("S1", addr=True, status="validated", confirm=False),   # present + verified
        _site("S2", addr=True, status="pending", confirm=True),      # present, unverified, confirm-required
        _site("S3", addr=False, status="none", confirm=False),       # missing address
    ]
    ds = build_dataset([], [], sites, [_customer(1)], [], [])
    rep = run_identity_audit(ds, generated_at=AT)

    assert rep["e911"]["sites_total"] == 3
    assert rep["e911"]["address_present"] == 2
    assert rep["e911"]["verified"] == 1
    assert rep["e911"]["confirmation_required"] == 1
    assert rep["gaps"]["missing_e911_address"] == 1
    assert rep["gaps"]["unverified_e911"] == 1     # S2: present but not verified
    assert rep["gaps"]["e911_confirmation_required"] == 1


def test_audit_truth_components_seeds():
    devices = [
        _device("d-ok", site_id="S1", iccid="ICCID-1", carrier="t", identifier_type="cellular"),
        _device("d-orphan", iccid="ICCID-2", carrier="t", identifier_type="cellular"),
    ]
    sims = [_sim("ICCID-1", site_id="S1", customer_id=1), _sim("ICCID-2", customer_id=1)]
    sites = [_site("S1", status="validated")]
    ds = build_dataset(devices, sims, sites, [_customer(1)], [], [])
    rep = run_identity_audit(ds, generated_at=AT)

    assert rep["truth_components"]["identity"] == round(1 / 2, 4)
    assert rep["truth_components"]["hierarchy"] == round(1 / 2, 4)  # only d-ok has site+customer
    assert rep["truth_components"]["e911"] == 1.0                    # 1/1 site verified


def test_audit_empty_dataset_no_div_by_zero():
    rep = run_identity_audit(build_dataset([], [], [], [], [], []), generated_at=AT)
    assert rep["totals"]["devices_total"] == 0
    assert rep["totals"]["resolution_rate"] == 0.0
    assert rep["truth_components"] == {"identity": 0.0, "hierarchy": 0.0, "e911": 0.0}


def test_audit_sample_limit_bounds_output():
    devices = [_device(f"d-{i}", iccid="GHOST", carrier="t", identifier_type="cellular")
               for i in range(10)]
    ds = build_dataset(devices, [], [], [], [], [])
    rep = run_identity_audit(ds, generated_at=AT, sample_limit=3)
    assert rep["totals"]["orphan"] == 10
    assert len(rep["samples"]["orphan"]) == 3      # capped
    assert rep["sample_limit"] == 3


def test_audit_by_reason_and_match_basis():
    devices = [_device("d-ok", site_id="S1", iccid="ICCID-1", carrier="t", identifier_type="cellular")]
    sims = [_sim("ICCID-1", site_id="S1", customer_id=1)]
    ds = build_dataset(devices, sims, [_site("S1")], [_customer(1)], [], [])
    rep = run_identity_audit(ds, generated_at=AT)
    assert "ICCID" in rep["by_match_basis"]
    assert "IDENTITY.RESOLVED_ICCID" in rep["by_reason"]
