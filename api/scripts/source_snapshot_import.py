"""Import an operational source export as an immutable evidence snapshot (D-024).

DRY-RUN BY DEFAULT: parses the file, interprets statuses, attributes each row
to the tenant (or not) and prints a MASKED report - nothing is written.
``--apply`` stores ONE immutable snapshot (+ one record per attributed row);
the same file (SHA-256) is never imported twice for a tenant + source.

Never writes a source system, canonical services, E911, the registry or
operator decisions.  The export must live OUTSIDE the repository (e.g. /tmp on
the Render shell) and should be deleted after a verified ``--apply`` - the
database snapshot and its SHA-256 remain.

Sources: NAPCO (StarLink RadioList), T_MOBILE (Infatrac/Genesis), VERIZON
(ThingSpace export), RED_POCKET (provisional contract).

Usage (Render shell, api service):
    python -m scripts.source_snapshot_import --tenant restoration-hardware --source NAPCO --file /tmp/Radiolist-20260930122903.xlsx
    python -m scripts.source_snapshot_import --tenant restoration-hardware --source NAPCO --file /tmp/Radiolist-20260930122903.xlsx --apply --imported-by you@example.com
    python -m scripts.source_snapshot_import --tenant restoration-hardware --list
    python -m scripts.source_snapshot_import --tenant restoration-hardware --show 12
Exit: 0 ok · 3 error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _parse_effective(v):
    if not v:
        return None
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def render_plan(plan: dict) -> str:
    s = plan["summary"]
    L = ["=== SOURCE SNAPSHOT %s ===" % ("(already imported as snapshot #%s)" % plan["duplicate_of"]
                                         if plan["duplicate_of"] else "PLAN"),
         "tenant=%s source=%s (%s)" % (plan["tenant_id"], plan["source_system"], plan["source_label"]),
         "file=%s size=%d sha256=%s" % (plan["original_basename"], plan["file_size"],
                                        plan["file_sha256"]),
         "parser=%s status_map=%s attribution=%s%s" % (
             plan["parser_version"], plan["status_map_version"],
             plan["attribution_rule_version"],
             "  [PROVISIONAL ADAPTER]" if s["provisional_adapter"] else ""),
         "source_effective_at=%s (basis=%s)" % (plan["source_effective_at"],
                                                plan["effective_at_basis"]),
         "sheet=%s recognised fields=%s" % (s["sheet"], ",".join(s["recognised_fields"])),
         "",
         "rows total=%d attributed=%d excluded=%d ambiguous=%d invalid=%d" % (
             plan["row_count_total"], plan["row_count_attributed"],
             plan["row_count_excluded"], plan["row_count_ambiguous"],
             plan["row_count_invalid"]),
         "attribution bases: %s" % json.dumps(s["attribution_bases"], sort_keys=True),
         "lifecycle (attributed): %s" % json.dumps(s["lifecycle"], sort_keys=True),
         "raw status (attributed): %s" % json.dumps(s["raw_status"], sort_keys=True),
         "identifier issues: %s" % json.dumps(s["identifier_issues"], sort_keys=True),
         "duplicate keys within file: %d" % s["duplicate_keys"]]
    if not s["status_column_present"]:
        L.append("WARNING: no status column - every record interprets as UNKNOWN lifecycle")
    if s["ambiguous"]:
        L.append("-- AMBIGUOUS rows (NOT stored - review) --")
        L.extend("row %s | %s | %s" % (a["row"], a["reason"], a["key"]) for a in s["ambiguous"])
    if s["invalid"]:
        L.append("-- INVALID rows (no usable identifier, NOT stored) --")
        L.extend("row %s | %s" % (a["row"], ",".join(a["issues"])) for a in s["invalid"][:50])
    return "\n".join(L)


async def run(args) -> int:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.source_snapshot import SourceSnapshot, SourceSnapshotRecord
    from app.services.source_snapshots import importer
    from scripts.canonical_operator_decisions import inside_repo

    async with AsyncSessionLocal() as db:
        if args.list:
            q = select(SourceSnapshot).where(SourceSnapshot.tenant_id == args.tenant) \
                .order_by(SourceSnapshot.id)
            for s in (await db.execute(q)).scalars().all():
                print(" | ".join(str(x) for x in (
                    s.id, s.source_system, s.original_basename, s.file_sha256[:12],
                    "effective=%s(%s)" % (s.source_effective_at, s.effective_at_basis),
                    "freshness=%s" % importer.freshness(s), "imported=%s by %s" % (
                        s.imported_at, s.imported_by),
                    "attributed=%d/%d" % (s.row_count_attributed, s.row_count_total),
                    s.parser_version)))
            return 0
        if args.show:
            s = (await db.execute(select(SourceSnapshot).where(
                SourceSnapshot.tenant_id == args.tenant,
                SourceSnapshot.id == args.show))).scalar()
            if s is None:
                print("no snapshot #%s for tenant %s" % (args.show, args.tenant))
                return 3
            recs = (await db.execute(select(SourceSnapshotRecord).where(
                SourceSnapshotRecord.snapshot_id == s.id))).scalars().all()
            print("snapshot #%d %s %s sha256=%s stored records=%d (expected %d) %s" % (
                s.id, s.source_system, s.original_basename, s.file_sha256, len(recs),
                s.row_count_attributed,
                "OK" if len(recs) == s.row_count_attributed else "MISMATCH"))
            return 0 if len(recs) == s.row_count_attributed else 3
        if not args.source or not args.file:
            print("--source and --file are required (or --list / --show)")
            return 3
        if inside_repo(args.file):
            print("refusing: the export must live OUTSIDE the repository")
            return 3
        if not os.path.isfile(args.file):
            print("file not found: %s" % args.file)
            return 3
        plan = await importer.plan_import(db, args.tenant, args.source.upper(), args.file,
                                          effective_at=_parse_effective(args.effective_at))
        print(render_plan(plan))
        if not args.apply:
            print("\nDRY-RUN: nothing was written")
            return 0
        if not args.imported_by:
            print("--apply requires --imported-by")
            return 3
        sid, created = await importer.apply_import(db, plan, imported_by=args.imported_by)
        print("\n%s snapshot #%d" % ("APPLIED: stored" if created else
                                     "UNCHANGED: file already imported as", sid))
        print("verify with: python -m scripts.source_snapshot_import --tenant %s --show %d"
              % (args.tenant, sid))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tenant", required=True)
    p.add_argument("--source", help="NAPCO | T_MOBILE | VERIZON | RED_POCKET")
    p.add_argument("--file", help="export file OUTSIDE the repository (.csv / .xlsx)")
    p.add_argument("--effective-at", help="source effective time (ISO-8601) if not in the filename")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--imported-by")
    p.add_argument("--list", action="store_true", help="list this tenant's snapshots")
    p.add_argument("--show", type=int, help="verify one persisted snapshot")
    args = p.parse_args()
    try:
        code = asyncio.run(run(args))
    except Exception as exc:
        print("ERROR: %s: %s" % (type(exc).__name__, exc))
        code = 3
    sys.exit(code)


if __name__ == "__main__":
    main()
