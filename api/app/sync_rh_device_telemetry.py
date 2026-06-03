"""Restoration Hardware — telemetry / heartbeat ingestion (dry-run-first).

P2 of the RH readiness plan (docs/RH_READINESS_AUDIT.md). PR #81 made RH devices
*monitorable* by backfilling vendor identity; identity alone does not create
liveness. This command asks the configured vendor adapters for REAL status and
persists fresh heartbeat/liveness onto the mapped RH devices.

The objective is trustworthy liveness, NOT making devices look online:
  * never fabricates a heartbeat — only persists a vendor's real ``last_seen``;
  * never overwrites fresher data with staler data (staleness guard);
  * never touches E911, device lifecycle status, or any Assurance label;
  * writes ONLY a whitelist of telemetry fields;
  * logs unavailable vendor APIs clearly and keeps going (per-device resilient);
  * routes devices with no automated source to the controlled MANUAL pathway
    (app.record_verification_test, PR #73) — it does NOT auto-create manual
    heartbeats.

Reuses the generic probe + update logic in app.sync_device_health (one place
owns vendor interpretation) and adds the RH-scoped readiness report + the
staleness guard.

Run:
    python -m app.sync_rh_device_telemetry                       # dry run (default)
    DRY_RUN=false python -m app.sync_rh_device_telemetry         # apply
    RH_TELEMETRY_TENANT=restoration-hardware python -m app.sync_rh_device_telemetry
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger("true911.sync_rh_device_telemetry")

RH_TENANT = os.environ.get("RH_TELEMETRY_TENANT", "restoration-hardware")

# Vendors with a live status probe today vs. those whose adapter is a stub
# awaiting implementation. Everything else (e.g. "future") has no automated path.
LIVE_VENDORS = frozenset({"vola", "tmobile"})
PENDING_VENDORS = frozenset({"telnyx", "inseego", "cisco_ata", "ms130"})

# Only these Device columns may be written by telemetry ingestion — defence in
# depth so E911 / lifecycle status / vendor identity can never be touched here.
ALLOWED_DEVICE_FIELDS = frozenset({
    "last_heartbeat", "network_status", "last_network_event",
    "vola_last_sync", "firmware_version", "wan_ip",
})
# Of those, the ones carrying a timestamp that must never go backwards.
STALENESS_GUARDED = ("last_heartbeat", "last_network_event", "vola_last_sync")

# Telemetry readiness classes.
READY = "ready"
TELEMETRY_PENDING = "telemetry_pending"
MANUAL_REQUIRED = "manual_verification_required"
UNMAPPED = "unmapped"


# ── pure helpers (unit-tested) ───────────────────────────────────────────
def required_identifier(vendor: str) -> str:
    """The identifier a live adapter keys on, for the readiness report."""
    return {"vola": "serial_number or imei", "tmobile": "msisdn"}.get(vendor, "—")


def has_required_identifier(vendor: str, device: dict) -> bool:
    if vendor == "vola":
        return bool((device.get("serial_number") or "").strip() or (device.get("imei") or "").strip())
    if vendor == "tmobile":
        return bool((device.get("msisdn") or "").strip() or (device.get("iccid") or "").strip()
                    or (device.get("imei") or "").strip())
    return False


def classify_telemetry_readiness(device: dict, probe_vendors, adapter_configured: dict) -> dict:
    """Pure: decide whether a device can yield a real heartbeat, and how.

    ``adapter_configured`` maps vendor -> bool (is_configured), injected so this
    stays env-free and testable.
    """
    probes = list(probe_vendors)
    base = {
        "device_id": device.get("device_id"),
        "probe_vendors": probes,
        "live_source_exists": any(v in LIVE_VENDORS and adapter_configured.get(v, False) for v in probes),
    }

    if not probes:
        return {**base, "telemetry_class": UNMAPPED, "required_identifier": "—",
                "has_identifier": False, "can_produce_heartbeat": False,
                "reason": "no vendor adapter — run device-identity backfill (PR #81) first"}

    live = next((v for v in probes if v in LIVE_VENDORS), None)
    req_id = required_identifier(live) if live else "—"
    has_id = bool(live) and has_required_identifier(live, device)

    ready_vendor = next(
        (v for v in probes
         if v in LIVE_VENDORS and adapter_configured.get(v, False) and has_required_identifier(v, device)),
        None,
    )
    if ready_vendor:
        return {**base, "telemetry_class": READY, "required_identifier": required_identifier(ready_vendor),
                "has_identifier": True, "can_produce_heartbeat": True,
                "reason": f"{ready_vendor} adapter configured and identifier present"}

    if live is not None:
        if not adapter_configured.get(live, False):
            reason = f"{live} adapter not configured (missing credentials) — telemetry pending"
        else:
            reason = f"{live} adapter configured but device missing {req_id} — telemetry pending"
        return {**base, "telemetry_class": TELEMETRY_PENDING, "required_identifier": req_id,
                "has_identifier": has_id, "can_produce_heartbeat": False, "reason": reason}

    if any(v in PENDING_VENDORS for v in probes):
        v = next(v for v in probes if v in PENDING_VENDORS)
        return {**base, "telemetry_class": TELEMETRY_PENDING, "required_identifier": "—",
                "has_identifier": False, "can_produce_heartbeat": False,
                "reason": f"{v} live probe not implemented yet — liveness via callbacks/CDR if any"}

    return {**base, "telemetry_class": MANUAL_REQUIRED, "required_identifier": "—",
            "has_identifier": False, "can_produce_heartbeat": False,
            "reason": "no automated liveness source for this device class — "
                      "record a manual verification test (app.record_verification_test)"}


def _coerce_utc(dt):
    if dt is None or not isinstance(dt, _dt.datetime):
        return dt
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=_dt.timezone.utc)


def _is_newer(proposed, current) -> bool:
    """True if ``proposed`` should replace ``current`` (current missing or older)."""
    if current is None:
        return True
    if proposed is None:
        return False
    try:
        return _coerce_utc(proposed) > _coerce_utc(current)
    except TypeError:
        return True  # incomparable — prefer the freshly probed value, but never crash


def guard_stale_updates(proposed: dict, current: dict) -> tuple[dict, list]:
    """Drop any guarded timestamp that would move BACKWARDS. Non-timestamp fields
    pass through. Returns (kept, notes)."""
    kept: dict = {}
    notes: list[str] = []
    for field, value in proposed.items():
        if field not in ALLOWED_DEVICE_FIELDS:
            notes.append(f"ignored non-telemetry field {field!r}")
            continue
        if field in STALENESS_GUARDED and not _is_newer(value, current.get(field)):
            notes.append(f"skipped stale {field} (vendor {value} <= stored {current.get(field)})")
            continue
        kept[field] = value
    return kept, notes


def compute_and_guard(vendor_statuses, current: dict, *, now) -> tuple[dict, list]:
    """Pure: compute the proposed device/sim updates from vendor statuses, then
    apply the staleness guard to the device timestamps. Returns
    ``({"device": {...}, "sim": {...}}, notes)``."""
    from app.sync_device_health import compute_device_updates

    proposed = compute_device_updates(vendor_statuses, now=now)
    dev_kept, notes = guard_stale_updates(proposed["device"], current)
    return {"device": dev_kept, "sim": proposed["sim"]}, notes


def safe_device_report(device_id: str, readiness: dict, vendor_lines: list, proposed: dict) -> dict:
    """A console/report-safe per-device record. Never includes raw vendor payload."""
    return {
        "device_id": device_id,
        "telemetry_class": readiness["telemetry_class"],
        "reason": readiness["reason"],
        "vendors": vendor_lines,                 # {vendor, available, status, reasons, error} — no payload
        "proposed_updates": {k: str(v) for k, v in proposed.items()},
    }


# ── DB orchestration (reuses sync_device_health) ─────────────────────────
def _adapter_configured_map(probe_vendors) -> dict:
    from app.services.device_health.adapters import get_status_adapter
    out = {}
    for v in probe_vendors:
        try:
            out[v] = bool(get_status_adapter(v).is_configured)
        except Exception:
            out[v] = False
    return out


async def run(*, dry_run: bool = True, tenant_id: str = RH_TENANT) -> dict:
    import uuid

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.device import Device
    from app.models.integration_payload import IntegrationPayload
    from app.services.audit_logger import log_audit
    from app.services.device_health.classifier import classify
    from app.sync_device_health import _probe_device

    now = _dt.datetime.now(_dt.timezone.utc)
    summary = {
        "devices": 0, "probed": 0, "updated": 0, "stale_skipped": 0,
        "by_class": {READY: 0, TELEMETRY_PENDING: 0, MANUAL_REQUIRED: 0, UNMAPPED: 0},
        "unavailable_vendor_calls": 0, "manual_candidates": [],
    }

    async with AsyncSessionLocal() as db:
        devices = (await db.execute(
            select(Device).where(Device.tenant_id == tenant_id).order_by(Device.device_id))).scalars().all()
        summary["devices"] = len(devices)

        for d in devices:
            cls = classify(model=d.model, device_type=d.device_type,
                           hardware_model_id=d.hardware_model_id,
                           manufacturer=d.manufacturer, carrier=d.carrier)
            dev_dict = {"device_id": d.device_id, "serial_number": d.serial_number,
                        "imei": d.imei, "iccid": d.iccid, "msisdn": d.msisdn}
            readiness = classify_telemetry_readiness(
                dev_dict, cls.probe_vendors, _adapter_configured_map(cls.probe_vendors))
            summary["by_class"][readiness["telemetry_class"]] += 1

            if readiness["telemetry_class"] == UNMAPPED:
                print(f"  {d.device_id:24} UNMAPPED — {readiness['reason']}")
                continue
            if readiness["telemetry_class"] == MANUAL_REQUIRED:
                summary["manual_candidates"].append(d.device_id)
                print(f"  {d.device_id:24} MANUAL — {readiness['reason']}")
                continue

            # telemetry_pending or ready → probe and report (probing a pending
            # device is harmless: the adapter returns available=False, logged).
            statuses = await _probe_device(d)
            summary["probed"] += 1
            vendor_lines = []
            for vs in statuses:
                if not vs.available:
                    summary["unavailable_vendor_calls"] += 1
                vendor_lines.append({"vendor": vs.vendor, "available": vs.available,
                                     "status": vs.normalized_status.value,
                                     "reasons": [r.value for r in vs.reason_codes],
                                     "error": vs.error})
                print(f"  {d.device_id:24} {vs.vendor:9} available={vs.available} "
                      f"status={vs.normalized_status.value} "
                      f"last_seen={vs.last_seen.isoformat() if vs.last_seen else None} "
                      f"reasons={[r.value for r in vs.reason_codes]}"
                      + (f" err={vs.error}" if vs.error else ""))

            current = {f: getattr(d, f, None) for f in STALENESS_GUARDED}
            kept, notes = compute_and_guard(statuses, current, now=now)
            dev_kept, sim_kept = kept["device"], kept["sim"]
            for n in notes:
                if n.startswith("skipped stale"):
                    summary["stale_skipped"] += 1
                print(f"      · {n}")

            if not dev_kept and not sim_kept:
                print(f"      (no fresh telemetry to apply for {d.device_id})")
                continue
            if dry_run:
                print(f"      would update device={dev_kept} sim={sim_kept}")
                continue

            # ── APPLY (whitelisted telemetry fields only) ──
            for field, value in dev_kept.items():
                setattr(d, field, value)
            if sim_kept:
                from app.models.sim import Sim
                sim = (await db.execute(
                    select(Sim).where(Sim.tenant_id == d.tenant_id, Sim.device_id == d.device_id))).scalar_one_or_none()
                if sim is None and d.iccid:
                    sim = (await db.execute(
                        select(Sim).where(Sim.tenant_id == d.tenant_id, Sim.iccid == d.iccid))).scalar_one_or_none()
                if sim is not None:
                    for field, value in sim_kept.items():
                        setattr(sim, field, value)
                    sim.last_synced_at = now
            for vs in statuses:
                if vs.raw_payload:
                    db.add(IntegrationPayload(
                        payload_id=f"rht-{uuid.uuid4().hex[:12]}",
                        source=vs.vendor, direction="outbound", body=vs.raw_payload, processed=True))
            summary["updated"] += 1
            await log_audit(
                db, d.tenant_id, "device_health", "rh_telemetry_sync",
                f"RH telemetry sync for {d.device_id} ({readiness['telemetry_class']})",
                actor="sync_rh_device_telemetry", target_type="device",
                target_id=d.device_id, site_id=d.site_id, device_id=d.device_id,
                detail={"device_changes": {k: str(v) for k, v in dev_kept.items()},
                        "sim_changes": sim_kept, "stale_notes": notes,
                        "vendors": [vs.vendor for vs in statuses]})

        if dry_run:
            await db.rollback()
            print("\nDRY RUN — no changes committed.")
        else:
            await db.commit()
            print("\nCommitted.")

    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    print("=" * 64)
    print(f"RH telemetry / heartbeat ingestion — tenant '{RH_TENANT}'")
    print(f"  mode: {'DRY RUN (no writes)' if dry_run else 'APPLY (telemetry fields only)'}")
    print("=" * 64)
    try:
        summary = asyncio.run(run(dry_run=dry_run))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: telemetry sync aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"  devices                : {summary['devices']}")
    for k in (READY, TELEMETRY_PENDING, MANUAL_REQUIRED, UNMAPPED):
        print(f"  {k:22} : {summary['by_class'][k]}")
    for k in ("probed", "updated", "stale_skipped", "unavailable_vendor_calls"):
        print(f"  {k:22} : {summary[k]}")
    if summary["manual_candidates"]:
        print(f"\n  Manual verification needed for {len(summary['manual_candidates'])} device(s): "
              "record a real test via `python -m app.record_verification_test`.")


if __name__ == "__main__":
    main()
