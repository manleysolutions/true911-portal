"""
True911 — Subscriber / Line-centric CSV import engine.

Each CSV row represents ONE service line (subscription).
Customer, site, and device fields may repeat across rows.
The engine deduplicates and links them correctly.

Two-phase flow:
  1. preview_import()  — parse, validate, match, return preview (no DB writes)
  2. commit_import()   — create/match all records, save audit trail
"""

import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, and_, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.customer import Customer
from ..models.site import Site
from ..models.device import Device
from ..models.line import Line
from ..models.import_batch import ImportBatch
from ..models.import_row import ImportRow
from ..models.command_activity import CommandActivity

# ── Constants ──────────────────────────────────────────────────────

TEMPLATE_COLUMNS = [
    "customer_name", "customer_account_number",
    "site_name", "site_code", "street_address", "city", "state", "zip", "country",
    "endpoint_type", "service_class", "transport", "carrier", "voice_provider",
    "device_id", "hardware_model", "serial_number", "imei",
    "iccid", "msisdn", "did",
    "e911_location", "heartbeat_schedule", "notes",
]

US_STATE_ABBREVS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "dc": "DC",
}

VALID_US_STATES = set(US_STATE_ABBREVS.values())


# ── Normalization helpers ──────────────────────────────────────────

def _strip(val: str | None) -> str:
    return (val or "").strip()


def _normalize_name(name: str) -> str:
    """Lowercase, collapse whitespace, strip."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _normalize_phone(raw: str) -> str:
    """Strip to digits, ensure 10 or 11 digits, return +1XXXXXXXXXX."""
    digits = re.sub(r"[^\d]", "", raw.strip())
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return raw.strip()  # Return as-is if not US-parseable


def _normalize_state(raw: str) -> str:
    """Normalize state to 2-letter abbreviation."""
    s = raw.strip()
    if len(s) <= 3:
        return s.upper()
    return US_STATE_ABBREVS.get(s.lower(), s)


def _validate_iccid(iccid: str) -> list[str]:
    """ICCID should be 19-20 digits."""
    digits = re.sub(r"[^\d]", "", iccid)
    if len(digits) < 18 or len(digits) > 22:
        return [f"ICCID '{iccid}' looks malformed (expected 19-20 digits, got {len(digits)})"]
    return []


def _validate_msisdn(msisdn: str) -> list[str]:
    """MSISDN should resolve to a valid phone."""
    digits = re.sub(r"[^\d]", "", msisdn)
    if len(digits) < 10 or len(digits) > 15:
        return [f"MSISDN '{msisdn}' looks malformed (expected 10-15 digits, got {len(digits)})"]
    return []


# ── Protocol normalization ────────────────────────────────────────
#
# `lines.protocol` is VARCHAR(20). The CSV `service_class`/`transport`
# columns carry display-friendly labels (e.g. "VoLTE (Cellular Voice)")
# that overflow that column. The display label is preserved in
# `lines.line_type` (VARCHAR(50)); only the canonical short code goes
# into `lines.protocol`.

PROTOCOL_MAX_LEN = 20

_PROTOCOL_CANONICAL = {
    "": "cellular",
    "volte": "VoLTE",
    "volte (cellular voice)": "VoLTE",
    "volte cellular voice": "VoLTE",
    "voip": "SIP",
    "voip (sip)": "SIP",
    "sip": "SIP",
    "pots": "POTS",
    "analog": "POTS",
    "analog (pots replacement)": "POTS",
    "analog pots": "POTS",
    "analog pots replacement": "POTS",
    "data": "DATA",
    "data only": "DATA",
    "cellular": "cellular",
    "lte": "LTE",
    "5g": "5G",
    "ethernet": "ethernet",
    "ethernet (lan)": "ethernet",
    "lan": "ethernet",
}


def _canonical_protocol(raw: str | None) -> str | None:
    """Map a free-text service_class/transport label to a canonical
    protocol code (≤ 20 chars). Returns None if the input is overlong
    AND not in the canonical map — caller should surface a validation
    error in that case.
    """
    s = (raw or "").strip()
    norm = s.lower()
    if norm in _PROTOCOL_CANONICAL:
        return _PROTOCOL_CANONICAL[norm]
    if len(s) <= PROTOCOL_MAX_LEN:
        return s or "cellular"
    return None


# ── CSV Parsing ────────────────────────────────────────────────────

def _parse_csv(csv_text: str) -> tuple[list[dict], list[str]]:
    """Parse CSV, normalize headers, return (rows, header_errors)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return [], ["Empty CSV or no header row"]

    # Normalize header names
    header_map = {}
    for h in reader.fieldnames:
        if h:
            header_map[h] = h.strip().lower().replace(" ", "_").replace("-", "_")

    rows = []
    for raw_row in reader:
        cleaned = {}
        for orig_key, val in raw_row.items():
            norm_key = header_map.get(orig_key, orig_key)
            cleaned[norm_key] = _strip(val)
        rows.append(cleaned)

    return rows, []


def _get(row: dict, *keys) -> str:
    """Get first non-empty value from row for given keys."""
    for k in keys:
        v = row.get(k, "")
        if v:
            return v
    return ""


# ── Row extraction ─────────────────────────────────────────────────

def _extract_row(row: dict, row_num: int) -> dict:
    """Extract and normalize all fields from a CSV row."""
    customer_name = _strip(row.get("customer_name", ""))
    customer_number = _strip(_get(row, "customer_number", "customer_account_number"))
    account_number = _strip(_get(row, "account_number", "customer_account_number"))

    site_name = _strip(row.get("site_name", ""))
    site_address = _strip(_get(row, "site_address", "street_address", "address", "e911_street", "e911_location"))
    city = _strip(_get(row, "city", "site_city", "e911_city"))
    state_raw = _strip(_get(row, "state", "site_state", "e911_state"))
    state = _normalize_state(state_raw) if state_raw else ""
    zip_code = _strip(_get(row, "zip", "site_zip", "zip_code", "e911_zip"))

    device_type = _strip(_get(row, "device_type", "endpoint_type", "equipment_type"))
    device_id = _strip(row.get("device_id", ""))
    imei = _strip(row.get("imei", ""))
    serial_number = _strip(_get(row, "serial_number", "serial"))
    starlink_id = _strip(_get(row, "starlink_id", "starlink_device_id"))
    model = _strip(_get(row, "model", "hardware_model"))
    vendor_name = _strip(_get(row, "vendor_name", "vendor", "manufacturer"))
    system_type = _strip(_get(row, "system_type"))

    msisdn_raw = _strip(_get(row, "msisdn", "phone_number", "did", "phone"))
    msisdn = _normalize_phone(msisdn_raw) if msisdn_raw else ""
    sim_iccid = _strip(_get(row, "sim_iccid", "iccid"))
    carrier = _strip(_get(row, "carrier", "voice_provider"))
    line_type = _strip(_get(row, "line_type", "service_class", "service_type", "protocol", "transport"))

    qb_description = _strip(_get(row, "qb_description", "description"))
    notes = _strip(row.get("notes", ""))

    return {
        "row_num": row_num,
        "customer_name": customer_name,
        "customer_number": customer_number,
        "account_number": account_number,
        "site_name": site_name,
        "site_address": site_address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "device_type": device_type,
        "device_id": device_id,
        "imei": imei,
        "serial_number": serial_number,
        "starlink_id": starlink_id,
        "model": model,
        "vendor_name": vendor_name,
        "system_type": system_type,
        "msisdn": msisdn,
        "sim_iccid": sim_iccid,
        "carrier": carrier,
        "line_type": line_type,
        "qb_description": qb_description,
        "notes": notes,
    }


