"""Command Testing Router — infrastructure test CRUD, execution, audit export.

Endpoints:
  GET    /infra-tests                   List tests
  POST   /infra-tests                   Create test
  PUT    /infra-tests/{test_id}         Update test
  DELETE /infra-tests/{test_id}         Delete test
  POST   /infra-tests/{test_id}/run     Execute test
  GET    /infra-tests/{test_id}/results Test results history
  GET    /audit-log                     List audit entries
  GET    /audit-log/export              Export audit CSV
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.infra_test import InfraTest
from app.models.infra_test_result import InfraTestResult
from app.models.audit_log_entry import AuditLogEntry
from app.routers.auth import get_current_user
from app.services.rbac import can
from app.services.infra_test_engine import run_test, create_verification_from_result
from app.services.audit_logger import log_audit, export_audit_csv
from app.schemas.command_phase7 import (
    InfraTestCreate,
    InfraTestUpdate,
    InfraTestOut,
    InfraTestResultOut,
    RunTestRequest,
    AuditLogEntryOut,
)

router = APIRouter()


# ── Infrastructure Test CRUD ────────────────────────────────────────

@router.get("/infra-tests", response_model=list[InfraTestOut])
async def list_infra_tests(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    test_type: str | None = None,
    site_id: str | None = None,
    enabled: bool | None = None,
):
    if not can(user.role, "COMMAND_VIEW_INFRA_TESTS"):
        raise HTTPException(403, "Not authorized")

    q = select(InfraTest).where(
        InfraTest.tenant_id == user.tenant_id,
    ).order_by(InfraTest.created_at.desc())

    if test_type:
        q = q.where(InfraTest.test_type == test_type)
    if site_id:
        q = q.where(InfraTest.site_id == site_id)
    if enabled is not None:
        q = q.where(InfraTest.enabled == enabled)

    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/infra-tests", response_model=InfraTestOut)
async def create_infra_test(
    payload: InfraTestCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_MANAGE_INFRA_TESTS"):
        raise HTTPException(403, "Not authorized")

    test = InfraTest(
        test_id=f"it-{uuid.uuid4().hex[:12]}",
        tenant_id=user.tenant_id,
        name=payload.name,
        test_type=payload.test_type,
        description=payload.description,
        site_id=payload.site_id,
        device_id=payload.device_id,
        schedule_cron=payload.schedule_cron,
        run_after_provision=payload.run_after_provision,
        config_json=payload.config_json,
    )
    db.add(test)

    await log_audit(
        db, user.tenant_id, "config", "infra_test_created",
        f"Infrastructure test '{payload.name}' created ({payload.test_type})",
        actor=user.email, site_id=payload.site_id, device_id=payload.device_id,
    )
    await db.commit()
    await db.refresh(test)
    return test


@router.put("/infra-tests/{test_pk}", response_model=InfraTestOut)
async def update_infra_test(
    test_pk: int,
    payload: InfraTestUpdate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_MANAGE_INFRA_TESTS"):
        raise HTTPException(403, "Not authorized")

    test = (await db.execute(
        select(InfraTest).where(InfraTest.id == test_pk, InfraTest.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not test:
        raise HTTPException(404, "Test not found")

    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(test, field, val)

    test.updated_at = datetime.now(timezone.utc)

    await log_audit(
        db, user.tenant_id, "config", "infra_test_updated",
        f"Infrastructure test '{test.name}' updated",
        actor=user.email, target_type="infra_test", target_id=test.test_id,
    )
    await db.commit()
    await db.refresh(test)
    return test


@router.delete("/infra-tests/{test_pk}")
async def delete_infra_test(
    test_pk: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_MANAGE_INFRA_TESTS"):
        raise HTTPException(403, "Not authorized")

    test = (await db.execute(
        select(InfraTest).where(InfraTest.id == test_pk, InfraTest.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not test:
        raise HTTPException(404, "Test not found")

    await log_audit(
        db, user.tenant_id, "config", "infra_test_deleted",
        f"Infrastructure test '{test.name}' deleted",
        actor=user.email, target_type="infra_test", target_id=test.test_id,
    )
    await db.delete(test)
    await db.commit()
    return {"status": "deleted"}


# ── Test Execution ──────────────────────────────────────────────────

@router.post("/infra-tests/{test_pk}/run", response_model=InfraTestResultOut)
async def execute_infra_test(
    test_pk: int,
    body: RunTestRequest = RunTestRequest(),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_RUN_INFRA_TESTS"):
        raise HTTPException(403, "Not authorized")

    test = (await db.execute(
        select(InfraTest).where(InfraTest.id == test_pk, InfraTest.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not test:
        raise HTTPException(404, "Test not found")

    result = await run_test(db, test, triggered_by=body.triggered_by)
    await create_verification_from_result(db, result, test)

    await log_audit(
        db, user.tenant_id, "verification", "infra_test_executed",
        f"Test '{test.name}' executed — result: {result.status}",
        actor=user.email, target_type="infra_test", target_id=test.test_id,
        site_id=test.site_id, device_id=test.device_id,
        detail={"result_id": result.result_id, "status": result.status},
    )
    await db.commit()
    await db.refresh(result)
    return result


@router.get("/infra-tests/{test_pk}/results", response_model=list[InfraTestResultOut])
async def list_test_results(
    test_pk: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
):
    if not can(user.role, "COMMAND_VIEW_INFRA_TESTS"):
        raise HTTPException(403, "Not authorized")

    test = (await db.execute(
        select(InfraTest).where(InfraTest.id == test_pk, InfraTest.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not test:
        raise HTTPException(404, "Test not found")

    rows = (await db.execute(
        select(InfraTestResult).where(
            InfraTestResult.test_id == test.test_id,
        ).order_by(InfraTestResult.created_at.desc()).limit(limit)
    )).scalars().all()
    return rows


# ── Audit Log ───────────────────────────────────────────────────────

@router.get("/audit-log", response_model=list[AuditLogEntryOut])
async def list_audit_log(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    category: str | None = None,
    target_type: str | None = None,
    site_id: str | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    if not can(user.role, "COMMAND_VIEW_AUDIT"):
        raise HTTPException(403, "Not authorized")

    q = select(AuditLogEntry).where(
        AuditLogEntry.tenant_id == user.tenant_id,
    ).order_by(AuditLogEntry.created_at.desc())

    if category:
        q = q.where(AuditLogEntry.category == category)
    if target_type:
        q = q.where(AuditLogEntry.target_type == target_type)
    if site_id:
        q = q.where(AuditLogEntry.site_id == site_id)

    q = q.offset(offset).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.get("/audit-log/export")
async def export_audit_log(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    category: str | None = None,
):
    if not can(user.role, "COMMAND_EXPORT_AUDIT"):
        raise HTTPException(403, "Not authorized")

    csv_data = await export_audit_csv(db, user.tenant_id, category=category)

    await log_audit(
        db, user.tenant_id, "config", "audit_log_exported",
        f"Audit log exported (category={category or 'all'})",
        actor=user.email,
    )
    await db.commit()

    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
