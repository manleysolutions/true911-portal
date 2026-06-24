"""Asset lookup by real-world identifier.

A caller usually has NO account number, so we match on whatever field
identifier they can read off the equipment: an elevator phone number, an
MSISDN, a Napco radio number, an ICCID, a Starlink ID, a site or building
name, a device label, etc.

Two layers of matching, in priority order:

  1. ``asset_identities`` — the purpose-built, normalized index.  This is
     the intended source once identities are imported/registered.
  2. Native-field fallback — targeted matches against existing
     Device / Site / ServiceUnit / Line columns, so lookup is useful
     immediately without requiring the identity index to be populated.

Every match resolves the authorized contact on file (from the owning
Site's POC) so the verification step has a destination.  Matches returned
here are RAW (include the full contact number + tenant); the router is
responsible for redaction before anything reaches a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.line import Line
from app.models.ops_center import AssetIdentity
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.services.ops_center.normalize import (
    NAME_LIKE_TYPES,
    PHONE_LIKE_TYPES,
    digits_only,
    normalize_identifier,
    normalize_name,
    normalize_phone,
    normalize_token,
)


@dataclass
class RawAssetMatch:
    asset_kind: str
    asset_ref: str
    match_source: str  # asset_identity | device | site | service_unit | line
    tenant_id: str
    matched_identifier_type: Optional[str] = None
    label: Optional[str] = None
    category: Optional[str] = None
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    service_unit_id: Optional[str] = None
    asset_identity_id: Optional[int] = None
    site_name: Optional[str] = None
    building_name: Optional[str] = None
    # Authorized contact (FULL — router masks before exposing).
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    _dedupe_key: tuple = field(default=(), repr=False)


def _phone_variants(value: str) -> set[str]:
    d = digits_only(value)
    ten = normalize_phone(value)
    out = {value, d, ten}
    if ten:
        out.update({ten, "1" + ten, "+1" + ten, "+" + d, d})
    return {v for v in out if v}


def _token_variants(value: str) -> set[str]:
    return {v for v in {value, value.strip(), normalize_token(value)} if v}


async def find_assets(
    db: AsyncSession,
    *,
    identifier: str,
    identifier_type: Optional[str] = None,
    restrict_tenant_id: Optional[str] = None,
    limit: int = 10,
) -> list[RawAssetMatch]:
    """Return redaction-pending matches for *identifier*.

    *restrict_tenant_id* scopes the search to a single tenant (used for
    customer-tenant callers).  ``None`` searches across all tenants — only
    the router's platform-operator path passes that.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return []

    matches: list[RawAssetMatch] = []
    seen: set[tuple] = set()

    def _add(m: RawAssetMatch) -> None:
        key = (m.asset_kind, m.asset_ref, m.tenant_id)
        if key in seen:
            return
        seen.add(key)
        matches.append(m)

    # ── 1. asset_identities index ────────────────────────────────────
    norm_candidates = {
        normalize_phone(identifier),
        normalize_name(identifier),
        normalize_token(identifier),
    }
    if identifier_type:
        norm_candidates.add(normalize_identifier(identifier_type, identifier))
    norm_candidates = {n for n in norm_candidates if n}

    if norm_candidates:
        q = select(AssetIdentity).where(
            AssetIdentity.identifier_value_normalized.in_(norm_candidates),
            AssetIdentity.is_active.is_(True),
        )
        if identifier_type:
            q = q.where(AssetIdentity.identifier_type == identifier_type)
        if restrict_tenant_id is not None:
            q = q.where(AssetIdentity.tenant_id == restrict_tenant_id)
        q = q.limit(limit)
        for ai in (await db.execute(q)).scalars().all():
            _add(
                RawAssetMatch(
                    asset_kind=ai.asset_kind,
                    asset_ref=ai.asset_ref,
                    match_source="asset_identity",
                    tenant_id=ai.tenant_id,
                    matched_identifier_type=ai.identifier_type,
                    label=ai.label,
                    category=ai.category,
                    site_id=ai.site_id,
                    device_id=ai.device_id,
                    service_unit_id=ai.service_unit_id,
                    asset_identity_id=ai.id,
                )
            )

    # ── 2. Native-field fallback ─────────────────────────────────────
    if len(matches) < limit:
        await _native_fallback(
            db,
            identifier=identifier,
            identifier_type=identifier_type,
            restrict_tenant_id=restrict_tenant_id,
            limit=limit,
            add=_add,
        )

    # ── 3. Resolve site name + authorized contact for each match ─────
    for m in matches:
        await _enrich_site_and_contact(db, m)

    return matches[:limit]


