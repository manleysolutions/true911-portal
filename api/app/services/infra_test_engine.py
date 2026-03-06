"""Infrastructure test engine — manages automated testing workflows.

Test types:
  - voice_path          End-to-end voice path verification
  - emergency_call      Emergency call routing test
  - heartbeat_verify    Device heartbeat validation
  - radio_coverage      Radio/cellular coverage check
  - connectivity        Network connectivity test

Results update readiness scoring via verification tasks.
"""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.infra_test import InfraTest
from app.models.infra_test_result import InfraTestResult
from app.models.device import Device
from app.models.verification_task import VerificationTask


TEST_TYPES = {
    "voice_path": {
        "name": "Voice Path Test",
        "description": "Verify end-to-end voice connectivity through the device",
        "checks": ["dial_tone", "call_setup", "audio_path", "disconnect"],
    },
    "emergency_call": {
        "name": "Emergency Call Test",
        "description": "Verify emergency call routing to PSAP",
        "checks": ["e911_registration", "call_routing", "location_delivery", "callback"],
    },
    "heartbeat_verify": {
        "name": "Heartbeat Verification",
        "description": "Validate device heartbeat timing and payload",
        "checks": ["heartbeat_received", "interval_compliance", "payload_valid"],
    },
    "radio_coverage": {
        "name": "Radio Coverage Verification",
        "description": "Check cellular/radio signal strength and quality",
        "checks": ["signal_strength", "signal_quality", "band_selection", "handover"],
    },
    "connectivity": {
        "name": "Connectivity Test",
        "description": "Test network connectivity and data path",
        "checks": ["dns_resolution", "tcp_connect", "latency", "packet_loss"],
    },
}


async def run_test(
    db: AsyncSession,
    test: InfraTest,
    triggered_by: str = "manual",
) -> InfraTestResult:
    """Execute an infrastructure test and record the result.

    In a production deployment, each test type would integrate with
    the actual device/network APIs.  This implementation provides the
    framework: it creates the result record, runs simulated checks,
    and updates the test's last_run metadata.
    """
    now = datetime.now(timezone.utc)
    result_id = f"tr-{uuid.uuid4().hex[:12]}"

    result = InfraTestResult(
        result_id=result_id,
        test_id=test.test_id,
        tenant_id=test.tenant_id,
        site_id=test.site_id,
        device_id=test.device_id,
        status="running",
        started_at=now,
        triggered_by=triggered_by,
    )
    db.add(result)

    # Run checks based on test type
    test_def = TEST_TYPES.get(test.test_type, {})
    checks = test_def.get("checks", [])
    check_results = {}
    all_passed = True

    for check in checks:
        passed = await _execute_check(db, test, check)
        check_results[check] = "pass" if passed else "fail"
        if not passed:
            all_passed = False

    # If test targets a specific device, validate device exists and is active
    if test.device_id:
        device = (await db.execute(
            select(Device).where(
                Device.device_id == test.device_id,
                Device.tenant_id == test.tenant_id,
            )
        )).scalar_one_or_none()
        if not device or device.status != "active":
            all_passed = False
            check_results["device_active"] = "fail"

    completed_at = datetime.now(timezone.utc)
    duration_ms = int((completed_at - now).total_seconds() * 1000)

    result.status = "pass" if all_passed else "fail"
    result.completed_at = completed_at
    result.duration_ms = duration_ms
    result.detail_json = json.dumps({"checks": check_results})

    # Update test metadata
    test.last_run_at = completed_at
    test.last_result = result.status

    return result


async def _execute_check(db: AsyncSession, test: InfraTest, check_name: str) -> bool:
    """Execute a single check within a test.

    In production, this dispatches to device APIs or network probes.
    The framework validates device/site existence and heartbeat state.
    """
    if check_name == "heartbeat_received" and test.device_id:
        device = (await db.execute(
            select(Device).where(Device.device_id == test.device_id)
        )).scalar_one_or_none()
        if device and device.last_heartbeat:
            age = (datetime.now(timezone.utc) - device.last_heartbeat).total_seconds()
            interval = (device.heartbeat_interval or 300) * 3
            return age < interval
        return False

    if check_name == "signal_strength" and test.device_id:
        device = (await db.execute(
            select(Device).where(Device.device_id == test.device_id)
        )).scalar_one_or_none()
        if device and device.network_status:
            return device.network_status.lower() not in ("disconnected", "not_registered")
        return True

    # Default: pass (real implementation would probe actual hardware)
    return True


async def create_verification_from_result(
    db: AsyncSession,
    result: InfraTestResult,
    test: InfraTest,
) -> None:
    """If a test fails, create a verification task for follow-up."""
    if result.status != "fail":
        return

    task = VerificationTask(
        tenant_id=result.tenant_id,
        site_id=result.site_id or "unknown",
        task_type="infra_test_followup",
        title=f"Failed: {test.name}",
        description=f"Infrastructure test '{test.name}' ({test.test_type}) failed. "
                     f"Result: {result.result_id}. Review and remediate.",
        system_category="network",
        status="pending",
        priority="high",
        created_by="system",
    )
    db.add(task)
