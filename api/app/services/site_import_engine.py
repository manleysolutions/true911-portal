"""
True911 — Site-centric CSV import engine.

Supports multi-system-per-site imports: each CSV row represents one system
at one site. A single site may appear on multiple rows.

Two-phase flow:
  1. preview_import()  — parse, validate, return preview without DB writes
  2. commit_import()   — actually create all records
"""

import csv
import io
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.site import Site
from ..models.device import Device
from ..models.vendor import Vendor
from ..models.site_vendor import SiteVendorAssignment
from ..models.verification_task import VerificationTask
from ..models.command_activity import CommandActivity

# ── Constants ──────────────────────────────────────────────────────────

from .address_enrichment import enrich_row

REQUIRED_COLUMNS = {"site_name", "system_type"}
ALL_COLUMNS = {
    "site_name", "site_code", "address", "city", "state", "zip", "country",
    "building_type", "floors", "elevator_count",
    "system_type", "device_type", "device_model", "carrier",
    "sim_iccid", "phone_number", "device_serial", "firmware_version",
    "vendor_name", "vendor_contact", "vendor_email",
    "verification_frequency", "install_date", "system_priority", "notes",
    # Address enrichment columns
    "service_address", "service_city", "service_state", "service_zip",
    "billing_address", "billing_city", "billing_state", "billing_zip",
    "shipping_address", "shipping_city", "shipping_state", "shipping_zip",
    "suggested_address", "suggested_city", "suggested_state", "suggested_zip",
    "e911_confirmed",
}

VALID_SYSTEM_TYPES = {
    "elevator_phone", "fire_alarm", "fire_alarm_communicator",
    "das_radio", "call_station", "backup_power", "other",
}

VALID_FREQUENCIES = {"monthly", "quarterly", "semiannual", "annual"}

FREQUENCY_DAYS = {
    "monthly": 30,
    "quarterly": 90,
    "semiannual": 182,
    "annual": 365,
}

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP",
}


def _strip(val: str | None) -> str:
    return (val or "").strip()


def _normalize_system_type(raw: str) -> str:
    """Normalize common system type aliases."""
    raw = raw.lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "elevator": "elevator_phone",
        "elev_phone": "elevator_phone",
        "fire": "fire_alarm",
        "fire_communicator": "fire_alarm_communicator",
        "facp": "fire_alarm",
        "das": "das_radio",
        "radio": "das_radio",
        "power": "backup_power",
        "ups": "backup_power",
        "generator": "backup_power",
        "call": "call_station",
    }
    return aliases.get(raw, raw)


