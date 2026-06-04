"""Restoration Hardware — ICCID Coverage & NAPCO Match-Readiness Audit (READ-ONLY).

PR #87 validated that the NAPCO StarLink export carries an ICCID for every radio,
and that ICCID is the strongest join into True911.  Import coverage therefore
depends on ``Device.iccid`` being populated for RH.  This audit measures exactly
that: per-device ICCID coverage, validity, duplication, and how many RH devices
could match the NAPCO export TODAY vs. need a backfill or manual review.

It is strictly READ-ONLY:
  * Only SELECTs — never writes a Device/Site/Sim/anything.
  * No backfill, no import apply, no E911 / T-Mobile / Assurance changes.
  * ``--export`` writes a CSV report the operator asks for — an output artifact,
    never a change to production data.

Reuses ``app.services.device_health.classifier.classify`` to decide which
devices are NAPCO StarLink candidates, and (optionally) the NAPCO importer's
pure parse helpers to cross-reference an actual export file.

Run:
    RH_ICCID_AUDIT_TENANT=restoration-hardware python -m app.audit_rh_iccid_coverage
    python -m app.audit_rh_iccid_coverage --export /tmp/rh_iccid_audit.csv
    python -m app.audit_rh_iccid_coverage --napco-export /path/to/Radiolist.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from collections import Counter
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RH_TENANT = os.environ.get("RH_ICCID_AUDIT_TENANT", "restoration-hardware")

# Per-device CSV/report columns (task #2).
REPORT_FIELDS = (
    "device_id", "device_name", "site_id", "site_name", "serial_number",
    "iccid", "iccid_normalized", "imei", "msisdn", "carrier", "vendor",
    "model", "classifier_family", "is_napco_candidate", "category",
)

CATEGORIES = (
    "ready_for_napco_import",
    "missing_iccid",
    "napco_candidate_no_iccid",
    "duplicate_iccid",
    "invalid_iccid",
    "conflicting_identity",
    "non_napco_device",
)


# ── pure helpers (unit-tested, no DB) ────────────────────────────────────
def normalize_iccid(raw) -> str:
    """Normalise an ICCID for comparison: keep digits, drop a trailing 'F' pad.

    Tolerates spaces/dashes and ``None``.  Does NOT validate — see
    :func:`is_valid_iccid`.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    # A trailing 'F'/'f' is a known 20th-nibble pad on some 19-digit ICCIDs.
    if s[-1] in ("F", "f") and s[:-1].replace(" ", "").replace("-", "").isdigit():
        s = s[:-1]
    return "".join(ch for ch in s if ch.isdigit())


def is_valid_iccid(value) -> bool:
    """True for a plausible SIM ICCID: 18–22 digits, telecom MII prefix '89'.

    Accepts the raw or normalised form (normalises internally).  This is a
    format check (matchability), not a Luhn/issuer check — we deliberately do
    NOT reject on Luhn so a legitimately-stored ICCID without a check digit is
    not flagged.
    """
    norm = normalize_iccid(value)
    return norm.startswith("89") and 18 <= len(norm) <= 22


def iccid_invalid_reason(raw) -> Optional[str]:
    """Human reason an ICCID is malformed, or None when valid/empty."""
    norm = normalize_iccid(raw)
    if not norm:
        return None
    if not norm.startswith("89"):
        return f"prefix {norm[:2]!r} != '89' (not a telecom ICCID)"
    if len(norm) < 18:
        return f"too short ({len(norm)} digits, expected 18-22)"
    if len(norm) > 22:
        return f"too long ({len(norm)} digits, expected 18-22)"
    return None


def looks_like_iccid(raw) -> bool:
    """True when a value (e.g. a serial field) is itself a valid ICCID —
    used to detect ICCID stored in the wrong column."""
    return is_valid_iccid(raw)


def is_napco_candidate(classification) -> bool:
    """A device is a NAPCO StarLink candidate when the classifier routes it to
    the NAPCO portal (vendor_cloud == 'napco_portal')."""
    return getattr(classification, "vendor_cloud", None) == "napco_portal"


def categorize_device(d: dict, *, is_napco: bool, dup_iccids: set) -> str:
    """Return the single primary category for a device (see CATEGORIES).

    Precedence is matchability-first for NAPCO candidates; non-candidates are
    out of scope for NAPCO import regardless of their ICCID.
    """
    norm = normalize_iccid(d.get("iccid"))
    serial_is_iccid = looks_like_iccid(d.get("serial_number"))

    if not is_napco:
        return "non_napco_device"
    if not norm:
        # ICCID may have been entered in the serial column.
        return "conflicting_identity" if serial_is_iccid else "napco_candidate_no_iccid"
    if not is_valid_iccid(norm):
        return "conflicting_identity" if serial_is_iccid else "invalid_iccid"
    if norm in dup_iccids:
        return "duplicate_iccid"
    if serial_is_iccid and normalize_iccid(d.get("serial_number")) != norm:
        return "conflicting_identity"
    return "ready_for_napco_import"


