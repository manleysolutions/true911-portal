"""Tests for the read-only Identity Audit loader (Phase 0 / PR-1b1).

``build_dataset`` is pure and tested with simple stand-in rows (attribute access).
``load_identity_dataset`` is exercised with an AsyncMock AsyncSession following the
house pattern (see test_health_signals_loader.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.identity.loader import (
    build_dataset,
    load_identity_dataset,
)


def _row(**kw):
    return SimpleNamespace(**kw)


def test_build_dataset_maps_facts_and_lookups():
    devices = [_row(device_id="dev-1", tenant_id="t1", site_id="SITE-1",
                    iccid="ICCID-1", imei="IMEI-1", msisdn="+1700",
                    carrier="t", identifier_type="cellular", status="active",
                    serial_number=None, sim_id=None)]
    sims = [_row(iccid="ICCID-1", msisdn="+1700", imei="IMEI-1",
                 device_id="dev-1", site_id="SITE-1", customer_id=42, carrier="t")]
    sites = [_row(site_id="SITE-1", tenant_id="t1", customer_id=42,
                  e911_street="1 Main", e911_city="Town", e911_state="FL",
                  e911_zip="33000", e911_status="validated", e911_confirmation_required=False)]
    customers = [_row(id=42, tenant_id="t1")]
    units = [_row(unit_id="U-1", site_id="SITE-1", device_id="dev-1")]
    ext = [_row(device_id="dev-1", customer_id=42, site_id="SITE-1", map_status="confirmed")]

    ds = build_dataset(devices, sims, sites, customers, units, ext)

    assert ds.devices[0].device_id == "dev-1"
    assert ds.sims_by_iccid["ICCID-1"].customer_id == 42
    assert ds.sims_by_imei["IMEI-1"] == (ds.sims[0],)
    assert ds.sims_by_msisdn["+1700"] == (ds.sims[0],)
    assert ds.sites_by_id["SITE-1"].e911_present is True       # address present
    assert ds.customers_by_id[42].tenant_id == "t1"
    assert ds.service_units_by_device["dev-1"][0].unit_id == "U-1"
    assert ds.external_map_by_device["dev-1"][0].map_status == "confirmed"


def test_build_dataset_msisdn_ambiguity_tuple():
    sims = [
        _row(iccid="A", msisdn="+1700", imei=None, device_id=None, site_id=None, customer_id=None, carrier="t"),
        _row(iccid="B", msisdn="+1700", imei=None, device_id=None, site_id=None, customer_id=None, carrier="t"),
    ]
    ds = build_dataset([], sims, [], [], [], [])
    assert len(ds.sims_by_msisdn["+1700"]) == 2  # ambiguity preserved for the resolver


def test_e911_three_dimensions_not_collapsed():
    # Address present but NOT verified, and confirmation required.
    sites = [_row(site_id="S1", tenant_id="t1", customer_id=1,
                  e911_street="1 Main", e911_city="T", e911_state="FL", e911_zip="33000",
                  e911_status="pending", e911_confirmation_required=True)]
    ds = build_dataset([], [], sites, [], [], [])
    e = ds.site_e911[0]
    assert e.e911_address_present is True
    assert e.e911_verified is False
    assert e.e911_confirmation_required is True
    # Resolver-facing SiteFacts uses address-present semantics.
    assert ds.sites_by_id["S1"].e911_present is True


def test_e911_missing_address():
    sites = [_row(site_id="S1", tenant_id="t1", customer_id=1,
                  e911_street=None, e911_city="T", e911_state="FL", e911_zip="33000",
                  e911_status="validated", e911_confirmation_required=False)]
    ds = build_dataset([], [], sites, [], [], [])
    e = ds.site_e911[0]
    assert e.e911_address_present is False
    assert e.e911_verified is True
    assert ds.sites_by_id["S1"].e911_present is False


def test_e911_verified_status_case_insensitive():
    for status, expected in (("VERIFIED", True), ("Validated", True), ("none", False), (None, False)):
        sites = [_row(site_id="S1", tenant_id="t1", customer_id=1,
                      e911_street="1", e911_city="T", e911_state="FL", e911_zip="3",
                      e911_status=status, e911_confirmation_required=False)]
        ds = build_dataset([], [], sites, [], [], [])
        assert ds.site_e911[0].e911_verified is expected


def _scalar_result(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_load_identity_dataset_executes_six_bounded_queries():
    device = _row(device_id="dev-1", tenant_id="t1", site_id="SITE-1", iccid="ICCID-1",
                  imei=None, msisdn=None, carrier="t", identifier_type="cellular",
                  status="active", serial_number=None, sim_id=None)
    sim = _row(iccid="ICCID-1", msisdn=None, imei=None, device_id="dev-1",
               site_id="SITE-1", customer_id=42, carrier="t")
    site = _row(site_id="SITE-1", tenant_id="t1", customer_id=42, e911_street="1",
                e911_city="T", e911_state="FL", e911_zip="3", e911_status="validated",
                e911_confirmation_required=False)
    customer = _row(id=42, tenant_id="t1")

    db = MagicMock()
    # Order matches loader: devices, sims, sites, customers, service_units, external_maps.
    db.execute = AsyncMock(side_effect=[
        _scalar_result([device]),
        _scalar_result([sim]),
        _scalar_result([site]),
        _scalar_result([customer]),
        _scalar_result([]),
        _scalar_result([]),
    ])

    ds = await load_identity_dataset(db, tenant_id="t1")
    assert db.execute.call_count == 6
    assert ds.devices[0].device_id == "dev-1"
    assert ds.sims_by_iccid["ICCID-1"].customer_id == 42
    assert ds.customers_by_id[42].tenant_id == "t1"
