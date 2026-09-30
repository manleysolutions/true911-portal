"""Canonical Life-Safety Service & Connection reconciliation (D-023) - backfill.

DRY-RUN BY DEFAULT.  Builds the canonical projection from a read-only snapshot
(True911 SELECTs + live, read-only Zoho GETs) and prints the reconciliation:
portfolio + per-building figures (INTERNAL), services, the strict report for
every BUILDING_IDENTITY_SUSPECT building (e.g. MEMPHIS RECONCILIATION),
lifecycle events / historical assets, findings and the review watchlist.

``--apply`` writes ONLY the eight canonical tables (idempotent upserts, never
deletes) and needs ``--confirm-tenant <tenant>``; it is ALWAYS refused when a
required source (Zoho) was unavailable - there is no override.  A degraded
DRY-RUN still prints the reconciliation and exits 2.  It never writes the
registry, sites, devices, lines, E911, Zoho, Napco, Genesis or any carrier.
Nothing customer-facing reads the canonical tables in PR #186a.

``--decisions-file`` PREVIEWS the effect of operator decisions that are not yet
recorded (they are overlaid in memory, never written).  Record decisions with
``scripts.canonical_operator_decisions``.

``--fixture <json>`` runs the engine on a snapshot file (no DB, no Zoho) -
used to exercise the dry-run on synthetic fixtures.

Usage (Render shell, api service):
    python -m scripts.canonical_service_backfill --tenant restoration-hardware
    python -m scripts.canonical_service_backfill --tenant restoration-hardware \\
        --decisions-file /tmp/rh_decisions.json
Exit: 0 ok · 2 degraded (a required source unavailable) · 3 error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_TENANT = "restoration-hardware"

# Per-tenant Zoho scoping + generic (parent-level) names that never place a record.
TENANT_PROFILES = {
    "restoration-hardware": {
        "generic_names": ("Restoration Hardware", "RH", "Restoration Hardware Inc"),
        "watchlist": [
            ("Edina #159", ("edina",), "159"),
            ("Raleigh #178", ("raleigh",), "178"),
            ("Leawood 119th Street", ("leawood", "119th"), None),
            ("San Rafael 20 Front Street", ("san rafael", "front st", "front street"), None),
            ("Beverly Modern / Hollywood", ("beverly", "hollywood"), None),
            ("Roseville duplicate", ("roseville",), None),
            ("Dawsonville duplicate", ("dawsonville",), None),
            ("Long Beach duplicate", ("long beach",), None),
        ],
    },
}


def _zoho_filter(tenant):
    if tenant == "restoration-hardware":
        from scripts.rh_portfolio_certification import is_rh_label
        return is_rh_label
    return None


def _jsonable(res: dict) -> dict:
    out = {k: v for k, v in res.items() if k not in ("records", "assets")}
    out["assets"] = [{k: v for k, v in a.items() if k != "records"} for a in res["assets"].values()]
    return out


async def run(args) -> int:
    from app.services.canonical import decisions as D
    from app.services.canonical import engine, report

    profile = TENANT_PROFILES.get(args.tenant, {})
    proposed_raw = None
    if args.decisions_file:
        from scripts.canonical_operator_decisions import inside_repo
        if inside_repo(args.decisions_file):
            print("refusing: the decision file must live OUTSIDE the repository")
            return 3
        proposed_raw = D.parse_file(args.decisions_file)
        if proposed_raw.get("tenant") not in (None, args.tenant):
            print("decision file is for tenant %r, not %r" % (proposed_raw.get("tenant"), args.tenant))
            return 3

    if args.fixture:
        if args.apply:
            print("--apply is not allowed with --fixture")
            return 3
        with open(args.fixture, encoding="utf-8") as fh:
            snap = json.load(fh)
        snap.setdefault("tenant_id", args.tenant)
        for k in ("buildings", "aliases", "mappings", "fused_groups", "sites", "devices",
                  "lines", "units", "zoho_rows", "decisions"):
            snap.setdefault(k, [])
        snap.setdefault("sources", {"fixture": {"status": "ok", "required": True,
                                                "system": "fixture file"}})
        if proposed_raw:
            proposed, errors = D.normalize_all(proposed_raw["decisions"], snap["buildings"])
            if errors:
                print("\n".join(errors))
                return 3
            snap["decisions"] = D.overlay(snap["decisions"], proposed)
        res = engine.project(snap)
    else:
        from app.database import AsyncSessionLocal
        from app.services.canonical import loader, writer
        async with AsyncSessionLocal() as db:
            zoho_mode = args.zoho
            zf = _zoho_filter(args.tenant) if zoho_mode == "live" else None
            if zoho_mode == "live" and zf is None:
                print("no Zoho row filter for tenant %r - use --zoho skip" % args.tenant)
                return 3
            proposed = []
            if proposed_raw:
                pre = await loader.build_snapshot(db, args.tenant, zoho="skip")
                proposed, errors = D.normalize_all(proposed_raw["decisions"], pre["buildings"])
                if errors:
                    print("\n".join(errors))
                    return 3
            snap = await loader.build_snapshot(
                db, args.tenant, zoho=zoho_mode, zoho_filter=zf, proposed_decisions=proposed,
                generic_names=profile.get("generic_names", ()))
            res = engine.project(snap)
            if args.apply:
                if proposed:
                    print("refusing --apply with --decisions-file: record decisions first with "
                          "scripts.canonical_operator_decisions")
                    return 3
                if args.confirm_tenant != args.tenant:
                    print("--apply requires --confirm-tenant %s" % args.tenant)
                    return 3
                try:
                    rid = await writer.apply_projection(db, res, run_by=args.run_by)
                except writer.DegradedProjectionError as exc:
                    print(str(exc))
                    print(report.render(res, snap=snap, targets=profile.get("watchlist", ()),
                                        mode="DRY-RUN"))
                    return 2
                print("APPLIED projection run id=%s" % rid)

    print(report.render(res, snap=snap, targets=profile.get("watchlist", ()),
                        mode="APPLY" if args.apply else "DRY-RUN"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(_jsonable(res), fh, indent=2, default=str)
        print("json written: %s" % args.json)
    return 2 if res["degraded"] else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tenant", default=DEFAULT_TENANT)
    p.add_argument("--zoho", choices=("live", "skip"), default="live")
    p.add_argument("--decisions-file", help="PREVIEW unrecorded operator decisions (external file)")
    p.add_argument("--fixture", help="run on a snapshot JSON file (no DB / Zoho)")
    p.add_argument("--json", help="also write the projection as JSON to this path")
    p.add_argument("--apply", action="store_true", help="write the canonical tables")
    p.add_argument("--confirm-tenant", help="required with --apply; must equal --tenant")
    p.add_argument("--run-by", default=os.environ.get("USER") or "operator")
    args = p.parse_args()
    try:
        code = asyncio.run(run(args))
    except Exception as exc:              # report, never half-apply silently
        print("ERROR: %s: %s" % (type(exc).__name__, exc))
        code = 3
    sys.exit(code)


if __name__ == "__main__":
    main()
