"""Generic customer dashboard company display (EPIC-GEN-001 slice).

Pins ``portfolio.company_name`` across single- and multi-customer tenants:
  1. resolved customer context -> its name (forward hook)
  2. exactly one Customer -> that name (the RH path; unchanged)
  3. zero or many Customers -> tenant org name (display_name or name)
  4. neither -> neutral "Your Portfolio"
Never an arbitrary LIMIT-1 customer, never the raw tenant_id slug.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.customer import portfolio as cportfolio


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    """Returns queued results per execute() call (customers probe, then tenant)."""
    def __init__(self, results):
        self._q = list(results)

    async def execute(self, stmt, *a, **k):
        return _Result(self._q.pop(0) if self._q else [])


def _tenant(display_name=None, name=None):
    return SimpleNamespace(display_name=display_name, name=name)


@pytest.mark.asyncio
async def test_single_customer_returns_customer_name():  # RH path — unchanged
    db = _Session([["Restoration Hardware"]])
    assert await cportfolio.company_name(db, "restoration-hardware") == "Restoration Hardware"


@pytest.mark.asyncio
async def test_many_customers_use_tenant_display_name():
    db = _Session([["Acme", "Beta"], [_tenant(display_name="North Mall Group", name="north-mall")]])
    assert await cportfolio.company_name(db, "north-mall") == "North Mall Group"


@pytest.mark.asyncio
async def test_many_customers_no_display_name_uses_tenant_name():
    db = _Session([["Acme", "Beta"], [_tenant(display_name=None, name="north-mall")]])
    assert await cportfolio.company_name(db, "north-mall") == "north-mall"


@pytest.mark.asyncio
async def test_zero_customers_uses_tenant_org_name():
    db = _Session([[], [_tenant(display_name="City Schools", name="city")]])
    assert await cportfolio.company_name(db, "city") == "City Schools"


@pytest.mark.asyncio
async def test_zero_customers_no_tenant_row_neutral_fallback():
    db = _Session([[], []])
    assert await cportfolio.company_name(db, "ghost-tenant") == "Your Portfolio"


@pytest.mark.asyncio
async def test_resolved_customer_context_wins():  # forward hook, no DB hit
    db = _Session([])
    rc = SimpleNamespace(name="Restoration Hardware")
    assert await cportfolio.company_name(db, "any", resolved_customer=rc) == "Restoration Hardware"


@pytest.mark.asyncio
async def test_never_returns_raw_tenant_slug():
    db = _Session([["Acme", "Beta"], [_tenant(display_name=None, name="Restoration Hardware")]])
    out = await cportfolio.company_name(db, "restoration-hardware")
    assert out == "Restoration Hardware" and out != "restoration-hardware"
