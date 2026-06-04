"""Restoration Hardware — NAPCO RadioNumber Match Audit + ICCID Backfill Plan (READ-ONLY).

The RH ICCID coverage audit found 0 devices with an ICCID, so NAPCO import
coverage is 0% — yet the NAPCO export carries an ICCID for every radio.  The
likely bridge: many RH NAPCO device_id values appear to BE NAPCO RadioNumbers
(e.g. 15474214, 5483291, 13864).  This audit tests that hypothesis by comparing
``Device.device_id`` / ``Device.serial_number`` to the export's ``RadioNumber``,
then produces a DRY-RUN ICCID backfill plan that is compatible with the existing
RH identity importer (``app.backfill_rh_device_identity`` from PR #81).

Strictly READ-ONLY:
  * Only SELECTs — never writes a Device/Site/anything.
  * Produces a PLAN only — never applies a backfill, never runs the NAPCO import.
  * ``--export-plan`` writes a JSON file the operator asks for (an artifact, not
    a production-data change).
  * No E911 / T-Mobile / Assurance / Integrity changes.  No migration.

Run:
    NAPCO_EXPORT_FILE=/path/to/Radiolist.xlsx python -m app.audit_rh_napco_radio_match
    python -m app.audit_rh_napco_radio_match --napco-export /path/to/Radiolist.xlsx
    python -m app.audit_rh_napco_radio_match --napco-export R.xlsx \
        --export-plan /tmp/rh_napco_iccid_backfill_plan.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Reuse validated helpers (read-only).
from app.audit_rh_iccid_coverage import is_napco_candidate, normalize_iccid  # noqa: E402
from app.backfill_rh_device_identity import ALLOWED_FIELDS, _valid_iccid as importer_valid_iccid  # noqa: E402

RH_TENANT = os.environ.get("RH_TENANT", os.environ.get(
    "RH_NAPCO_TENANT", "restoration-hardware"))

# Match statuses (task #4).
MATCH_STATUSES = (
    "exact_device_id_match", "exact_serial_match", "exact_name_match",
    "metadata_match", "no_match", "ambiguous_match", "duplicate_radio_number",
    "non_napco_device", "data_conflict",
)
# Backfill decisions (task #4 part 2 / part 4).
DECISIONS = (
    "backfill_ready", "review_required", "refused", "no_op",
    "unmatched", "skipped_non_napco",
)


# ── pure helpers (unit-tested, no DB / no I/O) ───────────────────────────
def normalize_radio(v) -> str:
    """Trim a RadioNumber / device identifier for exact comparison.

    Conservative: trims whitespace only — never strips leading zeros or digits,
    which would change identity and risk false matches.
    """
    if v is None:
        return ""
    return str(v).strip()


def proposed_iccid(export_iccid) -> Optional[str]:
    """Return the importer-valid normalised ICCID, or None if missing/malformed.

    Validated with the SAME rule the RH identity importer enforces
    (digits only, 18-20) so a proposed value can never be refused downstream.
    """
    norm = normalize_iccid(export_iccid)
    if norm and importer_valid_iccid(norm):
        return norm
    return None


def is_rh_subscriber(name) -> bool:
    """True when a NAPCO SubscriberName clearly belongs to Restoration Hardware."""
    s = (name or "").lower()
    return "restoration hardware" in s or s.strip().startswith("rh ") or " rh " in s


def build_export_index(export_rows: list[dict]) -> dict:
    """Map normalised RadioNumber -> list of export rows (list len>1 = duplicate)."""
    idx: dict[str, list] = defaultdict(list)
    for r in export_rows:
        radio = normalize_radio(r.get("radio_number"))
        if radio:
            idx[radio].append(r)
    return idx


def _match_key(device: dict, export_by_radio: dict) -> tuple:
    """Return (match_status, matched_radio) using device_id then serial_number.

    Device has no free-form name/metadata columns, so exact_name_match /
    metadata_match are structurally N/A here (kept in the taxonomy for the
    summary).  Returns ('no_match', None) when neither identifier matches.
    """
    did = normalize_radio(device.get("device_id"))
    if did and did in export_by_radio:
        return "exact_device_id_match", did
    ser = normalize_radio(device.get("serial_number"))
    if ser and ser in export_by_radio:
        return "exact_serial_match", ser
    return "no_match", None


def evaluate_device(device: dict, *, is_napco: bool, match_status: str,
                    matched_radio: Optional[str], export_by_radio: dict,
                    rh_match_counts: Counter) -> dict:
    """Decide the match + backfill outcome for one device. Pure."""
    rec = {
        "device_id": device.get("device_id"),
        "site_id": device.get("site_id"),
        "site_name": device.get("site_name"),
        "model": device.get("model"),
        "device_type": device.get("device_type"),
        "serial_number": device.get("serial_number"),
        "current_iccid": device.get("iccid"),
        "matched_radio_number": matched_radio,
        "export_iccid": None, "export_subscriber_name": None,
        "export_sim_status": None, "export_last_signal": None,
        "export_plan": None, "export_gentech": None,
        "match_status": match_status,
        "match_confidence": "n/a",
        "backfill_decision": None,
        "reason": None,
        "recommended_action": None,
        "proposed_update": None,
    }

    if not is_napco:
        rec["match_status"] = "non_napco_device"
        rec["backfill_decision"] = "skipped_non_napco"
        rec["recommended_action"] = "not a NAPCO candidate — out of scope for NAPCO import"
        return rec

    if matched_radio is None:
        rec["backfill_decision"] = "unmatched"
        rec["recommended_action"] = (
            "no RadioNumber match for device_id or serial_number — verify the "
            "identifier or add the device to the NAPCO portal")
        return rec

    rows = export_by_radio[matched_radio]
    er = rows[0]
    rec.update({
        "export_iccid": er.get("iccid"),
        "export_subscriber_name": er.get("subscriber_name"),
        "export_sim_status": er.get("sim_status"),
        "export_last_signal": er.get("last_signal"),
        "export_plan": er.get("plan"),
        "export_gentech": er.get("gen_tech"),
        "match_confidence": "high",
    })

    # ── safety gates (Part 3) ──
    if len(rows) > 1:  # rule 3
        rec["match_status"] = "duplicate_radio_number"
        rec["backfill_decision"] = "refused"
        rec["reason"] = f"RadioNumber {matched_radio} appears in {len(rows)} export rows"
        rec["recommended_action"] = "dedupe the NAPCO export / confirm the correct radio"
        return rec
    if rh_match_counts[matched_radio] > 1:  # rule 4
        rec["match_status"] = "ambiguous_match"
        rec["backfill_decision"] = "refused"
        rec["reason"] = f"{rh_match_counts[matched_radio]} RH devices match RadioNumber {matched_radio}"
        rec["recommended_action"] = "resolve duplicate RH device_ids before backfill"
        return rec

    prop = proposed_iccid(er.get("iccid"))
    if prop is None:  # rule 1
        rec["backfill_decision"] = "refused"
        rec["reason"] = "export ICCID missing or malformed"
        rec["recommended_action"] = "fix the ICCID in the NAPCO portal export"
        return rec

    cur = normalize_iccid(device.get("iccid"))
    if cur and cur != prop:  # rule 2 -> conflict, human decides
        rec["match_status"] = "data_conflict"
        rec["backfill_decision"] = "review_required"
        rec["reason"] = "device already has a DIFFERENT ICCID than the export"
        rec["recommended_action"] = "operator must reconcile the two ICCIDs"
        return rec
    if cur and cur == prop:
        rec["backfill_decision"] = "no_op"
        rec["reason"] = "device already has the export ICCID"
        return rec

    if not is_rh_subscriber(er.get("subscriber_name")):  # rule 5
        rec["match_status"] = "data_conflict"
        rec["backfill_decision"] = "review_required"
        rec["reason"] = (f"export SubscriberName {er.get('subscriber_name')!r} "
                         "is not clearly Restoration Hardware")
        rec["recommended_action"] = "confirm the radio belongs to RH before backfill"
        return rec

    # ── backfill-ready (exact match, empty ICCID, valid export ICCID, RH) ──
    rec["backfill_decision"] = "backfill_ready"
    rec["reason"] = "exact RadioNumber match, ICCID empty, export ICCID valid"
    update = {"device_id": device.get("device_id"), "iccid": prop}
    # Backfill serial_number with the RadioNumber too when it's empty (helps the
    # NAPCO importer's serial fallback later). Whitelisted field — importer-safe.
    if not normalize_radio(device.get("serial_number")):
        update["serial_number"] = matched_radio
    rec["proposed_update"] = update
    rec["recommended_action"] = "feed proposed_update to the RH identity importer (dry-run first)"
    return rec


def build_records(devices: list[dict], export_rows: list[dict], classify_fn) -> list[dict]:
    """Match every RH device to the NAPCO export and decide its backfill outcome."""
    export_by_radio = build_export_index(export_rows)

    prelim = []
    for d in devices:
        cls = classify_fn(
            model=d.get("model"), device_type=d.get("device_type"),
            hardware_model_id=d.get("hardware_model_id"),
            manufacturer=d.get("manufacturer"), carrier=d.get("carrier"))
        napco = is_napco_candidate(cls)
        status, radio = _match_key(d, export_by_radio)
        prelim.append((d, napco, status, radio))

    # How many RH devices matched each radio (ambiguity guard, rule 4).
    rh_match_counts = Counter(radio for _, _, _, radio in prelim if radio)

    return [
        evaluate_device(d, is_napco=napco, match_status=status,
                        matched_radio=radio, export_by_radio=export_by_radio,
                        rh_match_counts=rh_match_counts)
        for d, napco, status, radio in prelim
    ]


def summarize(records: list[dict], export_rows: list[dict]) -> dict:
    """Part 4 summary."""
    dec = Counter(r["backfill_decision"] for r in records)
    status = Counter(r["match_status"] for r in records)
    napco = sum(1 for r in records if r["match_status"] != "non_napco_device")
    backfill_ready = dec.get("backfill_ready", 0)
    return {
        "rh_devices_total": len(records),
        "napco_candidates": napco,
        "napco_export_rows": len(export_rows),
        "matched_by_device_id": status.get("exact_device_id_match", 0),
        "matched_by_serial": status.get("exact_serial_match", 0),
        "matched_by_metadata": status.get("metadata_match", 0),
        "unmatched_napco_candidates": dec.get("unmatched", 0),
        "review_required": dec.get("review_required", 0),
        "backfill_ready": backfill_ready,
        "no_op_already_set": dec.get("no_op", 0),
        "refused": dec.get("refused", 0),
        "estimated_backfill_ready_over_candidates": f"{backfill_ready}/{napco}",
        "estimated_coverage_after_backfill_pct": (
            round(100.0 * (backfill_ready + dec.get("no_op", 0)) / napco, 1) if napco else 0.0
        ),
    }


# ── plan assembly (importer-compatible) ──────────────────────────────────
def importer_mapping(records: list[dict]) -> list[dict]:
    """The directly importer-compatible mapping list (backfill_ready only).

    Each row contains ONLY ``device_id`` + whitelisted identity fields, so it can
    be fed straight to RH_DEVICE_MAP_FILE for ``app.backfill_rh_device_identity``.
    """
    out = []
    for r in records:
        if r["backfill_decision"] == "backfill_ready" and r["proposed_update"]:
            row = {k: v for k, v in r["proposed_update"].items()
                   if k == "device_id" or k in ALLOWED_FIELDS}
            out.append(row)
    return out


def review_plan(records: list[dict]) -> list[dict]:
    """Rich, human-reviewable rows for the backfill-ready devices."""
    out = []
    for r in records:
        if r["backfill_decision"] != "backfill_ready":
            continue
        out.append({
            "device_id": r["device_id"],
            "site_id": r["site_id"],
            "current_model": r["model"],
            "suggested_vendor": "napco",
            "suggested_model": r["model"],
            "serial_number": (r["proposed_update"] or {}).get("serial_number")
            or r["serial_number"] or r["matched_radio_number"],
            "iccid": (r["proposed_update"] or {}).get("iccid"),
            "napco_radio_number": r["matched_radio_number"],
            "napco_plan": r["export_plan"],
            "napco_gentech": r["export_gentech"],
            "napco_subscriber_name": r["export_subscriber_name"],
            "operator_notes": "Matched by exact RadioNumber/device_id from NAPCO export",
        })
    return out


def build_plan_document(records: list[dict], summary: dict, tenant_id: str) -> dict:
    """The full --export-plan JSON document."""
    return {
        "generated_for_tenant": tenant_id,
        "read_only": True,
        "apply": False,
        "summary": summary,
        # Feed THIS straight to RH_DEVICE_MAP_FILE (importer-compatible).
        "importer_mapping": importer_mapping(records),
        "review_plan": review_plan(records),
        "review_required": [
            {"device_id": r["device_id"], "match_status": r["match_status"],
             "reason": r["reason"], "recommended_action": r["recommended_action"]}
            for r in records if r["backfill_decision"] == "review_required"
        ],
        "refused": [
            {"device_id": r["device_id"], "match_status": r["match_status"],
             "reason": r["reason"]}
            for r in records if r["backfill_decision"] == "refused"
        ],
        "unmatched": [
            {"device_id": r["device_id"], "recommended_action": r["recommended_action"]}
            for r in records if r["backfill_decision"] == "unmatched"
        ],
    }


def write_plan(document: dict, path: str) -> int:
    """Write the plan JSON the operator requested. Returns importer-row count."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, ensure_ascii=False, default=str)
    return len(document.get("importer_mapping", []))


