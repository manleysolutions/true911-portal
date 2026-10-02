"""CHARACTERIZATION (not endorsement) of registration conversion site materialisation.

Today ``_materialize_sites`` writes ``Site(status="Connected")`` and copies the
prospect-entered address into the ``e911_*`` columns, leaving ``e911_status``
unset.  Under the truth rules a converted prospect address is NOT a deployed,
connected or E911-verified location (D-030, D-032).  These tests pin current
behaviour so the proposed remediation (docs/ACQUISITION.md §"Conversion truth")
is a deliberate, reviewed change — they are expected to be updated by that PR.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.models.registration_location import RegistrationLocation
from app.services import registration_conversion as conv


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, locations):
        self.locations, self.added = locations, []

    async def execute(self, _stmt):
        return _Result(self.locations)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for i, obj in enumerate(self.added, start=1):
            obj.id = obj.id or i


def _materialize(monkeypatch):
    async def _next(db, base):
        return base or "site"
    monkeypatch.setattr(conv, "_next_available_site_id", _next)
    loc = RegistrationLocation(id=7, registration_id=1, location_label="Store 12",
                               street="1 Main St", city="Tampa", state="FL", zip="33602",
                               access_notes=None, materialized_site_id=None)
    db = _FakeDB([loc])
    out = asyncio.run(conv._materialize_sites(
        db, SimpleNamespace(id=1), SimpleNamespace(tenant_id="acme"),
        SimpleNamespace(id=3, name="Acme")))
    return db.added[0], out, loc


def test_conversion_currently_marks_sites_connected(monkeypatch):
    site, out, loc = _materialize(monkeypatch)
    # CURRENT behaviour — a conversion is not evidence of connectivity.  Remediation proposed.
    assert site.status == "Connected"
    assert site.onboarding_status == "active"
    assert out[0].was_created is True and loc.materialized_site_id == site.id


def test_conversion_copies_prospect_address_into_e911_columns_without_verifying(monkeypatch):
    site, _, _ = _materialize(monkeypatch)
    assert (site.e911_street, site.e911_city, site.e911_state, site.e911_zip) == \
        ("1 Main St", "Tampa", "FL", "33602")
    # Address present ≠ E911 verified: conversion never asserts a verification status.
    assert site.e911_status is None
