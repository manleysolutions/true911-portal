"""Read-only snapshot builder for canonical reconciliation (D-023, Decision 4).

SELECT-only against the True911 database and GET-only against Zoho CRM
(``Subscription_Mgmnt``, live at run time).  Every source carries retrieval
metadata; a required source that fails is reported with its status and marks
the run DEGRADED - its data is never silently replaced with stale data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import select

from app.services.canonical import decisions as D

ZOHO_MODULE = "Subscription_Mgmnt"
ZOHO_MAX_PAGES = 300
_FIELD_TOKENS = ("imei", "sim", "iccid", "starlink", "radio", "facility", "serial",
                 "carrier", "created", "activ")


def _now():
    return datetime.now(timezone.utc)


async def fetch_zoho_rows(row_filter: Callable[..., bool]) -> tuple[list[dict], dict]:
    """Live, read-only pull of the subscription module.  ``row_filter(account,
    parent, facility)`` keeps only this tenant's rows.  -> (rows, source info)."""
    info = {"system": "zoho_crm", "module": ZOHO_MODULE, "required": True,
            "requested_at": _now().isoformat()}
    try:
        from app.backfill_zoho_subscription_staging import DEFAULT_FIELDS
        from app.services import zoho_crm
        if not zoho_crm.is_configured():
            info["status"] = "not configured in this environment"
            return [], info
        fields = list(DEFAULT_FIELDS)
        try:
            meta = await zoho_crm._zoho_get("/settings/fields", params={"module": ZOHO_MODULE})
            for f in meta.get("fields") or []:
                api = f.get("api_name") or ""
                if any(t in api.lower() for t in _FIELD_TOKENS) and api not in fields:
                    fields.append(api)
        except Exception as exc:            # field discovery is optional
            info["field_discovery"] = "failed: %s" % str(exc)[:120]
        fields = fields[:50]
        raw, token, page = [], None, 1
        for _ in range(ZOHO_MAX_PAGES):
            params = {"per_page": 200, "fields": ",".join(fields)}
            if token:
                params["page_token"] = token
            else:
                params["page"] = page
            try:
                data = await zoho_crm._zoho_get("/" + ZOHO_MODULE, params=params)
            except Exception as exc:
                if "204" in str(exc)[:40]:
                    break
                raise
            recs = data.get("data") or []
            raw.extend(recs)
            more = data.get("info") or {}
            if not recs:
                break
            if more.get("next_page_token"):
                token = more["next_page_token"]
            elif more.get("more_records") and not token:
                page += 1
            else:
                break
    except Exception as exc:
        info["status"] = "unavailable: %s" % str(exc)[:160]
        return [], info

    def look(rec, *keys):
        for k in keys:
            v = rec.get(k)
            if isinstance(v, dict):
                v = v.get("name")
            if v not in (None, "") and not isinstance(v, list):
                return str(v).strip()
        return None

    def look_like(rec, *tokens):
        for k, v in rec.items():
            if isinstance(v, (dict, list)) or v in (None, ""):
                continue
            if any(t in k.lower() for t in tokens):
                return str(v).strip()
        return None

    rows = []
    for r in raw:
        acct, parent = look(r, "Account", "Account_Name"), look(r, "Parent_Account")
        fac = look(r, "FacilityName", "Facility_Name")
        if not row_filter(acct, parent, fac):
            continue
        rows.append({
            "zoho_id": look(r, "id"), "account": acct, "parent": parent, "facility": fac,
            "msisdn": look(r, "MSISDN", "Mobile_Number"),
            "connection_type": look(r, "Connection_Type"),
            "subscription_type": look(r, "Subscription_Type"),
            "activation": look(r, "Device_Activation_Status"),
            "created": look(r, "Created_Time"), "modified": look(r, "Modified_Time"),
            "imei": look_like(r, "imei"), "sim": look_like(r, "iccid", "sim_n", "sim_i", "sim"),
            "starlink": look_like(r, "starlink", "radio"), "serial": look_like(r, "serial"),
        })
    info.update(status="ok", retrieved_at=_now().isoformat(), scanned=len(raw),
                tenant_rows=len(rows), fields=len(fields))
    return rows, info