async def _native_fallback(db, *, identifier, identifier_type, restrict_tenant_id, limit, add) -> None:
    t = (identifier_type or "").strip().lower()
    phones = _phone_variants(identifier)
    tokens = _token_variants(identifier)
    name = normalize_name(identifier)

    def _scope(q, model):
        if restrict_tenant_id is not None:
            q = q.where(model.tenant_id == restrict_tenant_id)
        return q.limit(limit)

    want_phone = (not t) or t in PHONE_LIKE_TYPES or t in {"msisdn", "phone_number", "did", "elevator_phone"}
    want_token = (not t) or t in {"iccid", "imei", "serial_number", "device_label", "starlink_id", "napco_radio", "central_station_account", "elevator_number"}
    want_name = (not t) or t in NAME_LIKE_TYPES

    # Devices — phone (msisdn) + token (iccid/imei/serial/device_id).
    dev_conds = []
    if want_phone:
        dev_conds.append(Device.msisdn.in_(phones))
    if want_token:
        dev_conds.append(Device.iccid.in_(tokens))
        dev_conds.append(Device.imei.in_(tokens))
        dev_conds.append(Device.serial_number.in_(tokens))
        dev_conds.append(Device.device_id.in_(tokens))
    if dev_conds:
        q = _scope(select(Device).where(or_(*dev_conds)), Device)
        for d in (await db.execute(q)).scalars().all():
            add(
                RawAssetMatch(
                    asset_kind="device",
                    asset_ref=d.device_id,
                    match_source="device",
                    tenant_id=d.tenant_id,
                    label=getattr(d, "model", None) or getattr(d, "device_type", None),
                    site_id=d.site_id,
                    device_id=d.device_id,
                )
            )

    # Lines — DID (phone).
    if want_phone:
        q = _scope(select(Line).where(Line.did.in_(phones)), Line)
        for ln in (await db.execute(q)).scalars().all():
            add(
                RawAssetMatch(
                    asset_kind="line",
                    asset_ref=ln.line_id,
                    match_source="line",
                    tenant_id=ln.tenant_id,
                    label=ln.line_id,
                    site_id=ln.site_id,
                    device_id=getattr(ln, "device_id", None),
                )
            )

    # Service units — unit name / unit id.
    if want_name or want_token:
        conds = [func.lower(ServiceUnit.unit_name) == name] if want_name and name else []
        if want_token:
            conds.append(ServiceUnit.unit_id.in_(tokens))
        if conds:
            q = _scope(select(ServiceUnit).where(or_(*conds)), ServiceUnit)
            for su in (await db.execute(q)).scalars().all():
                add(
                    RawAssetMatch(
                        asset_kind="service_unit",
                        asset_ref=su.unit_id,
                        match_source="service_unit",
                        tenant_id=su.tenant_id,
                        label=su.unit_name,
                        category=getattr(su, "unit_type", None),
                        site_id=su.site_id,
                        service_unit_id=su.unit_id,
                        device_id=getattr(su, "device_id", None),
                    )
                )

    # Sites — site name / site id.
    if want_name or want_token:
        conds = [func.lower(Site.site_name) == name] if want_name and name else []
        if want_token:
            conds.append(Site.site_id.in_(tokens))
        if conds:
            q = _scope(select(Site).where(or_(*conds)), Site)
            for s in (await db.execute(q)).scalars().all():
                add(
                    RawAssetMatch(
                        asset_kind="site",
                        asset_ref=s.site_id,
                        match_source="site",
                        tenant_id=s.tenant_id,
                        label=s.site_name,
                        site_id=s.site_id,
                        site_name=s.site_name,
                    )
                )


async def _enrich_site_and_contact(db: AsyncSession, m: RawAssetMatch) -> None:
    """Populate site_name + authorized contact from the owning Site POC."""
    if not m.site_id:
        return
    q = select(Site).where(Site.site_id == m.site_id, Site.tenant_id == m.tenant_id)
    site = (await db.execute(q)).scalar_one_or_none()
    if site is None:
        return
    if not m.site_name:
        m.site_name = site.site_name
    if getattr(site, "poc_phone", None):
        m.contact_name = getattr(site, "poc_name", None)
        m.contact_phone = site.poc_phone
