"""Tenant attribution for operational source rows (D-024).

Carrier and dealer exports contain MANY customers.  A row is stored for a
tenant only when:

  A. an exact normalised identifier (MSISDN / ICCID / IMEI / NAPCO radio id)
     matches an asset this tenant already has - and no other tenant has it
     (confidence HIGH), or
  B. its label passes the tenant profile's explicit label rule with enough
     specificity (confidence MEDIUM).

Anything else is not attributed.  AMBIGUOUS rows (a weak label, an identifier
known to another tenant, a label contradicted by another tenant's identifier)
are reported for review and never stored.  A label establishes the TENANT
only - it never establishes a building (parent / generic names are never
building evidence, D-023).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from app.services.canonical.normalize import n10, nid, words

ATTRIBUTED, EXCLUDED, AMBIGUOUS = "ATTRIBUTED", "EXCLUDED", "AMBIGUOUS"
HIGH, MEDIUM = "HIGH", "MEDIUM"


@dataclass(frozen=True)
class TenantProfile:
    version: str
    brand_phrases: tuple          # full phrases unique to the customer
    short_token: Optional[str]    # e.g. "rh" - only counts with a store code

    def label_verdict(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """-> ("MATCH" | "WEAK" | None, rule)."""
        t = words(text)
        for p in self.brand_phrases:
            if " %s " % p in t:
                return "MATCH", "BRAND_PHRASE"
        if self.short_token and re.search(r"\b%s\b" % re.escape(self.short_token), t):
            # the short token counts only with a 3-4 digit store code, directly
            # after it ("RH 147", "RH-506") or as "#NNN" anywhere ("RH Houston #130")
            raw = str(text or "").lower()
            if (re.search(r"\b%s\b[\s#-]*\d{3,4}\b" % re.escape(self.short_token), raw)
                    or re.search(r"#\s*\d{3,4}\b", raw)):
                return "MATCH", "STORE_CODE"
            return "WEAK", "SHORT_TOKEN_ONLY"
        return None, None


TENANT_PROFILES = {
    "restoration-hardware": TenantProfile(
        version="rh.attribution.v1",
        brand_phrases=("restoration hardware", "restoration hdwr"),
        short_token="rh"),
}


def profile_version(tenant_id: str) -> str:
    p = TENANT_PROFILES.get(tenant_id)
    return p.version if p else "identifier-only.v1"


def keys_for(idents: dict) -> set:
    out = set()
    for kind, v in idents.items():
        out.add(("P:" + v) if kind == "msisdn" else ("I:" + v))
    return out


class IdentifierIndex:
    """Normalised identifier -> tenants that hold it (across ALL tenants, so a
    row can be checked against other customers too)."""

    def __init__(self):
        self.owners = defaultdict(set)

    def add(self, tenant, value, phone=False):
        if not value or not tenant:
            return
        k = n10(value) if phone else nid(value)
        if k:
            self.owners[("P:" if phone else "I:") + k].add(tenant)


async def build_index(db) -> IdentifierIndex:
    """Read-only: every known identifier of every tenant."""
    from sqlalchemy import select

    from app.models.canonical import CommunicationsAsset
    from app.models.device import Device
    from app.models.line import Line
    from app.models.portfolio_registry import PortfolioDeviceMapping
    from app.models.sim import Sim

    ix = IdentifierIndex()
    for t, msisdn, iccid, imei, star, serial in (await db.execute(select(
            Device.tenant_id, Device.msisdn, Device.iccid, Device.imei, Device.starlink_id,
            Device.serial_number))).all():
        ix.add(t, msisdn, phone=True)
        for v in (iccid, imei, star, serial):
            ix.add(t, v)
    for t, did, sim in (await db.execute(select(Line.tenant_id, Line.did, Line.sim_iccid))).all():
        ix.add(t, did, phone=True)
        ix.add(t, sim)
    for t, iccid, msisdn, imei in (await db.execute(select(
            Sim.tenant_id, Sim.iccid, Sim.msisdn, Sim.imei))).all():
        ix.add(t, iccid)
        ix.add(t, imei)
        ix.add(t, msisdn, phone=True)
    for t, kind, value, active in (await db.execute(select(
            PortfolioDeviceMapping.tenant_id, PortfolioDeviceMapping.kind,
            PortfolioDeviceMapping.value, PortfolioDeviceMapping.active))).all():
        if not active:
            continue
        if kind in ("phone", "genesis_msisdn"):
            ix.add(t, value, phone=True)
        elif kind in ("napco_radio", "iccid", "imei"):
            ix.add(t, value)
    for t, atype, value in (await db.execute(select(
            CommunicationsAsset.tenant_id, CommunicationsAsset.asset_type,
            CommunicationsAsset.normalized_value))).all():
        ix.add(t, value, phone=(atype == "TELEPHONE_NUMBER"))
    return ix


def attribute(tenant_id: str, idents: dict, labels: list, ix: IdentifierIndex) -> dict:
    """-> {"verdict", "basis", "confidence"}."""
    keys = keys_for(idents)
    own = sorted(k for k in keys if tenant_id in ix.owners.get(k, ()))
    other = sorted(k for k in keys if ix.owners.get(k, set()) - {tenant_id})
    prof = TENANT_PROFILES.get(tenant_id)
    lab, rule = (None, None)
    if prof:
        for text in labels:
            lab, rule = prof.label_verdict(text)
            if lab == "MATCH":
                break
    if own and other:
        return {"verdict": AMBIGUOUS, "basis": "IDENTIFIER_CROSS_TENANT", "confidence": None}
    if other and lab:
        return {"verdict": AMBIGUOUS, "basis": "LABEL_VS_OTHER_TENANT_IDENTIFIER",
                "confidence": None}
    if own:
        kinds = sorted({k.split(":")[0] for k in own})
        basis = "IDENTIFIER_MATCH:%s" % ("PHONE" if kinds == ["P"] else
                                          "EQUIPMENT" if kinds == ["I"] else "PHONE+EQUIPMENT")
        if lab == "MATCH":
            basis += "+LABEL"
        return {"verdict": ATTRIBUTED, "basis": basis, "confidence": HIGH}
    if other:
        return {"verdict": EXCLUDED, "basis": "OTHER_TENANT_IDENTIFIER", "confidence": None}
    if lab == "MATCH":
        return {"verdict": ATTRIBUTED, "basis": "LABEL:%s" % rule, "confidence": MEDIUM}
    if lab == "WEAK":
        return {"verdict": AMBIGUOUS, "basis": "LABEL:%s" % rule, "confidence": None}
    return {"verdict": EXCLUDED, "basis": "NO_TENANT_EVIDENCE", "confidence": None}