async def build_snapshot(db, tenant_id: str, *, zoho: str = "live",
                         zoho_filter: Optional[Callable[..., bool]] = None,
                         zoho_rows: Optional[list] = None,
                         proposed_decisions: Optional[list] = None,
                         generic_names: tuple = ()) -> dict:
    """Assemble the engine snapshot.  ``zoho``: "live" (read-only GETs),
    "rows" (use ``zoho_rows`` - fixtures/tests), or "skip" (not consulted:
    reported as a required source that was skipped -> degraded)."""
    from app.models.action_audit import ActionAudit
    from app.models.device import Device
    from app.models.line import Line
    from app.models.portfolio_registry import (
        PortfolioAlias,
        PortfolioBuilding,
        PortfolioDeviceMapping,
        PortfolioReviewItem,
    )
    from app.models.service_unit import ServiceUnit
    from app.models.site import Site
    from app.services.customer import service_inference as si

    async def rows(model, *where):
        q = select(model).where(model.tenant_id == tenant_id, *where)
        return (await db.execute(q)).scalars().all()

    started = _now()
    buildings = [{"id": b.id, "name": b.canonical_name, "store_number": b.store_number,
                  "address": b.address, "city": b.city, "state": b.state}
                 for b in await rows(PortfolioBuilding, PortfolioBuilding.approved.is_(True))]
    bids = {b["id"] for b in buildings}
    aliases = [{"building_id": a.building_id, "alias": a.alias}
               for a in await rows(PortfolioAlias) if a.active and a.building_id in bids]
    mappings = [{"id": m.id, "building_id": m.building_id, "kind": m.kind, "value": m.value}
                for m in await rows(PortfolioDeviceMapping) if m.active and m.building_id in bids]
    fused = []
    for it in await rows(PortfolioReviewItem, PortfolioReviewItem.status == "approved"):
        try:
            cand = json.loads(it.payload) if it.payload else None
        except (TypeError, ValueError):
            continue
        for dv in (cand.get("devices") or []) if isinstance(cand, dict) else []:
            ids = [dv.get(k) for k in ("radio_number", "starlink_id", "serial", "iccid",
                                       "imei", "msisdn") if dv.get(k)]
            if len(ids) > 1:
                fused.append([str(i) for i in ids])
    overrides = {}
    q = select(ActionAudit).where(ActionAudit.tenant_id == tenant_id,
                                  ActionAudit.action_type == si.OVERRIDE_ACTION)
    for a in (await db.execute(q.order_by(ActionAudit.id))).scalars().all():
        try:
            dd = json.loads(a.details or "{}")
        except ValueError:
            continue
        if dd.get("device_id") and dd.get("service_type"):
            overrides[dd["device_id"]] = dd["service_type"]
    sites = [{"site_id": s.site_id, "site_name": s.site_name, "status": s.status,
              "street": s.e911_street, "city": s.e911_city, "state": s.e911_state}
             for s in await rows(Site)]
    devices = [{"device_id": d.device_id, "site_id": d.site_id, "status": d.status,
                "device_type": d.device_type, "model": d.model, "manufacturer": d.manufacturer,
                "identifier_type": d.identifier_type, "msisdn": d.msisdn, "iccid": d.iccid,
                "imei": d.imei, "serial": d.serial_number, "starlink_id": d.starlink_id,
                "notes": d.notes, "carrier": d.carrier, "last_heartbeat": d.last_heartbeat,
                "override_service_type": overrides.get(d.device_id)}
               for d in await rows(Device)]
    lines = [{"line_id": ln.line_id, "device_id": ln.device_id, "site_id": ln.site_id,
              "did": ln.did, "status": ln.status, "line_type": ln.line_type,
              "description": ln.qb_description, "notes": ln.notes, "carrier": ln.carrier}
             for ln in await rows(Line)]
    units = [{"unit_id": u.unit_id, "device_id": u.device_id, "line_id": u.line_id,
              "unit_type": u.unit_type, "unit_name": u.unit_name, "status": u.status}
             for u in await rows(ServiceUnit)]
    active = await D.load_active(db, tenant_id)
    decisions = D.overlay(active, proposed_decisions or [])

    sources = {"true911": {"system": "true911_db", "required": True, "status": "ok",
                           "retrieved_at": _now().isoformat(),
                           "counts": {"buildings": len(buildings), "sites": len(sites),
                                      "devices": len(devices), "lines": len(lines),
                                      "units": len(units), "mappings": len(mappings)}}}
    if zoho == "live":
        if zoho_filter is None:
            raise ValueError("a Zoho row filter is required for a live pull (tenant scoping)")
        zrows, sources["zoho"] = await fetch_zoho_rows(zoho_filter)
    elif zoho == "rows":
        zrows = list(zoho_rows or [])
        sources["zoho"] = {"system": "zoho_crm", "required": True, "status": "ok",
                           "retrieved_at": _now().isoformat(), "mode": "supplied rows",
                           "tenant_rows": len(zrows)}
    else:
        zrows = []
        sources["zoho"] = {"system": "zoho_crm", "required": True, "status": "skipped"}
    sources["operator_decisions"] = {"system": "true911_db", "required": False, "status": "ok",
                                     "active": len(active),
                                     "proposed_preview": len(proposed_decisions or [])}
    return {"tenant_id": tenant_id, "started_at": started, "buildings": buildings,
            "aliases": aliases, "mappings": mappings, "fused_groups": fused, "sites": sites,
            "devices": devices, "lines": lines, "units": units, "zoho_rows": zrows,
            "decisions": decisions, "sources": sources, "generic_names": list(generic_names)}