# ── NAPCO export loader (read-only, reuses importer parse) ───────────────
def load_napco_export(path: str) -> list[dict]:
    from app.import_napco_portal_status import (
        read_rows, build_column_map, parse_napco_row,
    )
    headers, rows = read_rows(path)
    cm = build_column_map(headers)
    out = []
    for raw in rows:
        p = parse_napco_row(raw, cm)
        lc = p.get("last_comm")
        out.append({
            "radio_number": p.get("serial"),
            "iccid": p.get("iccid"),
            "sim_status": p.get("portal_status"),
            "last_signal": lc.isoformat() if hasattr(lc, "isoformat") else lc,
            "subscriber_name": p.get("name"),
            "plan": p.get("config"),
            "gen_tech": p.get("gen_tech"),
        })
    return out


# ── DB load (READ-ONLY) ──────────────────────────────────────────────────
async def _load_devices(db, tenant_id: str) -> tuple:
    from sqlalchemy import select
    from app.models.device import Device
    from app.models.site import Site
    from app.models.tenant import Tenant

    exists = (await db.execute(
        select(Tenant.is_active).where(Tenant.tenant_id == tenant_id))).scalar_one_or_none()
    sites = {s.site_id: s.site_name for s in (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id))).scalars().all()}
    devices = [{
        "device_id": d.device_id, "site_id": d.site_id,
        "site_name": sites.get(d.site_id), "model": d.model,
        "device_type": d.device_type, "hardware_model_id": d.hardware_model_id,
        "manufacturer": d.manufacturer, "carrier": d.carrier,
        "serial_number": d.serial_number, "iccid": d.iccid,
    } for d in (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id).order_by(Device.device_id))).scalars().all()]
    return exists is not None, devices


