"""Phase 3a — dual-write tests for sites.customer_id.

Covers:
  - the bulk CustomerResolver helper (pure function, no DB)
  - validate_customer_id_for_tenant (mocked DB)
  - the sites router POST + PATCH dual-write logic (mocked DB)
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.site_customer_resolution import (
    CustomerNotFoundError,
    CustomerResolver,
    CustomerTenantMismatchError,
    ResolutionReason,
    normalize_customer_name,
    validate_customer_id_for_tenant,
)


def _cust(id_: int, tenant_id: str, name: str, status: str = "active"):
    return SimpleNamespace(id=id_, tenant_id=tenant_id, name=name, status=status)


# ── normalize_customer_name ────────────────────────────────────────────────

def test_normalize_lowercases_and_trims():
    assert normalize_customer_name("  Acme  Corp ") == "acme corp"


def test_normalize_strips_punctuation():
    # Punctuation is replaced with whitespace, then whitespace collapsed.
    # That's the same rule audit_data_alignment / preflight / backfill use,
    # so the same input always lands in the same bucket across phases.
    assert normalize_customer_name("Acme, Inc.") == "acme inc"
    assert normalize_customer_name("Bob's Plumbing & Heating") == "bob s plumbing heating"


def test_normalize_collapses_whitespace():
    assert normalize_customer_name("Acme\t\n  Corp") == "acme corp"


def test_normalize_handles_none_and_empty():
    assert normalize_customer_name(None) == ""
    assert normalize_customer_name("") == ""
    assert normalize_customer_name("   ") == ""


# ── CustomerResolver: bulk-mode resolution ─────────────────────────────────

def test_resolver_returns_resolved_for_single_in_tenant_match():
    customers = [
        _cust(1, "t1", "Acme Hospital"),
        _cust(2, "t2", "Acme Hospital"),  # different tenant — must not match
    ]
    r = CustomerResolver(customers).resolve("t1", "Acme Hospital")
    assert r.reason == ResolutionReason.RESOLVED
    assert r.is_resolved is True
    assert r.customer_id == 1
    assert r.customer_name_canonical == "Acme Hospital"
    assert r.candidate_ids == [1]


def test_resolver_normalization_makes_match_case_and_punct_insensitive():
    customers = [_cust(7, "t1", "Acme Hospital")]
    resolver = CustomerResolver(customers)
    for variant in ("acme hospital", "ACME HOSPITAL", "  Acme,  Hospital. "):
        assert resolver.resolve("t1", variant).customer_id == 7


def test_resolver_returns_multi_match_when_two_in_tenant_share_name():
    customers = [
        _cust(1, "t1", "Acme"),
        _cust(2, "t1", "ACME "),  # normalizes to same
    ]
    r = CustomerResolver(customers).resolve("t1", "acme")
    assert r.reason == ResolutionReason.MULTI_MATCH
    assert r.is_resolved is False
    assert r.customer_id is None
    assert sorted(r.candidate_ids) == [1, 2]


def test_resolver_returns_cross_tenant_only():
    customers = [_cust(9, "other", "Acme")]
    r = CustomerResolver(customers).resolve("t1", "Acme")
    assert r.reason == ResolutionReason.CROSS_TENANT_ONLY
    assert r.customer_id is None
    assert r.candidate_ids == [9]


def test_resolver_returns_no_match():
    r = CustomerResolver([_cust(1, "t1", "Acme")]).resolve("t1", "Beta")
    assert r.reason == ResolutionReason.NO_MATCH
    assert r.customer_id is None


def test_resolver_returns_empty_name_for_blank_input():
    r = CustomerResolver([_cust(1, "t1", "Acme")]).resolve("t1", "")
    assert r.reason == ResolutionReason.EMPTY_NAME
    r = CustomerResolver([_cust(1, "t1", "Acme")]).resolve("t1", None)
    assert r.reason == ResolutionReason.EMPTY_NAME


def test_resolver_skips_customers_with_blank_names_during_indexing():
    customers = [_cust(1, "t1", ""), _cust(2, "t1", "Real Co")]
    resolver = CustomerResolver(customers)
    assert resolver.resolve("t1", "Real Co").customer_id == 2
    assert resolver.resolve("t1", "").reason == ResolutionReason.EMPTY_NAME


# ── validate_customer_id_for_tenant ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_customer_id_returns_customer_when_tenants_match():
    db = MagicMock()
    customer = _cust(5, "t1", "Acme")
    db.get = AsyncMock(return_value=customer)
    result = await validate_customer_id_for_tenant(db, "t1", 5)
    assert result is customer


@pytest.mark.asyncio
async def test_validate_customer_id_raises_not_found_when_missing():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(CustomerNotFoundError):
        await validate_customer_id_for_tenant(db, "t1", 99)


@pytest.mark.asyncio
async def test_validate_customer_id_raises_mismatch_for_other_tenant():
    db = MagicMock()
    customer = _cust(5, "other_tenant", "Acme")
    db.get = AsyncMock(return_value=customer)
    with pytest.raises(CustomerTenantMismatchError):
        await validate_customer_id_for_tenant(db, "t1", 5)


# ── sites router POST/PATCH dual-write ─────────────────────────────────────

@pytest.mark.asyncio
async def test_post_with_only_customer_name_resolves_to_id():
    """When only customer_name is supplied, the router resolves it."""
    from app.routers import sites as sites_router

    customer = _cust(42, "t1", "Acme Hospital")
    db = MagicMock()
    db.get = AsyncMock(return_value=customer)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    # resolve_customer_for_site issues two SELECTs (in-tenant, then global).
    in_tenant_result = MagicMock()
    in_tenant_result.scalars.return_value.all.return_value = [customer]
    db.execute = AsyncMock(return_value=in_tenant_result)

    user = SimpleNamespace(tenant_id="t1", role="Admin", email="a@x")
    body = sites_router.SiteCreate(
        site_id="SITE-1",
        site_name="Main",
        customer_name="Acme Hospital",
        status="Not Connected",
    )

    # Patch the response builder so we don't hit the device join path.
    async def _fake_out(s, _db):
        return SimpleNamespace(id=getattr(s, "id", None))

    captured = {}

    def _capture_add(obj):
        captured["site"] = obj

    db.add.side_effect = _capture_add

    # Stub the geocoder import to avoid network.
    sites_router.geocode_address = AsyncMock(return_value=None)
    sites_router._site_out = _fake_out

    await sites_router.create_site(body=body, db=db, current_user=user)
    site = captured["site"]
    assert site.customer_id == 42
    # customer_name preserved (not refreshed) when only name was supplied.
    assert site.customer_name == "Acme Hospital"


@pytest.mark.asyncio
async def test_post_with_customer_id_validates_tenant_and_refreshes_name():
    from app.routers import sites as sites_router

    customer = _cust(7, "t1", "Beta Industries")
    db = MagicMock()
    db.get = AsyncMock(return_value=customer)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()

    user = SimpleNamespace(tenant_id="t1", role="Admin", email="a@x")
    body = sites_router.SiteCreate(
        site_id="SITE-2",
        site_name="HQ",
        customer_name="Old Cached Name",  # client passed stale name
        customer_id=7,
        status="Not Connected",
    )

    captured = {}

    def _capture_add(obj):
        captured["site"] = obj

    db.add.side_effect = _capture_add

    sites_router.geocode_address = AsyncMock(return_value=None)

    async def _fake_out(s, _db):
        return SimpleNamespace(id=getattr(s, "id", None))

    sites_router._site_out = _fake_out

    # No mismatch path — only customer_id supplied alongside any
    # customer_name, but resolution shortcut: when both supplied we call
    # resolve_customer_for_site.  Make it return RESOLVED to id=7 so the
    # match check passes.
    in_tenant_result = MagicMock()
    in_tenant_result.scalars.return_value.all.return_value = [
        _cust(7, "t1", "Old Cached Name")
    ]
    db.execute.return_value = in_tenant_result

    await sites_router.create_site(body=body, db=db, current_user=user)
    site = captured["site"]
    assert site.customer_id == 7
    # Cached name MUST be refreshed to the canonical value.
    assert site.customer_name == "Beta Industries"


@pytest.mark.asyncio
async def test_post_rejects_mismatched_customer_id_and_name():
    from fastapi import HTTPException
    from app.routers import sites as sites_router

    customer = _cust(7, "t1", "Beta Industries")
    db = MagicMock()
    db.get = AsyncMock(return_value=customer)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    # name resolves to a *different* customer
    in_tenant_result = MagicMock()
    in_tenant_result.scalars.return_value.all.return_value = [
        _cust(11, "t1", "Acme Hospital"),
    ]
    db.execute = AsyncMock(return_value=in_tenant_result)

    user = SimpleNamespace(tenant_id="t1", role="Admin", email="a@x")
    body = sites_router.SiteCreate(
        site_id="SITE-3",
        site_name="HQ",
        customer_name="Acme Hospital",  # resolves to id=11
        customer_id=7,                  # but supplied id=7
        status="Not Connected",
    )
    sites_router.geocode_address = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await sites_router.create_site(body=body, db=db, current_user=user)
    assert exc.value.status_code == 400
    assert "does not match" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_post_rejects_customer_id_from_another_tenant():
    from fastapi import HTTPException
    from app.routers import sites as sites_router

    db = MagicMock()
    db.get = AsyncMock(return_value=_cust(7, "OTHER_TENANT", "Beta"))
    sites_router.geocode_address = AsyncMock(return_value=None)

    user = SimpleNamespace(tenant_id="t1", role="Admin", email="a@x")
    body = sites_router.SiteCreate(
        site_id="SITE-4",
        site_name="HQ",
        customer_name="Beta",
        customer_id=7,
        status="Not Connected",
    )

    with pytest.raises(HTTPException) as exc:
        await sites_router.create_site(body=body, db=db, current_user=user)
    assert exc.value.status_code == 400
    assert "tenant" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_post_with_unresolved_name_leaves_customer_id_null():
    """Today's behavior: unresolved names still create the site."""
    from app.routers import sites as sites_router

    db = MagicMock()
    db.get = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    # In-tenant select returns nothing
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty)
    sites_router.geocode_address = AsyncMock(return_value=None)

    captured = {}
    db.add.side_effect = lambda o: captured.setdefault("site", o)

    async def _fake_out(s, _db):
        return SimpleNamespace(id=getattr(s, "id", None))

    sites_router._site_out = _fake_out

    user = SimpleNamespace(tenant_id="t1", role="Admin", email="a@x")
    body = sites_router.SiteCreate(
        site_id="SITE-5",
        site_name="Lonely",
        customer_name="No Such Customer",
        status="Not Connected",
    )

    await sites_router.create_site(body=body, db=db, current_user=user)
    site = captured["site"]
    assert site.customer_id is None
    # customer_name still cached as supplied — preserves today's behavior.
    assert site.customer_name == "No Such Customer"


# ── Bulk resolver matches preflight/backfill rules ─────────────────────────

def test_resolver_matches_phase0_preflight_buckets():
    """Single, multi, cross, no, empty — same five buckets the audit uses."""
    customers = [
        _cust(1, "t1", "Acme"),
        _cust(2, "t1", "Beta"),
        _cust(3, "t1", "Beta"),  # multi-match
        _cust(4, "t2", "Cross"),
    ]
    resolver = CustomerResolver(customers)
    assert resolver.resolve("t1", "Acme").reason == ResolutionReason.RESOLVED
    assert resolver.resolve("t1", "Beta").reason == ResolutionReason.MULTI_MATCH
    assert resolver.resolve("t1", "Cross").reason == ResolutionReason.CROSS_TENANT_ONLY
    assert resolver.resolve("t1", "Delta").reason == ResolutionReason.NO_MATCH
    assert resolver.resolve("t1", "").reason == ResolutionReason.EMPTY_NAME
