"""
True911 — Bulk CSV site importer.

Parses CSV data and creates sites with optional template application.
"""

import csv
import io
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.site import Site
from ..models.site_template import SiteTemplate
from ..models.command_activity import CommandActivity
from .template_engine import apply_template


REQUIRED_COLUMNS = {"site_name"}
# Zoho-style column aliases that can substitute for site_name
SITE_NAME_ALIASES = ["location_name", "customer_name", "subscription_id"]
OPTIONAL_COLUMNS = {
    "site_id", "customer_name", "e911_street", "e911_city", "e911_state",
    "e911_zip", "building_type", "kit_type", "template_name", "status",
    "poc_name", "poc_phone", "poc_email", "notes",
    "location_name", "subscription_id", "metadata",
}


def _resolve_site_name(row: dict) -> str:
    """Resolve a readable site name from CSV row using priority:
    location_name > customer_name > site_name > subscription_id.

    If the best value looks numeric (e.g. a Zoho subscription_id was used as
    site_name), check the metadata JSON for a readable name instead.
    """
    # Normalize keys for lookup
    normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}

    # Priority order: location_name > site_name > customer_name > subscription_id
    name = (
        normalized.get("location_name")
        or normalized.get("site_name")
        or normalized.get("customer_name")
        or ""
    )

    # If the resolved name looks like a numeric ID, try all remaining sources
    if name and _looks_numeric(name):
        # Try any alias column that has a non-numeric value
        for col in ("location_name", "site_name", "customer_name"):
            val = normalized.get(col, "")
            if val and not _looks_numeric(val):
                return val
        # Try metadata JSON
        readable = _extract_name_from_metadata(normalized)
        if readable:
            return readable

    # Last resort: subscription_id (but only if we have nothing else)
    if not name:
        name = normalized.get("subscription_id", "")
        # If that's also numeric, still try metadata
        if name and _looks_numeric(name):
            readable = _extract_name_from_metadata(normalized)
            if readable:
                return readable

    return name


def _looks_numeric(val: str) -> bool:
    """Return True if value looks like a bare numeric ID (not a real name)."""
    cleaned = val.replace("-", "").replace("_", "").replace(" ", "")
    return cleaned.isdigit()


def _extract_name_from_metadata(row: dict) -> str:
    """Try to pull a readable name from a metadata/JSON column."""
    raw = row.get("metadata") or row.get("metadata_json") or row.get("extra") or ""
    if not raw:
        return ""
    try:
        meta = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(meta, dict):
        return ""
    # Check common Zoho field names for a readable location/customer name
    for key in ("location_name", "Location_Name", "customer_name", "Customer_Name",
                "name", "Name", "site_name", "Site_Name", "account_name", "Account_Name"):
        val = meta.get(key, "")
        if val and isinstance(val, str) and val.strip() and not _looks_numeric(val.strip()):
            return val.strip()
    return ""


def _resolve_customer_name(row: dict) -> str:
    """Resolve customer_name, preferring readable values over numeric IDs."""
    normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    name = normalized.get("customer_name", "")
    if name and not _looks_numeric(name):
        return name
    # Try location_name as fallback for customer_name too
    alt = normalized.get("location_name", "")
    if alt and not _looks_numeric(alt):
        return alt
    readable = _extract_name_from_metadata(normalized)
    return readable or name


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

    # Validate headers — accept Zoho aliases for site_name
    headers = {h.strip().lower() for h in reader.fieldnames if h}
    has_site_name = "site_name" in headers or any(alias in headers for alias in SITE_NAME_ALIASES)
    if not has_site_name:
        return {"total_rows": 0, "created": 0, "skipped": 0, "errors": ["Missing required column: site_name (or location_name, customer_name, subscription_id)"]}

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
        site_name = _resolve_site_name(row)
        if not site_name:
            errors.append(f"Row {i}: missing site_name (and no location_name/customer_name fallback)")
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
            customer_name=_resolve_customer_name(row) or site_name,
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
