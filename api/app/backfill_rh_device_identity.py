"""Restoration Hardware — device identity / vendor-mapping importer.

P1 of the RH readiness plan (docs/RH_READINESS_AUDIT.md). RH device health is
0/51 because the devices are imported inventory rows with no vendor identity:
the classifier can't pick an adapter (no model/carrier) and there's no
identifier (imei/iccid/serial/vola_org_id) to key a vendor account on.

This tool BACKFILLS those identity fields from an operator-supplied mapping
file so the device-health classifier yields probe vendors AND each device has a
matchable identifier — i.e. becomes monitorable. It is dry-run-first and
refusal-gated, and it writes ONLY identity fields (never status, heartbeat, or
operational state).

Mapping file: JSON list of objects, each keyed by ``device_id`` plus any of the
allowed identity fields:
    [
      {"device_id": "RH-DEV-001", "model": "LM150", "carrier": "T-Mobile",
       "imei": "354000000000001", "vola_org_id": "rh-org-1"},
      {"device_id": "RH-DEV-002", "model": "Cisco-ATA", "msisdn": "8135550100",
       "serial_number": "FOC1234ABCD"}
    ]

Safety:
  * DRY_RUN defaults TRUE — nothing written unless DRY_RUN=false.
  * Backfills ONLY empty fields. A mapping value that CONFLICTS with an existing
    non-empty value REFUSES the batch (set RH_DEVICE_ALLOW_OVERWRITE=true to
    force) — imported identity is never silently overwritten.
  * Malformed identifiers (imei/iccid/msisdn) REFUSE the batch — bad matching
    data is worse than none for life-safety.
  * Unknown fields, unknown/duplicate device_ids REFUSE the batch.
  * All-or-nothing: any refusal ⇒ nothing is written.
  * Never touches another tenant; never changes device status.

Run:
    # Discovery — list devices that still need mapping (read-only):
    python -m app.backfill_rh_device_identity
    # Dry-run a mapping file:
    RH_DEVICE_MAP_FILE=rh_devices.json python -m app.backfill_rh_device_identity
    # Apply:
    DRY_RUN=false RH_DEVICE_MAP_FILE=rh_devices.json \
        RH_DEVICE_ACTOR="you@manleysolutions.com" python -m app.backfill_rh_device_identity
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.audit_rh_readiness import device_monitorable, diagnose_device  # noqa: E402
from app.services.device_health.classifier import classify  # noqa: E402

RH_TENANT = os.environ.get("RH_DEVICE_TENANT", "restoration-hardware")

# Identity / vendor-matching fields only. Never status / heartbeat / lifecycle.
ALLOWED_FIELDS = (
    "model", "device_type", "manufacturer", "carrier", "hardware_model_id",
    "serial_number", "imei", "iccid", "msisdn", "vola_org_id", "sim_id", "imsi",
)


def _norm(v) -> str:
    return (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())


def _valid_imei(v: str) -> bool:
    d = v.strip()
    return d.isdigit() and len(d) == 15


def _valid_iccid(v: str) -> bool:
    d = v.strip()
    return d.isdigit() and 18 <= len(d) <= 20


def _valid_msisdn(v: str) -> bool:
    d = v.strip().lstrip("+")
    return d.isdigit() and 10 <= len(d) <= 15


_VALIDATORS = {"imei": _valid_imei, "iccid": _valid_iccid, "msisdn": _valid_msisdn}


@dataclass
class DeviceMapPlan:
    safe: bool = False
    changes: list = field(default_factory=list)    # {device_id, set_fields:{f:(old,new)}, probe_vendors, becomes_monitorable}
    refusals: list = field(default_factory=list)
    noops: list = field(default_factory=list)       # device_ids with nothing to change


def _monitorable_after(merged: dict) -> tuple[bool, list]:
    cls = classify(model=merged.get("model"), device_type=merged.get("device_type"),
                   hardware_model_id=merged.get("hardware_model_id"),
                   manufacturer=merged.get("manufacturer"), carrier=merged.get("carrier"))
    return device_monitorable(merged, cls.probe_vendors), list(cls.probe_vendors)


def plan_device_mapping(mappings: list[dict], devices: list[dict], *, allow_overwrite: bool = False) -> DeviceMapPlan:
    """Pure planner. Decide which identity fields to backfill per device and
    whether each device becomes monitorable. Batch is all-or-nothing."""
    by_id = {d["device_id"]: d for d in devices}
    refusals: list[str] = []
    changes: list[dict] = []
    noops: list[str] = []
    seen: set[str] = set()

    for row in mappings:
        did = _norm(row.get("device_id"))
        if not did:
            refusals.append("mapping row missing device_id — refusing.")
            continue
        if did in seen:
            refusals.append(f"{did}: duplicate device_id in mapping file — refusing.")
            continue
        seen.add(did)
        d = by_id.get(did)
        if d is None:
            refusals.append(f"{did}: not found in tenant '{RH_TENANT}' — refusing.")
            continue
        unknown = [k for k in row if k != "device_id" and k not in ALLOWED_FIELDS]
        if unknown:
            refusals.append(f"{did}: unknown field(s) {unknown} — refusing.")
            continue

        set_fields: dict = {}
        row_refused = False
        for f in ALLOWED_FIELDS:
            if f not in row:
                continue
            new = _norm(row.get(f))
            if not new:
                continue
            validator = _VALIDATORS.get(f)
            if validator and not validator(new):
                refusals.append(f"{did}: invalid {f} {new!r} — refusing.")
                row_refused = True
                break
            existing = _norm(d.get(f))
            if not existing:
                set_fields[f] = (d.get(f), new)
            elif existing.lower() == new.lower():
                continue  # already set — no-op
            elif allow_overwrite:
                set_fields[f] = (d.get(f), new)
            else:
                refusals.append(
                    f"{did}: {f} already {existing!r}, mapping says {new!r} — refusing to "
                    f"overwrite (set RH_DEVICE_ALLOW_OVERWRITE=true to force).")
                row_refused = True
                break
        if row_refused:
            continue
        if not set_fields:
            noops.append(did)
            continue
        merged = dict(d)
        for f, (_old, new) in set_fields.items():
            merged[f] = new
        becomes, probes = _monitorable_after(merged)
        changes.append({"device_id": did, "set_fields": set_fields,
                        "probe_vendors": probes, "becomes_monitorable": becomes})

    return DeviceMapPlan(
        safe=not refusals,
        changes=[] if refusals else changes,
        refusals=refusals,
        noops=noops,
    )


# ── DB load + apply ──────────────────────────────────────────────────────
def _device_dict(d) -> dict:
    return {f: getattr(d, f, None) for f in ALLOWED_FIELDS} | {
        "device_id": d.device_id, "site_id": d.site_id,
        "last_heartbeat": d.last_heartbeat, "starlink_id": d.starlink_id,
    }


async def _load_devices(db, tenant_id: str) -> list:
    from sqlalchemy import select
    from app.models.device import Device
    return (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id).order_by(Device.device_id))).scalars().all()


def _read_mapping_file(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("mapping file must be a JSON list of objects")
    return data


async def run(dry_run: bool = True) -> DeviceMapPlan | None:
    from app.database import AsyncSessionLocal
    from app.services.audit_logger import log_audit

    map_file = os.environ.get("RH_DEVICE_MAP_FILE", "").strip()
    allow_overwrite = os.environ.get("RH_DEVICE_ALLOW_OVERWRITE", "false").strip().lower() in ("1", "true", "yes", "on")
    actor = os.environ.get("RH_DEVICE_ACTOR", "backfill_rh_device_identity")

    print("=" * 70)
    print(f"RH device identity backfill — tenant '{RH_TENANT}'")
    print(f"  mode: {'DRY RUN (no writes)' if dry_run else 'APPLY (identity fields only)'}"
          f"   overwrite: {allow_overwrite}")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        device_objs = await _load_devices(db, RH_TENANT)
        device_dicts = [_device_dict(d) for d in device_objs]

        if not map_file:
            _print_discovery(device_dicts)
            await db.rollback()
            return None

        try:
            mappings = _read_mapping_file(map_file)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            await db.rollback()
            print(f"\nERROR reading mapping file {map_file!r}: {exc}. Nothing written.")
            return None

        plan = plan_device_mapping(mappings, device_dicts, allow_overwrite=allow_overwrite)
        _print_plan(plan)

        if not plan.safe:
            await db.rollback()
            print("\nREFUSED — mapping file has problems. Nothing written.")
            return plan
        if not plan.changes:
            await db.rollback()
            print("\nNothing to change (all mapped fields already set). Nothing written.")
            return plan
        if dry_run:
            await db.rollback()
            print(f"\nDRY RUN — would update {len(plan.changes)} device(s). "
                  "Re-run with DRY_RUN=false to apply.")
            return plan

        # ── APPLY (identity fields only) ──
        by_id = {d.device_id: d for d in device_objs}
        for ch in plan.changes:
            d = by_id[ch["device_id"]]
            applied = {}
            for f, (_old, new) in ch["set_fields"].items():
                setattr(d, f, new)
                applied[f] = {"old": _old, "new": new}
            await log_audit(
                db, RH_TENANT, "device", "backfill_identity",
                f"Backfilled identity for {d.device_id}: {sorted(applied)} "
                f"(monitorable={ch['becomes_monitorable']}, probes={ch['probe_vendors']})",
                actor=actor, target_type="device", target_id=d.device_id, device_id=d.device_id,
                detail={"fields": applied, "probe_vendors": ch["probe_vendors"],
                        "becomes_monitorable": ch["becomes_monitorable"]},
            )
        await db.commit()
        ready = sum(1 for c in plan.changes if c["becomes_monitorable"])
        print(f"\nCOMMITTED — {len(plan.changes)} device(s) updated (identity only); "
              f"{ready} now monitorable. Each change audit-logged. Status/heartbeat untouched.")
        return plan


def _print_discovery(devices: list[dict]) -> None:
    print("\nNo RH_DEVICE_MAP_FILE given. Devices NOT yet monitorable (need mapping):")
    n = 0
    for d in devices:
        _, probes = _monitorable_after(d)
        if device_monitorable(d, tuple(probes)):
            continue
        n += 1
        reasons = "; ".join(diagnose_device(d, tuple(probes)))
        print(f"    - {d['device_id']:<18} model={str(d.get('model')):<12} "
              f"carrier={str(d.get('carrier')):<10} -> {reasons}")
    if n == 0:
        print("    (none — every device is already monitorable)")
    print("\n  Build a JSON mapping file (device_id + identity fields) and set "
          "RH_DEVICE_MAP_FILE to dry-run it.")


def _print_plan(plan: DeviceMapPlan) -> None:
    if plan.refusals:
        print("\nREFUSALS (batch will write nothing):")
        for r in plan.refusals:
            print(f"    ✗ {r}")
    if plan.changes:
        print("\nWILL UPDATE (identity fields only):")
        for ch in plan.changes:
            fields = {f: new for f, (_o, new) in ch["set_fields"].items()}
            flag = "MONITORABLE" if ch["becomes_monitorable"] else "still not monitorable"
            print(f"    → {ch['device_id']:<18} {fields}  probes={ch['probe_vendors'] or '-'}  [{flag}]")
    if plan.noops:
        print(f"\n  {len(plan.noops)} device(s) already had every mapped field set (no-op).")


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    try:
        asyncio.run(run(dry_run=dry_run))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: backfill aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
