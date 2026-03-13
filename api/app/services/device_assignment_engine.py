"""
True911 — Bulk device-to-site assignment engine.

Accepts a CSV worksheet mapping devices (by ICCID, IMEI, or MSISDN) to sites
(by site_name + customer_name).  Follows the same two-phase preview/commit
pattern used by site_import_engine.

Designed for the shared Verizon ThingSpace use-case: after sync pulls all
devices into one pool, this engine assigns each device to the correct
customer's site in bulk.
"""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.device import Device
from ..models.site import Site
from ..models.command_activity import CommandActivity


# ── CSV Parsing ───────────────────────────────────────────────────────

ACCEPTED_COLUMNS = {
    "iccid", "imei", "msisdn",
    "customer_name", "site_name", "site_id",
    "notes",
}

DEVICE_KEY_COLUMNS = {"iccid", "imei", "msisdn"}


def _strip(val: str | None) -> str:
    return (val or "").strip()


def _parse_csv(csv_text: str) -> tuple[list[dict], list[str]]:
    """Parse CSV text, return (rows, header_errors)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return [], ["Empty CSV or no header row"]

    headers = {h.strip().lower() for h in reader.fieldnames if h}

    # Must have at least one device identifier column
    has_device_key = bool(DEVICE_KEY_COLUMNS & headers)
    if not has_device_key:
        return [], [
            "CSV must contain at least one device identifier column: "
            "iccid, imei, or msisdn"
        ]

    # Must have a way to identify the target site
    has_site_target = bool({"site_name", "site_id"} & headers)
    if not has_site_target:
        return [], [
            "CSV must contain either site_name or site_id to identify "
            "the target site for assignment"
        ]

    rows = []
    for row in reader:
        cleaned = {k.strip().lower(): _strip(v) for k, v in row.items()}
        rows.append(cleaned)
    return rows, []


# ── Preview ───────────────────────────────────────────────────────────

async def preview_assignment(
    db: AsyncSession,
    csv_text: str,
    tenant_id: str,
) -> dict:
    """Parse + validate CSV, match devices and sites, return preview."""
    rows, header_errors = _parse_csv(csv_text)
    if header_errors:
        return {
            "total_rows": 0,
            "matched": 0,
            "unmatched": 0,
            "already_assigned": 0,
            "will_reassign": 0,
            "will_assign": 0,
            "conflicts": 0,
            "rows": [{"row": 0, "action": "error", "errors": header_errors,
                       "warnings": []}],
            "has_errors": True,
        }

    # Pre-load tenant devices indexed by all three keys
    dev_result = await db.execute(
        select(Device).where(Device.tenant_id == tenant_id)
    )
    all_devices = dev_result.scalars().all()

    devices_by_iccid: dict[str, Device] = {}
    devices_by_imei: dict[str, Device] = {}
    devices_by_msisdn: dict[str, Device] = {}
    for d in all_devices:
        if d.iccid:
            devices_by_iccid[d.iccid.lower()] = d
        if d.imei:
            devices_by_imei[d.imei.lower()] = d
        if d.msisdn:
            devices_by_msisdn[d.msisdn.lower()] = d

    # Pre-load tenant sites indexed by site_id and (name, customer_name)
    site_result = await db.execute(
        select(Site).where(Site.tenant_id == tenant_id)
    )
    all_sites = site_result.scalars().all()

    sites_by_id: dict[str, Site] = {}
    sites_by_name: dict[str, list[Site]] = {}  # site_name_lower -> [sites]
    for s in all_sites:
        sites_by_id[s.site_id.lower()] = s
        key = s.site_name.lower()
        sites_by_name.setdefault(key, []).append(s)

    # Process rows
    row_results = []
    matched = 0
    unmatched = 0
    already_assigned = 0
    will_reassign = 0
    will_assign = 0
    conflicts = 0
    has_errors = False

    for i, row in enumerate(rows, 1):
        errors = []
        warnings = []
        iccid = row.get("iccid", "")
        imei = row.get("imei", "")
        msisdn = row.get("msisdn", "")
        site_name = row.get("site_name", "")
        site_id_val = row.get("site_id", "")
        customer_name = row.get("customer_name", "")
        notes = row.get("notes", "")

        # ── Find device ──
        device = None
        match_key = None
        match_value = None

        if iccid:
            device = devices_by_iccid.get(iccid.lower())
            if device:
                match_key = "iccid"
                match_value = iccid
        if not device and imei:
            device = devices_by_imei.get(imei.lower())
            if device:
                match_key = "imei"
                match_value = imei
        if not device and msisdn:
            device = devices_by_msisdn.get(msisdn.lower())
            if device:
                match_key = "msisdn"
                match_value = msisdn

        if not device:
            identifiers = []
            if iccid:
                identifiers.append(f"iccid={iccid}")
            if imei:
                identifiers.append(f"imei={imei}")
            if msisdn:
                identifiers.append(f"msisdn={msisdn}")
            if not identifiers:
                errors.append("No device identifier provided (need iccid, imei, or msisdn)")
            else:
                errors.append(f"Device not found: {', '.join(identifiers)}")
            unmatched += 1
            has_errors = True
            row_results.append({
                "row": i,
                "iccid": iccid or None,
                "imei": imei or None,
                "msisdn": msisdn or None,
                "device_id": None,
                "site_name": site_name or None,
                "customer_name": customer_name or None,
                "action": "unmatched",
                "errors": errors,
                "warnings": warnings,
            })
            continue

        # ── Find target site ──
        target_site = None

        if site_id_val:
            target_site = sites_by_id.get(site_id_val.lower())
            if not target_site:
                errors.append(f"Site not found: site_id={site_id_val}")
        elif site_name:
            candidates = sites_by_name.get(site_name.lower(), [])
            if customer_name:
                # Filter by customer_name
                filtered = [
                    s for s in candidates
                    if s.customer_name.lower() == customer_name.lower()
                ]
                if len(filtered) == 1:
                    target_site = filtered[0]
                elif len(filtered) > 1:
                    errors.append(
                        f"Ambiguous: {len(filtered)} sites named '{site_name}' "
                        f"for customer '{customer_name}'"
                    )
                elif len(candidates) > 0:
                    errors.append(
                        f"Site '{site_name}' exists but not for customer "
                        f"'{customer_name}' (found: "
                        f"{', '.join(s.customer_name for s in candidates[:3])})"
                    )
                else:
                    errors.append(f"Site not found: '{site_name}'")
            else:
                if len(candidates) == 1:
                    target_site = candidates[0]
                elif len(candidates) > 1:
                    errors.append(
                        f"Ambiguous: {len(candidates)} sites named "
                        f"'{site_name}' — add customer_name column to "
                        f"disambiguate"
                    )
                else:
                    errors.append(f"Site not found: '{site_name}'")
        else:
            errors.append("No target site specified (need site_name or site_id)")

        if errors:
            conflicts += 1
            has_errors = True
            row_results.append({
                "row": i,
                "iccid": iccid or None,
                "imei": imei or None,
                "msisdn": msisdn or None,
                "device_id": device.device_id,
                "site_name": site_name or None,
                "customer_name": customer_name or None,
                "action": "conflict",
                "errors": errors,
                "warnings": warnings,
            })
            continue

        # ── Determine action ──
        matched += 1
        current_site_id = device.site_id

        if current_site_id and current_site_id == target_site.site_id:
            action = "already_assigned"
            already_assigned += 1
        elif current_site_id:
            action = "reassign"
            will_reassign += 1
            # Find current site name for display
            current_site = sites_by_id.get(current_site_id.lower())
            current_label = (
                f"{current_site.site_name} ({current_site.customer_name})"
                if current_site
                else current_site_id
            )
            warnings.append(
                f"Device currently assigned to '{current_label}' — "
                f"will be reassigned to '{target_site.site_name} "
                f"({target_site.customer_name})'"
            )
        else:
            action = "assign"
            will_assign += 1

        row_results.append({
            "row": i,
            "iccid": device.iccid or iccid or None,
            "imei": device.imei or imei or None,
            "msisdn": device.msisdn or msisdn or None,
            "device_id": device.device_id,
            "current_site_id": current_site_id,
            "target_site_id": target_site.site_id,
            "target_site_name": target_site.site_name,
            "target_customer": target_site.customer_name,
            "site_name": site_name or None,
            "customer_name": customer_name or None,
            "notes": notes or None,
            "action": action,
            "errors": errors,
            "warnings": warnings,
        })

    return {
        "total_rows": len(rows),
        "matched": matched,
        "unmatched": unmatched,
        "already_assigned": already_assigned,
        "will_reassign": will_reassign,
        "will_assign": will_assign,
        "conflicts": conflicts,
        "rows": row_results,
        "has_errors": has_errors,
    }


# ── Commit ────────────────────────────────────────────────────────────

async def commit_assignment(
    db: AsyncSession,
    csv_text: str,
    tenant_id: str,
    committed_by: str,
) -> dict:
    """Parse CSV, match devices to sites, and persist assignments."""
    # Run preview logic first to get all matches
    preview = await preview_assignment(db, csv_text, tenant_id)

    if preview["has_errors"]:
        return {
            "total_rows": preview["total_rows"],
            "assigned": 0,
            "reassigned": 0,
            "already_assigned": preview["already_assigned"],
            "skipped": preview["unmatched"] + preview["conflicts"],
            "errors": [
                f"Row {r['row']}: {'; '.join(r['errors'])}"
                for r in preview["rows"]
                if r["errors"]
            ],
        }

    # Apply assignments
    assigned = 0
    reassigned = 0
    skipped_already = 0

    # Re-load devices by device_id for efficient updates
    actionable_rows = [
        r for r in preview["rows"]
        if r["action"] in ("assign", "reassign")
    ]
    if not actionable_rows:
        return {
            "total_rows": preview["total_rows"],
            "assigned": 0,
            "reassigned": 0,
            "already_assigned": preview["already_assigned"],
            "skipped": 0,
            "errors": [],
        }

    device_ids = [r["device_id"] for r in actionable_rows]
    dev_result = await db.execute(
        select(Device).where(
            Device.tenant_id == tenant_id,
            Device.device_id.in_(device_ids),
        )
    )
    devices_by_did = {d.device_id: d for d in dev_result.scalars().all()}

    for row in actionable_rows:
        device = devices_by_did.get(row["device_id"])
        if not device:
            continue

        device.site_id = row["target_site_id"]
        if row.get("notes"):
            device.notes = row["notes"]

        if row["action"] == "assign":
            assigned += 1
        else:
            reassigned += 1

    # Log activity
    db.add(CommandActivity(
        tenant_id=tenant_id,
        activity_type="device_bulk_assignment",
        actor=committed_by,
        summary=(
            f"Bulk device assignment: {assigned} assigned, "
            f"{reassigned} reassigned, "
            f"{preview['already_assigned']} already correct"
        ),
    ))

    return {
        "total_rows": preview["total_rows"],
        "assigned": assigned,
        "reassigned": reassigned,
        "already_assigned": preview["already_assigned"],
        "skipped": 0,
        "errors": [],
    }


def generate_assignment_template_csv() -> str:
    """Return a CSV template for bulk device assignment."""
    headers = ["iccid", "imei", "msisdn", "customer_name", "site_name", "site_id", "notes"]
    example_1 = [
        "8901260882310000001", "353456789012345", "2145551001",
        "R&R Technologies", "100 Main St Elevator", "", "Assigned via worksheet",
    ]
    example_2 = [
        "8901260882310000002", "", "",
        "Benson Systems", "300 Elm St FACP", "", "",
    ]
    return (
        ",".join(headers) + "\n"
        + ",".join(example_1) + "\n"
        + ",".join(example_2) + "\n"
    )
