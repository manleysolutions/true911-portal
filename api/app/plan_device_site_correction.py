"""Device→site correction planner (DRY-RUN-FIRST, flag-gated, customer-scoped).

Corrects the R&R bulk-import artifact found by ``audit_rr_site_assignment``:
devices were imported onto a placeholder site while their lines carry the real
sites. For each ``likely_wrong_site`` device this plans ``devices.site_id <- the
matching line's site_id`` and, only when explicitly authorized, applies it.

Hard safety contract:
  * DRY-RUN by default — prints the proposed corrections and writes NOTHING.
  * APPLY (writes) requires BOTH ``--apply`` AND ``FEATURE_DEVICE_SITE_CORRECTION
    =true``; otherwise downgrades to dry-run.
  * Updates ``devices.site_id`` ONLY — never lines, never customers, never deletes.
  * Strictly CUSTOMER-SCOPED (reconciliation scoper). The proposed site must be
    one of THIS customer's sites (else refused as a customer mismatch).
  * Refuses ambiguous / multi-line / no-proposed-site rows. Every applied change
    is audit-logged.

Run:
    python -m app.plan_device_site_correction --customer "R&R Realty Group"            # dry run
    FEATURE_DEVICE_SITE_CORRECTION=true \
      python -m app.plan_device_site_correction --customer "R&R Realty Group" --apply  # apply
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.audit_zoho_true911_customer_reconciliation import _load_true911  # noqa: E402
from app.audit_rr_site_assignment import build_report  # noqa: E402

DEFAULT_CUSTOMER = os.environ.get("SITE_CORRECTION_CUSTOMER", "R&R Realty Group")

CHANGE_FIELDS = ("device_id", "msisdn", "current_site_id", "current_site_name",
                 "proposed_site_id", "proposed_site_name", "reason")


# ── pure planning + gating (unit-tested, no DB) ──────────────────────────
def _flag_on(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def feature_enabled() -> bool:
    return _flag_on(settings.FEATURE_DEVICE_SITE_CORRECTION)


def should_apply(apply_requested: bool) -> bool:
    """Write ONLY when requested AND the feature flag is on."""
    return bool(apply_requested) and feature_enabled()


def _brief(r: dict) -> dict:
    return {"device_id": r.get("device_id"), "msisdn": r.get("msisdn"),
            "classification": r.get("classification")}


def build_correction_plan(rows: list[dict], valid_site_ids: Optional[set]) -> dict:
    """Pure: turn site-assignment rows into proposed devices.site_id changes.

    Only ``likely_wrong_site`` rows with a proposed site OWNED by this customer
    become changes. Everything else is skipped with a reason (refusal contract).
    """
    changes: list[dict] = []
    skipped: list[dict] = []
    for r in rows:
        cls = r.get("classification")
        if cls == "likely_wrong_site":
            ps = r.get("proposed_site_id")
            if not ps:
                skipped.append({**_brief(r), "skip_reason": "no proposed site"})
                continue
            if valid_site_ids is not None and ps not in valid_site_ids:
                skipped.append({**_brief(r),
                                "skip_reason": "proposed site not owned by this customer (customer mismatch)"})
                continue
            changes.append({
                "device_id": r.get("device_id"), "msisdn": r.get("msisdn"),
                "current_site_id": r.get("device_site_id"),
                "current_site_name": r.get("device_site_name"),
                "proposed_site_id": ps, "proposed_site_name": r.get("line_site_name"),
                "reason": ("device on placeholder/wrong site; the matching line "
                           "(same MSISDN + customer) is on a different site"),
            })
        elif cls == "likely_correct":
            skipped.append({**_brief(r), "skip_reason": "already on the correct site"})
        elif cls == "unassigned":
            skipped.append({**_brief(r), "skip_reason": "device has no current site (unassigned)"})
        else:  # ambiguous (no or multiple matching lines)
            skipped.append({**_brief(r), "skip_reason": "ambiguous (no or multiple matching lines)"})
    return {"changes": changes, "skipped": skipped,
            "summary": {"to_correct": len(changes), "skipped": len(skipped)}}


# ── export ───────────────────────────────────────────────────────────────
def write_json(plan: dict, applied: Optional[int], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"applied": applied is not None, "applied_count": applied,
                   "summary": plan["summary"], "changes": plan["changes"],
                   "skipped": plan["skipped"]}, fh, indent=2, ensure_ascii=False, default=str)


def write_csv(plan: dict, path: str) -> int:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CHANGE_FIELDS), extrasaction="ignore")
        w.writeheader()
        for c in plan["changes"]:
            w.writerow(c)
    return len(plan["changes"])


# ── apply (WRITE — gated; devices.site_id only; never deletes) ───────────
async def _apply_changes(db, changes: list[dict], actor: str) -> int:
    from sqlalchemy import select
    from app.models.device import Device
    from app.services.audit_logger import log_audit

    applied = 0
    for ch in changes:
        d = (await db.execute(select(Device).where(
            Device.device_id == ch["device_id"]))).scalar_one_or_none()
        if d is None:
            continue
        old = d.site_id
        d.site_id = ch["proposed_site_id"]            # the ONLY field written
        applied += 1
        await log_audit(
            db, d.tenant_id, "device", "site_correction",
            f"Correct device {d.device_id} site_id {old!r} -> {ch['proposed_site_id']!r} "
            f"(matched its line by MSISDN)",
            actor=actor, target_type="device", target_id=d.device_id, device_id=d.device_id,
            detail={"field": "site_id", "from": old, "to": ch["proposed_site_id"],
                    "msisdn": ch.get("msisdn")})
    await db.commit()
    return applied


# ── report ───────────────────────────────────────────────────────────────
def _print(plan: dict, customer: str, applied: Optional[int]) -> None:
    mode = f"APPLIED ({applied} corrections)" if applied is not None else "DRY RUN (no writes)"
    print("=" * 84)
    print(f"Device→Site Correction Planner — {customer}  —  {mode}")
    print("=" * 84)
    print(f"  to_correct={plan['summary']['to_correct']}  skipped={plan['summary']['skipped']}")
    print(f"\n  PROPOSED CORRECTIONS ({len(plan['changes'])}):")
    for c in plan["changes"]:
        print(f"    {c['device_id']:<16} msisdn={c['msisdn']}  "
              f"site {c['current_site_id']} ({c['current_site_name']}) -> "
              f"{c['proposed_site_id']} ({c['proposed_site_name']})")
    if plan["skipped"]:
        from collections import Counter
        by = Counter(s["skip_reason"] for s in plan["skipped"])
        print(f"\n  SKIPPED ({len(plan['skipped'])}): {dict(by)}")
    if applied is None:
        print("\n  DRY RUN — nothing written. Apply needs --apply + "
              "FEATURE_DEVICE_SITE_CORRECTION=true.")
    print("\n  (Customer-scoped; devices.site_id only; never deletes; no line/customer changes.)")


async def run(customer: str, *, apply_requested: bool,
              export_json: Optional[str] = None, export_csv: Optional[str] = None,
              actor: str = "plan_device_site_correction") -> dict:
    from app.database import AsyncSessionLocal
    from collections import Counter

    async with AsyncSessionLocal() as db:
        t911 = await _load_true911(db, customer)
        sites = t911.get("sites", [])
        valid_site_ids = {s.get("site_id") for s in sites if s.get("site_id")}
        cust_id = Counter(s.get("customer_id") for s in sites if s.get("customer_id")).most_common(1)
        customer_id = cust_id[0][0] if cust_id else None
        customer_name = (t911.get("customer") or {}).get("name") or customer
        report = build_report(t911.get("devices", []), t911.get("lines", []), sites,
                              customer_id=customer_id, customer_name=customer_name)
        plan = build_correction_plan(report["rows"], valid_site_ids)

        applied = None
        if apply_requested:
            if not feature_enabled():
                print("REFUSED: FEATURE_DEVICE_SITE_CORRECTION is not true — running DRY RUN.\n")
            elif should_apply(apply_requested):
                applied = await _apply_changes(db, plan["changes"], actor)

    _print(plan, customer, applied)
    if export_json:
        write_json(plan, applied, export_json)
        print(f"\n  Wrote JSON -> {export_json}")
    if export_csv:
        n = write_csv(plan, export_csv)
        print(f"  Wrote {n} change rows (CSV) -> {export_csv}")
    return {"plan": plan, "applied": applied}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run-first device→site correction planner.")
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER, help="customer name")
    parser.add_argument("--apply", action="store_true",
                        help="WRITE devices.site_id (requires FEATURE_DEVICE_SITE_CORRECTION=true)")
    parser.add_argument("--export-json", dest="export_json")
    parser.add_argument("--export-csv", dest="export_csv")
    parser.add_argument("--actor", default=os.environ.get("SITE_CORRECTION_ACTOR",
                                                           "plan_device_site_correction"))
    args = parser.parse_args()
    try:
        asyncio.run(run(args.customer, apply_requested=args.apply,
                        export_json=args.export_json, export_csv=args.export_csv,
                        actor=args.actor))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: site correction planner aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