# ── reporting ────────────────────────────────────────────────────────────
def _print(records: list[dict], summary: dict, tenant_id: str) -> None:
    print("=" * 78)
    print("Restoration Hardware — NAPCO RadioNumber Match + ICCID Backfill Plan  (READ-ONLY)")
    print(f"tenant: {tenant_id}")
    print("=" * 78)

    print("\n--- MATCHED / BACKFILL-READY ---")
    for r in records:
        if r["backfill_decision"] not in ("backfill_ready", "no_op"):
            continue
        pu = r["proposed_update"] or {}
        print(f"  {str(r['device_id']):<14} radio={str(r['matched_radio_number']):<10} "
              f"site={str(r['site_id'] or '-'):<14} -> iccid={pu.get('iccid', '(set)')}  "
              f"[{r['backfill_decision']}]  sub={str(r['export_subscriber_name'])[:28]!r}")

    print("\n--- REVIEW-REQUIRED / REFUSED / UNMATCHED ---")
    for r in records:
        if r["backfill_decision"] in ("backfill_ready", "no_op", "skipped_non_napco"):
            continue
        print(f"  {str(r['device_id']):<14} {r['match_status']:<22} "
              f"{r['backfill_decision']:<16} {r['reason'] or r['recommended_action']}")

    print("\n--- SUMMARY (Part 4) ---")
    for k in ("rh_devices_total", "napco_candidates", "napco_export_rows",
              "matched_by_device_id", "matched_by_serial", "matched_by_metadata",
              "unmatched_napco_candidates", "review_required", "backfill_ready",
              "no_op_already_set", "refused",
              "estimated_backfill_ready_over_candidates",
              "estimated_coverage_after_backfill_pct"):
        print(f"  {k:<42}: {summary[k]}")
    print("\n  (Plan only — this audit writes nothing to the database.)")


