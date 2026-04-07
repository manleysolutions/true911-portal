"""Subscriber Import Router — guided CSV import for service lines.

Endpoints:
  POST /subscriber-import/preview           Parse CSV, validate, return preview
  POST /subscriber-import/commit            Commit import to DB
  GET  /subscriber-import/template-csv      Download CSV template
  GET  /subscriber-import/batches           List import batches
  GET  /subscriber-import/batches/{id}/rows Batch row detail
  GET  /subscriber-import/verify            Per-customer verification summary
  GET  /subscriber-import/verify/site/{id}  Site drill-down
  POST /subscriber-import/correct/reassign-line      Reassign line to device
  POST /subscriber-import/correct/reassign-device    Reassign device to site
  POST /subscriber-import/correct/merge-sites        Merge duplicate sites
  POST /subscriber-import/correct/merge-devices      Merge duplicate devices
  POST /subscriber-import/correct/reconciliation     Update reconciliation status
  PATCH /subscriber-import/correct/line/{line_id}    Edit line fields
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.audit_log_entry import AuditLogEntry
from ..models.user import User
from ..models.line import Line
from ..models.site import Site
from ..schemas.subscriber_import import (
    SubscriberPreviewResponse, SubscriberPreviewSummary, SubscriberRowPreview,
    SubscriberCommitResponse, SubscriberCommitSummary,
    CustomerVerificationSummary, SiteVerificationDetail,
    ImportBatchSummary, ImportRowDetail,
    ReassignLineRequest, ReassignDeviceRequest,
    MergeSitesRequest, MergeDevicesRequest,
    UpdateReconciliationRequest, UpdateLineRequest,
)
from ..services.subscriber_import_engine import (
    preview_import, commit_import, generate_subscriber_template_csv,
    get_verification_summary, get_site_detail,
    get_import_batches, get_batch_rows,
    reassign_line_to_device, reassign_device_to_site,
    merge_duplicate_sites, merge_duplicate_devices,
    update_reconciliation_status,
)

router = APIRouter()


# ── Preview & Commit ───────────────────────────────────────────────

@router.post("/subscriber-import/preview", response_model=SubscriberPreviewResponse)
async def import_preview(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Upload CSV and return a detailed preview of what will happen."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    csv_text = content.decode("utf-8-sig", errors="replace")

    result = await preview_import(db, csv_text, current_user.tenant_id)

    return SubscriberPreviewResponse(
        total_rows=result["total_rows"],
        summary=SubscriberPreviewSummary(**(result.get("summary", {}))),
        rows=[SubscriberRowPreview(**r) for r in result["rows"]],
        has_errors=result["has_errors"],
    )


@router.post("/subscriber-import/commit", response_model=SubscriberCommitResponse)
async def import_commit(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Upload CSV and commit the import."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    csv_text = content.decode("utf-8-sig", errors="replace")

    result = await commit_import(
        db, csv_text, current_user.tenant_id,
        current_user.email, file.filename,
    )

    # Audit log the import
    summary_data = result.get("summary", {})
    audit = AuditLogEntry(
        entry_id=f"import-subscriber-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        category="import",
        action="subscriber_import_commit",
        actor=current_user.email,
        target_type="line",
        summary=f"Subscriber import committed by {current_user.email} — {result.get('total_rows', 0)} rows, batch {result.get('batch_id', 'unknown')}",
        detail_json=json.dumps({
            "import_type": "subscriber",
            "user_role": current_user.role,
            "batch_id": result.get("batch_id"),
            "total_rows": result.get("total_rows", 0),
            "summary": summary_data,
            "error_count": len(result.get("errors", [])),
            "filename": file.filename,
        }),
    )
    db.add(audit)
    await db.commit()

    return SubscriberCommitResponse(
        batch_id=result["batch_id"],
        summary=SubscriberCommitSummary(**(result.get("summary", {}))),
        errors=result["errors"],
        total_rows=result["total_rows"],
    )


# ── Template ───────────────────────────────────────────────────────

@router.get("/subscriber-import/template-csv")
async def get_template(
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Download the subscriber import CSV template."""
    csv_data = generate_subscriber_template_csv()
    return PlainTextResponse(
        csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=subscriber_import_template.csv"},
    )


