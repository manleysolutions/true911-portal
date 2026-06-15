"""Table-driven tests for the pure Identity Engine resolver (Phase 0 / PR-1a).

Pure unit tests — no DB, no fixtures, no I/O.  Each case builds facts directly and
asserts the derived status, the proof chain, reason codes, and purity.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.services.identity import (
    CustomerFacts,
    DeviceFacts,
    ExternalMapFacts,
    LinkKind,
    LinkStatus,
    ResolutionStatus,
    ResolverInput,
    ServiceUnitFacts,
    SimFacts,
    SiteFacts,
    resolve_device,
)
from app.services.identity import reason_codes as rc


# ─────────────────────────── builders ───────────────────────────

def _full_input(device: DeviceFacts, *, sim=None, site=None, customer=None,
                service_unit=None, external=None):
    """Build a ResolverInput with the given related facts wired into lookups."""
    sims_by_iccid = {sim.iccid: sim} if sim else {}
    sims_by_imei = {sim.imei: (sim,)} if (sim and sim.imei) else {}
    sims_by_msisdn = {sim.msisdn: (sim,)} if (sim and sim.msisdn) else {}
    sites_by_id = {site.site_id: site} if site else {}
    customers_by_id = {customer.customer_id: customer} if customer else {}
    su = {}
    if service_unit:
        units = service_unit if isinstance(service_unit, tuple) else (service_unit,)
        su = {device.device_id: units}
    ext = {device.device_id: (external,)} if external else {}
    return ResolverInput(
        device=device,
        sims_by_iccid=sims_by_iccid,
        sims_by_imei=sims_by_imei,
        sims_by_msisdn=sims_by_msisdn,
        sites_by_id=sites_by_id,
        customers_by_id=customers_by_id,
        service_units_by_device=su,
        external_map_by_device=ext,
    )


def _healthy_chain(**device_overrides):
    """A device that resolves cleanly by ICCID with full hierarchy + E911 + unit."""
    sim = SimFacts(iccid="8901000000000000001", msisdn="+18563081391",
                   imei="3500000000001", site_id="SITE-1", customer_id=42, carrier="tmobile")
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    unit = ServiceUnitFacts(unit_id="U-1", site_id="SITE-1", device_id="dev-1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         iccid="8901000000000000001", carrier="tmobile",
                         identifier_type="cellular", **device_overrides)
    return _full_input(device, sim=sim, site=site, customer=customer, service_unit=unit)


def _codes(res):
    return set(res.reason_codes)


def _link_to(res, kind):
    return [l for l in res.proof_chain if l.to_kind == kind]


# ─────────────────────────── RESOLVED paths ───────────────────────────

def test_resolved_by_iccid():
    res = resolve_device(_healthy_chain())
    assert res.status == ResolutionStatus.RESOLVED
    assert res.sim_iccid == "8901000000000000001"
    assert res.site_id == "SITE-1"
    assert res.customer_id == 42
    assert res.tenant_id == "t1"
    assert res.e911_present is True
    assert res.service_unit_id == "U-1"
    assert rc.RESOLVED_ICCID.code in _codes(res)
    assert "ICCID" in res.match_basis
    assert res.confidence == 1.0


def test_resolved_by_imei_when_no_iccid_match():
    sim = SimFacts(iccid="ICCID-X", imei="IMEI-1", site_id="SITE-1", customer_id=42)
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         imei="IMEI-1", carrier="tmobile", identifier_type="cellular")
    res = resolve_device(_full_input(device, sim=sim, site=site, customer=customer))
    assert res.status == ResolutionStatus.RESOLVED
    assert rc.RESOLVED_IMEI.code in _codes(res)
    assert res.confidence == 0.9


def test_resolved_by_unique_msisdn():
    sim = SimFacts(iccid="ICCID-X", msisdn="+1700", site_id="SITE-1", customer_id=42, carrier="tmobile")
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         msisdn="+1700", carrier="tmobile", identifier_type="cellular")
    res = resolve_device(_full_input(device, sim=sim, site=site, customer=customer))
    assert res.status == ResolutionStatus.RESOLVED
    assert rc.RESOLVED_MSISDN.code in _codes(res)
    assert res.confidence == 0.8


def test_resolved_external_map_for_site():
    # No site_id on device, but a confirmed external map supplies the site.
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1",
                         identifier_type="ata")  # non-cellular: no SIM required
    ext = ExternalMapFacts(device_id="dev-1", site_id="SITE-1", map_status="confirmed")
    res = resolve_device(_full_input(device, site=site, customer=customer, external=ext))
    assert res.status == ResolutionStatus.RESOLVED
    assert rc.RESOLVED_EXTERNAL_MAP.code in _codes(res)
    assert res.site_id == "SITE-1"


def test_non_cellular_resolves_without_sim():
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         identifier_type="ata")
    res = resolve_device(_full_input(device, site=site, customer=customer))
    assert res.status == ResolutionStatus.RESOLVED
    assert res.sim_iccid is None
    # No SIM link emitted for a non-cellular device.
    assert _link_to(res, LinkKind.SIM) == []


# ─────────────────────────── AMBIGUOUS paths ───────────────────────────

def test_ambiguous_msisdn_two_sims():
    sim_a = SimFacts(iccid="ICCID-A", msisdn="+1700")
    sim_b = SimFacts(iccid="ICCID-B", msisdn="+1700")
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         msisdn="+1700", carrier="tmobile", identifier_type="cellular")
    inp = ResolverInput(
        device=device,
        sims_by_msisdn={"+1700": (sim_a, sim_b)},
        sites_by_id={"SITE-1": site},
        customers_by_id={42: customer},
    )
    res = resolve_device(inp)
    assert res.status == ResolutionStatus.AMBIGUOUS
    assert rc.AMBIGUOUS_MSISDN.code in _codes(res)
    assert res.confidence == 0.0


def test_ambiguous_iccid_site_mismatch():
    sim = SimFacts(iccid="ICCID-1", site_id="SITE-OTHER", customer_id=42)
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         iccid="ICCID-1", carrier="tmobile", identifier_type="cellular")
    res = resolve_device(_full_input(device, sim=sim, site=site, customer=customer))
    assert res.status == ResolutionStatus.AMBIGUOUS
    assert rc.AMBIGUOUS_ICCID_SITE_MISMATCH.code in _codes(res)


def test_ambiguity_beats_orphan():
    # Ambiguous MSISDN AND no site → AMBIGUOUS wins (documented precedence).
    sim_a = SimFacts(iccid="ICCID-A", msisdn="+1700")
    sim_b = SimFacts(iccid="ICCID-B", msisdn="+1700")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1",
                         msisdn="+1700", carrier="tmobile", identifier_type="cellular")
    inp = ResolverInput(device=device, sims_by_msisdn={"+1700": (sim_a, sim_b)})
    res = resolve_device(inp)
    assert res.status == ResolutionStatus.AMBIGUOUS


# ─────────────────────────── ORPHAN paths ───────────────────────────

def test_orphan_no_site():
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", iccid="ICCID-1",
                         carrier="tmobile", identifier_type="cellular")
    sim = SimFacts(iccid="ICCID-1", customer_id=42)
    inp = ResolverInput(device=device, sims_by_iccid={"ICCID-1": sim})
    res = resolve_device(inp)
    assert res.status == ResolutionStatus.ORPHAN
    assert rc.ORPHAN_NO_SITE.code in _codes(res)


def test_orphan_site_without_customer():
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=None, e911_present=True)
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         identifier_type="ata")
    res = resolve_device(_full_input(device, site=site))
    assert res.status == ResolutionStatus.ORPHAN
    assert rc.ORPHAN_NO_CUSTOMER.code in _codes(res)


def test_orphan_cellular_no_sim():
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         carrier="tmobile", identifier_type="cellular")  # no iccid/imei/msisdn match
    res = resolve_device(_full_input(device, site=site, customer=customer))
    assert res.status == ResolutionStatus.ORPHAN
    assert rc.ORPHAN_CELLULAR_NO_SIM.code in _codes(res)


# ─────────────────────────── gaps (do not orphan) ───────────────────────────

def test_resolved_with_missing_e911_gap():
    base = _healthy_chain()
    # Rebuild with e911 absent.
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=False)
    inp = dataclasses.replace(base, sites_by_id={"SITE-1": site})
    res = resolve_device(inp)
    assert res.status == ResolutionStatus.RESOLVED
    assert res.e911_present is False
    assert rc.MISSING_E911.code in _codes(res)


def test_resolved_with_missing_service_unit_gap():
    base = _healthy_chain()
    inp = dataclasses.replace(base, service_units_by_device={})
    res = resolve_device(inp)
    assert res.status == ResolutionStatus.RESOLVED
    assert res.service_unit_id is None
    assert rc.MISSING_SERVICE_UNIT.code in _codes(res)


def test_multiple_service_units_no_guess():
    base = _healthy_chain()
    u1 = ServiceUnitFacts(unit_id="U-1", site_id="SITE-1", device_id="dev-1")
    u2 = ServiceUnitFacts(unit_id="U-2", site_id="SITE-1", device_id="dev-1")
    inp = dataclasses.replace(base, service_units_by_device={"dev-1": (u1, u2)})
    res = resolve_device(inp)
    assert res.status == ResolutionStatus.RESOLVED
    assert res.service_unit_id is None  # never guesses which unit
    assert rc.MISSING_SERVICE_UNIT.code in _codes(res)


def test_unmatched_iccid_then_resolves_by_msisdn():
    # Declares an ICCID with no SIM record, but a unique MSISDN match resolves it.
    sim = SimFacts(iccid="ICCID-REAL", msisdn="+1700", site_id="SITE-1", customer_id=42, carrier="t")
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         iccid="ICCID-GHOST", msisdn="+1700", carrier="t",
                         identifier_type="cellular")
    inp = ResolverInput(
        device=device,
        sims_by_iccid={"ICCID-REAL": sim},
        sims_by_msisdn={"+1700": (sim,)},
        sites_by_id={"SITE-1": site},
        customers_by_id={42: customer},
    )
    res = resolve_device(inp)
    assert res.status == ResolutionStatus.RESOLVED
    assert rc.UNMATCHED_ICCID.code in _codes(res)
    assert rc.RESOLVED_MSISDN.code in _codes(res)


def test_unknown_carrier_info():
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         identifier_type="ata")  # no carrier
    res = resolve_device(_full_input(device, site=site, customer=customer))
    assert rc.UNKNOWN_CARRIER.code in _codes(res)


# ─────────────────────────── heuristics / org / proof chain ───────────────────────────

def test_heuristic_suggests_never_resolves():
    # Device has no site_id; matched SIM has a site → SUGGESTED, not resolved.
    sim = SimFacts(iccid="ICCID-1", site_id="SITE-1", customer_id=42)
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", iccid="ICCID-1",
                         carrier="t", identifier_type="cellular")
    res = resolve_device(_full_input(device, sim=sim, site=site, customer=customer))
    assert res.status == ResolutionStatus.ORPHAN          # site link only SUGGESTED
    assert res.site_id is None                            # suggestion not auto-applied
    assert rc.HEURISTIC_SUGGESTED.code in _codes(res)
    assert any("site=SITE-1" in s for s in res.suggestions)
    suggested = [l for l in res.proof_chain
                 if l.to_kind == LinkKind.SITE and l.status == LinkStatus.SUGGESTED]
    assert len(suggested) == 1


def test_organization_passthrough():
    base = _healthy_chain(org_id="ORG-9")
    res = resolve_device(base)
    assert res.organization_id == "ORG-9"
    assert any(l.to_kind == LinkKind.ORGANIZATION and l.to_id == "ORG-9"
               for l in res.proof_chain)


def test_organization_absent_is_none():
    res = resolve_device(_healthy_chain())
    assert res.organization_id is None


def test_proof_chain_anchored_and_ordered():
    res = resolve_device(_healthy_chain())
    assert res.proof_chain[0].from_kind == LinkKind.DEVICE
    assert res.proof_chain[0].to_kind == LinkKind.TENANT
    kinds = [l.to_kind for l in res.proof_chain]
    # Core hierarchy links are all present for a healthy device.
    for k in (LinkKind.TENANT, LinkKind.SIM, LinkKind.SITE, LinkKind.CUSTOMER,
              LinkKind.E911, LinkKind.SERVICE_UNIT):
        assert k in kinds


# ─────────────────────────── invariants ───────────────────────────

def test_every_emitted_code_is_in_catalog():
    # Exercise several shapes, then assert no orphan codes.
    inputs = [
        _healthy_chain(),
        _healthy_chain(org_id="ORG-1"),
    ]
    for inp in inputs:
        res = resolve_device(inp)
        for code in res.reason_codes:
            assert code in rc.ALL, f"undocumented code: {code}"
        for link in res.proof_chain:
            if link.reason_code is not None:
                assert link.reason_code in rc.ALL


def test_purity_inputs_not_mutated():
    base = _healthy_chain()
    snapshot = repr(base)
    resolve_device(base)
    assert repr(base) == snapshot  # inputs unchanged


def test_output_is_frozen():
    res = resolve_device(_healthy_chain())
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.status = ResolutionStatus.ORPHAN  # type: ignore[misc]


def test_confidence_monotonic_by_basis():
    # ICCID (1.0) >= MSISDN (0.8) for otherwise-identical resolved chains.
    iccid_res = resolve_device(_healthy_chain())
    sim = SimFacts(iccid="ICCID-X", msisdn="+1700", site_id="SITE-1", customer_id=42, carrier="t")
    site = SiteFacts(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_present=True)
    customer = CustomerFacts(customer_id=42, tenant_id="t1")
    device = DeviceFacts(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                         msisdn="+1700", carrier="t", identifier_type="cellular")
    msisdn_res = resolve_device(_full_input(device, sim=sim, site=site, customer=customer))
    assert iccid_res.confidence >= msisdn_res.confidence
