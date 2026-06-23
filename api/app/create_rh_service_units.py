"""Restoration Hardware — service-unit creation tool (dry-run-first, approval-gated).

P3 of the RH readiness plan (docs/OPERATION_GREEN_RH.md,
docs/P3_SERVICE_UNIT_CREATION_SPEC.md). RH has 0 service units for 51 devices;
service units are the emergency endpoints the Assurance engine reasons about.

This tool creates ONE emergency service unit per device (1:1, device-anchored)
from an operator-reviewed plan file. It is dry-run-first, refusal-gated, and
**Stuart-approval-gated**, idempotent and re-runnable, fully rollback-able, and
audit-logged. It writes ONLY service-unit rows (never device/site/E911/status).

Safety / contract:
  * DRY_RUN defaults TRUE — nothing written unless DRY_RUN=false.
  * APPLY additionally requires RH_SU_APPROVED_BY (Stuart approval) — recorded in audit.
  * Each plan row must carry ``confirmed: true`` (operator sign-off) or it is refused.
  * unit_type must be a canonical ServiceUnit type (else refuse).
  * Unknown fields / unknown or duplicate device_id / unresolved site REFUSE the batch.
  * All-or-nothing: any refusal ⇒ nothing is written.
  * Idempotent: a device that already has a unit ⇒ no-op (deterministic unit_id).
  * No false green: a unit on a device with no fresh heartbeat is "pending_install".
  * Rollback (RH_SU_ROLLBACK_BATCH): reverse a batch (soft=decommission default,
    hard=delete), drift-guarded, idempotent, audit-logged.
  * Never touches another tenant.

Run:
    # Discovery — devices needing a unit + a plan template (read-only):
    python -m app.create_rh_service_units
    python -m app.create_rh_service_units --export /tmp/rh_units    # writes .json + .csv
    # Dry-run a reviewed plan:
    RH_SU_PLAN_FILE=rh_units.json python -m app.create_rh_service_units
    # Apply (Stuart-approved):
    DRY_RUN=false RH_SU_PLAN_FILE=rh_units.json \
        RH_SU_APPROVED_BY="stuart@manleysolutions.com" \
        RH_SU_ACTOR="stuart@manleysolutions.com" python -m app.create_rh_service_units
    # Rollback a batch (soft):
    RH_SU_ROLLBACK_BATCH=su-20260624-a1b2 DRY_RUN=false python -m app.create_rh_service_units
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.audit_rh_readiness import device_identifiers, infer_unit_type  # noqa: E402
from app.services.continuity import compute_device_computed_status  # noqa: E402

RH_TENANT = os.environ.get("RH_SU_TENANT", "restoration-hardware")
SOURCE = "create_rh_service_units"

CANONICAL_UNIT_TYPES = frozenset(
    {"elevator_phone", "fire_alarm", "emergency_call_station", "fax_line", "voice_line", "other"}
)
# infer_unit_type() emits non-canonical strings; normalize to the model enum.
_NORMALIZE = {
    "elevator_phone": "elevator_phone",
    "fire_alarm_line": "fire_alarm",
    "alarm_line": "fire_alarm",
    "emergency_call_station": "emergency_call_station",
    "fax_line": "fax_line",
    "emergency_voice_line": "voice_line",
}
ALLOWED_FIELDS = (
    "unit_type", "unit_name", "location_description", "floor", "install_type",
    "monitoring_station_type", "compliance_status", "confirmed", "confidence_override",
)


def _norm(v) -> str:
    return (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())


# ── Inference + confidence (pure) ────────────────────────────────────────
def infer_canonical_unit(device: dict) -> tuple[str, float, str]:
    """Return (canonical_unit_type, base_confidence, reason)."""
    model, dtype = device.get("model"), device.get("device_type")
    raw = infer_unit_type(model, dtype, device.get("endpoint_type"))
    canonical = _NORMALIZE.get(raw, "other")
    s = " ".join(x for x in (model, dtype) if x).lower()
    if canonical != "voice_line":
        return canonical, 0.9, f"strong cue → {canonical}"
    if any(c in s for c in ("pots", "ata", "analog")):
        return canonical, 0.6, "analog/ATA cue → voice line"
    return canonical, 0.3, "no strong cue — defaulted to voice line; specify type"


def score_confidence(base: float, *, location_present: bool, has_identifier: bool,
                     override=None) -> float:
    if override is not None:
        return max(0.0, min(1.0, float(override)))
    c = base
    if location_present:
        c += 0.05
    if not has_identifier:
        c = min(c, 0.4)
    return max(0.0, min(1.0, round(c, 2)))


def derive_status(device: dict) -> str:
    """active only when the device is reporting fresh (Online); else
    pending_install — so a unit on a non-reporting device never reads green."""
    computed = compute_device_computed_status(
        device.get("last_heartbeat"), device.get("heartbeat_interval"))
    return "active" if computed == "Online" else "pending_install"


# ── Pure planner ─────────────────────────────────────────────────────────
@dataclass
class ServiceUnitPlan:
    safe: bool = False
    creates: list = field(default_factory=list)   # full create dicts (§ apply)
    refusals: list = field(default_factory=list)
    noops: list = field(default_factory=list)      # device_ids already covered


def plan_service_units(plan_rows, devices_by_id, site_ids, covered_device_ids,
                       *, min_confidence) -> ServiceUnitPlan:
    refusals, creates, noops, seen = [], [], [], set()
    for row in plan_rows:
        did = _norm(row.get("device_id"))
        if not did:
            refusals.append("plan row missing device_id — refusing.")
            continue
        if did in seen:
            refusals.append(f"{did}: duplicate device_id in plan — refusing.")
            continue
        seen.add(did)
        unknown = [k for k in row if k != "device_id" and k not in ALLOWED_FIELDS]
        if unknown:
            refusals.append(f"{did}: unknown field(s) {unknown} — refusing.")
            continue
        device = devices_by_id.get(did)
        if device is None:
            refusals.append(f"{did}: not found in tenant '{RH_TENANT}' — refusing.")
            continue
        if did in covered_device_ids:
            noops.append(did)
            continue
        site_id = device.get("site_id")
        if not site_id or site_id not in site_ids:
            refusals.append(f"{did}: site {site_id!r} unresolved in tenant — refusing.")
            continue
        unit_type = _norm(row.get("unit_type"))
        if unit_type not in CANONICAL_UNIT_TYPES:
            refusals.append(f"{did}: unit_type {unit_type!r} not canonical — refusing.")
            continue
        if row.get("confirmed") is not True:
            refusals.append(f"{did}: not confirmed (confirmed:true required) — refusing.")
            continue

        _t, base, _r = infer_canonical_unit(device)
        conf = score_confidence(
            base,
            location_present=bool(_norm(row.get("location_description"))),
            has_identifier=bool(device_identifiers(device)),
            override=row.get("confidence_override"),
        )
        if conf < min_confidence:  # confirmed rows are still floored by the operator override
            refusals.append(f"{did}: confidence {conf} < min {min_confidence} — set confidence_override or correct data.")
            continue

        site_name = device.get("site_name") or site_id
        creates.append({
            "device_id": did,
            "unit_id": f"SU-{did}",
            "site_id": site_id,
            "unit_type": unit_type,
            "unit_name": _norm(row.get("unit_name")) or f"{site_name} — {unit_type.replace('_', ' ')}",
            "location_description": _norm(row.get("location_description")) or None,
            "floor": _norm(row.get("floor")) or None,
            "install_type": _norm(row.get("install_type")) or None,
            "compliance_status": _norm(row.get("compliance_status")) or "unknown",
            "status": derive_status(device),
            "confidence": conf,
        })

    return ServiceUnitPlan(
        safe=not refusals,
        creates=[] if refusals else creates,
        refusals=refusals,
        noops=noops,
    )


def apply_allowed(dry_run: bool, approver: str, plan: ServiceUnitPlan) -> tuple[bool, str]:
    """Pure apply-gate decision (DRY_RUN + Stuart approval + safe/non-empty)."""
    if not plan.safe:
        return False, "refused"
    if not plan.creates:
        return False, "nothing-to-create"
    if dry_run:
        return False, "dry-run"
    if not (approver or "").strip():
        return False, "approval-required"
    return True, "apply"


def build_unit_meta(create: dict, *, batch_id: str, actor: str, approver: str, now_iso: str) -> dict:
    return {
        "source": SOURCE, "batch_id": batch_id, "confidence": create["confidence"],
        "created_by": actor, "approved_by": approver, "created_at_iso": now_iso,
    }


# ── Rollback planner (pure) ──────────────────────────────────────────────
@dataclass
class RollbackPlan:
    safe: bool = False
    to_reverse: list = field(default_factory=list)
    refusals: list = field(default_factory=list)
    skipped_already: list = field(default_factory=list)


def plan_rollback(units, *, batch_id: str, epsilon_seconds: float = 2.0) -> RollbackPlan:
    """Select tool-created units in this batch; drift-guard against human edits;
    skip already-rolled-back (idempotent). All-or-nothing."""
    to_reverse, refusals, skipped = [], [], []
    for u in units:
        meta = getattr(u, "meta", None) or {}
        if meta.get("source") != SOURCE or meta.get("batch_id") != batch_id:
            continue
        if (getattr(u, "status", "") or "") == "decommissioned" and meta.get("rolled_back_at"):
            skipped.append(getattr(u, "unit_id", "?"))
            continue
        ca, ua = getattr(u, "created_at", None), getattr(u, "updated_at", None)
        if ca and ua and (ua - ca).total_seconds() > epsilon_seconds:
            refusals.append(f"{getattr(u, 'unit_id', '?')}: modified after creation — refusing rollback.")
            continue
        to_reverse.append(u)
    return RollbackPlan(
        safe=not refusals,
        to_reverse=[] if refusals else to_reverse,
        refusals=refusals,
        skipped_already=skipped,
    )


# ── DB load (read-only) ──────────────────────────────────────────────────
_DEVICE_FIELDS = (
    "device_id", "site_id", "model", "device_type", "last_heartbeat", "heartbeat_interval",
    "imei", "iccid", "msisdn", "serial_number", "vola_org_id", "starlink_id",
    "manufacturer", "carrier", "hardware_model_id",
)


def _device_dict(d) -> dict:
    out = {f: getattr(d, f, None) for f in _DEVICE_FIELDS}
    out["site_name"] = None
    return out


async def _load(db, tenant_id: str):
    from sqlalchemy import select
    from app.models.device import Device
    from app.models.service_unit import ServiceUnit
    from app.models.site import Site

    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id).order_by(Device.device_id))).scalars().all()
    sites = (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id))).scalars().all()
    units = (await db.execute(
        select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all()

    site_name_by_id = {s.site_id: s.site_name for s in sites}
    device_dicts = {}
    for d in devices:
        dd = _device_dict(d)
        dd["site_name"] = site_name_by_id.get(d.site_id)
        device_dicts[d.device_id] = dd
    return device_dicts, set(site_name_by_id), {u.device_id for u in units if u.device_id}, units


def _read_plan_file(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("plan file must be a JSON list of objects")
    return data


# ── Orchestration ────────────────────────────────────────────────────────
async def run(dry_run: bool = True):
    from app.database import AsyncSessionLocal
    from app.models.service_unit import ServiceUnit
    from app.services.audit_logger import log_audit

    plan_file = os.environ.get("RH_SU_PLAN_FILE", "").strip()
    actor = os.environ.get("RH_SU_ACTOR", SOURCE)
    approver = os.environ.get("RH_SU_APPROVED_BY", "").strip()
    rollback_batch = os.environ.get("RH_SU_ROLLBACK_BATCH", "").strip()
    rollback_hard = os.environ.get("RH_SU_ROLLBACK_HARD", "false").strip().lower() in ("1", "true", "yes", "on")
    min_conf = float(os.environ.get("RH_SU_MIN_CONFIDENCE", "0.5"))
    batch_id = os.environ.get("RH_SU_BATCH_ID", "").strip() or \
        f"su-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:6]}"

    print("=" * 72)
    print(f"RH service-unit creation — tenant '{RH_TENANT}'")
    mode = "ROLLBACK" if rollback_batch else ("DISCOVERY" if not plan_file else ("DRY RUN" if dry_run else "APPLY"))
    print(f"  mode: {mode}" + (f"   batch: {batch_id}" if not rollback_batch and plan_file else ""))
    print("=" * 72)

    async with AsyncSessionLocal() as db:
        device_dicts, site_ids, covered, units = await _load(db, RH_TENANT)

        # ── Rollback ──
        if rollback_batch:
            rp = plan_rollback(units, batch_id=rollback_batch)
            _print_rollback(rp, rollback_batch, rollback_hard)
            if not rp.safe or not rp.to_reverse or dry_run:
                await db.rollback()
                return rp
            now_iso = datetime.now(timezone.utc).isoformat()
            for u in rp.to_reverse:
                if rollback_hard:
                    await db.delete(u)
                else:
                    u.status = "decommissioned"
                    u.meta = {**(u.meta or {}), "rolled_back_at": now_iso}
                await log_audit(db, RH_TENANT, "service_unit", "rollback_service_unit",
                                f"Rolled back {u.unit_id} (batch {rollback_batch}, "
                                f"{'hard-delete' if rollback_hard else 'soft'}).",
                                actor=actor, target_type="service_unit", target_id=u.unit_id,
                                site_id=u.site_id, device_id=u.device_id,
                                detail={"batch_id": rollback_batch, "hard": rollback_hard})
            await db.commit()
            print(f"\nROLLED BACK — {len(rp.to_reverse)} unit(s) "
                  f"{'deleted' if rollback_hard else 'decommissioned'} (batch {rollback_batch}).")
            return rp

        # ── Discovery ──
        if not plan_file:
            _print_discovery(device_dicts, covered, min_conf)
            await db.rollback()
            return None

        # ── Plan (dry-run / apply) ──
        try:
            rows = _read_plan_file(plan_file)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            await db.rollback()
            print(f"\nERROR reading plan file {plan_file!r}: {exc}. Nothing written.")
            return None

        plan = plan_service_units(rows, device_dicts, site_ids, covered, min_confidence=min_conf)
        _print_plan(plan)

        proceed, why = apply_allowed(dry_run, approver, plan)
        if not proceed:
            await db.rollback()
            print({
                "refused": "\nREFUSED — plan has problems. Nothing written.",
                "nothing-to-create": "\nNothing to create (all covered). Nothing written.",
                "dry-run": f"\nDRY RUN — would create {len(plan.creates)} unit(s). "
                           "Re-run with DRY_RUN=false AND RH_SU_APPROVED_BY=<approver> to apply.",
                "approval-required": "\nAPPROVAL REQUIRED — set RH_SU_APPROVED_BY=<Stuart> to apply. Nothing written.",
            }[why])
            return plan

        # ── APPLY (service-unit rows only) ──
        now_iso = datetime.now(timezone.utc).isoformat()
        for c in plan.creates:
            db.add(ServiceUnit(
                tenant_id=RH_TENANT, site_id=c["site_id"], unit_id=c["unit_id"],
                unit_name=c["unit_name"], unit_type=c["unit_type"],
                location_description=c["location_description"], floor=c["floor"],
                install_type=c["install_type"], device_id=c["device_id"],
                status=c["status"], compliance_status=c["compliance_status"],
                meta=build_unit_meta(c, batch_id=batch_id, actor=actor, approver=approver, now_iso=now_iso),
            ))
            await log_audit(db, RH_TENANT, "service_unit", "create_service_unit",
                            f"Created {c['unit_id']} ({c['unit_type']}, status={c['status']}) "
                            f"for device {c['device_id']} at site {c['site_id']}.",
                            actor=actor, target_type="service_unit", target_id=c["unit_id"],
                            site_id=c["site_id"], device_id=c["device_id"],
                            detail={"batch_id": batch_id, "unit_type": c["unit_type"],
                                    "status": c["status"], "confidence": c["confidence"],
                                    "approved_by": approver})
        await db.commit()
        active = sum(1 for c in plan.creates if c["status"] == "active")
        print(f"\nCOMMITTED — {len(plan.creates)} unit(s) created "
              f"({active} active, {len(plan.creates) - active} pending_install). "
              f"batch_id={batch_id}. Each create audit-logged.")
        print("  Run `python -m app.audit_rh_readiness` to confirm.")
        return plan


# ── Reporting ────────────────────────────────────────────────────────────
def _discovery_rows(device_dicts, covered, min_conf):
    rows = []
    for did, d in device_dicts.items():
        if did in covered:
            continue
        unit_type, base, reason = infer_canonical_unit(d)
        conf = score_confidence(base, location_present=False,
                                has_identifier=bool(device_identifiers(d)))
        tier = "HIGH" if conf >= 0.8 else ("MEDIUM" if conf >= 0.5 else "LOW")
        rows.append({"device_id": did, "site_id": d.get("site_id"),
                     "model": d.get("model"), "suggested_unit_type": unit_type,
                     "confidence": conf, "tier": tier, "reason": reason,
                     "confirmed": False})
    return rows


def _print_discovery(device_dicts, covered, min_conf):
    rows = _discovery_rows(device_dicts, covered, min_conf)
    print(f"\nDevices with NO service unit ({len(rows)}):")
    for r in rows:
        print(f"  - {r['device_id']:<16} site={str(r['site_id']):<12} "
              f"model={str(r['model']):<12} → {r['suggested_unit_type']:<22} "
              f"conf={r['confidence']:.2f} {r['tier']}  ({r['reason']})")
    if not rows:
        print("  (none — every device already has a service unit)")
    export = _export_path()
    if export and rows:
        _write_exports(export, rows)
        print(f"\n  Wrote plan template {export}.json and review sheet {export}.csv. "
              "Edit + set confirmed:true, then RH_SU_PLAN_FILE to dry-run.")
    else:
        print("\n  Build a plan file (device_id + unit_type + confirmed:true) "
              "and set RH_SU_PLAN_FILE to dry-run.")


def _write_exports(path_base: str, rows: list[dict]) -> None:
    template = [{"device_id": r["device_id"], "unit_type": r["suggested_unit_type"],
                 "unit_name": "", "location_description": "", "floor": "",
                 "confirmed": False} for r in rows]
    with open(f"{path_base}.json", "w", encoding="utf-8") as fh:
        json.dump(template, fh, indent=2)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["device_id", "site_id", "model",
                                        "suggested_unit_type", "confidence", "tier", "reason"])
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in w.fieldnames})
    with open(f"{path_base}.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())


def _print_plan(plan: ServiceUnitPlan) -> None:
    if plan.refusals:
        print("\nREFUSALS (batch will write nothing):")
        for r in plan.refusals:
            print(f"    ✗ {r}")
    if plan.creates:
        print("\nWILL CREATE:")
        for c in plan.creates:
            print(f"    → {c['unit_id']:<18} {c['unit_type']:<22} site={c['site_id']:<12} "
                  f"status={c['status']:<15} conf={c['confidence']:.2f}")
    if plan.noops:
        print(f"\n  {len(plan.noops)} device(s) already have a unit (no-op).")


def _print_rollback(rp: RollbackPlan, batch_id: str, hard: bool) -> None:
    if rp.refusals:
        print("\nREFUSALS (rollback will change nothing):")
        for r in rp.refusals:
            print(f"    ✗ {r}")
    print(f"\nWILL {'DELETE' if hard else 'DECOMMISSION'} {len(rp.to_reverse)} unit(s) in batch {batch_id}.")
    if rp.skipped_already:
        print(f"  {len(rp.skipped_already)} already rolled back (no-op).")


def _export_path() -> str | None:
    if "--export" in sys.argv:
        i = sys.argv.index("--export")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    try:
        asyncio.run(run(dry_run=dry_run))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
