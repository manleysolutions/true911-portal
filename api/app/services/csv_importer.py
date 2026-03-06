"""
True911 — Bulk CSV site importer.

Parses CSV data and creates sites with optional template application.
"""

import csv
import io
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.site import Site
from ..models.site_template import SiteTemplate
from ..models.command_activity import CommandActivity
from .template_engine import apply_template


REQUIRED_COLUMNS = {"site_name"}
OPTIONAL_COLUMNS = {
    "site_id", "customer_name", "e911_street", "e911_city", "e911_state",
    "e911_zip", "building_type", "kit_type", "template_name", "status",
    "poc_name", "poc_phone", "poc_email", "notes",
}


async def import_sites_from_csv(
    db: AsyncSession,
    csv_text: str,
    tenant_id: str,
    created_by: str,
) -> dict:
    """Parse CSV text and create sites. Returns import summary."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return {"total_rows": 0, "created": 0, "skipped": 0, "errors": ["Empty CSV or no header row"]}

    # Validate headers
    headers = set(reader.fieldnames)
    missing = REQUIRED_COLUMNS - headers
    if missing:
        return {"total_rows": 0, "created": 0, "skipped": 0, "errors": [f"Missing required columns: {', '.join(missing)}"]}

    # Load existing site IDs for duplicate check
    existing_q = await db.execute(
        select(Site.site_id).where(Site.tenant_id == tenant_id)
    )
    existing_ids = set(r[0] for r in existing_q.all())

    # Load templates for matching
    templates_q = await db.execute(
        select(SiteTemplate).where(
            (SiteTemplate.tenant_id == tenant_id) | (SiteTemplate.is_global == True)  # noqa: E712
        )
    )
    templates_by_name = {t.name.lower(): t for t in templates_q.scalars().all()}

    rows = list(reader)
    created = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows, 1):
        site_name = (row.get("site_name") or "").strip()
        if not site_name:
            errors.append(f"Row {i}: missing site_name")
            skipped += 1
            continue

        site_id = (row.get("site_id") or "").strip()
        if not site_id:
            site_id = f"SITE-{uuid.uuid4().hex[:8].upper()}"

        if site_id in existing_ids:
            errors.append(f"Row {i}: site_id '{site_id}' already exists, skipped")
            skipped += 1
            continue

        building_type = (row.get("building_type") or "").strip() or None
        template_name = (row.get("template_name") or "").strip().lower()

        site = Site(
            site_id=site_id,
            tenant_id=tenant_id,
            site_name=site_name,
            customer_name=(row.get("customer_name") or "").strip() or site_name,
            status=(row.get("status") or "").strip() or "Not Connected",
            e911_street=(row.get("e911_street") or "").strip() or None,
            e911_city=(row.get("e911_city") or "").strip() or None,
            e911_state=(row.get("e911_state") or "").strip() or None,
            e911_zip=(row.get("e911_zip") or "").strip() or None,
            kit_type=(row.get("kit_type") or "").strip() or None,
            building_type=building_type,
            poc_name=(row.get("poc_name") or "").strip() or None,
            poc_phone=(row.get("poc_phone") or "").strip() or None,
            poc_email=(row.get("poc_email") or "").strip() or None,
            notes=(row.get("notes") or "").strip() or None,
            onboarding_status="onboarding",
        )
        db.add(site)
        existing_ids.add(site_id)
        created += 1

        # Apply template if specified
        if template_name and template_name in templates_by_name:
            template = templates_by_name[template_name]
            site.template_id = template.id
            site.building_type = site.building_type or template.building_type
            await apply_template(db, template, site_id, tenant_id, created_by)

    if created > 0:
        db.add(CommandActivity(
            tenant_id=tenant_id,
            activity_type="bulk_import",
            actor=created_by,
            summary=f"Bulk import: {created} sites created from CSV ({skipped} skipped)",
        ))

    return {
        "total_rows": len(rows),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }
