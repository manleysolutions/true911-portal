"""Phase 3a — site → customer resolution for write paths.

Centralizes the rule used by every code path that writes a Site to
populate ``sites.customer_id`` alongside the existing
``sites.customer_name`` cache.  Pure read; this module never writes.

Two access modes:

    resolve_customer_for_site(db, tenant_id, customer_name)
        One-shot resolution.  Issues two SELECTs against ``customers``.
        Use from request handlers (POST /sites, PATCH /sites) where one
        DB hit per request is fine.

    CustomerResolver(customers)
        Bulk-mode.  Preloads a list of customers (the importers already
        load them for their own use) and answers in O(1).  Use from
        importers that process many rows.

Both return a CustomerResolution.  Resolution rules mirror the audit,
preflight and backfill scripts so a customer_name written by the API
resolves the same way as one written by the import pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer


_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_customer_name(s: Optional[str]) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not s:
        return ""
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


class ResolutionReason(str, Enum):
    RESOLVED = "resolved"
    EMPTY_NAME = "empty_name"
    NO_MATCH = "no_match"
    MULTI_MATCH = "multi_match"
    CROSS_TENANT_ONLY = "cross_tenant_only"


@dataclass
class CustomerResolution:
    reason: ResolutionReason
    customer_id: Optional[int] = None
    customer_name_canonical: Optional[str] = None
    candidate_ids: list[int] = field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return self.reason == ResolutionReason.RESOLVED


class CustomerResolver:
    """Bulk resolver.  Preload customers once; answer many resolutions."""

    def __init__(self, customers: Iterable[Customer]) -> None:
        self._by_tenant_name: dict[tuple[str, str], list[Customer]] = {}
        self._by_name_global: dict[str, list[Customer]] = {}
        for c in customers:
            n = normalize_customer_name(c.name)
            if not n:
                continue
            self._by_tenant_name.setdefault((c.tenant_id, n), []).append(c)
            self._by_name_global.setdefault(n, []).append(c)

    def resolve(
        self, tenant_id: str, customer_name: Optional[str]
    ) -> CustomerResolution:
        n = normalize_customer_name(customer_name)
        if not n:
            return CustomerResolution(reason=ResolutionReason.EMPTY_NAME)
        in_tenant = self._by_tenant_name.get((tenant_id, n), [])
        if len(in_tenant) == 1:
            c = in_tenant[0]
            return CustomerResolution(
                reason=ResolutionReason.RESOLVED,
                customer_id=c.id,
                customer_name_canonical=c.name,
                candidate_ids=[c.id],
            )
        if len(in_tenant) >= 2:
            return CustomerResolution(
                reason=ResolutionReason.MULTI_MATCH,
                candidate_ids=[c.id for c in in_tenant],
            )
        cross = [
            c for c in self._by_name_global.get(n, []) if c.tenant_id != tenant_id
        ]
        if cross:
            return CustomerResolution(
                reason=ResolutionReason.CROSS_TENANT_ONLY,
                candidate_ids=[c.id for c in cross],
            )
        return CustomerResolution(reason=ResolutionReason.NO_MATCH)


async def resolve_customer_for_site(
    db: AsyncSession,
    tenant_id: str,
    customer_name: Optional[str],
) -> CustomerResolution:
    """One-shot resolution against the DB.  Pure read."""
    n = normalize_customer_name(customer_name)
    if not n:
        return CustomerResolution(reason=ResolutionReason.EMPTY_NAME)
    r = await db.execute(select(Customer).where(Customer.tenant_id == tenant_id))
    in_tenant = [c for c in r.scalars().all() if normalize_customer_name(c.name) == n]
    if len(in_tenant) == 1:
        c = in_tenant[0]
        return CustomerResolution(
            reason=ResolutionReason.RESOLVED,
            customer_id=c.id,
            customer_name_canonical=c.name,
            candidate_ids=[c.id],
        )
    if len(in_tenant) >= 2:
        return CustomerResolution(
            reason=ResolutionReason.MULTI_MATCH,
            candidate_ids=[c.id for c in in_tenant],
        )
    r = await db.execute(select(Customer))
    cross = [
        c
        for c in r.scalars().all()
        if c.tenant_id != tenant_id and normalize_customer_name(c.name) == n
    ]
    if cross:
        return CustomerResolution(
            reason=ResolutionReason.CROSS_TENANT_ONLY,
            candidate_ids=[c.id for c in cross],
        )
    return CustomerResolution(reason=ResolutionReason.NO_MATCH)


class CustomerTenantMismatchError(ValueError):
    """Raised when a supplied customer_id does not live in the expected tenant."""


class CustomerNotFoundError(ValueError):
    """Raised when a supplied customer_id does not exist."""


async def validate_customer_id_for_tenant(
    db: AsyncSession,
    tenant_id: str,
    customer_id: int,
) -> Customer:
    """Verify a customer_id exists and belongs to ``tenant_id``.

    Returns the matched Customer.  Raises CustomerNotFoundError or
    CustomerTenantMismatchError so the API layer can map them to a
    precise HTTP 400 response.
    """
    c = await db.get(Customer, customer_id)
    if c is None:
        raise CustomerNotFoundError(f"customer_id={customer_id} does not exist")
    if c.tenant_id != tenant_id:
        raise CustomerTenantMismatchError(
            f"customer_id={customer_id} belongs to tenant '{c.tenant_id}', "
            f"not '{tenant_id}'"
        )
    return c