def duplicate_iccid_set(devices: list[dict]) -> set:
    """Normalised valid ICCIDs that appear on more than one RH device."""
    counts = Counter(
        normalize_iccid(d.get("iccid")) for d in devices
        if is_valid_iccid(d.get("iccid"))
    )
    return {ic for ic, n in counts.items() if n > 1}


def build_records(devices: list[dict], sites_by_id: dict, classify_fn) -> list[dict]:
    """Build the per-device audit records (pure given a classify function)."""
    dup = duplicate_iccid_set(devices)
    records: list[dict] = []
    for d in devices:
        cls = classify_fn(
            model=d.get("model"), device_type=d.get("device_type"),
            hardware_model_id=d.get("hardware_model_id"),
            manufacturer=d.get("manufacturer"), carrier=d.get("carrier"),
        )
        napco = is_napco_candidate(cls)
        norm = normalize_iccid(d.get("iccid"))
        site = sites_by_id.get(d.get("site_id")) or {}
        records.append({
            "device_id": d.get("device_id"),
            "device_name": d.get("model") or d.get("device_id"),
            "site_id": d.get("site_id"),
            "site_name": site.get("site_name"),
            "serial_number": d.get("serial_number"),
            "iccid": d.get("iccid"),
            "iccid_normalized": norm,
            "imei": d.get("imei"),
            "msisdn": d.get("msisdn"),
            "carrier": d.get("carrier"),
            "vendor": d.get("manufacturer") or getattr(cls, "vendor_cloud", None),
            "model": d.get("model"),
            "classifier_family": getattr(cls, "device_family", None) or "unknown",
            "is_napco_candidate": napco,
            "category": categorize_device(d, is_napco=napco, dup_iccids=dup),
        })
    return records


def summarize(records: list[dict]) -> dict:
    """Coverage summary (task #4)."""
    cat = Counter(r["category"] for r in records)
    total = len(records)
    with_iccid = sum(1 for r in records if r["iccid_normalized"])
    napco = sum(1 for r in records if r["is_napco_candidate"])
    import_ready = cat.get("ready_for_napco_import", 0)
    dup_values = len({r["iccid_normalized"] for r in records
                      if r["category"] == "duplicate_iccid"})
    return {
        "total_devices": total,
        "devices_with_iccid": with_iccid,
        "devices_missing_iccid": total - with_iccid,
        "duplicate_iccid_values": dup_values,
        "duplicate_iccid_devices": cat.get("duplicate_iccid", 0),
        "invalid_iccids": cat.get("invalid_iccid", 0),
        "conflicting_identity": cat.get("conflicting_identity", 0),
        "napco_candidates": napco,
        "napco_candidate_no_iccid": cat.get("napco_candidate_no_iccid", 0),
        "import_ready": import_ready,
        # Coverage = import-ready as a share of NAPCO candidates (the population
        # the export is about). 0 candidates -> 0.0 to avoid div/0.
        "estimated_match_coverage_pct": (
            round(100.0 * import_ready / napco, 1) if napco else 0.0
        ),
        "by_category": dict(cat),
    }


def cross_reference(records: list[dict], export_iccids: set,
                    export_radio_numbers: set) -> dict:
    """Cross-reference RH device ICCIDs against a real NAPCO export (task #5).

    ``export_iccids`` / ``export_radio_numbers`` are normalised sets parsed
    from the export.  Pure — no DB, no file I/O.
    """
    ready = [r for r in records if r["category"] == "ready_for_napco_import"]
    match_today = sum(1 for r in ready if r["iccid_normalized"] in export_iccids)
    serial_match = sum(
        1 for r in records
        if r["category"] != "non_napco_device"
        and (str(r.get("serial_number") or "").strip() in export_radio_numbers)
    )
    need_backfill = sum(1 for r in records if r["category"] == "napco_candidate_no_iccid")
    manual_review = sum(
        1 for r in records
        if r["category"] in ("invalid_iccid", "duplicate_iccid", "conflicting_identity")
    )
    rh_iccids = {r["iccid_normalized"] for r in records if r["iccid_normalized"]}
    export_only = sorted(export_iccids - rh_iccids)
    return {
        "export_rows": len(export_iccids),
        "match_today_by_iccid": match_today,
        "match_today_by_radionumber_serial": serial_match,
        "need_iccid_backfill": need_backfill,
        "need_manual_review": manual_review,
        "export_iccids_with_no_rh_device": len(export_only),
        "export_only_sample": export_only[:10],
    }


