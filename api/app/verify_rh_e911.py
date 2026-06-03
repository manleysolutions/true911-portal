"""Restoration Hardware — E911 verification tool (dry-run-first, refusal-gated).

P0 of the RH readiness plan (docs/RH_READINESS_AUDIT.md). Moves sites whose
dispatchable address is ALREADY COMPLETE from "needs validation" to
``e911_status = validated`` — but ONLY for sites an operator has explicitly
listed as verified against the authoritative source.

This tool DOES NOT decide that an address is correct. A script cannot verify an
address against a PSAP authority, and bulk auto-validating would create false
life-safety confidence. So the operator must name the verified sites; the tool
only enforces eligibility, writes the status, and records an audit entry.

Contract:
  * DRY_RUN defaults TRUE — nothing is written unless DRY_RUN=false.
  * Validates ONLY sites in RH that are in the
    ``address_complete_needs_validation`` bucket (all 4 address parts present,
    status not already verified) AND named in RH_E911_VERIFIED_SITES.
  * REFUSES the whole batch (writes nothing) if any named site is missing
    address parts or is not found — never validate an incomplete address.
  * Already-verified named sites are skipped as no-ops (not a refusal).
  * There is deliberately NO "validate all" shortcut.

Never touches any other tenant.

Run:
    # 1. See eligible sites (no list yet):
    python -m app.verify_rh_e911
    # 2. Dry-run a verified set:
    RH_E911_VERIFIED_SITES="RH-TAMPA-01,RH-MIAMI-02" python -m app.verify_rh_e911
    # 3. Apply (only after the dry run looks right):
    DRY_RUN=false RH_E911_VERIFIED_SITES="RH-TAMPA-01,RH-MIAMI-02" \
        RH_E911_ACTOR="you@manleysolutions.com" python -m app.verify_rh_e911
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.audit_rh_readiness import e911_readiness, missing_e911_parts  # noqa: E402

RH_TENANT = os.environ.get("RH_E911_TENANT", "restoration-hardware")
VALIDATED_STATUS = "validated"


@dataclass
class VerifyPlan:
    safe: bool = False
    to_validate: list = field(default_factory=list)        # site dicts (eligible + requested)
    already_verified: list = field(default_factory=list)   # site_ids (no-op)
    refusals: list = field(default_factory=list)           # str
    not_requested_eligible: list = field(default_factory=list)  # site_ids eligible but not named


def plan_e911_verification(requested_site_ids: list[str], sites: list[dict]) -> VerifyPlan:
    """Pure planner. Decide which named RH sites may be moved to ``validated``.

    Refuses the batch on any named site that is missing address parts or not
    found — an incomplete address must never be validated.
    """
    by_id = {s["site_id"]: s for s in sites}
    requested = [s.strip() for s in requested_site_ids if s.strip()]

    eligible_ids = [s["site_id"] for s in sites
                    if e911_readiness(s) == "address_complete_needs_validation"]

    to_validate: list[dict] = []
    already: list[str] = []
    refusals: list[str] = []

    for sid in requested:
        s = by_id.get(sid)
        if s is None:
            refusals.append(f"{sid}: not found in tenant '{RH_TENANT}' — refusing.")
            continue
        bucket = e911_readiness(s)
        if bucket == "verified":
            already.append(sid)
        elif bucket == "address_complete_needs_validation":
            to_validate.append(s)
        else:  # address_partial / address_missing
            miss = [p.replace("e911_", "") for p in missing_e911_parts(s)]
            refusals.append(f"{sid}: address incomplete (missing {miss}) — refusing to validate.")

    # Batch is all-or-nothing: any refusal means we validate nothing.
    return VerifyPlan(
        safe=not refusals,
        to_validate=[] if refusals else to_validate,
        already_verified=already,
        refusals=refusals,
        not_requested_eligible=[e for e in eligible_ids if e not in requested],
    )


# ── DB load + apply ──────────────────────────────────────────────────────
async def _load_sites(db, tenant_id: str) -> list:
    from sqlalchemy import select
    from app.models.site import Site
    return (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id).order_by(Site.site_id))).scalars().all()


def _to_dict(s) -> dict:
    return {
        "site_id": s.site_id, "status": s.status, "e911_status": s.e911_status,
        "e911_street": s.e911_street, "e911_city": s.e911_city,
        "e911_state": s.e911_state, "e911_zip": s.e911_zip,
    }


async def run(dry_run: bool = True) -> VerifyPlan:
    from app.database import AsyncSessionLocal
    from app.services.audit_logger import log_audit

    requested = [s for s in os.environ.get("RH_E911_VERIFIED_SITES", "").split(",") if s.strip()]
    actor = os.environ.get("RH_E911_ACTOR", "verify_rh_e911")

    print("=" * 70)
    print(f"RH E911 verification — tenant '{RH_TENANT}'")
    print(f"  mode: {'DRY RUN (no writes)' if dry_run else 'APPLY (sets e911_status=validated)'}")
    print(f"  actor: {actor}")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        site_objs = await _load_sites(db, RH_TENANT)
        plan = plan_e911_verification(requested, [_to_dict(s) for s in site_objs])
        _print_plan(plan, requested)

        if not plan.safe:
            await db.rollback()
            print("\nREFUSED — one or more named sites are not safe to validate. Nothing written.")
            return plan
        if not plan.to_validate:
            await db.rollback()
            print("\nNothing to validate (no eligible sites named). Nothing written.")
            return plan
        if dry_run:
            await db.rollback()
            print(f"\nDRY RUN — would validate {len(plan.to_validate)} site(s). "
                  "Re-run with DRY_RUN=false to apply.")
            return plan

        # ── APPLY ──
        by_id = {s.site_id: s for s in site_objs}
        validate_ids = {s["site_id"] for s in plan.to_validate}
        for sid in validate_ids:
            s = by_id[sid]
            old = s.e911_status
            s.e911_status = VALIDATED_STATUS
            s.e911_confirmation_required = False
            await log_audit(
                db, RH_TENANT, "e911", "verify_address",
                f"Verified E911 dispatchable address for {sid}: {old!r} → '{VALIDATED_STATUS}'",
                actor=actor, target_type="site", target_id=sid, site_id=sid,
                detail={
                    "old_e911_status": old, "new_e911_status": VALIDATED_STATUS,
                    "address": {"street": s.e911_street, "city": s.e911_city,
                                "state": s.e911_state, "zip": s.e911_zip},
                },
            )
        await db.commit()
        print(f"\nCOMMITTED — {len(validate_ids)} site(s) set to e911_status='{VALIDATED_STATUS}', "
              "each audit-logged. No other field touched.")
        return plan


def _print_plan(plan: VerifyPlan, requested: list[str]) -> None:
    if not requested:
        print("\nNo RH_E911_VERIFIED_SITES given. Eligible sites awaiting verification:")
        for sid in plan.not_requested_eligible:
            print(f"    - {sid}  (address complete; needs authoritative verification)")
        if not plan.not_requested_eligible:
            print("    (none — no sites in 'address_complete_needs_validation')")
        print("\n  List the sites you have verified in RH_E911_VERIFIED_SITES to proceed.")
        return
    if plan.refusals:
        print("\nREFUSALS (batch will write nothing):")
        for r in plan.refusals:
            print(f"    ✗ {r}")
    if plan.already_verified:
        print("\nAlready verified (no-op):")
        for sid in plan.already_verified:
            print(f"    = {sid}")
    if plan.to_validate:
        print("\nWILL VALIDATE (set e911_status=validated):")
        for s in plan.to_validate:
            print(f"    → {s['site_id']}  {s['e911_street']}, {s['e911_city']} "
                  f"{s['e911_state']} {s['e911_zip']}  ({s['e911_status']!r} → validated)")
    if plan.not_requested_eligible:
        print(f"\n  Note: {len(plan.not_requested_eligible)} more eligible site(s) not named this run.")


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    try:
        asyncio.run(run(dry_run=dry_run))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: verification aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
