"""Record a site / service-unit verification test into ``verification_tasks``.

Safe internal operational command — the same standalone-script pattern as
``app.seed_integrity`` and ``app.sync_device_health``.  ``DRY_RUN`` defaults to
**true**, so nothing is written unless you pass ``DRY_RUN=false`` explicitly,
AND the result must be supplied explicitly (``RVT_RESULT``) — this command will
never fabricate a passing test on its own.

Source of truth
---------------
``verification_tasks`` is the PRIMARY "last test" source the Assurance Engine
reads (``services/assurance/loader._load_last_test``).  ``command_testing`` /
``infra_test_results`` is the secondary source and is intentionally NOT written
here.

What it records
---------------
One completed ``VerificationTask`` per service unit (result + ``completed_at`` =
now), tenant-scoped, referencing the unit in the title / evidence notes.

Optional E911 validation (off by default)
-----------------------------------------
The Assurance Engine reaches **Protected** only when E911 is *validated* AND a
recent passing test exists AND the device is reachable.  Belle Terre's
``e911_status`` is ``provided`` (address on file, not yet validated).  When — and
only when — the real field test also confirmed the dispatchable E911 address, set
``VALIDATE_E911=true`` to additionally promote ``Site.e911_status`` →
``validated`` and write an audited ``E911ChangeLog`` entry (address unchanged).
This is an explicit operator action, never automatic.

Run
---
    # dry run — prints the plan, writes nothing (default)
    python -m app.record_verification_test

    # APPLY after the real field/phone test (records the test only):
    DRY_RUN=false RVT_RESULT=pass python -m app.record_verification_test

    # APPLY + validate E911 (real test confirmed the dispatchable address):
    DRY_RUN=false RVT_RESULT=pass VALIDATE_E911=true \
        RVT_COMPLETED_BY="cindy@ipmflorida.com" python -m app.record_verification_test

Overridable inputs (env) — default to the Belle Terre target:
    RVT_TENANT        integrity-pm
    RVT_SITE          IPM-BELLE-TERRE
    RVT_UNITS         IPM-BELLE-TERRE-EL1,IPM-BELLE-TERRE-EL2,IPM-BELLE-TERRE-EL3
    RVT_TEST_TYPE     elevator_emergency_call_test
    RVT_RESULT        (REQUIRED to apply — "pass" or "fail"; "passed"/"failed" ok)
    RVT_NOTES         Verified LM150 VoLTE elevator emergency call path and
                      dispatchable E911 address.
    RVT_COMPLETED_BY  manley-ops
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Defaults (Belle Terre target) ────────────────────────────────────
DEFAULT_TENANT = "integrity-pm"
DEFAULT_SITE = "IPM-BELLE-TERRE"
DEFAULT_UNITS = "IPM-BELLE-TERRE-EL1,IPM-BELLE-TERRE-EL2,IPM-BELLE-TERRE-EL3"
DEFAULT_TEST_TYPE = "elevator_emergency_call_test"
DEFAULT_NOTES = (
    "Verified LM150 VoLTE elevator emergency call path and dispatchable "
    "E911 address."
)
DEFAULT_COMPLETED_BY = "manley-ops"

_PASS = "pass"
_FAIL = "fail"


def normalize_result(raw: str | None) -> str | None:
    """Map 'passed'/'pass'/'failed'/'fail' (any case) → 'pass'/'fail', else None.

    Returns None for anything unrecognized so the caller refuses to record a
    test it cannot trust — never defaults to a pass.
    """
    v = (raw or "").strip().lower()
    if v in ("pass", "passed", "ok", "success", "successful"):
        return _PASS
    if v in ("fail", "failed", "error"):
        return _FAIL
    return None


def build_verification_task_kwargs(
    *, tenant_id: str, site_id: str, unit_id: str, test_type: str,
    result: str, notes: str, completed_by: str, now: _dt.datetime,
) -> dict:
    """Pure: build the VerificationTask(**kwargs) for one unit. No I/O."""
    return {
        "tenant_id": tenant_id,
        "site_id": site_id,
        "task_type": test_type,
        "title": f"Emergency call test — {unit_id}",
        "description": notes,
        "system_category": "elevator_phone",
        "status": "completed",
        "priority": "high",
        "result": result,                 # "pass" | "fail" — read by the engine
        "completed_at": now,
        "completed_by": completed_by,
        "evidence_notes": f"[{unit_id}] {notes}",
        "created_by": completed_by,
    }


def build_e911_validation_log_kwargs(site, *, tenant_id: str, requested_by: str,
                                     now: _dt.datetime) -> dict:
    """Pure: audited E911ChangeLog row recording a VALIDATION (address unchanged)."""
    return {
        "log_id": f"e911-val-{uuid.uuid4().hex[:12]}",
        "site_id": site.site_id,
        "tenant_id": tenant_id,
        "requested_by": requested_by,
        "requester_name": requested_by,
        "requested_at": now,
        "old_street": site.e911_street, "old_city": site.e911_city,
        "old_state": site.e911_state, "old_zip": site.e911_zip,
        # Address is unchanged — this records validation of the existing address.
        "new_street": site.e911_street or "", "new_city": site.e911_city or "",
        "new_state": site.e911_state or "", "new_zip": site.e911_zip or "",
        "reason": ("Dispatchable E911 address validated during "
                   "elevator emergency call test."),
        "status": "validated",
        "applied_at": now,
    }


async def apply(*, tenant_id: str, site_id: str, unit_ids: list[str],
                test_type: str, result: str, notes: str, completed_by: str,
                validate_e911: bool, dry_run: bool = True) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.models.verification_task import VerificationTask
    from app.models.e911_change_log import E911ChangeLog

    now = _dt.datetime.now(_dt.timezone.utc)
    summary: dict[str, list[str]] = {"recorded": [], "skipped": [], "e911": [], "notes": []}

    def log(line: str) -> None:
        print(line)

    async with AsyncSessionLocal() as db:
        # Site must exist in this tenant.
        site = (await db.execute(
            select(Site).where(Site.tenant_id == tenant_id, Site.site_id == site_id)
        )).scalar_one_or_none()
        if site is None:
            summary["notes"].append(f"site {site_id} not found in tenant {tenant_id} — aborting")
            log(f"! site {site_id} not found in tenant {tenant_id} — nothing recorded")
            return summary

        # Resolve the requested service units; never fabricate a missing unit.
        for unit_id in unit_ids:
            su = (await db.execute(
                select(ServiceUnit).where(
                    ServiceUnit.tenant_id == tenant_id,
                    ServiceUnit.site_id == site_id,
                    ServiceUnit.unit_id == unit_id,
                )
            )).scalar_one_or_none()
            if su is None:
                summary["skipped"].append(unit_id)
                log(f"! service unit {unit_id} not found — SKIPPED (not fabricated)")
                continue

            summary["recorded"].append(unit_id)
            log(f"+ verification_task {test_type}={result} for {unit_id} "
                f"(completed_at={now.isoformat()}, by={completed_by})")
            if not dry_run:
                db.add(VerificationTask(**build_verification_task_kwargs(
                    tenant_id=tenant_id, site_id=site_id, unit_id=unit_id,
                    test_type=test_type, result=result, notes=notes,
                    completed_by=completed_by, now=now,
                )))

        # Optional, opt-in, audited E911 validation (only on a passing test).
        if validate_e911:
            if result != _PASS:
                summary["notes"].append("VALIDATE_E911 ignored — result is not pass")
                log("! VALIDATE_E911 ignored because result is not 'pass'")
            elif (site.e911_status or "").strip().lower() in ("validated", "verified", "confirmed"):
                summary["e911"].append(f"{site_id}:already-{site.e911_status}")
                log(f"= E911 already {site.e911_status} for {site_id} (left untouched)")
            else:
                summary["e911"].append(f"{site_id}:{site.e911_status}->validated")
                log(f"+ E911 validate {site_id}: '{site.e911_status}' -> 'validated' "
                    f"(audited E911ChangeLog)")
                if not dry_run:
                    db.add(E911ChangeLog(**build_e911_validation_log_kwargs(
                        site, tenant_id=tenant_id, requested_by=completed_by, now=now)))
                    site.e911_status = "validated"
                    site.e911_confirmation_required = False

        if dry_run:
            await db.rollback()
            log("\nDRY RUN — no changes committed. Re-run with DRY_RUN=false to apply.")
        else:
            await db.commit()
            log("\nCommitted.")

    return summary


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() not in ("0", "false", "no", "off")
    tenant_id = os.environ.get("RVT_TENANT", DEFAULT_TENANT).strip()
    site_id = os.environ.get("RVT_SITE", DEFAULT_SITE).strip()
    unit_ids = [u.strip() for u in os.environ.get("RVT_UNITS", DEFAULT_UNITS).split(",") if u.strip()]
    test_type = os.environ.get("RVT_TEST_TYPE", DEFAULT_TEST_TYPE).strip()
    notes = os.environ.get("RVT_NOTES", DEFAULT_NOTES).strip()
    completed_by = os.environ.get("RVT_COMPLETED_BY", DEFAULT_COMPLETED_BY).strip()
    validate_e911 = os.environ.get("VALIDATE_E911", "").strip().lower() in ("1", "true", "yes")
    result = normalize_result(os.environ.get("RVT_RESULT"))

    print("=" * 64)
    print("Record verification test")
    print("=" * 64)
    print(f"  tenant      : {tenant_id}")
    print(f"  site        : {site_id}")
    print(f"  units       : {', '.join(unit_ids)}")
    print(f"  test_type   : {test_type}")
    print(f"  result      : {result or '(MISSING)'}")
    print(f"  completed_by: {completed_by}")
    print(f"  validate_e911: {validate_e911}")
    print(f"  mode        : {'DRY RUN (no writes)' if dry_run else 'APPLY (writing)'}")
    print()

    # Refuse to APPLY without an explicit, recognized result — never fake a pass.
    if not dry_run and result is None:
        print("ERROR: RVT_RESULT must be 'pass' or 'fail' to apply (the REAL "
              "field/phone test result). Nothing recorded.")
        raise SystemExit(2)
    if result is None:
        result = _PASS  # dry-run preview only; apply path is guarded above
        print("(dry-run preview assumes result=pass; set RVT_RESULT to apply)")

    if not dry_run:
        print("APPLYING a real test result — ensure the field/phone test was "
              "actually completed before this point.\n")

    try:
        summary = asyncio.run(apply(
            tenant_id=tenant_id, site_id=site_id, unit_ids=unit_ids,
            test_type=test_type, result=result, notes=notes,
            completed_by=completed_by, validate_e911=validate_e911, dry_run=dry_run,
        ))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    for key in ("recorded", "skipped", "e911"):
        items = summary.get(key, [])
        print(f"  {key:9}: {len(items)}  {items if items else ''}")
    for n in summary.get("notes", []):
        print(f"  ! {n}")


if __name__ == "__main__":
    main()