# ── Batch History ──────────────────────────────────────────────────

@router.get("/subscriber-import/batches", response_model=list[ImportBatchSummary])
async def list_batches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """List all import batches."""
    batches = await get_import_batches(db, current_user.tenant_id)
    return [ImportBatchSummary(**b) for b in batches]


@router.get("/subscriber-import/batches/{batch_id}/rows", response_model=list[ImportRowDetail])
async def list_batch_rows(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Get row-level detail for a specific batch."""
    rows = await get_batch_rows(db, batch_id)
    return [ImportRowDetail(**r) for r in rows]


# ── Verification ───────────────────────────────────────────────────

@router.get("/subscriber-import/verify/customer-sites")
async def customer_sites(
    customer_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Get sites for a specific customer name."""
    q = await db.execute(
        select(Site).where(
            and_(Site.tenant_id == current_user.tenant_id, Site.customer_name == customer_name)
        )
    )
    sites = q.scalars().all()
    return [
        {
            "site_id": s.site_id,
            "site_name": s.site_name,
            "customer_name": s.customer_name,
            "e911_street": s.e911_street,
            "e911_city": s.e911_city,
            "e911_state": s.e911_state,
            "e911_zip": s.e911_zip,
            "status": s.status,
            "reconciliation_status": s.reconciliation_status,
        }
        for s in sites
    ]


@router.get("/subscriber-import/verify", response_model=list[CustomerVerificationSummary])
async def verification_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Per-customer verification summary."""
    data = await get_verification_summary(db, current_user.tenant_id)
    return [CustomerVerificationSummary(**d) for d in data]


@router.get("/subscriber-import/verify/site/{site_id}", response_model=SiteVerificationDetail)
async def site_verification_detail(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Site drill-down with devices, lines, and warnings."""
    detail = await get_site_detail(db, current_user.tenant_id, site_id)
    if not detail:
        raise HTTPException(404, "Site not found")
    return SiteVerificationDetail(**detail)


# ── Correction Tools ──────────────────────────────────────────────

@router.post("/subscriber-import/correct/reassign-line")
async def correct_reassign_line(
    body: ReassignLineRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Move a line to a different device."""
    result = await reassign_line_to_device(db, current_user.tenant_id, body.line_id, body.new_device_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.post("/subscriber-import/correct/reassign-device")
async def correct_reassign_device(
    body: ReassignDeviceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Move a device to a different site."""
    result = await reassign_device_to_site(db, current_user.tenant_id, body.device_id, body.new_site_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.post("/subscriber-import/correct/merge-sites")
async def correct_merge_sites(
    body: MergeSitesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Merge a duplicate site into the keeper site."""
    result = await merge_duplicate_sites(db, current_user.tenant_id, body.keep_site_id, body.merge_site_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.post("/subscriber-import/correct/merge-devices")
async def correct_merge_devices(
    body: MergeDevicesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Merge a duplicate device into the keeper device."""
    result = await merge_duplicate_devices(db, current_user.tenant_id, body.keep_device_id, body.merge_device_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.post("/subscriber-import/correct/reconciliation")
async def correct_reconciliation(
    body: UpdateReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Update reconciliation status on a line, device, or site."""
    result = await update_reconciliation_status(
        db, current_user.tenant_id, body.entity_type, body.entity_id, body.status,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.patch("/subscriber-import/correct/line/{line_id}")
async def correct_line_fields(
    line_id: str,
    body: UpdateLineRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("SUBSCRIBER_IMPORT")),
):
    """Edit line fields (SIM, MSISDN, carrier, etc.)."""
    q = await db.execute(
        select(Line).where(and_(Line.tenant_id == current_user.tenant_id, Line.line_id == line_id))
    )
    line = q.scalars().first()
    if not line:
        raise HTTPException(404, "Line not found")

    if body.did is not None:
        line.did = body.did
    if body.sim_iccid is not None:
        line.sim_iccid = body.sim_iccid
    if body.carrier is not None:
        line.carrier = body.carrier
    if body.line_type is not None:
        line.line_type = body.line_type
    if body.qb_description is not None:
        line.qb_description = body.qb_description
    if body.notes is not None:
        line.notes = body.notes

    await db.commit()
    return {"success": True, "line_id": line_id}
