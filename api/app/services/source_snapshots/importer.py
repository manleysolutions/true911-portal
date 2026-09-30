"""Source snapshot import: dry-run plan, then an immutable ``--apply`` (D-024).

``plan_import`` reads the file, interprets statuses, attributes every row to
the tenant (or not) and reports - it writes NOTHING.  ``apply_import`` inserts
exactly one ``source_snapshots`` row and one ``source_snapshot_records`` row per
ATTRIBUTED row, in one transaction.  The same file (same SHA-256) for the same
tenant and source is never imported twice.  No other table is written.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from app.services.canonical.normalize import mask
from app.services.source_snapshots import adapters as A
from app.services.source_snapshots import attribution as AT
from app.services.source_snapshots import reader
from app.services.source_snapshots import status as ST

EFFECTIVE_OPERATOR, EFFECTIVE_FILENAME, EFFECTIVE_UNKNOWN = "OPERATOR", "FILENAME", "UNKNOWN"


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _mask_key(kind: Optional[str], value: Optional[str]) -> str:
    if not value:
        return "-"
    return value if kind == A.MSISDN else mask(value)


async def plan_import(db, tenant_id: str, source_system: str, path: str, *,
                      effective_at: Optional[datetime] = None, index=None) -> dict:
    """Read + interpret + attribute.  Writes nothing."""
    from sqlalchemy import select

    from app.models.source_snapshot import SourceSnapshot

    if source_system not in A.ADAPTERS:
        raise ValueError("unknown source '%s' (one of %s)" % (source_system,
                                                              ", ".join(A.ADAPTERS)))
    adapter = A.ADAPTERS[source_system]
    sha = file_sha256(path)
    dup = (await db.execute(select(SourceSnapshot.id).where(
        SourceSnapshot.tenant_id == tenant_id, SourceSnapshot.source_system == source_system,
        SourceSnapshot.file_sha256 == sha))).scalar()
    sheet, header, data = reader.read_table(path, adapter.accepts)
    cmap = adapter.column_map(header)
    ix = index if index is not None else await AT.build_index(db)

    basename = os.path.basename(path)
    if effective_at is not None:
        eff, basis = effective_at, EFFECTIVE_OPERATOR
    else:
        eff = adapter.effective_from_filename(basename)
        basis = EFFECTIVE_FILENAME if eff else EFFECTIVE_UNKNOWN

    records, ambiguous, invalid = [], [], []
    verdicts, bases, lifecycles, raw_status = Counter(), Counter(), Counter(), Counter()
    issues, keys = Counter(), Counter()
    for i, row in enumerate(data, start=1):
        p = adapter.parse(header, row, i, cmap)
        issues.update(p.issues)
        if not p.record_key:
            invalid.append({"row": i, "issues": p.issues or ["NO_IDENTIFIER"]})
            verdicts["INVALID"] += 1
            continue
        att = AT.attribute(tenant_id, p.identifiers, p.labels, ix)
        verdicts[att["verdict"]] += 1
        bases[att["basis"]] += 1
        if att["verdict"] == AT.AMBIGUOUS:
            ambiguous.append({"row": i, "reason": att["basis"],
                              "key": _mask_key(p.identifier_type, p.record_key)})
            continue
        if att["verdict"] != AT.ATTRIBUTED:
            continue
        lifecycle, rule = ST.interpret(source_system, p.status_raw)
        lifecycles[lifecycle] += 1
        raw_status[p.status_raw or "<empty>"] += 1
        keys[p.record_key] += 1
        records.append({
            "row_number": i, "source_record_key": p.record_key,
            "identifier_type": p.identifier_type, "normalized_identifier": p.record_key,
            "msisdn": p.identifiers.get("msisdn"), "iccid": p.identifiers.get("iccid"),
            "imei": p.identifiers.get("imei"), "napco_radio": p.identifiers.get("napco_radio"),
            "source_status_raw": (p.status_raw or None) and p.status_raw[:120],
            "lifecycle_interpretation": lifecycle, "interpretation_rule": rule,
            "activity_at": p.activity_at, "location_hint": p.location_hint,
            "attribution_basis": att["basis"], "attribution_confidence": att["confidence"],
            "row_hash": p.row_hash, "attributes": p.attributes,
        })
    summary = {
        "sheet": sheet, "columns": header, "recognised_fields": sorted(cmap),
        "verdicts": dict(verdicts), "attribution_bases": dict(bases),
        "lifecycle": dict(lifecycles), "raw_status": dict(raw_status),
        "identifier_issues": dict(issues),
        "duplicate_keys": sum(1 for c in keys.values() if c > 1),
        "ambiguous": ambiguous, "invalid": invalid,
        "provisional_adapter": adapter.provisional,
        "status_column_present": "status" in cmap,
    }
    return {
        "tenant_id": tenant_id, "source_system": source_system,
        "source_label": adapter.source_label, "file_sha256": sha, "duplicate_of": dup,
        "original_basename": basename[:255], "file_size": os.path.getsize(path),
        "parser_name": adapter.parser_name, "parser_version": adapter.parser_version,
        "status_map_version": ST.map_version(source_system),
        "attribution_rule_version": AT.profile_version(tenant_id),
        "source_effective_at": eff, "effective_at_basis": basis,
        "row_count_total": len(data), "row_count_attributed": len(records),
        "row_count_excluded": verdicts[AT.EXCLUDED], "row_count_ambiguous": len(ambiguous),
        "row_count_invalid": len(invalid), "summary": summary, "records": records,
    }


async def apply_import(db, plan: dict, *, imported_by: str) -> tuple[int, bool]:
    """Persist the plan as ONE immutable snapshot.  -> (snapshot id, created).
    A file already imported for this tenant + source returns its id, writes nothing."""
    from sqlalchemy import select

    from app.models.source_snapshot import SourceSnapshot, SourceSnapshotRecord

    existing = (await db.execute(select(SourceSnapshot.id).where(
        SourceSnapshot.tenant_id == plan["tenant_id"],
        SourceSnapshot.source_system == plan["source_system"],
        SourceSnapshot.file_sha256 == plan["file_sha256"]))).scalar()
    if existing is not None:
        return existing, False
    snap = SourceSnapshot(
        tenant_id=plan["tenant_id"], source_system=plan["source_system"],
        source_label=plan["source_label"], file_sha256=plan["file_sha256"],
        original_basename=plan["original_basename"], file_size=plan["file_size"],
        parser_name=plan["parser_name"], parser_version=plan["parser_version"],
        status_map_version=plan["status_map_version"],
        attribution_rule_version=plan["attribution_rule_version"],
        source_effective_at=plan["source_effective_at"],
        effective_at_basis=plan["effective_at_basis"],
        imported_at=datetime.now(timezone.utc), imported_by=imported_by,
        row_count_total=plan["row_count_total"],
        row_count_attributed=plan["row_count_attributed"],
        row_count_excluded=plan["row_count_excluded"],
        row_count_ambiguous=plan["row_count_ambiguous"],
        row_count_invalid=plan["row_count_invalid"],
        summary=json.dumps(plan["summary"], sort_keys=True, default=str))
    db.add(snap)
    await db.flush()
    for r in plan["records"]:
        db.add(SourceSnapshotRecord(
            snapshot_id=snap.id, tenant_id=plan["tenant_id"],
            source_system=plan["source_system"],
            **{k: v for k, v in r.items() if k != "attributes"},
            attributes=json.dumps(r["attributes"], sort_keys=True, default=str)))
    await db.commit()
    return snap.id, True


# ── freshness (inventory certification only - NOT monitoring health) ─

FRESH, STALE, UNDATED = "FRESH", "STALE", "UNDATED"


def freshness(snapshot, now: Optional[datetime] = None, days: Optional[int] = None) -> str:
    """Inventory-certification freshness of a snapshot, from its SOURCE
    effective time (never the import time - an old export imported today is
    still old).  UNDATED snapshots are never fresh."""
    from app.config import settings
    days = days if days is not None else int(settings.SOURCE_SNAPSHOT_FRESHNESS_DAYS)
    now = now or datetime.now(timezone.utc)
    eff = snapshot.source_effective_at
    if eff is None:
        return UNDATED
    if eff.tzinfo is None:
        eff = eff.replace(tzinfo=timezone.utc)
    return FRESH if (now - eff).total_seconds() <= days * 86400 else STALE


async def latest_snapshot(db, tenant_id: str, source_system: str):
    """Most recent snapshot by source effective time (then import time)."""
    from sqlalchemy import select

    from app.models.source_snapshot import SourceSnapshot
    q = select(SourceSnapshot).where(SourceSnapshot.tenant_id == tenant_id,
                                     SourceSnapshot.source_system == source_system)
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return None
    floor = datetime.min.replace(tzinfo=timezone.utc)

    def key(s):
        e = s.source_effective_at or floor
        e = e if e.tzinfo else e.replace(tzinfo=timezone.utc)
        i = s.imported_at if s.imported_at.tzinfo else s.imported_at.replace(tzinfo=timezone.utc)
        return (e, i, s.id)
    return max(rows, key=key)
