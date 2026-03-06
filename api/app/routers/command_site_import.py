"""Command Site Import Router — CSV-based site + system onboarding.

Endpoints:
  POST /site-import/preview       Parse CSV and return preview (no DB writes)
  POST /site-import/commit        Commit previewed import to DB
  GET  /site-import/template-csv  Download CSV template with example rows
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.user import User
from ..schemas.site_import import ImportPreviewSummary, ImportCommitResult
from ..services.site_import_engine import preview_import, commit_import, generate_template_csv

router = APIRouter()


@router.post("/site-import/preview", response_model=ImportPreviewSummary)
async def import_preview(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_SITE_IMPORT")),
):
    """Upload CSV and return a preview of what will be created."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    csv_text = content.decode("utf-8-sig", errors="replace")

    result = await preview_import(db, csv_text, current_user.tenant_id)
    return ImportPreviewSummary(**result)


@router.post("/site-import/commit", response_model=ImportCommitResult)
async def import_commit(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_SITE_IMPORT")),
):
    """Upload CSV and commit the import (creates all records)."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    csv_text = content.decode("utf-8-sig", errors="replace")

    result = await commit_import(db, csv_text, current_user.tenant_id, current_user.email)
    await db.commit()
    return ImportCommitResult(**result)


@router.get("/site-import/template-csv")
async def get_import_template(
    current_user: User = Depends(require_permission("COMMAND_SITE_IMPORT")),
):
    """Download the CSV template with headers and example rows."""
    csv_data = generate_template_csv()
    return PlainTextResponse(
        csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=site_import_template.csv"},
    )
