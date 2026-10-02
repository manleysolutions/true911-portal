"""Canonical customer service-inventory read model (#186b, D-023) - READ-ONLY.

Turns the APPLIED canonical projection (life_safety_services /
life_safety_connections / connection_asset_links / communications_assets) into a
customer-safe, machine-readable SERVICE INVENTORY state per building and for the
portfolio.  It replaces the hard-coded "Being finalized by True911" placeholder
only when explicitly enabled.

This is inventory truth - NOT regulatory certification, E911 verification,
monitoring certification or customer attestation.  States:

  READY                  "Service inventory confirmed by True911"
  PARTIALLY_READY        "Some service inventory is confirmed. Additional records
                          are being finalized by True911."
  BEING_FINALIZED        "Being finalized by True911"
  NO_SERVICES_ON_RECORD  "No life-safety services on record"

A service is READY only when ALL hold: it belongs to the latest clean APPLY
projection; its type is a life-safety type; it is not REJECTED; its confidence
is CONFIRMED or it is explicitly APPROVED; its lifecycle is CURRENT; it has at
least one REQUIRED connection (the writer creates connections only for counted
services); and its building is approved, active, not pending and not marked
BUILDING_IDENTITY_SUSPECT.  Historical / decommissioned and REJECTED services
are never shown.  Everything else still current (PROBABLE / UNRESOLVED /
UNCLASSIFIED / confirmed-but-not-counted) only ever makes a building "being
finalized" - it is never listed or counted as inventory.

Never exposed: canonical keys, radio / SIM / IMEI / ICCID values, provenance,
evidence, findings, database ids (refs are opaque - see refs.py).  A telephone
number appears ONLY for a READY Elevator / Emergency Phone service, from that
service's own active CARRIER_LINE link; an FACP never carries one.  E911 is not
an input or an output of this module.

Gating: FEATURE_CANONICAL_SERVICE_MODEL == "true" AND the tenant is in
CANONICAL_SERVICE_MODEL_TENANT_ALLOWLIST AND the durable CUSTOMER_REF_SECRET is
configured (fails closed otherwise) AND a clean APPLY run exists.  Off -> the
loaders return None and no customer payload changes.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict

from sqlalchemy import select

from app.config import settings
from app.services.canonical import vocab as V
from app.services.customer.refs import dedicated_secret_configured, encode_ref

logger = logging.getLogger("customer.canonical_view")

READY = "READY"
PARTIALLY_READY = "PARTIALLY_READY"
BEING_FINALIZED = "BEING_FINALIZED"
NO_SERVICES = "NO_SERVICES_ON_RECORD"
STATES = (READY, PARTIALLY_READY, BEING_FINALIZED, NO_SERVICES)
MESSAGES = {
    READY: "Service inventory confirmed by True911",
    PARTIALLY_READY: ("Some service inventory is confirmed. Additional records are being "
                      "finalized by True911."),
    BEING_FINALIZED: "Being finalized by True911",
    NO_SERVICES: "No life-safety services on record",
}
SERVICE_LABEL = {V.FACP: "Fire Alarm", V.ELEVATOR: "Elevator",
                 V.EMERGENCY_PHONE: "Emergency Phone"}
_NUMBERED = (V.ELEVATOR, V.EMERGENCY_PHONE)        # FACP never carries a number


def canonical_mode_enabled(tenant_id) -> bool:
    return (settings.FEATURE_CANONICAL_SERVICE_MODEL == "true"
            and tenant_id in settings.canonical_service_model_tenant_id_set)


async def load_inventory(db, tenant_id: str, *, force: bool = False):
    """The tenant's canonical inventory from its latest clean APPLY run, or None
    (mode off / no durable ref secret / no clean run).  ``force`` bypasses the
    flag and secret checks for the internal read-only preview ONLY."""
    from app.models.canonical import (
        CommunicationsAsset,
        ConnectionAssetLink,
        LifeSafetyConnection,
        LifeSafetyService,
        OperatorDecision,
        ProjectionRun,
    )
    if not force:
        if not canonical_mode_enabled(tenant_id):
            return None
        if not dedicated_secret_configured():
            logger.error("canonical customer view: tenant=%s enabled but CUSTOMER_REF_SECRET is "
                         "not configured - failing closed (legacy view served)", tenant_id)
            return None
    # the LATEST applied projection only - never an older one: if the latest is
    # degraded or unfinished, nothing is served (fail closed, no stale fallback)
    run = (await db.execute(
        select(ProjectionRun).where(ProjectionRun.tenant_id == tenant_id,
                                    ProjectionRun.mode == "APPLY")
        .order_by(ProjectionRun.id.desc()).limit(1))).scalars().first()
    if run is None or run.degraded or run.finished_at is None:
        return None
    services = (await db.execute(select(LifeSafetyService).where(
        LifeSafetyService.tenant_id == tenant_id,
        LifeSafetyService.last_projection_run_id == run.id))).scalars().all()
    conns = (await db.execute(select(LifeSafetyConnection).where(
        LifeSafetyConnection.tenant_id == tenant_id,
        LifeSafetyConnection.last_projection_run_id == run.id,
        LifeSafetyConnection.requirement == V.REQUIRED))).scalars().all()
    paths = Counter(c.service_id for c in conns)
    conn_service = {c.id: c.service_id for c in conns}
    phone_by_service = {}
    if conns:
        links = (await db.execute(select(ConnectionAssetLink).where(
            ConnectionAssetLink.tenant_id == tenant_id,
            ConnectionAssetLink.connection_id.in_(list(conn_service)),
            ConnectionAssetLink.active.is_(True),
            ConnectionAssetLink.relationship == V.REL_CARRIER_LINE))).scalars().all()
        asset_ids = {ln.asset_id for ln in links}
        tel = {}
        if asset_ids:
            tel = {a.id: a.normalized_value for a in (await db.execute(
                select(CommunicationsAsset).where(
                    CommunicationsAsset.tenant_id == tenant_id,
                    CommunicationsAsset.id.in_(list(asset_ids)),
                    CommunicationsAsset.asset_type == V.TELEPHONE_NUMBER))).scalars().all()}
        for ln in sorted(links, key=lambda x: x.id):
            if ln.asset_id in tel:
                phone_by_service.setdefault(conn_service[ln.connection_id], tel[ln.asset_id])
    suspect = set()
    for d in (await db.execute(select(OperatorDecision).where(
            OperatorDecision.tenant_id == tenant_id,
            OperatorDecision.decision_type == V.D_BUILDING_IDENTITY_SUSPECT,
            OperatorDecision.superseded_by_id.is_(None)))).scalars().all():
        try:
            subj, state = json.loads(d.subject or "{}"), json.loads(d.new_state or "{}")
        except ValueError:
            continue
        if state.get("suspect") and subj.get("building_id") is not None:
            suspect.add(int(subj["building_id"]))
    by_building = defaultdict(list)
    for s in services:
        by_building[s.building_id].append({
            "id": s.id, "service_type": s.service_type, "display_name": s.display_name,
            "confidence": s.confidence, "approval": s.approval, "lifecycle": s.lifecycle,
            "required_paths": paths.get(s.id, 0), "telephone": phone_by_service.get(s.id)})
    return {"run_id": run.id, "as_of": run.finished_at.isoformat() if run.finished_at else None,
            "by_building": dict(by_building), "suspect": suspect}


def classify(svc: dict) -> str:
    """READY (subject to the building's eligibility), FINALIZING, or EXCLUDED."""
    if svc["approval"] == V.REJECTED or svc["lifecycle"] in V.NOT_CURRENT:
        return "EXCLUDED"                          # rejected / historical: never shown
    if (svc["service_type"] in V.LIFE_SAFETY_TYPES
            and (svc["confidence"] == V.CONFIRMED or svc["approval"] == V.APPROVED)
            and svc["lifecycle"] == V.CURRENT and svc["required_paths"] >= 1):
        return READY
    return "FINALIZING"


def _format_phone(n):
    from app.services.customer.self_service import format_phone
    return format_phone(n)


def _service_dto(svc: dict) -> dict:
    from app.services.customer.serialize import customer_name
    label = SERVICE_LABEL[svc["service_type"]]
    return {
        "service_ref": encode_ref("lss", svc["id"]),
        "service": label,
        "name": customer_name(svc.get("display_name"), label),
        # requirements, not provisioned paths: never a number / IP / path name
        "required_paths": svc["required_paths"],
        "telephone_number": (_format_phone(svc["telephone"])
                             if svc["service_type"] in _NUMBERED and svc.get("telephone")
                             else None),
    }


def building_inventory(inv: dict, building_id, *, approved: bool, active: bool,
                       pending: bool) -> dict:
    """Customer-safe service-inventory block for one building."""
    eligible = (approved and active and not pending
                and building_id not in inv.get("suspect", set()))
    ready, finalizing = [], False
    for svc in inv["by_building"].get(building_id, []):
        c = classify(svc)
        if c == READY and eligible:
            ready.append(_service_dto(svc))
        elif c != "EXCLUDED":
            finalizing = True
    if ready and finalizing:
        state = PARTIALLY_READY
    elif ready:
        state = READY
    elif finalizing:
        state = BEING_FINALIZED
    else:
        state = NO_SERVICES
    ready.sort(key=lambda s: (s["service"], s["name"] or ""))
    return {"state": state, "message": MESSAGES[state], "ready_services": ready,
            "as_of": inv.get("as_of")}


def portfolio_inventory(blocks: list[dict], as_of=None) -> dict:
    """Portfolio roll-up: location counts per state and READY-service counts by
    type.  Deliberately NO service grand total, NO connection total and NO count
    of probable / unresolved records."""
    states = Counter(b["state"] for b in blocks)
    by_type = Counter(s["service"] for b in blocks for s in b["ready_services"])
    return {
        "locations_total": len(blocks),
        "locations_ready": states.get(READY, 0),
        "locations_partially_ready": states.get(PARTIALLY_READY, 0),
        "locations_being_finalized": states.get(BEING_FINALIZED, 0),
        "locations_no_services_on_record": states.get(NO_SERVICES, 0),
        "ready_services_by_type": [{"service": k, "count": v}
                                   for k, v in sorted(by_type.items())],
        "records_being_finalized": any(b["state"] in (PARTIALLY_READY, BEING_FINALIZED)
                                       for b in blocks),
        "as_of": as_of if as_of is not None else next(
            (b.get("as_of") for b in blocks if b.get("as_of")), None),
    }
