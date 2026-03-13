"""Command Device Assignment Router — CSV-based bulk device-to-site assignment.

Endpoints:
  POST /device-assignment/preview        Parse CSV and return match preview (no DB writes)
  POST /device-assignment/commit         Commit matched assignments to DB
  GET  /device-assignment/template-csv   Download CSV template with example rows
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.user import User
from ..services.device_assignment_engine import (
    preview_assignment,
    commit_assignment,
    generate_assignment_template_csv,
)

router = APIRouter()


@router.post("/device-assignment/preview")
async def assignment_preview(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Upload CSV and return a preview of device-to-site matches."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    csv_text = content.decode("utf-8-sig", errors="replace")

    result = await preview_assignment(db, csv_text, current_user.tenant_id)
    return result


@router.post("/device-assignment/commit")
async def assignment_commit(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Upload CSV and commit device-to-site assignments."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    csv_text = content.decode("utf-8-sig", errors="replace")

    result = await commit_assignment(
        db, csv_text, current_user.tenant_id, current_user.email,
    )
    await db.commit()
    return result


@router.get("/device-assignment/template-csv")
async def get_assignment_template(
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Download the CSV template for bulk device assignment."""
    csv_data = generate_assignment_template_csv()
    return PlainTextResponse(
        csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=device_assignment_template.csv"
        },
    )
