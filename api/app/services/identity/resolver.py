"""Identity Engine — pure deterministic IdentityResolver (Phase 0 / PR-1a).

The Identity Engine answers "what is this and where does it belong?" — the first
layer of the stack:  Reality -> Identity Engine -> Truth Engine -> Assurance
Engine -> AI -> Automation.  This module is its deterministic *core*.

Design (see ``docs/TRUTH_ENGINE.md``):

    Facts  ->  Proof Chain  ->  Decision

The **proof chain is the canonical artifact**.  The resolution *status*
(RESOLVED / AMBIGUOUS / ORPHAN) is DERIVED from the chain — it is not the primary
product.  The function is pure: no I/O, no DB, no network, no clock, and it never
mutates its inputs.  It NEVER guesses — ambiguous input yields AMBIGUOUS, and
heuristics only ever *suggest* (they never auto-resolve).

Inputs are plain ``*Facts`` value objects, not ORM rows, so the resolver is
trivially testable and decoupled from the database.  A later PR's read-only loader
maps ORM rows -> these facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional

from . import reason_codes as rc


# ─────────────────────────── Enums ───────────────────────────

class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    ORPHAN = "orphan"


class LinkKind(str, Enum):
    DEVICE = "device"
    SIM = "sim"
    MSISDN = "msisdn"
    SITE = "site"
    SERVICE_UNIT = "service_unit"
    CUSTOMER = "customer"
    TENANT = "tenant"
    ORGANIZATION = "organization"
    E911 = "e911"


class LinkStatus(str, Enum):
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    SUGGESTED = "suggested"


class MatchBasis(str, Enum):
    ICCID = "ICCID"
    IMEI = "IMEI"
    MSISDN = "MSISDN"
    EXTERNAL_MAP = "EXTERNAL_MAP"
    SITE_FK = "SITE_FK"
    CUSTOMER_FK = "CUSTOMER_FK"
    TENANT_FK = "TENANT_FK"
    SERVICE_UNIT_FK = "SERVICE_UNIT_FK"
    SIM_FIELD = "SIM_FIELD"
    E911_FIELD = "E911_FIELD"
    HEURISTIC = "HEURISTIC"
    ORG_FIELD = "ORG_FIELD"


_BASIS_CONFIDENCE: dict[MatchBasis, float] = {
    MatchBasis.ICCID: 1.0,
    MatchBasis.IMEI: 0.9,
    MatchBasis.MSISDN: 0.8,
    MatchBasis.EXTERNAL_MAP: 0.7,
    MatchBasis.SITE_FK: 1.0,
    MatchBasis.CUSTOMER_FK: 1.0,
    MatchBasis.TENANT_FK: 1.0,
    MatchBasis.SERVICE_UNIT_FK: 1.0,
    MatchBasis.SIM_FIELD: 1.0,
    MatchBasis.E911_FIELD: 1.0,
    MatchBasis.ORG_FIELD: 1.0,
    MatchBasis.HEURISTIC: 0.5,
}


# ─────────────────────────── Input facts ───────────────────────────

@dataclass(frozen=True)
class DeviceFacts:
    device_id: str
    tenant_id: str
    org_id: Optional[str] = None
    site_id: Optional[str] = None
    iccid: Optional[str] = None
    imei: Optional[str] = None
    serial_number: Optional[str] = None
    msisdn: Optional[str] = None
    sim_id: Optional[str] = None
    carrier: Optional[str] = None
    identifier_type: Optional[str] = None  # cellular | ata | starlink | None
    status: Optional[str] = None


@dataclass(frozen=True)
class SimFacts:
    iccid: str
    msisdn: Optional[str] = None
    imei: Optional[str] = None
    device_id: Optional[str] = None
    site_id: Optional[str] = None
    customer_id: Optional[int] = None
    carrier: Optional[str] = None


@dataclass(frozen=True)
class SiteFacts:
    site_id: str
    tenant_id: str
    customer_id: Optional[int] = None
    e911_present: bool = False


@dataclass(frozen=True)
class CustomerFacts:
    customer_id: int
    tenant_id: str


@dataclass(frozen=True)
class ServiceUnitFacts:
    unit_id: str
    site_id: str
    device_id: Optional[str] = None


@dataclass(frozen=True)
class ExternalMapFacts:
    device_id: Optional[str] = None
    customer_id: Optional[int] = None
    site_id: Optional[str] = None
    map_status: str = "unmapped"  # unmapped | suggested | confirmed


@dataclass(frozen=True)
class ResolverInput:
    device: DeviceFacts
    sims_by_iccid: Mapping[str, SimFacts] = field(default_factory=dict)
    sims_by_imei: Mapping[str, tuple[SimFacts, ...]] = field(default_factory=dict)
    sims_by_msisdn: Mapping[str, tuple[SimFacts, ...]] = field(default_factory=dict)
    sites_by_id: Mapping[str, SiteFacts] = field(default_factory=dict)
    customers_by_id: Mapping[int, CustomerFacts] = field(default_factory=dict)
    service_units_by_device: Mapping[str, tuple[ServiceUnitFacts, ...]] = field(default_factory=dict)
    external_map_by_device: Mapping[str, tuple[ExternalMapFacts, ...]] = field(default_factory=dict)


# ─────────────────────────── Output ───────────────────────────

@dataclass(frozen=True)
class ProofLink:
    from_kind: LinkKind
    from_id: Optional[str]
    to_kind: LinkKind
    to_id: Optional[str]
    basis: Optional[MatchBasis]
    source: str
    status: LinkStatus
    confidence: float
    reason_code: Optional[str] = None


@dataclass(frozen=True)
class HierarchyResolution:
    device_id: str
    status: ResolutionStatus
    proof_chain: tuple[ProofLink, ...]
    organization_id: Optional[str]
    tenant_id: Optional[str]
    customer_id: Optional[int]
    site_id: Optional[str]
    service_unit_id: Optional[str]
    sim_iccid: Optional[str]
    msisdn: Optional[str]
    e911_present: bool
    reason_codes: tuple[str, ...]
    match_basis: tuple[str, ...]
    suggestions: tuple[str, ...]
    confidence: float


# ─────────────────────────── Helpers ───────────────────────────

def _is_cellular(d: DeviceFacts) -> bool:
    if d.identifier_type in ("ata", "starlink"):
        return False
    if d.identifier_type == "cellular":
        return True
    # Unknown type: infer cellular only if it carries a cellular identity.
    return bool(d.iccid or d.msisdn or d.imei or d.sim_id or d.carrier)


def _conf(basis: MatchBasis) -> float:
    return _BASIS_CONFIDENCE[basis]


# ─────────────────────────── Core ───────────────────────────

def resolve_device(inp: ResolverInput) -> HierarchyResolution:
    """Resolve a device into the canonical hierarchy.

    Builds the proof chain from facts, then derives the status from the chain.
    Pure and side-effect free.
    """
    d = inp.device
    links: list[ProofLink] = []
    suggestions: list[str] = []

    # 1) DEVICE -> TENANT (authoritative; tenant_id is NOT NULL on devices).
    links.append(ProofLink(
        LinkKind.DEVICE, d.device_id, LinkKind.TENANT, d.tenant_id,
        MatchBasis.TENANT_FK, "devices.tenant_id", LinkStatus.CONFIRMED,
        _conf(MatchBasis.TENANT_FK),
    ))
    organization_id: Optional[str] = None
    if d.org_id:
        organization_id = d.org_id
        links.append(ProofLink(
            LinkKind.TENANT, d.tenant_id, LinkKind.ORGANIZATION, d.org_id,
            MatchBasis.ORG_FIELD, "tenant.org_id", LinkStatus.CONFIRMED,
            _conf(MatchBasis.ORG_FIELD),
        ))

    # 2) DEVICE -> SIM (precedence: ICCID > IMEI > MSISDN).
    cellular = _is_cellular(d)
    sim: Optional[SimFacts] = None
    sim_link: Optional[ProofLink] = None

    if d.iccid and d.iccid in inp.sims_by_iccid:
        candidate = inp.sims_by_iccid[d.iccid]
        # Contradiction check: SIM assigned to a different site than the device.
        if candidate.site_id and d.site_id and candidate.site_id != d.site_id:
            sim_link = ProofLink(
                LinkKind.DEVICE, d.device_id, LinkKind.SIM, candidate.iccid,
                MatchBasis.ICCID, "devices.iccid -> sims.iccid", LinkStatus.AMBIGUOUS,
                _conf(MatchBasis.ICCID), rc.AMBIGUOUS_ICCID_SITE_MISMATCH.code,
            )
        else:
            sim = candidate
            sim_link = ProofLink(
                LinkKind.DEVICE, d.device_id, LinkKind.SIM, candidate.iccid,
                MatchBasis.ICCID, "devices.iccid -> sims.iccid", LinkStatus.CONFIRMED,
                _conf(MatchBasis.ICCID), rc.RESOLVED_ICCID.code,
            )
    elif d.iccid:
        # Declared an ICCID but no SIM record matches it (info; continue precedence).
        links.append(ProofLink(
            LinkKind.DEVICE, d.device_id, LinkKind.SIM, d.iccid,
            MatchBasis.ICCID, "devices.iccid", LinkStatus.MISSING,
            0.0, rc.UNMATCHED_ICCID.code,
        ))

    if sim is None and sim_link is None and d.imei:
        imei_hits = inp.sims_by_imei.get(d.imei, ())
        if len(imei_hits) == 1:
            sim = imei_hits[0]
            sim_link = ProofLink(
                LinkKind.DEVICE, d.device_id, LinkKind.SIM, sim.iccid,
                MatchBasis.IMEI, "devices.imei -> sims.imei", LinkStatus.CONFIRMED,
                _conf(MatchBasis.IMEI), rc.RESOLVED_IMEI.code,
            )

    if sim is None and sim_link is None and d.msisdn:
        msisdn_hits = inp.sims_by_msisdn.get(d.msisdn, ())
        if len(msisdn_hits) == 1:
            sim = msisdn_hits[0]
            sim_link = ProofLink(
                LinkKind.DEVICE, d.device_id, LinkKind.SIM, sim.iccid,
                MatchBasis.MSISDN, "devices.msisdn -> sims.msisdn", LinkStatus.CONFIRMED,
                _conf(MatchBasis.MSISDN), rc.RESOLVED_MSISDN.code,
            )
        elif len(msisdn_hits) > 1:
            sim_link = ProofLink(
                LinkKind.DEVICE, d.device_id, LinkKind.SIM, None,
                MatchBasis.MSISDN, "devices.msisdn -> sims.msisdn", LinkStatus.AMBIGUOUS,
                _conf(MatchBasis.MSISDN), rc.AMBIGUOUS_MSISDN.code,
            )

    if sim_link is None:
        # No SIM identity at all.
        if cellular:
            sim_link = ProofLink(
                LinkKind.DEVICE, d.device_id, LinkKind.SIM, None,
                None, "devices.(iccid|imei|msisdn)", LinkStatus.MISSING,
                0.0, rc.MISSING_SIM.code,
            )
        # Non-cellular: no SIM link required (omit).
    if sim_link is not None:
        links.append(sim_link)

    # 3) SIM -> MSISDN (gap if absent).
    msisdn_value: Optional[str] = (sim.msisdn if sim else None) or d.msisdn
    if msisdn_value:
        links.append(ProofLink(
            LinkKind.SIM if sim else LinkKind.DEVICE,
            sim.iccid if sim else d.device_id,
            LinkKind.MSISDN, msisdn_value,
            MatchBasis.SIM_FIELD, "sims.msisdn" if sim else "devices.msisdn",
            LinkStatus.CONFIRMED, _conf(MatchBasis.SIM_FIELD),
        ))
    elif cellular:
        links.append(ProofLink(
            LinkKind.SIM if sim else LinkKind.DEVICE,
            sim.iccid if sim else d.device_id,
            LinkKind.MSISDN, None, None, "sims.msisdn", LinkStatus.MISSING,
            0.0, rc.MISSING_MSISDN.code,
        ))

    # Carrier completeness (info) — a device attribute, not a SIM-identity link.
    if not (d.carrier or (sim and sim.carrier)):
        links.append(ProofLink(
            LinkKind.DEVICE, d.device_id, LinkKind.DEVICE, d.device_id,
            None, "devices.carrier|sims.carrier", LinkStatus.MISSING,
            0.0, rc.UNKNOWN_CARRIER.code,
        ))

    # 4) DEVICE -> SITE (FK > confirmed external map > heuristic suggestion).
    site: Optional[SiteFacts] = None
    ext = inp.external_map_by_device.get(d.device_id, ())
    ext_site = next((e.site_id for e in ext if e.map_status == "confirmed" and e.site_id), None)
    ext_customer = next((e.customer_id for e in ext if e.map_status == "confirmed" and e.customer_id), None)

    if d.site_id and d.site_id in inp.sites_by_id:
        site = inp.sites_by_id[d.site_id]
        links.append(ProofLink(
            LinkKind.DEVICE, d.device_id, LinkKind.SITE, site.site_id,
            MatchBasis.SITE_FK, "devices.site_id", LinkStatus.CONFIRMED,
            _conf(MatchBasis.SITE_FK),
        ))
    elif ext_site and ext_site in inp.sites_by_id:
        site = inp.sites_by_id[ext_site]
        links.append(ProofLink(
            LinkKind.DEVICE, d.device_id, LinkKind.SITE, site.site_id,
            MatchBasis.EXTERNAL_MAP, "external_record_map(confirmed).site_id",
            LinkStatus.CONFIRMED, _conf(MatchBasis.EXTERNAL_MAP), rc.RESOLVED_EXTERNAL_MAP.code,
        ))
    else:
        # Heuristic suggestion from the matched SIM's site — never auto-applied.
        if sim and sim.site_id and sim.site_id in inp.sites_by_id:
            links.append(ProofLink(
                LinkKind.DEVICE, d.device_id, LinkKind.SITE, sim.site_id,
                MatchBasis.HEURISTIC, "sims.site_id (suggested)", LinkStatus.SUGGESTED,
                _conf(MatchBasis.HEURISTIC), rc.HEURISTIC_SUGGESTED.code,
            ))
            suggestions.append(f"site={sim.site_id} (from matched SIM; needs approval)")
        links.append(ProofLink(
            LinkKind.DEVICE, d.device_id, LinkKind.SITE, None,
            None, "devices.site_id", LinkStatus.MISSING, 0.0, rc.MISSING_SITE.code,
        ))

    # 5) SITE -> CUSTOMER (FK > confirmed external map > heuristic).
    customer_id: Optional[int] = None
    if site is not None:
        if site.customer_id is not None and site.customer_id in inp.customers_by_id:
            customer_id = site.customer_id
            links.append(ProofLink(
                LinkKind.SITE, site.site_id, LinkKind.CUSTOMER, str(customer_id),
                MatchBasis.CUSTOMER_FK, "sites.customer_id", LinkStatus.CONFIRMED,
                _conf(MatchBasis.CUSTOMER_FK),
            ))
        elif ext_customer is not None and ext_customer in inp.customers_by_id:
            customer_id = ext_customer
            links.append(ProofLink(
                LinkKind.SITE, site.site_id, LinkKind.CUSTOMER, str(customer_id),
                MatchBasis.EXTERNAL_MAP, "external_record_map(confirmed).customer_id",
                LinkStatus.CONFIRMED, _conf(MatchBasis.EXTERNAL_MAP), rc.RESOLVED_EXTERNAL_MAP.code,
            ))
        else:
            if sim and sim.customer_id is not None and sim.customer_id in inp.customers_by_id:
                links.append(ProofLink(
                    LinkKind.SITE, site.site_id, LinkKind.CUSTOMER, str(sim.customer_id),
                    MatchBasis.HEURISTIC, "sims.customer_id (suggested)", LinkStatus.SUGGESTED,
                    _conf(MatchBasis.HEURISTIC), rc.HEURISTIC_SUGGESTED.code,
                ))
                suggestions.append(f"customer={sim.customer_id} (from matched SIM; needs approval)")
            links.append(ProofLink(
                LinkKind.SITE, site.site_id, LinkKind.CUSTOMER, None,
                None, "sites.customer_id", LinkStatus.MISSING, 0.0, rc.MISSING_CUSTOMER.code,
            ))

    # 6) SITE -> E911 (gap; never blocks RESOLVED).
    e911_present = bool(site.e911_present) if site is not None else False
    if site is not None:
        if e911_present:
            links.append(ProofLink(
                LinkKind.SITE, site.site_id, LinkKind.E911, site.site_id,
                MatchBasis.E911_FIELD, "sites.e911_*", LinkStatus.CONFIRMED,
                _conf(MatchBasis.E911_FIELD),
            ))
        else:
            links.append(ProofLink(
                LinkKind.SITE, site.site_id, LinkKind.E911, None,
                None, "sites.e911_*", LinkStatus.MISSING, 0.0, rc.MISSING_E911.code,
            ))

    # 7) DEVICE -> SERVICE_UNIT (gap; exactly-one only, never guess).
    service_unit_id: Optional[str] = None
    units = inp.service_units_by_device.get(d.device_id, ())
    if len(units) == 1:
        service_unit_id = units[0].unit_id
        links.append(ProofLink(
            LinkKind.DEVICE, d.device_id, LinkKind.SERVICE_UNIT, service_unit_id,
            MatchBasis.SERVICE_UNIT_FK, "service_units.device_id", LinkStatus.CONFIRMED,
            _conf(MatchBasis.SERVICE_UNIT_FK),
        ))
    else:
        links.append(ProofLink(
            LinkKind.DEVICE, d.device_id, LinkKind.SERVICE_UNIT, None,
            None, "service_units.device_id", LinkStatus.MISSING, 0.0,
            rc.MISSING_SERVICE_UNIT.code,
        ))

    # ── Derive the decision FROM the proof chain ──
    status, decision_reasons = _derive_status(links, cellular=cellular, has_site=site is not None)

    # Aggregate explainability.
    reason_codes: list[str] = []
    match_basis: list[str] = []
    confirmed_required_conf: list[float] = []
    for link in links:
        if link.reason_code and link.reason_code not in reason_codes:
            reason_codes.append(link.reason_code)
        if link.status == LinkStatus.CONFIRMED and link.basis is not None:
            if link.basis.value not in match_basis:
                match_basis.append(link.basis.value)
    for code in decision_reasons:
        if code not in reason_codes:
            reason_codes.append(code)

    # Confidence = min over confirmed REQUIRED links (tenant + sim-if-cellular +
    # site + customer); 0.0 when not resolved.
    if status == ResolutionStatus.RESOLVED:
        required_kinds = {LinkKind.TENANT, LinkKind.SITE, LinkKind.CUSTOMER}
        if cellular:
            required_kinds.add(LinkKind.SIM)
        for link in links:
            if link.to_kind in required_kinds and link.status == LinkStatus.CONFIRMED:
                confirmed_required_conf.append(link.confidence)
        confidence = min(confirmed_required_conf) if confirmed_required_conf else 1.0
    else:
        confidence = 0.0

    return HierarchyResolution(
        device_id=d.device_id,
        status=status,
        proof_chain=tuple(links),
        organization_id=organization_id,
        tenant_id=d.tenant_id,
        customer_id=customer_id,
        site_id=site.site_id if site is not None else None,
        service_unit_id=service_unit_id,
        sim_iccid=sim.iccid if sim is not None else None,
        msisdn=msisdn_value,
        e911_present=e911_present,
        reason_codes=tuple(reason_codes),
        match_basis=tuple(match_basis),
        suggestions=tuple(suggestions),
        confidence=confidence,
    )


def _derive_status(
    links: list[ProofLink], *, cellular: bool, has_site: bool
) -> tuple[ResolutionStatus, list[str]]:
    """Derive status from the proof chain. Ambiguity beats orphan."""
    # Ambiguity in any required identity link → cannot trust the placement.
    if any(link.status == LinkStatus.AMBIGUOUS for link in links):
        return ResolutionStatus.AMBIGUOUS, []

    reasons: list[str] = []
    # Required links MISSING → orphan (gaps E911/service_unit/msisdn excluded).
    site_missing = any(
        link.to_kind == LinkKind.SITE and link.status == LinkStatus.MISSING for link in links
    )
    customer_missing = (not has_site) or any(
        link.to_kind == LinkKind.CUSTOMER and link.status == LinkStatus.MISSING for link in links
    )
    sim_missing = cellular and any(
        link.to_kind == LinkKind.SIM and link.status == LinkStatus.MISSING
        and link.reason_code == rc.MISSING_SIM.code
        for link in links
    )

    if site_missing:
        reasons.append(rc.ORPHAN_NO_SITE.code)
    if has_site and customer_missing:
        reasons.append(rc.ORPHAN_NO_CUSTOMER.code)
    if sim_missing:
        reasons.append(rc.ORPHAN_CELLULAR_NO_SIM.code)

    if reasons:
        return ResolutionStatus.ORPHAN, reasons
    return ResolutionStatus.RESOLVED, []
