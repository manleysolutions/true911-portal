"""Customer portfolio orchestration (PR-C2).

Composition layer between the read-only Assurance engine and the customer
serializer.  It loads tenant sites, runs ``compute_site_assurance`` per site,
and maps each engine result to a customer ``StatusObject`` using ONLY PR-C1
serializer primitives (``status_object`` / ``evidence_object``).  It emits no
raw model fields — all customer-facing shaping happens in ``serialize.py``.

Reused by GET /api/customer/dashboard and /locations[/{ref}].

NOTE (perf): assurance is computed per site via ``load_site_assurance_signals``
(~6 bounded queries/site).  At RH scale (42 sites) a portfolio read is ~250
queries.  A batched loader / assurance snapshot is the planned optimization
(docs/ASSURANCE_ENGINE.md) — out of scope for PR-C2.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.site import Site
from app.services.assurance import compute_site_assurance, reason_codes as rc
from app.services.assurance.loader import load_site_assurance_signals
from app.services.assurance.signals import AssuranceLabel
from app.services.customer.refs import decode_ref
from app.services.customer.serialize import evidence_object, status_object

# Engine label -> customer six-label vocabulary (serialize.SIX_LABELS).
# Explicit so a vocabulary change in either layer fails a drift test rather
# than silently producing "Unknown".  (Engine INACTIVE value is
# "Inactive / Deactivated"; the customer label is "Inactive".)
_LABEL_MAP = {
    AssuranceLabel.PROTECTED: "Protected",
    AssuranceLabel.ATTENTION: "Attention Needed",
    AssuranceLabel.CRITICAL: "Critical",
    AssuranceLabel.PENDING_INSTALL: "Pending Install",
    AssuranceLabel.INACTIVE: "Inactive",
    AssuranceLabel.UNKNOWN: "Unknown",
}


def _evidence(result, signals, as_of: str):
    """Build an EvidenceObject for a Protected site, or None.  When None, the
    no-false-green rule in ``status_object`` recodes the label to Unknown."""
    signals_out = []
    online = sum(1 for d in result.devices if getattr(d, "last_heartbeat_at", None) is not None)
    if online:
        signals_out.append(f"{online} device{'s' if online != 1 else ''} reporting")
    lt = getattr(signals, "last_test", None)
    if lt is not None and (getattr(lt, "result", "") or "").lower() == "pass":
        signals_out.append(f"test passed {lt.at.date().isoformat()}")
    return evidence_object(as_of, signals_out) if signals_out else None


def _reason(result):
    for code in result.reason_codes:
        meta = rc.ALL.get(code)
        if meta is not None and getattr(meta, "customer_message", None):
            return meta.customer_message
    return None


def protection_from_assurance(signals, now) -> dict:
    """Map an Assurance engine result for one site to a customer StatusObject."""
    result = compute_site_assurance(signals, now=now)
    label = _LABEL_MAP.get(result.label, "Unknown")
    as_of = now.isoformat()
    if label == "Protected":
        # status_object downgrades to Unknown if evidence is empty (no false green)
        return status_object("Protected", as_of=as_of, evidence=_evidence(result, signals, as_of))
    return status_object(label, as_of=as_of, reason=_reason(result))


def _unknown(now) -> dict:
    return status_object("Unknown", as_of=now.isoformat(), reason="Status cannot be confirmed yet")


async def load_portfolio(db: AsyncSession, tenant_id: str, now) -> list[tuple[Site, dict]]:
    """Return (Site, protection StatusObject) for every site in the tenant."""
    sites = (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id)
    )).scalars().all()
    out: list[tuple[Site, dict]] = []
    for site in sites:
        signals = await load_site_assurance_signals(db, tenant_id, site.site_id)
        protection = protection_from_assurance(signals, now) if signals is not None else _unknown(now)
        out.append((site, protection))
    return out


async def resolve_location(db: AsyncSession, tenant_id: str, location_ref: str, now):
    """Resolve an opaque location_ref to (Site, protection) within the caller's
    tenant, or None (unknown / forged / cross-tenant ref)."""
    raw = decode_ref("loc", location_ref)
    if raw is None:
        return None
    try:
        site_pk = int(raw)
    except (TypeError, ValueError):
        return None
    site = (await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if site is None:
        return None
    signals = await load_site_assurance_signals(db, tenant_id, site.site_id)
    protection = protection_from_assurance(signals, now) if signals is not None else _unknown(now)
    return site, protection


async def company_name(db: AsyncSession, tenant_id: str) -> str:
    """Display company for the tenant (single-customer assumption; RH is one
    Customer).  Falls back to the tenant id."""
    name = (await db.execute(
        select(Customer.name).where(Customer.tenant_id == tenant_id).limit(1)
    )).scalar_one_or_none()
    return name or tenant_id
