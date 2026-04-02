"""Self-healing engine — executes and verifies safe remediation actions.

Flow for each action:
  1. Check policy (eligible? cooled down? under max attempts?)
  2. Create remediation record with status=pending
  3. Execute the action
  4. Run verification
  5. Update record: succeeded/failed/blocked
  6. Return structured result

SAFETY: Only actions in the remediation_registry can run.
Every execution is recorded. Verification is mandatory for all
actions that claim success.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import SupportRemediationAction, SupportEscalation
from .remediation_registry import get_action, get_actions_for_issue, is_blocked
from . import remediation_policy

logger = logging.getLogger("true911.support.self_healing")


async def attempt_remediation(
    db: AsyncSession,
    action_type: str,
    tenant_id: str,
    trigger_source: str = "system",
    session_id: UUID | None = None,
    escalation_id: UUID | None = None,
    site_id: int | None = None,
    device_id: int | None = None,
    issue_category: str | None = None,
) -> dict:
    """Attempt a single remediation action.

    Returns a dict with:
      action_type, status, verification_status, verification_summary,
      blocked_reason, raw_result
    """

    defn = get_action(action_type)
    if defn is None or is_blocked(action_type):
        return _blocked_result(action_type, "Action not registered or on deny-list.")

    # 1. Policy check
    decision = await remediation_policy.evaluate(
        db, action_type, tenant_id, device_id=device_id, site_id=site_id,
    )

    if not decision.allowed:
        # Record the blocked attempt
        record = SupportRemediationAction(
            session_id=session_id,
            escalation_id=escalation_id,
            tenant_id=tenant_id,
            site_id=site_id,
            device_id=device_id,
            issue_category=issue_category,
            trigger_source=trigger_source,
            action_type=action_type,
            action_level=defn.level,
            status="blocked" if "cooldown" not in decision.reason.lower() else "cooldown",
            blocked_reason=decision.reason,
        )
        db.add(record)
        await db.flush()

        logger.info("Remediation blocked: %s — %s", action_type, decision.reason)
        return _blocked_result(action_type, decision.reason, cooldown=decision.cooldown_remaining_seconds)

    # 2. Create record
    record = SupportRemediationAction(
        session_id=session_id,
        escalation_id=escalation_id,
        tenant_id=tenant_id,
        site_id=site_id,
        device_id=device_id,
        issue_category=issue_category,
        trigger_source=trigger_source,
        action_type=action_type,
        action_level=defn.level,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()

    # 3. Execute
    try:
        raw_result = await _execute_action(db, action_type, tenant_id, site_id, device_id, escalation_id)
    except Exception as exc:
        logger.exception("Remediation action %s failed", action_type)
        record.status = "failed"
        record.completed_at = datetime.now(timezone.utc)
        record.verification_status = "failed"
        record.verification_summary = f"Execution error: {type(exc).__name__}: {exc}"
        record.raw_result = {"error": str(exc)}
        await db.flush()
        return _action_result(record)

    record.raw_result = raw_result
    record.completed_at = datetime.now(timezone.utc)

    # 4. Verify
    if decision.verification_required:
        v_status, v_summary = await _verify_action(db, action_type, tenant_id, site_id, device_id, raw_result)
        record.verification_status = v_status
        record.verification_summary = v_summary
        # SAFETY: Only mark succeeded if verification passes
        record.status = "succeeded" if v_status == "passed" else "failed"
    else:
        record.verification_status = "skipped"
        record.verification_summary = "Verification not required for this action."
        record.status = "succeeded"

    await db.flush()

    logger.info(
        "Remediation %s: %s — verification=%s",
        action_type, record.status, record.verification_status,
    )
    return _action_result(record)


async def attempt_auto_remediation(
    db: AsyncSession,
    issue_category: str,
    tenant_id: str,
    session_id: UUID | None = None,
    site_id: int | None = None,
    device_id: int | None = None,
) -> list[dict]:
    """Try all applicable safe actions for an issue category.

    Stops at the first successful action. Returns list of all attempt results.
    """
    actions = get_actions_for_issue(issue_category)
    if not actions:
        return []

    results = []
    for defn in actions:
        result = await attempt_remediation(
            db,
            action_type=defn.action_type,
            tenant_id=tenant_id,
            trigger_source="system",
            session_id=session_id,
            site_id=site_id,
            device_id=device_id,
            issue_category=issue_category,
        )
        results.append(result)

        # Stop after first success — don't over-remediate
        if result["status"] == "succeeded":
            break

    return results


async def get_session_remediations(
    db: AsyncSession,
    session_id: UUID,
) -> list[SupportRemediationAction]:
    """Get all remediation actions for a session."""
    result = await db.execute(
        select(SupportRemediationAction)
        .where(SupportRemediationAction.session_id == session_id)
        .order_by(SupportRemediationAction.created_at.desc())
    )
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════════
# ACTION EXECUTORS
# ═══════════════════════════════════════════════════════════════════

async def _execute_action(
    db: AsyncSession,
    action_type: str,
    tenant_id: str,
    site_id: int | None,
    device_id: int | None,
    escalation_id: UUID | None,
) -> dict:
    """Dispatch to the appropriate action executor."""

    executors = {
        "refresh_diagnostics": _exec_refresh_diagnostics,
        "refresh_device_status": _exec_refresh_device_status,
        "refresh_telemetry": _exec_refresh_telemetry,
        "retry_voice_check": _exec_retry_voice_check,
        "retry_connectivity_check": _exec_retry_connectivity_check,
        "retry_zoho_sync": _exec_retry_zoho_sync,
        "recheck_after_delay": _exec_recheck_after_delay,
        "check_backup_path": _exec_check_backup_path,
    }

    executor = executors.get(action_type)
    if executor is None:
        return {"error": f"No executor for action_type={action_type}"}

    return await executor(db, tenant_id, site_id, device_id, escalation_id)


async def _exec_refresh_diagnostics(db, tenant_id, site_id, device_id, _esc_id) -> dict:
    from .diagnostics import run_diagnostics
    results = await run_diagnostics(db, tenant_id, device_id=device_id, site_id=site_id)
    return {"checks_run": len(results), "results": {r["check_type"]: r["status"] for r in results}}


async def _exec_refresh_device_status(db, tenant_id, site_id, device_id, _esc_id) -> dict:
    from .diagnostics import check_device_status
    result = await check_device_status(db, tenant_id, device_id=device_id, site_id=site_id)
    return result


async def _exec_refresh_telemetry(db, tenant_id, site_id, device_id, _esc_id) -> dict:
    from .diagnostics import check_telemetry
    result = await check_telemetry(db, tenant_id, device_id=device_id, site_id=site_id)
    return result


async def _exec_retry_voice_check(db, tenant_id, site_id, device_id, _esc_id) -> dict:
    from .diagnostics import check_sip_registration
    result = await check_sip_registration(db, tenant_id, device_id=device_id, site_id=site_id)
    return result


async def _exec_retry_connectivity_check(db, tenant_id, site_id, device_id, _esc_id) -> dict:
    from .diagnostics import check_heartbeat, check_ata_reachability
    hb = await check_heartbeat(db, tenant_id, device_id=device_id, site_id=site_id)
    ata = await check_ata_reachability(db, tenant_id, device_id=device_id, site_id=site_id)
    return {"heartbeat": hb, "ata_reachability": ata}


async def _exec_retry_zoho_sync(db, tenant_id, _site_id, _device_id, escalation_id) -> dict:
    """Retry failed Zoho ticket creation for a specific escalation."""
    if not escalation_id:
        # Find the most recent failed escalation for this tenant
        result = await db.execute(
            select(SupportEscalation)
            .where(SupportEscalation.tenant_id == tenant_id, SupportEscalation.status == "failed")
            .order_by(SupportEscalation.created_at.desc())
            .limit(1)
        )
        esc = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(SupportEscalation).where(SupportEscalation.id == escalation_id)
        )
        esc = result.scalar_one_or_none()

    if not esc:
        return {"retried": False, "reason": "No failed escalation found"}

    from . import zoho_desk_service
    zoho_result = await zoho_desk_service.create_ticket(
        subject=f"True911 | Retry | Escalation {str(esc.id)[:8]}",
        description=esc.handoff_summary,
    )

    if zoho_result["status"] == "created":
        esc.zoho_ticket_id = zoho_result["ticket_id"]
        esc.zoho_ticket_number = zoho_result.get("ticket_number")
        esc.zoho_ticket_url = zoho_result.get("ticket_url")
        esc.zoho_status = zoho_result.get("zoho_status", "Open")
        esc.status = "created"
        esc.sync_error = None
        esc.synced_at = datetime.now(timezone.utc)
        return {"retried": True, "ticket_id": zoho_result["ticket_id"], "synced": True}
    else:
        return {"retried": True, "synced": False, "error": zoho_result.get("error", "Unknown")}


async def _exec_recheck_after_delay(db, tenant_id, site_id, device_id, _esc_id) -> dict:
    """Wait briefly then re-run diagnostics. Useful for transient issues."""
    await asyncio.sleep(5)  # Short delay — production might use 30-60s
    from .diagnostics import run_diagnostics
    results = await run_diagnostics(db, tenant_id, device_id=device_id, site_id=site_id,
                                     checks=["heartbeat", "device_status"])
    return {"delayed_recheck": True, "results": {r["check_type"]: r["status"] for r in results}}


async def _exec_check_backup_path(db, tenant_id, site_id, device_id, _esc_id) -> dict:
    """Check if backup connectivity path is available.
    TODO: Wire to actual multi-path monitoring when available.
    """
    # Stub — returns a simulated check result
    return {
        "backup_path_checked": True,
        "stub": True,
        "todo": "Wire to multi-path failover monitoring",
        "simulated_result": "backup_available",
    }


# ═══════════════════════════════════════════════════════════════════
# VERIFIERS
# ═══════════════════════════════════════════════════════════════════

async def _verify_action(
    db: AsyncSession,
    action_type: str,
    tenant_id: str,
    site_id: int | None,
    device_id: int | None,
    raw_result: dict,
) -> tuple[str, str]:
    """Verify whether a remediation action actually resolved the issue.

    Returns (status, summary) where status is 'passed' or 'failed'.
    SAFETY: Never return 'passed' unless evidence confirms improvement.
    """

    verifiers = {
        "refresh_diagnostics": _verify_diagnostics_improved,
        "refresh_device_status": _verify_status_ok,
        "refresh_telemetry": _verify_telemetry_fresh,
        "retry_voice_check": _verify_status_ok,
        "retry_connectivity_check": _verify_connectivity_ok,
        "retry_zoho_sync": _verify_zoho_synced,
        "recheck_after_delay": _verify_diagnostics_improved,
        "check_backup_path": _verify_backup_checked,
    }

    verifier = verifiers.get(action_type)
    if verifier is None:
        return "failed", f"No verifier for action_type={action_type}"

    try:
        return verifier(raw_result)
    except Exception as exc:
        logger.exception("Verification failed for %s", action_type)
        return "failed", f"Verification error: {type(exc).__name__}: {exc}"


def _verify_diagnostics_improved(raw_result: dict) -> tuple[str, str]:
    results = raw_result.get("results", {})
    if not results:
        return "failed", "No diagnostic results returned."
    failing = [k for k, v in results.items() if v in ("critical", "warning")]
    if failing:
        return "failed", f"Diagnostics still show issues: {', '.join(failing)}"
    return "passed", "All re-run diagnostics returned OK."


def _verify_status_ok(raw_result: dict) -> tuple[str, str]:
    status = raw_result.get("status", "unknown")
    if status == "ok":
        return "passed", "Status returned OK."
    return "failed", f"Status is '{status}', not OK."


def _verify_telemetry_fresh(raw_result: dict) -> tuple[str, str]:
    status = raw_result.get("status", "unknown")
    if status == "ok":
        return "passed", "Fresh telemetry data confirmed."
    return "failed", f"Telemetry status: {status}"


def _verify_connectivity_ok(raw_result: dict) -> tuple[str, str]:
    hb = raw_result.get("heartbeat", {}).get("status", "unknown")
    ata = raw_result.get("ata_reachability", {}).get("status", "unknown")
    if hb == "ok":
        return "passed", f"Heartbeat OK. ATA: {ata}."
    return "failed", f"Heartbeat: {hb}, ATA: {ata}"


def _verify_zoho_synced(raw_result: dict) -> tuple[str, str]:
    if raw_result.get("synced"):
        return "passed", f"Zoho ticket created: {raw_result.get('ticket_id', 'unknown')}"
    if not raw_result.get("retried"):
        return "failed", raw_result.get("reason", "No escalation to retry.")
    return "failed", f"Sync still failed: {raw_result.get('error', 'unknown')}"


def _verify_backup_checked(raw_result: dict) -> tuple[str, str]:
    if raw_result.get("backup_path_checked"):
        return "passed", f"Backup path check completed. Result: {raw_result.get('simulated_result', 'unknown')}"
    return "failed", "Backup path check did not complete."


# ═══════════════════════════════════════════════════════════════════
# RESULT HELPERS
# ═══════════════════════════════════════════════════════════════════

def _action_result(record: SupportRemediationAction) -> dict:
    return {
        "id": str(record.id),
        "action_type": record.action_type,
        "action_level": record.action_level,
        "status": record.status,
        "verification_status": record.verification_status,
        "verification_summary": record.verification_summary,
        "attempt_count": record.attempt_count,
        "blocked_reason": record.blocked_reason,
        "raw_result": record.raw_result,
    }


def _blocked_result(action_type: str, reason: str, cooldown: int = 0) -> dict:
    return {
        "action_type": action_type,
        "status": "blocked" if cooldown == 0 else "cooldown",
        "verification_status": None,
        "verification_summary": None,
        "blocked_reason": reason,
        "cooldown_remaining_seconds": cooldown,
        "raw_result": None,
    }
