"""Customer retirement planner (DRY-RUN-FIRST, flag-gated, customer-scoped).

Produces — and, only when explicitly authorized, applies — a retirement plan for
ONE customer: setting the customer / its sites / devices / lines to retired
statuses and marking its Zoho ``external_record_map`` rows ``retired``. Built for
Webber Infra: Zoho shows all subscriptions De-activated and every True911 asset is
stale (no heartbeat/network event/call/telemetry), yet the customer is still
``active``.

Hard safety contract:
  * DRY-RUN by default — prints the exact field changes and writes NOTHING.
  * APPLY (writes) requires ALL of: ``--apply`` AND ``FEATURE_CUSTOMER_RETIREMENT
    =true`` AND the safety gates pass.
  * Gate 1 — Zoho lifecycle: every Zoho subscription for the customer must derive
    to ``deactivated`` (none active).
  * Gate 2 — no live assets: no device/line may show liveness within the window
    (heartbeat / network event / call / telemetry).
  * Strictly CUSTOMER-SCOPED (reuses the reconciliation customer scoper) — never
    touches another customer.
  * NEVER deletes. Only updates status / map_status fields. Every change is
    audit-logged.

Run:
    python -m app.plan_customer_retirement --customer "Webber Infra"            # dry run
    FEATURE_CUSTOMER_RETIREMENT=true \
      python -m app.plan_customer_retirement --customer "Webber Infra" --apply  # apply
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as _dt
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.audit_zoho_true911_customer_reconciliation import (  # noqa: E402
    derive_zoho_lifecycle, scope_true911_by_customer, name_matches,
    _load_zoho_records,
)
from app.audit_asset_liveness import _most_recent  # noqa: E402

ACTIVE_DAYS = 30

# Target retirement statuses per entity (current -> proposed).
RETIRE_CUSTOMER = "inactive"
RETIRE_SITE = "decommissioned"
RETIRE_DEVICE = "decommissioned"
RETIRE_LINE = "disconnected"
RETIRE_MAP = "retired"

CHANGE_FIELDS = ("entity_type", "entity_id", "field", "current", "proposed")


# ── pure planning + gates (unit-tested, no DB) ───────────────────────────
def _flag_on(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def feature_enabled() -> bool:
    return _flag_on(settings.FEATURE_CUSTOMER_RETIREMENT)


def _chg(entity_type, entity_id, field, current, proposed) -> dict:
    return {"entity_type": entity_type, "entity_id": entity_id, "field": field,
            "current": current, "proposed": proposed}


def _is_live(asset: dict, now: _dt.datetime, active_days: int = ACTIVE_DAYS) -> bool:
    last = _most_recent(asset.get("last_heartbeat"), asset.get("last_network_event"),
                        asset.get("last_call_at"), asset.get("last_telemetry_at"))
    return last is not None and (now - last).days <= active_days


def build_retirement_plan(*, customer: dict, sites: list[dict], devices: list[dict],
                          lines: list[dict], record_maps: list[dict],
                          zoho_records: list[dict], now: _dt.datetime) -> dict:
    """Pure: compute the proposed changes + safety gates. No DB, no I/O."""
    changes: list[dict] = []
    if customer and (customer.get("status") or "").strip().lower() != RETIRE_CUSTOMER:
        changes.append(_chg("customer", customer.get("id"), "status",
                            customer.get("status"), RETIRE_CUSTOMER))
    for s in sites:
        if (s.get("status") or "").strip().lower() != RETIRE_SITE:
            changes.append(_chg("site", s.get("site_id"), "status", s.get("status"), RETIRE_SITE))
    for d in devices:
        if (d.get("status") or "").strip().lower() != RETIRE_DEVICE:
            changes.append(_chg("device", d.get("device_id"), "status", d.get("status"), RETIRE_DEVICE))
    for l in lines:
        if (l.get("status") or "").strip().lower() != RETIRE_LINE:
            changes.append(_chg("line", l.get("line_id"), "status", l.get("status"), RETIRE_LINE))
    for m in record_maps:
        if (m.get("map_status") or "").strip().lower() not in ("confirmed", RETIRE_MAP):
            changes.append(_chg("external_record_map", m.get("id"), "map_status",
                                m.get("map_status"), RETIRE_MAP))

    # ── safety gates ──
    zoho_states = [derive_zoho_lifecycle(z) for z in zoho_records]
    zoho_deactivated = bool(zoho_states) and all(s == "deactivated" for s in zoho_states)
    live_assets = [a for a in (devices + lines) if _is_live(a, now)]
    no_active_liveness = not live_assets
    customer_resolved = bool(customer and customer.get("id") is not None)

    safe = zoho_deactivated and no_active_liveness and customer_resolved
    blockers = []
    if not customer_resolved:
        blockers.append("customer not resolved")
    if not zoho_deactivated:
        blockers.append(f"Zoho lifecycle not all deactivated (states={zoho_states})")
    if not no_active_liveness:
        blockers.append("assets with recent liveness: "
                        + ", ".join(str(a.get("device_id") or a.get("line_id")) for a in live_assets))

    return {
        "customer": customer,
        "changes": changes,
        "gates": {"zoho_deactivated": zoho_deactivated,
                  "no_active_liveness": no_active_liveness,
                  "customer_resolved": customer_resolved,
                  "zoho_states": zoho_states},
        "safe_to_apply": safe,
        "blockers": blockers,
    }


def should_apply(apply_requested: bool, plan: dict) -> bool:
    """Write ONLY when requested AND the feature flag is on AND gates pass."""
    return bool(apply_requested) and feature_enabled() and bool(plan.get("safe_to_apply"))


# ── export ───────────────────────────────────────────────────────────────
def write_json(plan: dict, applied: bool, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"applied": applied, "safe_to_apply": plan["safe_to_apply"],
                   "blockers": plan["blockers"], "gates": plan["gates"],
                   "customer": plan["customer"], "changes": plan["changes"]},
                  fh, indent=2, ensure_ascii=False, default=str)


def write_csv(plan: dict, path: str) -> int:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CHANGE_FIELDS), extrasaction="ignore")
        w.writeheader()
        for c in plan["changes"]:
            w.writerow(c)
    return len(plan["changes"])


# ── DB load (READ-ONLY) ──────────────────────────────────────────────────
async def _load_customer_scope(db, query: str, now: _dt.datetime) -> dict:
    from sqlalchemy import select, text
    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.device import Device
    from app.models.line import Line
    from app.models.external_record_map import ExternalRecordMap

    customers = [{"id": c.id, "name": c.name, "status": c.status, "tenant_id": c.tenant_id,
                  "zoho_account_id": c.zoho_account_id, "onboarding_status": c.onboarding_status}
                 for c in (await db.execute(select(Customer))).scalars().all()]
    matched = [c for c in customers if name_matches(query, c["name"])]
    if not matched:
        return {"customer": {}, "sites": [], "devices": [], "lines": [],
                "record_maps": [], "matched_ids": []}
    tenant_ids = {c["tenant_id"] for c in matched}
    sites = [{"site_id": s.site_id, "site_name": s.site_name, "status": s.status,
              "customer_id": s.customer_id, "tenant_id": s.tenant_id}
             for s in (await db.execute(select(Site).where(Site.tenant_id.in_(tenant_ids)))).scalars().all()]
    devices = [{"device_id": d.device_id, "site_id": d.site_id, "status": d.status,
                "msisdn": d.msisdn, "tenant_id": d.tenant_id,
                "last_heartbeat": d.last_heartbeat, "last_network_event": d.last_network_event}
               for d in (await db.execute(select(Device).where(Device.tenant_id.in_(tenant_ids)))).scalars().all()]
    lines = [{"line_id": l.line_id, "site_id": l.site_id, "status": l.status, "did": l.did,
              "customer_id": l.customer_id, "tenant_id": l.tenant_id}
             for l in (await db.execute(select(Line).where(Line.tenant_id.in_(tenant_ids)))).scalars().all()]

    scoped = scope_true911_by_customer(query, customers, sites, devices, lines)

    # Best-effort liveness signals (call/telemetry) per scoped device.
    dev_ids = [d["device_id"] for d in scoped["devices"]]
    if dev_ids:
        for d in scoped["devices"]:
            d["last_call_at"] = await _best_effort_scalar(
                db, "SELECT max(started_at) FROM call_records WHERE device_id = :d", {"d": d["device_id"]})
            d["last_telemetry_at"] = await _best_effort_scalar(
                db, "SELECT max(recorded_at) FROM command_telemetry WHERE device_id = :d", {"d": d["device_id"]})

    # external_record_map rows for this customer's Zoho subscriptions.
    zoho = await _load_zoho_records(db, query)
    sub_ids = [z["subscription_mgmt_id"] for z in zoho if z.get("subscription_mgmt_id")]
    record_maps = []
    if sub_ids:
        rms = (await db.execute(select(ExternalRecordMap).where(
            ExternalRecordMap.external_record_id.in_(sub_ids)))).scalars().all()
        record_maps = [{"id": m.id, "external_record_id": m.external_record_id,
                        "map_status": m.map_status, "org_id": m.org_id} for m in rms]

    return {"customer": scoped["customer"] | {"id": matched[0]["id"]},
            "sites": scoped["sites"], "devices": scoped["devices"], "lines": scoped["lines"],
            "record_maps": record_maps, "zoho": zoho,
            "matched_ids": scoped.get("matched_customer_ids", [])}


async def _best_effort_scalar(db, sql, params):
    from sqlalchemy import text
    try:
        return (await db.execute(text(sql), params)).scalar()
    except Exception:
        return None


# ── apply (WRITE — gated; never deletes) ──────────────────────────────────
async def _apply_changes(db, plan: dict, actor: str) -> int:
    from sqlalchemy import select
    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.device import Device
    from app.models.line import Line
    from app.models.external_record_map import ExternalRecordMap
    from app.services.audit_logger import log_audit

    model_key = {
        "customer": (Customer, "id"), "site": (Site, "site_id"),
        "device": (Device, "device_id"), "line": (Line, "line_id"),
        "external_record_map": (ExternalRecordMap, "id"),
    }
    tenant_id = (plan["customer"] or {}).get("tenant_id") or "default"
    applied = 0
    for ch in plan["changes"]:
        model, key = model_key[ch["entity_type"]]
        obj = (await db.execute(
            select(model).where(getattr(model, key) == ch["entity_id"]))).scalar_one_or_none()
        if obj is None:
            continue
        setattr(obj, ch["field"], ch["proposed"])   # status / map_status only — never a delete
        applied += 1
        await log_audit(
            db, tenant_id, "customer_lifecycle", "retire",
            f"Retire {ch['entity_type']} {ch['entity_id']}: {ch['field']} "
            f"{ch['current']!r} -> {ch['proposed']!r}",
            actor=actor, target_type=ch["entity_type"], target_id=str(ch["entity_id"]),
            detail={"field": ch["field"], "from": ch["current"], "to": ch["proposed"]})
    await db.commit()
    return applied


# ── report ───────────────────────────────────────────────────────────────
def _print(plan: dict, customer_q: str, applied: Optional[int]) -> None:
    print("=" * 78)
    mode = (f"APPLIED ({applied} changes)" if applied is not None
            else "DRY RUN (no writes)")
    print(f"Customer Retirement Plan — {customer_q}  —  {mode}")
    print("=" * 78)
    c = plan["customer"] or {}
    print(f"  customer={c.get('name')!r} id={c.get('id')} status={c.get('status')!r} "
          f"tenant={c.get('tenant_id')}")
    g = plan["gates"]
    print(f"  GATES: zoho_deactivated={g['zoho_deactivated']} "
          f"no_active_liveness={g['no_active_liveness']} "
          f"customer_resolved={g['customer_resolved']}  -> safe_to_apply={plan['safe_to_apply']}")
    if plan["blockers"]:
        for b in plan["blockers"]:
            print(f"    ✗ BLOCKER: {b}")
    print(f"\n  PROPOSED CHANGES ({len(plan['changes'])}):")
    for ch in plan["changes"]:
        print(f"    {ch['entity_type']:<20} {str(ch['entity_id']):<22} "
              f"{ch['field']}: {ch['current']!r} -> {ch['proposed']!r}")
    if applied is None:
        print("\n  DRY RUN — nothing written. Apply needs --apply + "
              "FEATURE_CUSTOMER_RETIREMENT=true + passing gates.")
    print("\n  (Customer-scoped; never deletes.)")


async def run(customer_q: str, *, apply_requested: bool,
              export_json: Optional[str] = None, export_csv: Optional[str] = None,
              actor: str = "plan_customer_retirement") -> dict:
    from app.database import AsyncSessionLocal
    now = _dt.datetime.now(_dt.timezone.utc)

    async with AsyncSessionLocal() as db:
        scope = await _load_customer_scope(db, customer_q, now)
        plan = build_retirement_plan(
            customer=scope.get("customer") or {}, sites=scope.get("sites", []),
            devices=scope.get("devices", []), lines=scope.get("lines", []),
            record_maps=scope.get("record_maps", []), zoho_records=scope.get("zoho", []),
            now=now)

        applied = None
        if apply_requested:
            if not feature_enabled():
                print("REFUSED: FEATURE_CUSTOMER_RETIREMENT is not true — running DRY RUN.\n")
            elif not plan["safe_to_apply"]:
                print("REFUSED: safety gates not satisfied — running DRY RUN.\n")
            elif should_apply(apply_requested, plan):
                applied = await _apply_changes(db, plan, actor)

    _print(plan, customer_q, applied)
    if export_json:
        write_json(plan, applied is not None, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(plan, export_csv)
        print(f"  Wrote {n} change rows (CSV) -> {export_csv}")
    return {"plan": plan, "applied": applied}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run-first customer retirement planner.")
    parser.add_argument("--customer", required=True, help="customer name (e.g. 'Webber Infra')")
    parser.add_argument("--apply", action="store_true",
                        help="WRITE (requires FEATURE_CUSTOMER_RETIREMENT=true + passing gates)")
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    parser.add_argument("--actor", default=os.environ.get("RETIRE_ACTOR", "plan_customer_retirement"))
    args = parser.parse_args()
    try:
        asyncio.run(run(args.customer, apply_requested=args.apply,
                        export_json=args.export_json, export_csv=args.export_csv,
                        actor=args.actor))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: retirement planner aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