# ── Endpoint classification ────────────────────────────────────────

def _is_napco_starlink_row(extracted: dict) -> bool:
    """True if the row represents a Napco / SLELTE / StarLink fire-alarm communicator.

    Identifier rules for these endpoints differ — they typically have
    serial_number / starlink_id / device_id in place of MSISDN/ICCID.
    Classifier is intentionally narrow to avoid sweeping in regular
    cellular voice, elevator, or DID-based endpoints.
    """
    carrier = (extracted.get("carrier") or "").strip().lower()
    vendor = (extracted.get("vendor_name") or "").strip().lower()
    model = (extracted.get("model") or "").strip().lower()
    device_type = (extracted.get("device_type") or "").strip().lower()
    system_type = (extracted.get("system_type") or "").strip().lower()

    if carrier == "napco":
        return True
    if "napco" in vendor:
        return True
    if "slelte" in model or "starlink" in model:
        return True
    if re.search(r"\bsle\b", model):
        return True
    if "starlink" in device_type or "fire communicator" in device_type:
        return True
    if "fire alarm" in device_type or "fire alarm" in system_type:
        return True
    return False


# ── Validation ─────────────────────────────────────────────────────

def _validate_row(
    extracted: dict,
    seen: dict,
    existing_devices: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Validate a single extracted row. Returns (errors, warnings)."""
    errors = []
    warnings = []

    # Required fields
    if not extracted["customer_name"]:
        errors.append("Missing customer_name")
    if not extracted["site_name"]:
        errors.append("Missing site_name")

    # Identifier requirement — branch by endpoint type.
    # Napco/SLELTE/StarLink fire alarm communicators may use
    # serial_number / starlink_id / device_id in place of MSISDN/ICCID.
    if _is_napco_starlink_row(extracted):
        if not (
            extracted.get("serial_number")
            or extracted.get("starlink_id")
            or extracted.get("device_id")
        ):
            errors.append(
                "Napco/SLELTE devices may use serial_number, starlink_id, or "
                "device_id in place of MSISDN/ICCID."
            )
    else:
        if not extracted["msisdn"] and not extracted["sim_iccid"]:
            errors.append("Missing both msisdn and sim_iccid — at least one required")

    # ICCID format
    if extracted["sim_iccid"]:
        errors.extend(_validate_iccid(extracted["sim_iccid"]))

    # MSISDN format
    if extracted["msisdn"]:
        errors.extend(_validate_msisdn(extracted["msisdn"]))

    # Protocol mappability: lines.protocol is VARCHAR(20). Surface a
    # preview-time error rather than crashing at INSERT.
    if extracted["line_type"]:
        if _canonical_protocol(extracted["line_type"]) is None:
            errors.append(
                f"line_type '{extracted['line_type']}' "
                f"({len(extracted['line_type'])} chars) cannot be mapped to a "
                f"canonical protocol code (max {PROTOCOL_MAX_LEN} chars). "
                f"Add it to the canonical mapping or shorten the source value."
            )

    # State validation
    if extracted["state"] and extracted["state"] not in VALID_US_STATES:
        warnings.append(f"Unrecognized state: '{extracted['state']}'")

    # Whitespace/case issues
    if extracted["customer_name"] and extracted["customer_name"] != extracted["customer_name"].strip():
        warnings.append("customer_name has leading/trailing whitespace")
    if extracted["site_name"] and extracted["site_name"] != extracted["site_name"].strip():
        warnings.append("site_name has leading/trailing whitespace")

    row_num = extracted["row_num"]

    # Intra-CSV duplicate checks
    if extracted["device_id"]:
        key = extracted["device_id"].lower()
        if key in seen.get("device_ids", {}):
            prev = seen["device_ids"][key]
            # Same device across rows is OK (shared device), but different sites = conflict
            if prev.get("site_key") and extracted.get("_site_key") and prev["site_key"] != extracted.get("_site_key"):
                warnings.append(f"device_id '{extracted['device_id']}' also on row {prev['row']} with different site")

    if extracted["msisdn"]:
        key = extracted["msisdn"]
        if key in seen.get("msisdns", {}):
            prev = seen["msisdns"][key]
            if prev.get("device_key") != extracted.get("_device_key"):
                warnings.append(f"msisdn '{extracted['msisdn']}' also on row {prev['row']} with different device")

    if extracted["sim_iccid"]:
        key = extracted["sim_iccid"].lower()
        if key in seen.get("iccids", {}):
            prev = seen["iccids"][key]
            warnings.append(f"sim_iccid '{extracted['sim_iccid']}' also on row {prev['row']}")

    if extracted.get("serial_number"):
        key = extracted["serial_number"].lower()
        if key in seen.get("serials", {}):
            prev = seen["serials"][key]
            warnings.append(f"serial_number '{extracted['serial_number']}' also on row {prev['row']}")

    if extracted.get("starlink_id"):
        key = extracted["starlink_id"].lower()
        if key in seen.get("starlinks", {}):
            prev = seen["starlinks"][key]
            warnings.append(f"starlink_id '{extracted['starlink_id']}' also on row {prev['row']}")

    # Cross-DB collision: serial_number / starlink_id already owned by a
    # different existing device. Only an error when the row also names a
    # device_id that disagrees — otherwise it's a normal serial-based match.
    if existing_devices is not None and extracted.get("device_id"):
        if extracted.get("serial_number"):
            owner = existing_devices.get(f"serial:{extracted['serial_number'].lower()}")
            if owner is not None and owner.device_id != extracted["device_id"]:
                errors.append(
                    f"serial_number '{extracted['serial_number']}' already belongs to "
                    f"existing device '{owner.device_id}' (row specifies '{extracted['device_id']}')"
                )
        if extracted.get("starlink_id"):
            owner = existing_devices.get(f"starlink:{extracted['starlink_id'].lower()}")
            if owner is not None and owner.device_id != extracted["device_id"]:
                errors.append(
                    f"starlink_id '{extracted['starlink_id']}' already belongs to "
                    f"existing device '{owner.device_id}' (row specifies '{extracted['device_id']}')"
                )

    return errors, warnings


# ── Preview ────────────────────────────────────────────────────────

async def preview_import(
    db: AsyncSession,
    csv_text: str,
    tenant_id: str,
) -> dict:
    """Parse, validate, match — return preview without DB writes."""
    rows, header_errors = _parse_csv(csv_text)
    if header_errors:
        return {
            "total_rows": 0,
            "summary": {},
            "rows": [{"row": 0, "status": "error", "errors": header_errors, "warnings": []}],
            "has_errors": True,
        }

    # Load existing data for matching
    existing_customers = await _load_customers(db, tenant_id)
    existing_sites = await _load_sites(db, tenant_id)
    existing_devices = await _load_devices(db, tenant_id)
    existing_lines = await _load_lines(db, tenant_id)

    # Track intra-CSV state
    seen = {"device_ids": {}, "msisdns": {}, "iccids": {}, "serials": {}, "starlinks": {}}
    # Track planned creates within this CSV
    planned_customers = {}  # norm_name -> "create"
    planned_sites = {}  # (tenant_key, norm_name, norm_addr) -> "create"
    planned_devices = {}  # device_id or imei -> "create"

    row_results = []
    summary = {
        "total_rows": len(rows),
        "new_tenants": 0, "matched_tenants": 0,
        "new_sites": 0, "matched_sites": 0,
        "new_devices": 0, "matched_devices": 0,
        "new_lines": 0, "updated_lines": 0,
        "duplicate_rows": 0, "error_rows": 0, "warning_rows": 0,
    }
    has_errors = False

    for i, row in enumerate(rows, 1):
        extracted = _extract_row(row, i)

        # Compute matching keys
        site_key = _normalize_name(f"{extracted['site_name']}|{extracted['site_address']}")
        device_key = extracted["device_id"].lower() if extracted["device_id"] else (extracted["imei"] if extracted["imei"] else "")
        extracted["_site_key"] = site_key
        extracted["_device_key"] = device_key

        errors, warnings = _validate_row(extracted, seen, existing_devices)

        # Track in seen
        if extracted["device_id"]:
            seen["device_ids"][extracted["device_id"].lower()] = {"row": i, "site_key": site_key, "device_key": device_key}
        if extracted["msisdn"]:
            seen["msisdns"][extracted["msisdn"]] = {"row": i, "device_key": device_key}
        if extracted["sim_iccid"]:
            seen["iccids"][extracted["sim_iccid"].lower()] = {"row": i}
        if extracted.get("serial_number"):
            seen["serials"][extracted["serial_number"].lower()] = {"row": i}
        if extracted.get("starlink_id"):
            seen["starlinks"][extracted["starlink_id"].lower()] = {"row": i}

        # Determine actions
        tenant_action = "skip"
        site_action = "skip"
        device_action = "skip"
        line_action = "skip"

        if not errors:
            # Customer matching
            tenant_action = _match_customer(extracted, existing_customers, planned_customers)
            if tenant_action == "create":
                summary["new_tenants"] += 1
            else:
                summary["matched_tenants"] += 1

            # Site matching
            site_action = _match_site(extracted, existing_sites, planned_sites, tenant_id)
            if site_action == "create":
                summary["new_sites"] += 1
            else:
                summary["matched_sites"] += 1

            # Device matching (only if device info present)
            if (
                extracted["device_id"]
                or extracted["imei"]
                or extracted["device_type"]
                or extracted.get("serial_number")
                or extracted.get("starlink_id")
            ):
                device_action = _match_device(extracted, existing_devices, planned_devices)
                if device_action == "create":
                    summary["new_devices"] += 1
                elif device_action == "match":
                    summary["matched_devices"] += 1

            # Line matching
            line_action = _match_line(extracted, existing_lines)
            if line_action == "create":
                summary["new_lines"] += 1
            elif line_action == "update":
                summary["updated_lines"] += 1
            elif line_action == "duplicate":
                summary["duplicate_rows"] += 1
        else:
            has_errors = True
            summary["error_rows"] += 1

        if warnings and not errors:
            summary["warning_rows"] += 1

        row_results.append({
            "row": i,
            "customer_name": extracted["customer_name"],
            "site_name": extracted["site_name"],
            "device_id": extracted["device_id"] or extracted["imei"] or None,
            "msisdn": extracted["msisdn"] or None,
            "sim_iccid": extracted["sim_iccid"] or None,
            "tenant_action": tenant_action,
            "site_action": site_action,
            "device_action": device_action,
            "line_action": line_action,
            "status": "error" if errors else ("warning" if warnings else "ok"),
            "errors": errors,
            "warnings": warnings,
        })

    return {
        "total_rows": len(rows),
        "summary": summary,
        "rows": row_results,
        "has_errors": has_errors,
    }


# ── Commit ─────────────────────────────────────────────────────────

async def commit_import(
    db: AsyncSession,
    csv_text: str,
    tenant_id: str,
    created_by: str,
    file_name: str | None = None,
) -> dict:
    """Parse CSV and commit all records to DB with full audit trail."""
    rows, header_errors = _parse_csv(csv_text)
    if header_errors:
        return {"batch_id": None, "errors": header_errors, "summary": {}}

    batch_id = f"IMP-{uuid.uuid4().hex[:10].upper()}"

    # Create batch record
    batch = ImportBatch(
        batch_id=batch_id,
        tenant_id=tenant_id,
        file_name=file_name,
        status="committed",
        total_rows=len(rows),
        created_by=created_by,
        committed_at=datetime.now(timezone.utc),
    )
    db.add(batch)

    # Load existing data
    existing_customers = await _load_customers(db, tenant_id)
    existing_sites = await _load_sites(db, tenant_id)
    existing_devices = await _load_devices(db, tenant_id)
    existing_lines = await _load_lines(db, tenant_id)

    # Track what we create during this commit
    created_customers = {}  # norm_name -> Customer
    created_sites = {}  # site_match_key -> Site
    created_devices = {}  # device_match_key -> Device

    stats = {
        "tenants_created": 0, "tenants_matched": 0,
        "sites_created": 0, "sites_matched": 0,
        "devices_created": 0, "devices_matched": 0,
        "lines_created": 0, "lines_updated": 0, "lines_matched": 0,
        "rows_created": 0, "rows_updated": 0, "rows_matched": 0,
        "rows_failed": 0, "rows_flagged": 0,
    }
    row_errors = []

    for i, row in enumerate(rows, 1):
        extracted = _extract_row(row, i)
        errors, warnings = _validate_row(
            extracted,
            {"device_ids": {}, "msisdns": {}, "iccids": {}, "serials": {}, "starlinks": {}},
            existing_devices,
        )

        if errors:
            stats["rows_failed"] += 1
            row_errors.append(f"Row {i}: {'; '.join(errors)}")
            db.add(ImportRow(
                batch_id=batch_id, row_number=i, status="failed",
                errors_json=json.dumps(errors), warnings_json=json.dumps(warnings),
                raw_data_json=json.dumps(extracted, default=str),
            ))
            continue

        try:
            # 1. Find or create customer
            customer, c_action = await _find_or_create_customer(
                db, extracted, tenant_id, existing_customers, created_customers
            )
            if c_action == "create":
                stats["tenants_created"] += 1
            else:
                stats["tenants_matched"] += 1

            # 2. Find or create site
            site, s_action = await _find_or_create_site(
                db, extracted, tenant_id, customer, existing_sites, created_sites, batch_id
            )
            if s_action == "create":
                stats["sites_created"] += 1
            else:
                stats["sites_matched"] += 1

            # 3. Find or create device
            device = None
            d_action = "skip"
            if (
                extracted["device_id"]
                or extracted["imei"]
                or extracted["device_type"]
                or extracted.get("serial_number")
                or extracted.get("starlink_id")
            ):
                device, d_action = await _find_or_create_device(
                    db, extracted, tenant_id, site.site_id, existing_devices, created_devices, batch_id
                )
                if d_action == "create":
                    stats["devices_created"] += 1
                else:
                    stats["devices_matched"] += 1

            # 4. Find or create line
            line, l_action = await _find_or_create_line(
                db, extracted, tenant_id, site.site_id,
                device.device_id if device else None,
                customer.id if customer else None,
                existing_lines, batch_id, i,
            )
            if l_action == "create":
                stats["lines_created"] += 1
                stats["rows_created"] += 1
            elif l_action == "update":
                stats["lines_updated"] += 1
                stats["rows_updated"] += 1
            else:
                stats["lines_matched"] += 1
                stats["rows_matched"] += 1

            # Determine reconciliation status
            recon = "clean"
            if warnings:
                recon = "needs_review"
            if not extracted["msisdn"] or not extracted["sim_iccid"]:
                recon = "incomplete"

            # Save import row audit
            db.add(ImportRow(
                batch_id=batch_id, row_number=i, status=l_action,
                action_summary=f"tenant:{c_action} site:{s_action} device:{d_action} line:{l_action}",
                tenant_action=c_action, site_action=s_action,
                device_action=d_action, line_action=l_action,
                tenant_id_resolved=tenant_id,
                site_id_resolved=site.site_id,
                device_id_resolved=device.device_id if device else None,
                line_id_resolved=line.line_id if line else None,
                warnings_json=json.dumps(warnings) if warnings else None,
                raw_data_json=json.dumps(extracted, default=str),
                reconciliation_status=recon,
            ))

        except Exception as e:
            stats["rows_failed"] += 1
            row_errors.append(f"Row {i}: {str(e)[:200]}")
            db.add(ImportRow(
                batch_id=batch_id, row_number=i, status="failed",
                errors_json=json.dumps([str(e)[:200]]),
                raw_data_json=json.dumps(extracted, default=str),
            ))

    # Update batch stats
    batch.rows_created = stats["rows_created"]
    batch.rows_updated = stats["rows_updated"]
    batch.rows_matched = stats["rows_matched"]
    batch.rows_failed = stats["rows_failed"]
    batch.rows_flagged = stats["rows_flagged"]
    batch.tenants_created = stats["tenants_created"]
    batch.sites_created = stats["sites_created"]
    batch.devices_created = stats["devices_created"]
    batch.lines_created = stats["lines_created"]
    batch.summary_json = json.dumps(stats)

    # Log activity
    db.add(CommandActivity(
        tenant_id=tenant_id,
        activity_type="subscriber_import",
        actor=created_by,
        summary=(
            f"Subscriber import [{batch_id}]: "
            f"{stats['lines_created']} lines created, {stats['lines_updated']} updated, "
            f"{stats['devices_created']} devices, {stats['sites_created']} sites, "
            f"{stats['tenants_created']} customers — {stats['rows_failed']} failures"
        ),
    ))

    return {
        "batch_id": batch_id,
        "summary": stats,
        "errors": row_errors,
        "total_rows": len(rows),
    }


# ── Data loaders ───────────────────────────────────────────────────

async def _load_customers(db: AsyncSession, tenant_id: str) -> dict:
    """Load existing customers for matching."""
    q = await db.execute(select(Customer).where(Customer.tenant_id == tenant_id))
    result = {}
    for c in q.scalars().all():
        if c.customer_number:
            result[f"num:{c.customer_number.lower()}"] = c
        result[f"name:{_normalize_name(c.name)}"] = c
    return result


async def _load_sites(db: AsyncSession, tenant_id: str) -> dict:
    """Load existing sites for matching."""
    q = await db.execute(select(Site).where(Site.tenant_id == tenant_id))
    result = {}
    for s in q.scalars().all():
        result[f"id:{s.site_id}"] = s
        name_key = _normalize_name(s.site_name)
        addr_key = _normalize_name(s.e911_street or "")
        result[f"name_addr:{name_key}|{addr_key}"] = s
        result[f"name:{name_key}"] = s
    return result


async def _load_devices(db: AsyncSession, tenant_id: str) -> dict:
    """Load existing devices for matching."""
    q = await db.execute(select(Device).where(Device.tenant_id == tenant_id))
    result = {}
    for d in q.scalars().all():
        result[f"id:{d.device_id}"] = d
        if d.imei:
            result[f"imei:{d.imei.lower()}"] = d
        if d.serial_number:
            result[f"serial:{d.serial_number.lower()}"] = d
        if d.starlink_id:
            result[f"starlink:{d.starlink_id.lower()}"] = d
    return result


async def _load_lines(db: AsyncSession, tenant_id: str) -> dict:
    """Load existing lines for matching."""
    q = await db.execute(select(Line).where(Line.tenant_id == tenant_id))
    result = {}
    for l in q.scalars().all():
        result[f"id:{l.line_id}"] = l
        if l.did:
            result[f"msisdn:{l.did}"] = l
        if l.sim_iccid:
            result[f"iccid:{l.sim_iccid.lower()}"] = l
    return result


# ── Matching functions (preview-safe, no writes) ───────────────────

def _match_customer(extracted: dict, existing: dict, planned: dict) -> str:
    """Return 'match' or 'create'."""
    if extracted["customer_number"]:
        key = f"num:{extracted['customer_number'].lower()}"
        if key in existing:
            return "match"
    name_key = _normalize_name(extracted["customer_name"])
    if f"name:{name_key}" in existing:
        return "match"
    if name_key in planned:
        return "match"
    planned[name_key] = "create"
    return "create"


def _match_site(extracted: dict, existing: dict, planned: dict, tenant_id: str) -> str:
    """Return 'match' or 'create'."""
    name_key = _normalize_name(extracted["site_name"])
    addr_key = _normalize_name(extracted["site_address"])

    # Priority 1: name + address
    full_key = f"name_addr:{name_key}|{addr_key}"
    if full_key in existing:
        return "match"
    if full_key in planned:
        return "match"

    # Priority 2: name only (if no address)
    if not addr_key:
        if f"name:{name_key}" in existing:
            return "match"

    planned[full_key] = "create"
    return "create"


def _match_device(extracted: dict, existing: dict, planned: dict) -> str:
    """Return 'match' or 'create'."""
    if extracted["device_id"]:
        key = f"id:{extracted['device_id']}"
        if key in existing or key in planned:
            return "match"
    if extracted["imei"]:
        key = f"imei:{extracted['imei'].lower()}"
        if key in existing or key in planned:
            return "match"
    if extracted.get("serial_number"):
        key = f"serial:{extracted['serial_number'].lower()}"
        if key in existing or key in planned:
            return "match"
    if extracted.get("starlink_id"):
        key = f"starlink:{extracted['starlink_id'].lower()}"
        if key in existing or key in planned:
            return "match"

    # Choose planned key in identifier-priority order
    if extracted["device_id"]:
        plan_key = f"id:{extracted['device_id']}"
    elif extracted["imei"]:
        plan_key = f"imei:{extracted['imei'].lower()}"
    elif extracted.get("serial_number"):
        plan_key = f"serial:{extracted['serial_number'].lower()}"
    elif extracted.get("starlink_id"):
        plan_key = f"starlink:{extracted['starlink_id'].lower()}"
    else:
        plan_key = None

    if plan_key:
        if plan_key in planned:
            return "match"
        planned[plan_key] = "create"
    return "create"


def _match_line(extracted: dict, existing: dict) -> str:
    """Return 'create', 'update', or 'duplicate'."""
    if extracted["msisdn"]:
        key = f"msisdn:{extracted['msisdn']}"
        if key in existing:
            return "update"
    if extracted["sim_iccid"]:
        key = f"iccid:{extracted['sim_iccid'].lower()}"
        if key in existing:
            return "update"
    return "create"


# ── Find-or-create functions (commit phase) ────────────────────────

async def _find_or_create_customer(
    db: AsyncSession,
    extracted: dict,
    tenant_id: str,
    existing: dict,
    created: dict,
) -> tuple:
    """Returns (Customer, action)."""
    # Match by customer_number
    if extracted["customer_number"]:
        key = f"num:{extracted['customer_number'].lower()}"
        if key in existing:
            return existing[key], "match"

    # Match by name
    name_key = _normalize_name(extracted["customer_name"])
    if f"name:{name_key}" in existing:
        c = existing[f"name:{name_key}"]
        # Update customer_number if we have it and they don't
        if extracted["customer_number"] and not c.customer_number:
            c.customer_number = extracted["customer_number"]
        if extracted["account_number"] and not c.account_number:
            c.account_number = extracted["account_number"]
        return c, "match"

    # Check already created in this batch
    if name_key in created:
        return created[name_key], "match"

    # Create new
    customer = Customer(
        tenant_id=tenant_id,
        name=extracted["customer_name"],
        customer_number=extracted["customer_number"] or None,
        account_number=extracted["account_number"] or None,
        status="active",
        onboarding_status="in_progress",
    )
    db.add(customer)
    await db.flush()
    existing[f"name:{name_key}"] = customer
    if extracted["customer_number"]:
        existing[f"num:{extracted['customer_number'].lower()}"] = customer
    created[name_key] = customer
    return customer, "create"


async def _find_or_create_site(
    db: AsyncSession,
    extracted: dict,
    tenant_id: str,
    customer: Customer | None,
    existing: dict,
    created: dict,
    batch_id: str,
) -> tuple:
    """Returns (Site, action)."""
    name_key = _normalize_name(extracted["site_name"])
    addr_key = _normalize_name(extracted["site_address"])

    # Priority 1: name + address
    full_key = f"name_addr:{name_key}|{addr_key}"
    if full_key in existing:
        return existing[full_key], "match"
    if full_key in created:
        return created[full_key], "match"

    # Priority 2: name only
    if not addr_key and f"name:{name_key}" in existing:
        return existing[f"name:{name_key}"], "match"

    # Create
    site_id = f"SITE-{uuid.uuid4().hex[:8].upper()}"
    site = Site(
        site_id=site_id,
        tenant_id=tenant_id,
        site_name=extracted["site_name"],
        customer_name=extracted["customer_name"],
        status="Not Connected",
        onboarding_status="onboarding",
        e911_street=extracted["site_address"] or None,
        e911_city=extracted["city"] or None,
        e911_state=extracted["state"] or None,
        e911_zip=extracted["zip"] or None,
        reconciliation_status="imported_unverified",
        import_batch_id=batch_id,
    )
    db.add(site)
    existing[full_key] = site
    existing[f"name:{name_key}"] = site
    existing[f"id:{site_id}"] = site
    created[full_key] = site
    return site, "create"


async def _find_or_create_device(
    db: AsyncSession,
    extracted: dict,
    tenant_id: str,
    site_id: str,
    existing: dict,
    created: dict,
    batch_id: str,
) -> tuple:
    """Returns (Device, action). Existing devices are returned unchanged."""
    # Match by device_id
    if extracted["device_id"]:
        key = f"id:{extracted['device_id']}"
        if key in existing:
            return existing[key], "match"
        if key in created:
            return created[key], "match"

    # Match by IMEI
    if extracted["imei"]:
        key = f"imei:{extracted['imei'].lower()}"
        if key in existing:
            return existing[key], "match"
        if key in created:
            return created[key], "match"

    # Match by serial_number (Napco/SLELTE common case)
    if extracted.get("serial_number"):
        key = f"serial:{extracted['serial_number'].lower()}"
        if key in existing:
            return existing[key], "match"
        if key in created:
            return created[key], "match"

    # Match by starlink_id
    if extracted.get("starlink_id"):
        key = f"starlink:{extracted['starlink_id'].lower()}"
        if key in existing:
            return existing[key], "match"
        if key in created:
            return created[key], "match"

    # Create
    dev_id = extracted["device_id"] or f"DEV-{uuid.uuid4().hex[:8].upper()}"
    device = Device(
        device_id=dev_id,
        tenant_id=tenant_id,
        site_id=site_id,
        status="provisioning",
        device_type=extracted["device_type"] or None,
        model=extracted.get("model") or None,
        serial_number=extracted.get("serial_number") or None,
        imei=extracted["imei"] or None,
        starlink_id=extracted.get("starlink_id") or None,
        carrier=extracted["carrier"] or None,
        iccid=extracted["sim_iccid"] or None,
        msisdn=extracted["msisdn"] or None,
        reconciliation_status="imported_unverified",
        import_batch_id=batch_id,
        source_row_id=extracted["row_num"],
        notes=f"Imported: {extracted['device_type'] or 'device'} at {extracted['site_name']}",
    )
    db.add(device)
    existing[f"id:{dev_id}"] = device
    if extracted["imei"]:
        existing[f"imei:{extracted['imei'].lower()}"] = device
    if extracted.get("serial_number"):
        existing[f"serial:{extracted['serial_number'].lower()}"] = device
    if extracted.get("starlink_id"):
        existing[f"starlink:{extracted['starlink_id'].lower()}"] = device
    created[f"id:{dev_id}"] = device
    return device, "create"


async def _find_or_create_line(
    db: AsyncSession,
    extracted: dict,
    tenant_id: str,
    site_id: str,
    device_id: str | None,
    customer_db_id: int | None,
    existing: dict,
    batch_id: str,
    row_num: int,
) -> tuple:
    """Returns (Line, action)."""
    # Match by msisdn
    if extracted["msisdn"]:
        key = f"msisdn:{extracted['msisdn']}"
        if key in existing:
            line = existing[key]
            # Update fields
            if extracted["sim_iccid"] and not line.sim_iccid:
                line.sim_iccid = extracted["sim_iccid"]
            if extracted["carrier"] and not line.carrier:
                line.carrier = extracted["carrier"]
            if device_id and not line.device_id:
                line.device_id = device_id
            if site_id and not line.site_id:
                line.site_id = site_id
            if extracted["line_type"] and not line.line_type:
                line.line_type = extracted["line_type"]
            if extracted["qb_description"] and not line.qb_description:
                line.qb_description = extracted["qb_description"]
            line.import_batch_id = batch_id
            line.source_row_id = row_num
            line.reconciliation_status = "imported_unverified"
            return line, "update"

    # Match by ICCID
    if extracted["sim_iccid"]:
        key = f"iccid:{extracted['sim_iccid'].lower()}"
        if key in existing:
            line = existing[key]
            if extracted["msisdn"] and not line.did:
                line.did = extracted["msisdn"]
            if extracted["carrier"] and not line.carrier:
                line.carrier = extracted["carrier"]
            if device_id and not line.device_id:
                line.device_id = device_id
            if site_id and not line.site_id:
                line.site_id = site_id
            line.import_batch_id = batch_id
            line.source_row_id = row_num
            line.reconciliation_status = "imported_unverified"
            return line, "update"

    # Create new line
    line_id = f"LINE-{uuid.uuid4().hex[:8].upper()}"
    # Canonical short code for VARCHAR(20) protocol column; full label
    # is preserved separately in line_type (VARCHAR(50)).
    canonical = _canonical_protocol(extracted["line_type"]) or "cellular"
    line = Line(
        line_id=line_id,
        tenant_id=tenant_id,
        site_id=site_id,
        device_id=device_id,
        provider=extracted["carrier"] or "other",
        did=extracted["msisdn"] or None,
        protocol=canonical,
        status="provisioning",
        sim_iccid=extracted["sim_iccid"] or None,
        carrier=extracted["carrier"] or None,
        line_type=extracted["line_type"] or None,
        qb_description=extracted["qb_description"] or None,
        notes=extracted["notes"] or None,
        customer_id=customer_db_id,
        reconciliation_status="imported_unverified",
        import_batch_id=batch_id,
        source_row_id=row_num,
    )
    db.add(line)
    if extracted["msisdn"]:
        existing[f"msisdn:{extracted['msisdn']}"] = line
    if extracted["sim_iccid"]:
        existing[f"iccid:{extracted['sim_iccid'].lower()}"] = line
    return line, "create"


# ── Verification queries ───────────────────────────────────────────

async def get_verification_summary(db: AsyncSession, tenant_id: str) -> list[dict]:
    """Return per-customer verification summary."""
    # Get all customers
    cust_q = await db.execute(select(Customer).where(Customer.tenant_id == tenant_id))
    customers = cust_q.scalars().all()

    result = []
    for c in customers:
        # Count sites with this customer_name
        sites_q = await db.execute(
            select(sa_func.count()).select_from(Site).where(
                and_(Site.tenant_id == tenant_id, Site.customer_name == c.name)
            )
        )
        site_count = sites_q.scalar() or 0

        # Count devices at those sites
        devices_q = await db.execute(
            select(sa_func.count()).select_from(Device).where(
                and_(
                    Device.tenant_id == tenant_id,
                    Device.site_id.in_(
                        select(Site.site_id).where(
                            and_(Site.tenant_id == tenant_id, Site.customer_name == c.name)
                        )
                    ),
                )
            )
        )
        device_count = devices_q.scalar() or 0

        # Count lines for this customer
        lines_q = await db.execute(
            select(sa_func.count()).select_from(Line).where(
                and_(Line.tenant_id == tenant_id, Line.customer_id == c.id)
            )
        )
        line_count = lines_q.scalar() or 0

        # Count unresolved issues
        issues_q = await db.execute(
            select(sa_func.count()).select_from(Line).where(
                and_(
                    Line.tenant_id == tenant_id,
                    Line.customer_id == c.id,
                    Line.reconciliation_status.in_(["needs_review", "incomplete", "duplicate_suspected"]),
                )
            )
        )
        issue_count = issues_q.scalar() or 0

        # Health score: simple ratio of clean+verified lines
        clean_q = await db.execute(
            select(sa_func.count()).select_from(Line).where(
                and_(
                    Line.tenant_id == tenant_id,
                    Line.customer_id == c.id,
                    Line.reconciliation_status.in_(["clean", "verified"]),
                )
            )
        )
        clean_count = clean_q.scalar() or 0
        health = round((clean_count / max(line_count, 1)) * 100)

        result.append({
            "customer_id": c.id,
            "customer_name": c.name,
            "customer_number": c.customer_number,
            "sites": site_count,
            "devices": device_count,
            "lines": line_count,
            "health_score": health,
            "unresolved_issues": issue_count,
            "reconciliation_status": c.onboarding_status or "pending",
        })

    return result


async def get_site_detail(db: AsyncSession, tenant_id: str, site_id: str) -> dict | None:
    """Return detailed site info with devices and lines for verification."""
    site_q = await db.execute(
        select(Site).where(and_(Site.tenant_id == tenant_id, Site.site_id == site_id))
    )
    site = site_q.scalars().first()
    if not site:
        return None

    # Devices at this site
    dev_q = await db.execute(
        select(Device).where(and_(Device.tenant_id == tenant_id, Device.site_id == site_id))
    )
    devices = dev_q.scalars().all()

    # Lines at this site
    lines_q = await db.execute(
        select(Line).where(and_(Line.tenant_id == tenant_id, Line.site_id == site_id))
    )
    lines = lines_q.scalars().all()

    device_list = []
    for d in devices:
        device_lines = [l for l in lines if l.device_id == d.device_id]
        device_list.append({
            "device_id": d.device_id,
            "device_type": d.device_type,
            "imei": d.imei,
            "iccid": d.iccid,
            "msisdn": d.msisdn,
            "carrier": d.carrier,
            "status": d.status,
            "reconciliation_status": d.reconciliation_status,
            "lines": [
                {
                    "line_id": l.line_id,
                    "did": l.did,
                    "sim_iccid": l.sim_iccid,
                    "carrier": l.carrier,
                    "line_type": l.line_type,
                    "status": l.status,
                    "reconciliation_status": l.reconciliation_status,
                    "qb_description": l.qb_description,
                }
                for l in device_lines
            ],
            "warnings": _device_warnings(d, device_lines),
        })

    # Orphan lines (no device)
    orphan_lines = [l for l in lines if not l.device_id or not any(d.device_id == l.device_id for d in devices)]

    return {
        "site_id": site.site_id,
        "site_name": site.site_name,
        "customer_name": site.customer_name,
        "address": site.e911_street,
        "city": site.e911_city,
        "state": site.e911_state,
        "zip": site.e911_zip,
        "status": site.status,
        "reconciliation_status": site.reconciliation_status,
        "devices": device_list,
        "orphan_lines": [
            {
                "line_id": l.line_id,
                "did": l.did,
                "sim_iccid": l.sim_iccid,
                "carrier": l.carrier,
                "reconciliation_status": l.reconciliation_status,
            }
            for l in orphan_lines
        ],
    }


def _device_warnings(device: Device, lines: list) -> list[str]:
    """Generate warnings for a device."""
    warnings = []
    if not lines:
        warnings.append("Device has no lines — may be orphaned")
    if not device.imei and not device.device_id:
        warnings.append("Device has no IMEI or device_id")
    for line in lines:
        if not line.did:
            warnings.append(f"Line {line.line_id} missing phone number (MSISDN)")
        if not line.sim_iccid:
            warnings.append(f"Line {line.line_id} missing SIM ICCID")
    return warnings


async def get_import_batches(db: AsyncSession, tenant_id: str) -> list[dict]:
    """Return all import batches for a tenant."""
    q = await db.execute(
        select(ImportBatch)
        .where(ImportBatch.tenant_id == tenant_id)
        .order_by(ImportBatch.created_at.desc())
    )
    batches = q.scalars().all()
    return [
        {
            "batch_id": b.batch_id,
            "file_name": b.file_name,
            "status": b.status,
            "total_rows": b.total_rows,
            "rows_created": b.rows_created,
            "rows_updated": b.rows_updated,
            "rows_failed": b.rows_failed,
            "tenants_created": b.tenants_created,
            "sites_created": b.sites_created,
            "devices_created": b.devices_created,
            "lines_created": b.lines_created,
            "created_by": b.created_by,
            "committed_at": b.committed_at.isoformat() if b.committed_at else None,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in batches
    ]


async def get_batch_rows(db: AsyncSession, batch_id: str) -> list[dict]:
    """Return all rows for a given batch."""
    q = await db.execute(
        select(ImportRow).where(ImportRow.batch_id == batch_id).order_by(ImportRow.row_number)
    )
    rows = q.scalars().all()
    return [
        {
            "row_number": r.row_number,
            "status": r.status,
            "action_summary": r.action_summary,
            "tenant_action": r.tenant_action,
            "site_action": r.site_action,
            "device_action": r.device_action,
            "line_action": r.line_action,
            "site_id_resolved": r.site_id_resolved,
            "device_id_resolved": r.device_id_resolved,
            "line_id_resolved": r.line_id_resolved,
            "reconciliation_status": r.reconciliation_status,
            "errors": json.loads(r.errors_json) if r.errors_json else [],
            "warnings": json.loads(r.warnings_json) if r.warnings_json else [],
        }
        for r in rows
    ]


# ── Correction operations ──────────────────────────────────────────

async def reassign_line_to_device(
    db: AsyncSession, tenant_id: str, line_id: str, new_device_id: str
) -> dict:
    """Move a line to a different device."""
    line_q = await db.execute(
        select(Line).where(and_(Line.tenant_id == tenant_id, Line.line_id == line_id))
    )
    line = line_q.scalars().first()
    if not line:
        return {"error": "Line not found"}

    device_q = await db.execute(
        select(Device).where(and_(Device.tenant_id == tenant_id, Device.device_id == new_device_id))
    )
    device = device_q.scalars().first()
    if not device:
        return {"error": "Target device not found"}

    old_device_id = line.device_id
    line.device_id = new_device_id
    line.site_id = device.site_id  # Follow device's site
    return {"success": True, "old_device_id": old_device_id, "new_device_id": new_device_id}


async def reassign_device_to_site(
    db: AsyncSession, tenant_id: str, device_id: str, new_site_id: str
) -> dict:
    """Move a device to a different site."""
    device_q = await db.execute(
        select(Device).where(and_(Device.tenant_id == tenant_id, Device.device_id == device_id))
    )
    device = device_q.scalars().first()
    if not device:
        return {"error": "Device not found"}

    site_q = await db.execute(
        select(Site).where(and_(Site.tenant_id == tenant_id, Site.site_id == new_site_id))
    )
    site = site_q.scalars().first()
    if not site:
        return {"error": "Target site not found"}

    old_site_id = device.site_id
    device.site_id = new_site_id

    # Also move lines that follow this device
    lines_q = await db.execute(
        select(Line).where(and_(Line.tenant_id == tenant_id, Line.device_id == device_id))
    )
    for line in lines_q.scalars().all():
        line.site_id = new_site_id

    return {"success": True, "old_site_id": old_site_id, "new_site_id": new_site_id}


async def merge_duplicate_sites(
    db: AsyncSession, tenant_id: str, keep_site_id: str, merge_site_id: str
) -> dict:
    """Merge merge_site into keep_site (move all devices and lines)."""
    keep_q = await db.execute(
        select(Site).where(and_(Site.tenant_id == tenant_id, Site.site_id == keep_site_id))
    )
    keep_site = keep_q.scalars().first()
    if not keep_site:
        return {"error": "Keep site not found"}

    merge_q = await db.execute(
        select(Site).where(and_(Site.tenant_id == tenant_id, Site.site_id == merge_site_id))
    )
    merge_site = merge_q.scalars().first()
    if not merge_site:
        return {"error": "Merge site not found"}

    # Move devices
    dev_q = await db.execute(
        select(Device).where(and_(Device.tenant_id == tenant_id, Device.site_id == merge_site_id))
    )
    moved_devices = 0
    for d in dev_q.scalars().all():
        d.site_id = keep_site_id
        moved_devices += 1

    # Move lines
    lines_q = await db.execute(
        select(Line).where(and_(Line.tenant_id == tenant_id, Line.site_id == merge_site_id))
    )
    moved_lines = 0
    for l in lines_q.scalars().all():
        l.site_id = keep_site_id
        moved_lines += 1

    # Mark merged site as decommissioned
    merge_site.status = "Decommissioned"
    merge_site.notes = (merge_site.notes or "") + f"\nMerged into {keep_site_id}"

    return {"success": True, "moved_devices": moved_devices, "moved_lines": moved_lines}


async def merge_duplicate_devices(
    db: AsyncSession, tenant_id: str, keep_device_id: str, merge_device_id: str
) -> dict:
    """Merge merge_device into keep_device (move all lines)."""
    keep_q = await db.execute(
        select(Device).where(and_(Device.tenant_id == tenant_id, Device.device_id == keep_device_id))
    )
    keep_device = keep_q.scalars().first()
    if not keep_device:
        return {"error": "Keep device not found"}

    merge_q = await db.execute(
        select(Device).where(and_(Device.tenant_id == tenant_id, Device.device_id == merge_device_id))
    )
    merge_device = merge_q.scalars().first()
    if not merge_device:
        return {"error": "Merge device not found"}

    # Move lines
    lines_q = await db.execute(
        select(Line).where(and_(Line.tenant_id == tenant_id, Line.device_id == merge_device_id))
    )
    moved_lines = 0
    for l in lines_q.scalars().all():
        l.device_id = keep_device_id
        moved_lines += 1

    # Decommission merged device
    merge_device.status = "decommissioned"
    merge_device.notes = (merge_device.notes or "") + f"\nMerged into {keep_device_id}"

    return {"success": True, "moved_lines": moved_lines}


async def update_reconciliation_status(
    db: AsyncSession, tenant_id: str,
    entity_type: str, entity_id: str, new_status: str,
) -> dict:
    """Update reconciliation status on a line, device, or site."""
    valid_statuses = {"clean", "needs_review", "incomplete", "duplicate_suspected", "imported_unverified", "verified"}
    if new_status not in valid_statuses:
        return {"error": f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}"}

    if entity_type == "line":
        q = await db.execute(
            select(Line).where(and_(Line.tenant_id == tenant_id, Line.line_id == entity_id))
        )
        entity = q.scalars().first()
    elif entity_type == "device":
        q = await db.execute(
            select(Device).where(and_(Device.tenant_id == tenant_id, Device.device_id == entity_id))
        )
        entity = q.scalars().first()
    elif entity_type == "site":
        q = await db.execute(
            select(Site).where(and_(Site.tenant_id == tenant_id, Site.site_id == entity_id))
        )
        entity = q.scalars().first()
    else:
        return {"error": "entity_type must be 'line', 'device', or 'site'"}

    if not entity:
        return {"error": f"{entity_type} not found"}

    entity.reconciliation_status = new_status
    return {"success": True, "entity_type": entity_type, "entity_id": entity_id, "status": new_status}


# ── Template ───────────────────────────────────────────────────────

def generate_subscriber_template_csv() -> str:
    """Return a production-grade CSV import template.

    Uses proper csv.writer for correct quoting/escaping.
    Includes 4 realistic example rows showing:
      - repeated customer/site across devices
      - different endpoint types and carriers
      - one row per device/line
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header row
    writer.writerow(TEMPLATE_COLUMNS)

    # Example 1: Elevator line at hospital main campus
    writer.writerow([
        "Metro Hospital Group", "ACCT-1001",
        "Metro Hospital Main Campus", "", "500 Medical Center Dr", "Dallas", "TX", "75201", "US",
        "Elevator", "VoLTE (Cellular Voice)", "Cellular", "T-Mobile", "",
        "DEV-ELV-001", "MS130v4", "MS130-SN-001", "353456789012345",
        "89012608822800000010", "+12145551001", "",
        "Main lobby elevator bank", "", "Cars 1-3",
    ])

    # Example 2: Fire alarm at same campus (same customer/site, different device)
    writer.writerow([
        "Metro Hospital Group", "ACCT-1001",
        "Metro Hospital Main Campus", "", "500 Medical Center Dr", "Dallas", "TX", "75201", "US",
        "Fire Alarm Control Panel", "Data Only", "Cellular", "T-Mobile", "",
        "DEV-FACP-001", "Napco StarLink", "SL-SN-001", "353456789012346",
        "89012608822800000011", "+12145551002", "",
        "Main building FACP", "", "Napco communicator",
    ])

    # Example 3: Emergency phone at a different site (same customer)
    writer.writerow([
        "Metro Hospital Group", "ACCT-1001",
        "Metro Hospital North Clinic", "", "1200 North Ave", "Dallas", "TX", "75204", "US",
        "Emergency Phone", "VoIP (SIP)", "Ethernet (LAN)", "", "Telnyx",
        "DEV-EMRG-001", "", "", "",
        "", "", "+12145551005",
        "Parking garage call station", "", "Level 1 entrance",
    ])

    # Example 4: Fax at clinic (different endpoint type)
    writer.writerow([
        "Metro Hospital Group", "ACCT-1001",
        "Metro Hospital North Clinic", "", "1200 North Ave", "Dallas", "TX", "75204", "US",
        "Fax", "Analog (POTS Replacement)", "Cellular", "Verizon", "",
        "DEV-FAX-001", "", "FAX-SN-001", "353456789012348",
        "89012608822800000013", "+12145551006", "",
        "Clinic fax line", "", "",
    ])

    return output.getvalue()
