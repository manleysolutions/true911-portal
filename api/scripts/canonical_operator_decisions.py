"""Record operator ground-truth decisions for the canonical model (D-023).

DRY-RUN BY DEFAULT: validates the EXTERNAL decision file and prints, per
decision, NEW / SUPERSEDE / UNCHANGED against the active ledger.  ``--apply``
(with ``--recorded-by``) appends the decisions to ``operator_decisions``; a
changed decision supersedes - never edits or deletes - the earlier one.

The decision file holds real operational identifiers and MUST live outside the
repository (e.g. /tmp on the Render shell); a path inside the repository is
refused.  Format and decision types: docs/customer/CANONICAL_SERVICE_MODEL.md.

Usage (Render shell, api service):
    python -m scripts.canonical_operator_decisions --tenant restoration-hardware \\
        --file /tmp/rh_decisions.json
    python -m scripts.canonical_operator_decisions --tenant restoration-hardware \\
        --file /tmp/rh_decisions.json --apply --recorded-by you@example.com
    python -m scripts.canonical_operator_decisions --tenant restoration-hardware --history
Exit: 0 ok · 3 error / invalid file
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def inside_repo(path: str) -> bool:
    real = os.path.realpath(path)
    try:
        return os.path.commonpath([real, REPO_ROOT]) == REPO_ROOT
    except ValueError:                     # different drives (Windows)
        return False


async def run(args) -> int:
    from app.database import AsyncSessionLocal
    from app.services.canonical import decisions as D
    from app.services.canonical import loader

    async with AsyncSessionLocal() as db:
        if args.history:
            for d in await D.load_history(db, args.tenant):
                print(" | ".join(str(x) for x in (
                    d["id"], d["decision_type"], d["decision_key"],
                    "ACTIVE" if not d["superseded_by_id"] else "superseded by %s" % d["superseded_by_id"],
                    d["recorded_by"], d["recorded_at"], json.dumps(d["new_state"], sort_keys=True),
                    d["reason"])))
            return 0
        if not args.file:
            print("--file is required (or --history)")
            return 3
        if inside_repo(args.file):
            print("refusing: the decision file must live OUTSIDE the repository (%s)" % REPO_ROOT)
            return 3
        data = D.parse_file(args.file)
        if data.get("tenant") not in (None, args.tenant):
            print("decision file is for tenant %r, not %r" % (data.get("tenant"), args.tenant))
            return 3
        snap = await loader.build_snapshot(db, args.tenant, zoho="skip")
        decisions, errors = D.normalize_all(data["decisions"], snap["buildings"])
        if errors:
            print("INVALID decision file - nothing recorded:")
            print("\n".join("  " + e for e in errors))
            return 3
        if args.apply and not args.recorded_by:
            print("--apply requires --recorded-by")
            return 3
        plan = await D.plan_and_record(db, args.tenant, decisions,
                                       recorded_by=args.recorded_by or "-", apply=args.apply)
        names = {b["id"]: b["name"] for b in snap["buildings"]}
        for p in plan:
            d = p["decision"]
            bname = names.get(d["subject"].get("building_id"), "-")
            print(" | ".join(str(x) for x in (
                p["action"], d["decision_type"], bname, d["decision_key"],
                "prev=%s" % json.dumps(p.get("previous_state"), sort_keys=True)
                if p["action"] == "SUPERSEDE" else "",
                "new=%s" % json.dumps(d["new_state"], sort_keys=True),
                "effective=%s" % (d["effective_date"].date() if d["effective_date"] else "-"))))
        print("%s: %d new, %d supersede, %d unchanged" % (
            "APPLIED" if args.apply else "DRY-RUN (nothing written)",
            sum(p["action"] == "NEW" for p in plan), sum(p["action"] == "SUPERSEDE" for p in plan),
            sum(p["action"] == "UNCHANGED" for p in plan)))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tenant", required=True)
    p.add_argument("--file", help="external decision JSON (never inside the repository)")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--recorded-by")
    p.add_argument("--history", action="store_true", help="print the full decision ledger")
    args = p.parse_args()
    try:
        code = asyncio.run(run(args))
    except Exception as exc:
        print("ERROR: %s: %s" % (type(exc).__name__, exc))
        code = 3
    sys.exit(code)


if __name__ == "__main__":
    main()
