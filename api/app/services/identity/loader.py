"""Read-only loader for the Identity Audit (Phase 0 / PR-1b1).

Maps ORM rows -> the pure resolver's ``*Facts`` value objects and the lookup maps
``resolve_device`` needs, plus site-level E911 facts the audit reports separately.

Strictly read-only: it issues bounded SELECTs and builds plain data structures.  It
performs no writes, no mutations, and no external calls.  The pure mapping
(``build_dataset``) is separated from the I/O (``load_identity_dataset``) so it can
be unit-tested without a database.

E911 (per ``DECISIONS.md`` — Option 3, do not collapse):
  * ``e911_address_present`` = street + city + state + zip are populated
  * ``e911_verified``        = e911_status indicates verified / validated
  * ``e911_confirmation_required`` = the confirmation-required flag is set
The resolver's ``SiteFacts.e911_present`` maps to *address present* (its
``MISSING_E911`` gap means "no dispatchable address"); verification is a
data-quality / assurance concern reported by the audit, not an identity gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.device import Device
from app.models.external_record_map import ExternalRecordMap
from app.models.service_unit import ServiceUnit
from app.models.sim import Sim
from app.models.site import Site

from .resolver import (
    CustomerFacts,
    DeviceFacts,
    ExternalMapFacts,
    ResolverInput,
    ServiceUnitFacts,
    SimFacts,
    SiteFacts,
)

# e911_status values that count as verified (case-insensitive).
VERIFIED_E911_STATUSES = frozenset({"validated", "verified"})


@dataclass(frozen=True)
class SiteE911Facts:
    site_id: str
    tenant_id: str
    e911_address_present: bool
    e911_verified: bool
    e911_confirmation_required: bool


@dataclass
class IdentityDataset:
    """Everything the audit needs for one scope, as plain data."""

    devices: list[DeviceFacts] = field(default_factory=list)
    sims: list[SimFacts] = field(default_factory=list)
    sims_by_iccid: dict[str, SimFacts] = field(default_factory=dict)
    sims_by_imei: dict[str, tuple[SimFacts, ...]] = field(default_factory=dict)
    sims_by_msisdn: dict[str, tuple[SimFacts, ...]] = field(default_factory=dict)
    sites_by_id: dict[str, SiteFacts] = field(default_factory=dict)
    customers_by_id: dict[int, CustomerFacts] = field(default_factory=dict)
    service_units_by_device: dict[str, tuple[ServiceUnitFacts, ...]] = field(default_factory=dict)
    external_map_by_device: dict[str, tuple[ExternalMapFacts, ...]] = field(default_factory=dict)
    site_e911: list[SiteE911Facts] = field(default_factory=list)

    def resolver_input(self, device: DeviceFacts) -> ResolverInput:
        return ResolverInput(
            device=device,
            sims_by_iccid=self.sims_by_iccid,
            sims_by_imei=self.sims_by_imei,
            sims_by_msisdn=self.sims_by_msisdn,
            sites_by_id=self.sites_by_id,
            customers_by_id=self.customers_by_id,
            service_units_by_device=self.service_units_by_device,
            external_map_by_device=self.external_map_by_device,
        )


def _g(row: Any, name: str, default: Any = None) -> Any:
    return getattr(row, name, default)


def _addr_present(site: Any) -> bool:
    return all(
        bool(_g(site, f))
        for f in ("e911_street", "e911_city", "e911_state", "e911_zip")
    )


def _is_verified(status: Any) -> bool:
    return bool(status) and str(status).strip().lower() in VERIFIED_E911_STATUSES


def _device_facts(row: Any) -> DeviceFacts:
    return DeviceFacts(
        device_id=_g(row, "device_id"),
        tenant_id=_g(row, "tenant_id"),
        org_id=None,  # no Organization entity yet (DECISIONS D-012)
        site_id=_g(row, "site_id"),
        iccid=_g(row, "iccid"),
        imei=_g(row, "imei"),
        serial_number=_g(row, "serial_number"),
        msisdn=_g(row, "msisdn"),
        sim_id=_g(row, "sim_id"),
        carrier=_g(row, "carrier"),
        identifier_type=_g(row, "identifier_type"),
        status=_g(row, "status"),
    )


def _sim_facts(row: Any) -> SimFacts:
    return SimFacts(
        iccid=_g(row, "iccid"),
        msisdn=_g(row, "msisdn"),
        imei=_g(row, "imei"),
        device_id=_g(row, "device_id"),
        site_id=_g(row, "site_id"),
        customer_id=_g(row, "customer_id"),
        carrier=_g(row, "carrier"),
    )


def _site_facts(row: Any) -> SiteFacts:
    return SiteFacts(
        site_id=_g(row, "site_id"),
        tenant_id=_g(row, "tenant_id"),
        customer_id=_g(row, "customer_id"),
        e911_present=_addr_present(row),  # resolver: address present
    )


def _site_e911_facts(row: Any) -> SiteE911Facts:
    return SiteE911Facts(
        site_id=_g(row, "site_id"),
        tenant_id=_g(row, "tenant_id"),
        e911_address_present=_addr_present(row),
        e911_verified=_is_verified(_g(row, "e911_status")),
        e911_confirmation_required=bool(_g(row, "e911_confirmation_required")),
    )


def build_dataset(
    devices: Iterable[Any],
    sims: Iterable[Any],
    sites: Iterable[Any],
    customers: Iterable[Any],
    service_units: Iterable[Any],
    external_maps: Iterable[Any],
) -> IdentityDataset:
    """Pure: map row collections into an IdentityDataset (no I/O)."""
    sim_facts = [_sim_facts(s) for s in sims]
    sims_by_iccid: dict[str, SimFacts] = {}
    sims_by_imei: dict[str, list[SimFacts]] = {}
    sims_by_msisdn: dict[str, list[SimFacts]] = {}
    for s in sim_facts:
        if s.iccid:
            sims_by_iccid[s.iccid] = s  # iccid is globally unique
        if s.imei:
            sims_by_imei.setdefault(s.imei, []).append(s)
        if s.msisdn:
            sims_by_msisdn.setdefault(s.msisdn, []).append(s)

    sites_list = list(sites)
    sites_by_id = {sf.site_id: sf for sf in (_site_facts(s) for s in sites_list)}
    site_e911 = [_site_e911_facts(s) for s in sites_list]

    customers_by_id: dict[int, CustomerFacts] = {}
    for c in customers:
        cid = _g(c, "id")
        if cid is not None:
            customers_by_id[cid] = CustomerFacts(customer_id=cid, tenant_id=_g(c, "tenant_id"))

    su_by_device: dict[str, list[ServiceUnitFacts]] = {}
    for u in service_units:
        suf = ServiceUnitFacts(
            unit_id=_g(u, "unit_id"), site_id=_g(u, "site_id"), device_id=_g(u, "device_id")
        )
        if suf.device_id:
            su_by_device.setdefault(suf.device_id, []).append(suf)

    ext_by_device: dict[str, list[ExternalMapFacts]] = {}
    for e in external_maps:
        ef = ExternalMapFacts(
            device_id=_g(e, "device_id"),
            customer_id=_g(e, "customer_id"),
            site_id=_g(e, "site_id"),
            map_status=_g(e, "map_status", "unmapped"),
        )
        if ef.device_id:
            ext_by_device.setdefault(ef.device_id, []).append(ef)

    return IdentityDataset(
        devices=[_device_facts(d) for d in devices],
        sims=sim_facts,
        sims_by_iccid=sims_by_iccid,
        sims_by_imei={k: tuple(v) for k, v in sims_by_imei.items()},
        sims_by_msisdn={k: tuple(v) for k, v in sims_by_msisdn.items()},
        sites_by_id=sites_by_id,
        customers_by_id=customers_by_id,
        service_units_by_device={k: tuple(v) for k, v in su_by_device.items()},
        external_map_by_device={k: tuple(v) for k, v in ext_by_device.items()},
        site_e911=site_e911,
    )


async def _fetch(db: AsyncSession, stmt) -> list[Any]:
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def load_identity_dataset(
    db: AsyncSession, tenant_id: str | None = None
) -> IdentityDataset:
    """Read-only: bounded SELECTs for one tenant (or all), then build_dataset.

    Six independent queries; results assembled into plain dicts.  No writes.
    """
    def _scope(model, stmt):
        return stmt.where(model.tenant_id == tenant_id) if tenant_id else stmt

    devices = await _fetch(db, _scope(Device, select(Device)))
    sims = await _fetch(db, _scope(Sim, select(Sim)))
    sites = await _fetch(db, _scope(Site, select(Site)))
    customers = await _fetch(db, _scope(Customer, select(Customer)))
    service_units = await _fetch(db, _scope(ServiceUnit, select(ServiceUnit)))
    external_maps = await _fetch(db, select(ExternalRecordMap))

    return build_dataset(devices, sims, sites, customers, service_units, external_maps)