async def run(tenant_id: str, *, napco_export: Optional[str],
              export_plan: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    from app.services.device_health.classifier import classify

    if not napco_export:
        print("No NAPCO export given. Set NAPCO_EXPORT_FILE or --napco-export "
              "to the RadioList .xlsx/.csv.")
        return {"ok": False}
    try:
        export_rows = load_napco_export(napco_export)
    except (OSError, ValueError, ImportError) as exc:
        print(f"ERROR reading NAPCO export {napco_export!r}: {exc}")
        return {"ok": False}

    async with AsyncSessionLocal() as db:
        exists, devices = await _load_devices(db, tenant_id)
    if not exists:
        print(f"Tenant {tenant_id!r} does not exist — check the slug in Admin → Tenants.")
        return {"ok": False}

    records = build_records(devices, export_rows, classify)
    summary = summarize(records, export_rows)
    _print(records, summary, tenant_id)

    if export_plan:
        doc = build_plan_document(records, summary, tenant_id)
        n = write_plan(doc, export_plan)
        print(f"\n  Wrote backfill plan ({n} importer-ready rows) -> {export_plan}")
        print("  Feed document['importer_mapping'] to RH_DEVICE_MAP_FILE "
              "(DRY_RUN first) for app.backfill_rh_device_identity.")
    return {"ok": True, "summary": summary, "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only RH NAPCO RadioNumber match + dry-run ICCID backfill plan.")
    parser.add_argument("--napco-export", dest="napco_export",
                        default=os.environ.get("NAPCO_EXPORT_FILE"),
                        help="NAPCO RadioList .xlsx/.csv export")
    parser.add_argument("--export-plan", dest="export_plan",
                        help="write the dry-run backfill plan JSON to this path")
    parser.add_argument("--tenant", default=RH_TENANT, help="tenant slug (default RH)")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.tenant, napco_export=args.napco_export,
                        export_plan=args.export_plan))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
