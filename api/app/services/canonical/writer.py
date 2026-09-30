"""Persist a canonical projection (D-023) - ONLY under an explicit ``--apply``.

Idempotent upserts on natural keys; NEVER deletes.  Rows a later run no longer
produces keep their older ``last_projection_run_id`` (identifiable as stale);
connections of a service that no longer qualifies are kept and marked
NOT_REQUIRED; superseded asset links are marked inactive.  Evidence and the
run record are append-only.  Touches only the eight canonical tables - never
registry, site, device, line, E911 or any external system.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.canonical import (
    AssetLifecycleEvent,
    CanonicalEvidence,
    CommunicationsAsset,
    ConnectionAssetLink,
    LifeSafetyConnection,
    LifeSafetyService,
    ProjectionRun,
)
from app.services.canonical import vocab as V


class DegradedProjectionError(RuntimeError):
    pass


def _dt(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _json(v) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def is_degraded(result: dict) -> bool:
    """A projection is degraded when the engine said so OR any required source
    did not report ``ok`` - re-derived here so a caller cannot launder it."""
    if result.get("degraded"):
        return True
    return any(s.get("required") and s.get("status") != "ok"
               for s in (result.get("sources") or {}).values())


async def apply_projection(db, result: dict, *, run_by: str) -> int:
    """Write ``result`` (from ``engine.project``).  Returns the ProjectionRun id.
    ALWAYS refuses a degraded projection - there is no override: a projection
    built without a required source is never persisted."""
    if is_degraded(result):
        raise DegradedProjectionError(
            "projection is DEGRADED (a required source was unavailable) - refusing to apply; "
            "degraded projections are never persisted")
    tenant = result["tenant_id"]
    now = datetime.now(timezone.utc)
    run = ProjectionRun(tenant_id=tenant, mode="APPLY", run_by=run_by, started_at=now,
                        sources=_json(result["sources"]),
                        summary=_json({"portfolio": result["portfolio"],
                                       "findings": result["findings"]}),
                        degraded=bool(result["degraded"]))
    db.add(run)
    await db.flush()
    rid = run.id

    def evidence(subject_type, subject_key, source, etype, *, record=None, conf=None,
                 observed=None, payload=None):
        db.add(CanonicalEvidence(
            tenant_id=tenant, projection_run_id=rid, subject_type=subject_type,
            subject_key=subject_key[:200], source=source, source_record_id=record,
            evidence_type=etype[:60], confidence=conf, observed_at=_dt(observed),
            payload=_json(payload) if payload is not None else None))

    # lifecycle events (one per operator decision)
    event_ids = {}
    for ev in result["lifecycle_events"]:
        row = None
        if ev.get("decision_id") is not None:
            row = (await db.execute(select(AssetLifecycleEvent).where(
                AssetLifecycleEvent.tenant_id == tenant,
                AssetLifecycleEvent.operator_decision_id == ev["decision_id"]))).scalars().first()
        if row is None:
            row = AssetLifecycleEvent(
                tenant_id=tenant, building_id=ev["building_id"], event_type=ev["event_type"],
                effective_at=_dt(ev.get("effective_at")),
                description="%s: %d legacy -> %d replacement lines. %s" % (
                    ev["event_type"], len(ev["legacy"]), len(ev["replacement"]),
                    ev.get("reason") or ""),
                source=V.SRC_OPERATOR, operator_decision_id=ev.get("decision_id"))
            db.add(row)
            await db.flush()
        event_ids[ev["decision_key"]] = row.id

    # assets
    asset_ids = {}
    for a in result["assets"].values():
        row = (await db.execute(select(CommunicationsAsset).where(
            CommunicationsAsset.tenant_id == tenant,
            CommunicationsAsset.asset_type == a["asset_type"],
            CommunicationsAsset.normalized_value == a["normalized_value"]))).scalars().first()
        if row is None:
            row = CommunicationsAsset(tenant_id=tenant, asset_type=a["asset_type"],
                                      normalized_value=a["normalized_value"])
            db.add(row)
        row.display_value = a["display_value"]
        row.carrier = a.get("carrier")
        row.lifecycle = a["lifecycle"]
        row.lifecycle_reason = a.get("lifecycle_reason")
        row.lifecycle_source = a.get("lifecycle_source")
        row.effective_from = _dt(a.get("effective_from"))
        row.effective_to = _dt(a.get("effective_to"))
        row.lifecycle_event_id = event_ids.get(a.get("lifecycle_event_key"))
        row.building_id = a["building_id"]
        row.placement_confidence = a["placement_confidence"]
        row.placement_basis = a["placement_basis"]
        srcs = sorted({r["source"] for r in a["records"]})
        row.source = srcs[0] if len(srcs) == 1 else ("MULTIPLE" if srcs else V.SRC_OPERATOR)
        row.source_record_id = a["records"][0]["rid"][:120] if a["records"] else None
        row.last_projection_run_id = rid
        await db.flush()
        asset_ids[a["key"]] = row.id
        for r in a["records"]:
            p = r["placement"]
            evidence("ASSET", a["key"], r["source"], "PLACEMENT:%s" % p["basis"],
                     record=r["rid"][:120], conf=p["confidence"], observed=r.get("observed_at"),
                     payload={"note": p["note"], "status": r.get("status")})
        if a.get("lifecycle_source"):
            evidence("ASSET", a["key"], a["lifecycle_source"], "LIFECYCLE:%s" % a["lifecycle"],
                     payload={"reason": a.get("lifecycle_reason")})

    # services, connections, links
    for s in result["services"]:
        row = (await db.execute(select(LifeSafetyService).where(
            LifeSafetyService.tenant_id == tenant,
            LifeSafetyService.building_id == s["building_id"],
            LifeSafetyService.service_key == s["service_key"]))).scalars().first()
        if row is None:
            row = LifeSafetyService(tenant_id=tenant, building_id=s["building_id"],
                                    service_key=s["service_key"])
            db.add(row)
        row.service_type = s["service_type"]
        row.display_name = s["display_name"]
        row.confidence = s["confidence"]
        row.approval = s["approval"]
        row.lifecycle = s["lifecycle"]
        row.lifecycle_reason = s.get("lifecycle_reason")
        row.source_summary = _json(s["evidence"])[:4000]
        row.last_projection_run_id = rid
        await db.flush()
        evidence("SERVICE", s["service_key"], "ENGINE", "SERVICE:%s" % s["service_type"],
                 conf=s["confidence"], payload={"evidence": s["evidence"],
                                                "approval": s["approval"]})
        wanted = {c["ordinal"]: c for c in result["connections"]
                  if c["building_id"] == s["building_id"] and c["service_key"] == s["service_key"]}
        existing = {c.ordinal: c for c in (await db.execute(select(LifeSafetyConnection).where(
            LifeSafetyConnection.service_id == row.id))).scalars().all()}
        for ordinal, conn in existing.items():
            if ordinal not in wanted:
                conn.requirement = V.NOT_REQUIRED
                conn.last_projection_run_id = rid
        for ordinal, c in wanted.items():
            conn = existing.get(ordinal)
            if conn is None:
                conn = LifeSafetyConnection(tenant_id=tenant, service_id=row.id, ordinal=ordinal)
                db.add(conn)
            conn.connection_type = c["connection_type"]
            conn.requirement = c["requirement"]
            conn.provisioning = c["provisioning"]
            conn.confidence = c["confidence"]
            conn.last_projection_run_id = rid
            await db.flush()
            want_links = {(asset_ids[k], rel) for k, rel in c["links"] if k in asset_ids}
            have = (await db.execute(select(ConnectionAssetLink).where(
                ConnectionAssetLink.connection_id == conn.id))).scalars().all()
            for ln in have:
                ln.active = (ln.asset_id, ln.relationship) in want_links
            have_keys = {(ln.asset_id, ln.relationship) for ln in have}
            for aid, rel in sorted(want_links - have_keys):
                db.add(ConnectionAssetLink(tenant_id=tenant, connection_id=conn.id,
                                           asset_id=aid, relationship=rel, active=True))

    # services this run no longer produces are kept (stale run id) but stop
    # requiring connections
    stale = (await db.execute(select(LifeSafetyService.id).where(
        LifeSafetyService.tenant_id == tenant,
        LifeSafetyService.last_projection_run_id != rid))).scalars().all()
    if stale:
        for conn in (await db.execute(select(LifeSafetyConnection).where(
                LifeSafetyConnection.service_id.in_(stale)))).scalars().all():
            if conn.requirement != V.NOT_REQUIRED:
                conn.requirement = V.NOT_REQUIRED
                conn.last_projection_run_id = rid

    for f in result["findings"]:
        evidence("FINDING", "%s:%s" % (f["code"], f["subject"]), "ENGINE", f["code"],
                 payload={"severity": f["severity"], "building": f["building"],
                          "detail": f["detail"]})
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    return rid
