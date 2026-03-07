"""
True911 Command — Site templates and bulk import.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.site_template import SiteTemplate
from ..models.site import Site
from ..models.user import User
from ..schemas.command_phase5 import (
    SiteTemplateCreate, SiteTemplateUpdate, SiteTemplateOut,
    BulkImportResult,
)
from ..services.template_engine import apply_template
from ..services.csv_importer import import_sites_from_csv

router = APIRouter()


# ---------------------------------------------------------------------------
# Site Templates CRUD
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=list[SiteTemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all templates available to this tenant (own + global)."""
    q = select(SiteTemplate).where(
        (SiteTemplate.tenant_id == current_user.tenant_id)
        | (SiteTemplate.is_global == True)  # noqa: E712
    ).order_by(SiteTemplate.name)
    result = await db.execute(q)
    return [SiteTemplateOut.model_validate(t) for t in result.scalars().all()]


@router.get("/templates/{template_id}", response_model=SiteTemplateOut)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(SiteTemplate).where(
            SiteTemplate.id == template_id,
            (SiteTemplate.tenant_id == current_user.tenant_id) | (SiteTemplate.is_global == True),  # noqa: E712
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")
    return SiteTemplateOut.model_validate(template)


@router.post("/templates", response_model=SiteTemplateOut)
async def create_template(
    body: SiteTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_TEMPLATES")),
):
    template = SiteTemplate(
        tenant_id=current_user.tenant_id,
        name=body.name,
        description=body.description,
        building_type=body.building_type,
        systems_json=body.systems_json,
        verification_tasks_json=body.verification_tasks_json,
        monitoring_rules_json=body.monitoring_rules_json,
        readiness_weights_json=body.readiness_weights_json,
        is_global=body.is_global and current_user.role == "SuperAdmin",
        created_by=current_user.email,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return SiteTemplateOut.model_validate(template)


@router.put("/templates/{template_id}", response_model=SiteTemplateOut)
async def update_template(
    template_id: int,
    body: SiteTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_TEMPLATES")),
):
    result = await db.execute(
        select(SiteTemplate).where(
            SiteTemplate.id == template_id,
            SiteTemplate.tenant_id == current_user.tenant_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(template, field, val)
    template.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(template)
    return SiteTemplateOut.model_validate(template)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_TEMPLATES")),
):
    result = await db.execute(
        select(SiteTemplate).where(
            SiteTemplate.id == template_id,
            SiteTemplate.tenant_id == current_user.tenant_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")
    await db.delete(template)
    await db.commit()
    return {"deleted": template_id}


# ---------------------------------------------------------------------------
# Apply template to existing site
# ---------------------------------------------------------------------------

@router.post("/site/{site_id}/apply-template/{template_id}")
async def apply_template_to_site(
    site_id: str,
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_TEMPLATES")),
):
    """Apply a template to an existing site, creating verification tasks and rules."""
    # Verify site
    site_q = await db.execute(
        select(Site).where(Site.tenant_id == current_user.tenant_id, Site.site_id == site_id)
    )
    site = site_q.scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Site not found")

    # Verify template
    tmpl_q = await db.execute(
        select(SiteTemplate).where(
            SiteTemplate.id == template_id,
            (SiteTemplate.tenant_id == current_user.tenant_id) | (SiteTemplate.is_global == True),  # noqa: E712
        )
    )
    template = tmpl_q.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "Template not found")

    site.template_id = template.id
    site.building_type = site.building_type or template.building_type

    results = await apply_template(db, template, site_id, current_user.tenant_id, current_user.email)
    await db.commit()

    return {"status": "ok", "site_id": site_id, "template": template.name, **results}


# ---------------------------------------------------------------------------
# Bulk CSV Import
# ---------------------------------------------------------------------------

@router.post("/bulk-import", response_model=BulkImportResult)
async def bulk_import_sites(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_BULK_IMPORT")),
):
    """Import sites from a CSV file."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    csv_text = content.decode("utf-8-sig", errors="replace")

    try:
        result = await import_sites_from_csv(
            db, csv_text, current_user.tenant_id, current_user.email,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Import failed: {str(e)[:300]}")

    return BulkImportResult(**result)


@router.get("/bulk-import/template-csv")
async def get_csv_template():
    """Return a CSV template for bulk import."""
    headers = "site_name,site_id,customer_name,e911_street,e911_city,e911_state,e911_zip,building_type,device_type,manufacturer,device_model,device_serial,imei,sim_iccid,phone_number,mac_address,sim_id,carrier,firmware_version,activated_at,term_end_date,poc_name,poc_phone,poc_email,notes"
    example = 'RH Gallery Dallas,RH-DAL-001,Restoration Hardware,8300 NorthPark Center,Dallas,TX,75225,retail,FACP,Napco,StarLink SLE,SL-SN-00001,352656100123456,8901260882310000001,+12145559001,AA:BB:CC:DD:EE:01,NAP-DEV-001,T-Mobile,3.8.0,2024-06-15,,Mike Torres,+12145550100,mike@rh.com,Main lobby FACP communicator'
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        f"{headers}\n{example}\n",
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bulk_import_template.csv"},
    )