def _parse_csv(csv_text: str) -> tuple[list[dict], list[str]]:
    """Parse CSV text and return (rows, header_errors)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return [], ["Empty CSV or no header row"]

    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        return [], [f"Missing required columns: {', '.join(sorted(missing))}"]

    rows = []
    for row in reader:
        cleaned = {k.strip().lower(): _strip(v) for k, v in row.items()}
        rows.append(cleaned)
    return rows, []


# ── Preview ────────────────────────────────────────────────────────────

async def preview_import(
    db: AsyncSession,
    csv_text: str,
    tenant_id: str,
) -> dict:
    """Parse + validate CSV, return preview without writing to DB."""
    rows, header_errors = _parse_csv(csv_text)
    if header_errors:
        return {
            "total_rows": 0,
            "sites_to_create": 0,
            "sites_to_attach": 0,
            "systems_to_create": 0,
            "devices_to_create": 0,
            "vendors_to_create": 0,
            "vendors_to_match": 0,
            "verifications_to_create": 0,
            "rows": [{"row": 0, "action": "skip", "errors": header_errors, "warnings": []}],
            "has_errors": True,
        }

    # Load existing data for duplicate detection
    existing_sites_q = await db.execute(
        select(Site.site_id, Site.site_name, Site.e911_street).where(Site.tenant_id == tenant_id)
    )
    existing_sites = {}
    existing_site_match = {}  # (name_lower, addr_lower) -> site_id
    for sid, sname, saddr in existing_sites_q.all():
        existing_sites[sid] = True
        key = (sname.lower().strip(), (saddr or "").lower().strip())
        existing_site_match[key] = sid

    existing_vendors_q = await db.execute(
        select(Vendor.name).where(Vendor.tenant_id == tenant_id)
    )
    existing_vendor_names = {v[0].lower() for v in existing_vendors_q.all()}

    existing_serials_q = await db.execute(
        select(Device.serial_number).where(
            Device.tenant_id == tenant_id,
            Device.serial_number.isnot(None),
        )
    )
    existing_serials = {s[0].lower() for s in existing_serials_q.all() if s[0]}

    existing_iccids_q = await db.execute(
        select(Device.iccid).where(
            Device.tenant_id == tenant_id,
            Device.iccid.isnot(None),
        )
    )
    existing_iccids = {s[0].lower() for s in existing_iccids_q.all() if s[0]}

    # Track what this import will create (for intra-CSV duplicate detection)
    new_site_codes = set()
    new_site_fallbacks = set()  # (name, addr)
    seen_serials = {}  # serial -> row_num
    seen_iccids = {}  # iccid -> row_num
    new_vendor_names = set()

    row_results = []
    sites_to_create = set()
    sites_to_attach = set()
    systems_count = 0
    devices_count = 0
    vendors_to_create = set()
    vendors_to_match = set()
    verifications_count = 0
    has_errors = False

    for i, row in enumerate(rows, 1):
        errors = []
        warnings = []
        site_name = row.get("site_name", "")
        site_code = row.get("site_code", "")
        system_type_raw = row.get("system_type", "")
        device_serial = row.get("device_serial", "")
        sim_iccid = row.get("sim_iccid", "")
        vendor_name = row.get("vendor_name", "")
        verification_freq = row.get("verification_frequency", "")
        state = row.get("state", "")

        # Required field validation
        if not site_name:
            errors.append("Missing site_name")
        if not system_type_raw:
            errors.append("Missing system_type")

        # Normalize and validate system_type
        system_type = _normalize_system_type(system_type_raw) if system_type_raw else ""
        if system_type_raw and system_type not in VALID_SYSTEM_TYPES:
            errors.append(f"Unrecognized system_type: '{system_type_raw}'")

        # Validate state
        if state and state.upper() not in US_STATES:
            warnings.append(f"Unrecognized state: '{state}'")

        # Validate verification_frequency
        if verification_freq and verification_freq.lower() not in VALID_FREQUENCIES:
            errors.append(f"Unrecognized verification_frequency: '{verification_freq}' (use: monthly, quarterly, semiannual, annual)")

        # Duplicate serial check
        if device_serial:
            serial_lower = device_serial.lower()
            if serial_lower in existing_serials:
                warnings.append(f"Device serial '{device_serial}' already exists in system")
            elif serial_lower in seen_serials:
                warnings.append(f"Duplicate device_serial '{device_serial}' (also on row {seen_serials[serial_lower]})")
            else:
                seen_serials[serial_lower] = i

        # Duplicate ICCID check
        if sim_iccid:
            iccid_lower = sim_iccid.lower()
            if iccid_lower in existing_iccids:
                warnings.append(f"SIM ICCID '{sim_iccid}' already exists in system")
            elif iccid_lower in seen_iccids:
                warnings.append(f"Duplicate sim_iccid '{sim_iccid}' (also on row {seen_iccids[iccid_lower]})")
            else:
                seen_iccids[iccid_lower] = i

        # Determine site action
        action = "skip"
        if not errors:
            address = row.get("address", "")
            if site_code and site_code in existing_sites:
                action = "attach_to_site"
                sites_to_attach.add(site_code)
            elif site_code and site_code in new_site_codes:
                action = "attach_to_site"
                sites_to_attach.add(site_code)
            elif not site_code:
                fallback_key = (site_name.lower(), address.lower())
                if fallback_key in existing_site_match:
                    action = "attach_to_site"
                    sites_to_attach.add(existing_site_match[fallback_key])
                elif fallback_key in new_site_fallbacks:
                    action = "attach_to_site"
                else:
                    action = "create_site"
                    new_site_fallbacks.add(fallback_key)
                    sites_to_create.add(f"{site_name}|{address}")
            else:
                action = "create_site"
                new_site_codes.add(site_code)
                sites_to_create.add(site_code)

            systems_count += 1

            if device_serial or row.get("device_model"):
                devices_count += 1

            if vendor_name:
                if vendor_name.lower() in existing_vendor_names or vendor_name.lower() in new_vendor_names:
                    vendors_to_match.add(vendor_name.lower())
                else:
                    vendors_to_create.add(vendor_name.lower())
                    new_vendor_names.add(vendor_name.lower())

            if verification_freq and verification_freq.lower() in VALID_FREQUENCIES:
                verifications_count += 1
        else:
            has_errors = True

        row_results.append({
            "row": i,
            "site_name": site_name or None,
            "site_code": site_code or None,
            "system_type": system_type or None,
            "device_serial": device_serial or None,
            "action": action,
            "errors": errors,
            "warnings": warnings,
        })

    return {
        "total_rows": len(rows),
        "sites_to_create": len(sites_to_create),
        "sites_to_attach": len(sites_to_attach),
        "systems_to_create": systems_count,
        "devices_to_create": devices_count,
        "vendors_to_create": len(vendors_to_create),
        "vendors_to_match": len(vendors_to_match),
        "verifications_to_create": verifications_count,
        "rows": row_results,
        "has_errors": has_errors,
    }


# ── Commit ─────────────────────────────────────────────────────────────

async def commit_import(
    db: AsyncSession,
    csv_text: str,
    tenant_id: str,
    created_by: str,
) -> dict:
    """Parse CSV and commit all records to DB."""
    rows, header_errors = _parse_csv(csv_text)
    if header_errors:
        return {
            "total_rows": 0,
            "sites_created": 0,
            "sites_attached": 0,
            "devices_created": 0,
            "vendors_created": 0,
            "vendor_assignments_created": 0,
            "verifications_created": 0,
            "errors": header_errors,
        }

    # Load existing sites
    existing_sites_q = await db.execute(
        select(Site).where(Site.tenant_id == tenant_id)
    )
    existing_sites_by_id = {}
    existing_site_match = {}
    for site in existing_sites_q.scalars().all():
        existing_sites_by_id[site.site_id] = site
        key = (site.site_name.lower().strip(), (site.e911_street or "").lower().strip())
        existing_site_match[key] = site.site_id

    # Load existing vendors
    existing_vendors_q = await db.execute(
        select(Vendor).where(Vendor.tenant_id == tenant_id)
    )
    existing_vendors = {v.name.lower(): v for v in existing_vendors_q.scalars().all()}

    # Track created entities within this import
    created_sites = {}  # site_code_or_key -> site_id
    created_vendors = {}  # vendor_name_lower -> Vendor

    stats = {
        "total_rows": len(rows),
        "sites_created": 0,
        "sites_attached": 0,
        "devices_created": 0,
        "vendors_created": 0,
        "vendor_assignments_created": 0,
        "verifications_created": 0,
        "errors": [],
    }

    for i, row in enumerate(rows, 1):
        site_name = row.get("site_name", "")
        site_code = row.get("site_code", "")
        system_type_raw = row.get("system_type", "")
        address = row.get("address", "")

        if not site_name or not system_type_raw:
            stats["errors"].append(f"Row {i}: missing required field(s)")
            continue

        system_type = _normalize_system_type(system_type_raw)
        if system_type not in VALID_SYSTEM_TYPES:
            stats["errors"].append(f"Row {i}: unrecognized system_type '{system_type_raw}'")
            continue

        # ── Resolve or create site ──
        site_id = None

        if site_code and site_code in existing_sites_by_id:
            site_id = site_code
            stats["sites_attached"] += 1
        elif site_code and site_code in created_sites:
            site_id = created_sites[site_code]
            stats["sites_attached"] += 1
        elif not site_code:
            fallback_key = (site_name.lower(), address.lower())
            if fallback_key in existing_site_match:
                site_id = existing_site_match[fallback_key]
                stats["sites_attached"] += 1
            elif f"{site_name}|{address}" in created_sites:
                site_id = created_sites[f"{site_name}|{address}"]
                stats["sites_attached"] += 1

        if site_id is None:
            # Create new site — run address enrichment
            enriched = enrich_row(row, i)
            site_id = site_code or f"SITE-{uuid.uuid4().hex[:8].upper()}"
            # Use enriched final address if available, fall back to raw columns
            e_street = enriched.final_address_street or address or None
            e_city = enriched.final_address_city or row.get("city") or None
            e_state = enriched.final_address_state or row.get("state") or None
            e_zip = enriched.final_address_zip or row.get("zip") or None
            site = Site(
                site_id=site_id,
                tenant_id=tenant_id,
                site_name=site_name,
                customer_name=site_name,
                status="Not Connected",
                onboarding_status="onboarding",
                e911_street=e_street,
                e911_city=e_city,
                e911_state=e_state,
                e911_zip=e_zip,
                building_type=row.get("building_type") or None,
                notes=row.get("notes") or None,
                address_source=enriched.address_source or None,
                e911_status=enriched.e911_status,
                e911_confirmation_required=enriched.e911_confirmation_required,
                address_notes=enriched.address_notes or None,
            )
            db.add(site)
            existing_sites_by_id[site_id] = site
            if site_code:
                created_sites[site_code] = site_id
                existing_site_match[(site_name.lower(), address.lower())] = site_id
            else:
                created_sites[f"{site_name}|{address}"] = site_id
                existing_site_match[(site_name.lower(), address.lower())] = site_id
            stats["sites_created"] += 1

        # ── Create device if device data present ──
        device_serial = row.get("device_serial", "")
        device_model = row.get("device_model", "")
        if device_serial or device_model:
            device_id = f"DEV-{uuid.uuid4().hex[:8].upper()}"
            device = Device(
                device_id=device_id,
                tenant_id=tenant_id,
                site_id=site_id,
                status="provisioning",
                device_type=system_type,
                model=device_model or None,
                serial_number=device_serial or None,
                iccid=row.get("sim_iccid") or None,
                msisdn=row.get("phone_number") or None,
                carrier=row.get("carrier") or None,
                firmware_version=row.get("firmware_version") or None,
                notes=f"Imported: {system_type} at {site_name}",
            )
            db.add(device)
            stats["devices_created"] += 1

        # ── Resolve or create vendor ──
        vendor_name = row.get("vendor_name", "")
        if vendor_name:
            vname_lower = vendor_name.lower()
            vendor = None

            if vname_lower in existing_vendors:
                vendor = existing_vendors[vname_lower]
            elif vname_lower in created_vendors:
                vendor = created_vendors[vname_lower]
            else:
                vendor = Vendor(
                    tenant_id=tenant_id,
                    name=vendor_name,
                    vendor_type="general",
                    contact_name=row.get("vendor_contact") or None,
                    contact_email=row.get("vendor_email") or None,
                )
                db.add(vendor)
                await db.flush()  # get vendor.id
                existing_vendors[vname_lower] = vendor
                created_vendors[vname_lower] = vendor
                stats["vendors_created"] += 1

            # Create site-vendor assignment
            assignment = SiteVendorAssignment(
                tenant_id=tenant_id,
                site_id=site_id,
                vendor_id=vendor.id,
                system_category=system_type,
                is_primary=True,
            )
            db.add(assignment)
            stats["vendor_assignments_created"] += 1

        # ── Create verification task ──
        verification_freq = (row.get("verification_frequency") or "").lower()
        if verification_freq in VALID_FREQUENCIES:
            due_days = FREQUENCY_DAYS[verification_freq]
            priority_val = row.get("system_priority", "medium") or "medium"
            if priority_val.lower() not in ("low", "medium", "high"):
                priority_val = "medium"

            # Map system_type to a readable task title
            system_label = system_type.replace("_", " ").title()
            task = VerificationTask(
                tenant_id=tenant_id,
                site_id=site_id,
                task_type=f"{verification_freq}_inspection",
                title=f"{system_label} {verification_freq.title()} Verification",
                description=f"Baseline {verification_freq} verification for {system_label} at {site_name}",
                system_category=system_type,
                status="pending",
                priority=priority_val.lower(),
                due_date=datetime.now(timezone.utc) + timedelta(days=due_days),
                created_by=created_by,
            )
            db.add(task)
            stats["verifications_created"] += 1

    # Log activity
    if stats["sites_created"] > 0 or stats["sites_attached"] > 0:
        db.add(CommandActivity(
            tenant_id=tenant_id,
            activity_type="site_import",
            actor=created_by,
            summary=(
                f"Site import: {stats['sites_created']} sites created, "
                f"{stats['devices_created']} devices, "
                f"{stats['vendors_created']} vendors, "
                f"{stats['verifications_created']} verifications"
            ),
        ))

    return stats


def generate_template_csv() -> str:
    """Return a CSV template string with headers and one example row."""
    headers = [
        "site_name", "site_code", "address", "city", "state", "zip", "country",
        "building_type", "floors", "elevator_count",
        "system_type", "device_type", "device_model", "carrier",
        "sim_iccid", "phone_number", "device_serial", "firmware_version",
        "vendor_name", "vendor_contact", "vendor_email",
        "verification_frequency", "install_date", "system_priority", "notes",
        "service_address", "service_city", "service_state", "service_zip",
        "billing_address", "billing_city", "billing_state", "billing_zip",
        "shipping_address", "shipping_city", "shipping_state", "shipping_zip",
        "suggested_address", "suggested_city", "suggested_state", "suggested_zip",
        "e911_confirmed",
    ]
    example_1 = [
        "RH Gallery Dallas", "RH-DAL-001", "8300 NorthPark Center", "Dallas", "TX", "75225", "US",
        "retail", "3", "2",
        "elevator_phone", "Cellular Communicator", "MS130v4", "T-Mobile",
        "8901260882280000001", "+12145559001", "MS130-SN-00001", "4.2.1",
        "Lone Star Elevator", "Mike Torres", "mike@lonestarelev.com",
        "quarterly", "2025-06-15", "high", "Main gallery elevator bank",
        "8300 NorthPark Center", "Dallas", "TX", "75225",
        "", "", "", "",
        "", "", "", "",
        "", "", "", "",
        "yes",
    ]
    example_2 = [
        "RH Gallery Dallas", "RH-DAL-001", "8300 NorthPark Center", "Dallas", "TX", "75225", "US",
        "retail", "3", "",
        "fire_alarm_communicator", "Cellular Communicator", "Napco StarLink", "T-Mobile",
        "8901260882280000002", "+12145559002", "SL-SN-00001", "3.8.0",
        "Metro Fire Systems", "Sarah Chen", "sarah@metrofire.com",
        "annual", "2025-06-15", "high", "FACP communicator",
        "", "", "", "",
        "100 Commerce Blvd", "Dallas", "TX", "75201",
        "8300 NorthPark Center", "Dallas", "TX", "75225",
        "", "", "", "",
        "",
    ]
    return (
        ",".join(headers) + "\n"
        + ",".join(example_1) + "\n"
        + ",".join(example_2) + "\n"
    )
