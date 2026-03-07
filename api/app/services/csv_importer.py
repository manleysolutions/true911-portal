"""
True911 — Bulk CSV site importer.

Parses CSV data and creates sites with optional template application.
"""

import csv
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.device import Device
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
    # Device columns
    "manufacturer", "device_serial", "device_model", "device_type",
    "carrier", "sim_iccid", "iccid", "phone_number", "firmware_version",
    "imei", "msisdn", "mac_address", "sim_id",
    "activated_at", "term_end_date",
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
    devices_created = 0
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

        # ── Device field extraction ──
        device_serial = (row.get("device_serial") or "").strip()
        device_model = (row.get("device_model") or "").strip()
        manufacturer = (row.get("manufacturer") or "").strip()
        device_type = (row.get("device_type") or row.get("kit_type") or "").strip()
        dev_imei = (row.get("imei") or "").strip()
        dev_iccid = (row.get("sim_iccid") or row.get("iccid") or "").strip()
        dev_msisdn = (row.get("phone_number") or row.get("msisdn") or "").strip()
        dev_mac = (row.get("mac_address") or "").strip()
        dev_sim_id = (row.get("sim_id") or "").strip()
        dev_carrier = (row.get("carrier") or "").strip()

        # Parse activation date and auto-calculate 3-year term end
        activated_at = None
        term_end_date = None
        raw_activated = (row.get("activated_at") or "").strip()
        raw_term_end = (row.get("term_end_date") or "").strip()
        if raw_activated:
            try:
                activated_at = date.fromisoformat(raw_activated)
            except ValueError:
                try:
                    activated_at = datetime.strptime(raw_activated, "%m/%d/%Y").date()
                except ValueError:
                    pass
        if raw_term_end:
            try:
                term_end_date = date.fromisoformat(raw_term_end)
            except ValueError:
                try:
                    term_end_date = datetime.strptime(raw_term_end, "%m/%d/%Y").date()
                except ValueError:
                    pass
        elif activated_at:
            # Auto-calculate 3-year term from activation date
            term_end_date = activated_at + timedelta(days=1095)

        # Create device if ANY device-related column has data
        has_device_data = (
            device_serial or device_model or manufacturer
            or dev_imei or dev_iccid or dev_msisdn or dev_mac or dev_sim_id
        )
        if has_device_data:
            device_id_val = f"DEV-{uuid.uuid4().hex[:8].upper()}"
            try:
                device = Device(
                    device_id=device_id_val,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    status="active",
                    device_type=device_type or None,
                    manufacturer=manufacturer or None,
                    model=device_model or None,
                    serial_number=device_serial or None,
                    mac_address=dev_mac or None,
                    imei=dev_imei or None,
                    iccid=dev_iccid or None,
                    msisdn=dev_msisdn or None,
                    carrier=dev_carrier or None,
                    firmware_version=(row.get("firmware_version") or "").strip() or None,
                    sim_id=dev_sim_id or None,
                    activated_at=activated_at,
                    term_end_date=term_end_date,
                    notes=f"Imported with site {site_name}",
                )
                db.add(device)
                devices_created += 1
            except Exception as e:
                errors.append(f"Row {i}: device creation failed: {str(e)[:100]}")

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
        "devices_created": devices_created,
        "errors": errors,
    }