def write_csv(records: list[dict], path: str) -> int:
    """Write the per-device audit to a CSV the operator requested. Returns rows."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(REPORT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r)
    return len(records)


# ── NAPCO export cross-reference loader (read-only, reuses importer) ─────
def load_export_keys(path: str) -> tuple:
    """Return (normalised_iccid_set, radio_number_set) from a NAPCO export.

    Reuses the validated importer parse helpers — no DB, read-only file read.
    """
    from app.import_napco_portal_status import (
        read_rows, build_column_map, parse_napco_row,
    )
    headers, rows = read_rows(path)
    cm = build_column_map(headers)
    iccids: set = set()
    radios: set = set()
    for raw in rows:
        p = parse_napco_row(raw, cm)
        if p.get("iccid"):
            iccids.add(normalize_iccid(p["iccid"]))
        if p.get("serial"):
            radios.add(str(p["serial"]).strip())
    return iccids, radios


# ── DB load (READ-ONLY) ──────────────────────────────────────────────────
async def _load(db, tenant_id: str) -> dict:
    from sqlalchemy import select
    from app.models.device import Device
    from app.models.site import Site
    from app.models.tenant import Tenant

    exists = (await db.execute(
        select(Tenant.is_active).where(Tenant.tenant_id == tenant_id))).scalar_one_or_none()

    sites_by_id = {
        s.site_id: {"site_id": s.site_id, "site_name": s.site_name}
        for s in (await db.execute(
            select(Site).where(Site.tenant_id == tenant_id))).scalars().all()
    }
    devices = [{
        "device_id": d.device_id, "site_id": d.site_id, "status": d.status,
        "device_type": d.device_type, "model": d.model,
        "manufacturer": d.manufacturer, "hardware_model_id": d.hardware_model_id,
        "carrier": d.carrier, "serial_number": d.serial_number,
        "imei": d.imei, "iccid": d.iccid, "msisdn": d.msisdn,
    } for d in (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id).order_by(Device.site_id))).scalars().all()]

    return {"tenant_id": tenant_id, "exists": exists is not None,
            "sites_by_id": sites_by_id, "devices": devices}


# ── reporting ────────────────────────────────────────────────────────────
def _print(records: list[dict], summary: dict, tenant_id: str,
           cross: Optional[dict]) -> None:
    print("=" * 74)
    print(f"Restoration Hardware — ICCID Coverage & NAPCO Match-Readiness  (READ-ONLY)")
    print(f"tenant: {tenant_id}")
    print("=" * 74)

    print("\n--- PER-DEVICE ---")
    print(f"  {'device_id':<16} {'site_id':<16} {'model':<14} "
          f"{'iccid':<22} {'category'}")
    for r in records:
        print(f"  {str(r['device_id']):<16} {str(r['site_id']):<16} "
              f"{str(r['model'])[:14]:<14} {str(r['iccid'] or '-'):<22} {r['category']}")

    print("\n--- SUMMARY (task #4) ---")
    for k in ("total_devices", "devices_with_iccid", "devices_missing_iccid",
              "duplicate_iccid_values", "duplicate_iccid_devices", "invalid_iccids",
              "conflicting_identity", "napco_candidates", "napco_candidate_no_iccid",
              "import_ready", "estimated_match_coverage_pct"):
        print(f"  {k:<32}: {summary[k]}")

    print("\n--- BY CATEGORY ---")
    for c in CATEGORIES:
        print(f"  {c:<28}: {summary['by_category'].get(c, 0)}")

    if cross is not None:
        print("\n--- CROSS-REFERENCE vs NAPCO EXPORT (task #5) ---")
        for k in ("export_rows", "match_today_by_iccid",
                  "match_today_by_radionumber_serial", "need_iccid_backfill",
                  "need_manual_review", "export_iccids_with_no_rh_device"):
            print(f"  {k:<36}: {cross[k]}")

    print("\n  (Findings only — this audit writes nothing to the database.)")


async def run(tenant_id: str, *, export_path: Optional[str] = None,
              napco_export: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal
    from app.services.device_health.classifier import classify

    async with AsyncSessionLocal() as db:
        data = await _load(db, tenant_id)

    if not data["exists"]:
        print(f"Tenant {tenant_id!r} does not exist — check the slug in Admin → Tenants.")
        return {"exists": False}

    records = build_records(data["devices"], data["sites_by_id"], classify)
    summary = summarize(records)

    cross = None
    if napco_export:
        try:
            export_iccids, export_radios = load_export_keys(napco_export)
            cross = cross_reference(records, export_iccids, export_radios)
        except (OSError, ValueError, ImportError) as exc:
            print(f"  WARN: could not read NAPCO export {napco_export!r}: {exc}")

    _print(records, summary, tenant_id, cross)

    if export_path:
        n = write_csv(records, export_path)
        print(f"\n  Wrote {n} device rows -> {export_path}")

    return {"exists": True, "summary": summary, "records": records, "cross": cross}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only RH ICCID coverage / NAPCO match-readiness audit.")
    parser.add_argument("--export", dest="export_path",
                        help="write the per-device audit to this CSV path")
    parser.add_argument("--napco-export", dest="napco_export",
                        help="cross-reference against a NAPCO RadioList .xlsx/.csv export")
    parser.add_argument("--tenant", default=RH_TENANT, help="tenant slug (default RH)")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.tenant, export_path=args.export_path,
                        napco_export=args.napco_export))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
