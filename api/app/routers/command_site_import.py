"""Command Site Import Router — CSV-based site + system onboarding.

Endpoints:
  POST /site-import/preview              Parse CSV and return preview (no DB writes)
  POST /site-import/commit               Commit previewed import to DB
  GET  /site-import/template-csv         Download CSV template with example rows
  POST /site-import/enrich               Address enrichment — returns summary + 3 CSVs
  POST /site-import/enrich/main-csv      Download enriched main CSV
  POST /site-import/enrich/review-csv    Download review-needed CSV
  POST /site-import/enrich/confirm-csv   Download E911-confirmation-needed CSV
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.user import User
from ..schemas.site_import import ImportPreviewSummary, ImportCommitResult
from ..services.site_import_engine import preview_import, commit_import, generate_template_csv
from ..services.address_enrichment import (
    enrich_csv, export_main_csv, export_review_needed_csv,
    export_e911_confirmation_csv, print_summary,
)

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


# ── Address Enrichment Endpoints ──────────────────────────────────────

async def _read_csv_upload(file: UploadFile) -> str:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")
    content = await file.read()
    return content.decode("utf-8-sig", errors="replace")


@router.post("/site-import/enrich")
async def enrich_addresses(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("COMMAND_SITE_IMPORT")),
):
    """Upload CSV and return address enrichment summary (no DB writes)."""
    csv_text = await _read_csv_upload(file)
    rows = enrich_csv(csv_text)
    if not rows:
        raise HTTPException(400, "Empty CSV or no parseable rows")
    summary = print_summary(rows)
    # Include a sample of rows needing action
    action_rows = [
        {
            "row": r.row_number,
            "site_name": r.site_name,
            "address_source": r.address_source,
            "e911_status": r.e911_status,
            "address_notes": r.address_notes,
        }
        for r in rows if r.e911_confirmation_required
    ][:50]  # cap preview at 50
    return {**summary, "action_rows_preview": action_rows}


@router.post("/site-import/enrich/main-csv")
async def enrich_main_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("COMMAND_SITE_IMPORT")),
):
    """Upload CSV, enrich addresses, return the full cleaned CSV."""
    csv_text = await _read_csv_upload(file)
    rows = enrich_csv(csv_text)
    return PlainTextResponse(
        export_main_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=enriched_sites.csv"},
    )


@router.post("/site-import/enrich/review-csv")
async def enrich_review_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("COMMAND_SITE_IMPORT")),
):
    """Upload CSV, return only rows needing address review."""
    csv_text = await _read_csv_upload(file)
    rows = enrich_csv(csv_text)
    output = export_review_needed_csv(rows)
    if not output:
        return PlainTextResponse(
            "No rows need review — all addresses resolved.\n",
            media_type="text/plain",
        )
    return PlainTextResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=review_needed.csv"},
    )


@router.post("/site-import/enrich/confirm-csv")
async def enrich_confirm_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("COMMAND_SITE_IMPORT")),
):
    """Upload CSV, return E911 confirmation worklist."""
    csv_text = await _read_csv_upload(file)
    rows = enrich_csv(csv_text)
    output = export_e911_confirmation_csv(rows)
    if not output:
        return PlainTextResponse(
            "No rows need E911 confirmation — all addresses confirmed.\n",
            media_type="text/plain",
        )
    return PlainTextResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=e911_confirmation_needed.csv"},
    )
