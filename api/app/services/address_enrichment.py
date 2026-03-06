"""
True911 — Address enrichment engine.

Resolves a final address for each site row from multiple candidate sources,
tracks provenance, and flags rows that need E911 confirmation.

Address priority (highest to lowest):
  1. service_address   — the actual site/service location
  2. shipping_address  — where equipment was shipped (strong proxy)
  3. billing_address   — billing entity address (weaker proxy)
  4. suggested_address — Google Places or geocoder suggestion (unverified)

E911 status values:
  - confirmed   — explicitly marked confirmed in source data
  - temporary   — using a fallback address that hasn't been verified
  - needs_review — using a machine-suggested address
  - unverified  — no address available at all
"""

import csv
import io
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Data structures ───────────────────────────────────────────────────

@dataclass
class AddressBlock:
    """A parsed street/city/state/zip address from any source."""
    street: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""

    @property
    def is_populated(self) -> bool:
        return bool(self.street.strip())

    def as_oneline(self) -> str:
        parts = [p for p in [self.street, self.city, self.state, self.zip_code] if p.strip()]
        return ", ".join(parts)


@dataclass
class EnrichedRow:
    """One row after address enrichment."""
    row_number: int
    site_name: str = ""
    site_code: str = ""

    # Raw candidate addresses
    service_address: str = ""
    billing_address: str = ""
    shipping_address: str = ""
    suggested_address: str = ""

    # Resolved output
    final_address_street: str = ""
    final_address_city: str = ""
    final_address_state: str = ""
    final_address_zip: str = ""
    address_source: str = ""       # service | shipping | billing | suggested | none
    e911_status: str = "unverified"  # confirmed | temporary | needs_review | unverified
    e911_confirmation_required: bool = False
    address_notes: str = ""

    # Pass-through fields (preserved from input)
    extra: dict = field(default_factory=dict)


# ── Column name mappings ──────────────────────────────────────────────
# Maps common CSV header variations to our canonical names.

SERVICE_ADDR_COLS = {
    "service_address", "site_address", "location_address",
    "address", "e911_street", "street", "street_address",
}
SERVICE_CITY_COLS = {"service_city", "site_city", "city", "e911_city"}
SERVICE_STATE_COLS = {"service_state", "site_state", "state", "e911_state"}
SERVICE_ZIP_COLS = {"service_zip", "site_zip", "zip", "zip_code", "e911_zip", "postal_code"}

BILLING_ADDR_COLS = {"billing_address", "bill_address", "billing_street"}
BILLING_CITY_COLS = {"billing_city", "bill_city"}
BILLING_STATE_COLS = {"billing_state", "bill_state"}
BILLING_ZIP_COLS = {"billing_zip", "bill_zip", "billing_zip_code"}

SHIPPING_ADDR_COLS = {"shipping_address", "ship_address", "ship_to_address", "shipping_street"}
SHIPPING_CITY_COLS = {"shipping_city", "ship_city"}
SHIPPING_STATE_COLS = {"shipping_state", "ship_state"}
SHIPPING_ZIP_COLS = {"shipping_zip", "ship_zip", "shipping_zip_code"}

SUGGESTED_ADDR_COLS = {"suggested_address", "google_address", "places_address", "geocoded_address"}
SUGGESTED_CITY_COLS = {"suggested_city", "google_city"}
SUGGESTED_STATE_COLS = {"suggested_state", "google_state"}
SUGGESTED_ZIP_COLS = {"suggested_zip", "google_zip"}

E911_CONFIRMED_COLS = {"e911_confirmed", "e911_verified", "address_confirmed", "confirmed"}

SITE_NAME_COLS = {"site_name", "location_name", "name"}
SITE_CODE_COLS = {"site_code", "site_id", "location_id", "location_code"}

# Fields that are consumed by enrichment and not passed through
CONSUMED_FIELDS = (
    SERVICE_ADDR_COLS | SERVICE_CITY_COLS | SERVICE_STATE_COLS | SERVICE_ZIP_COLS |
    BILLING_ADDR_COLS | BILLING_CITY_COLS | BILLING_STATE_COLS | BILLING_ZIP_COLS |
    SHIPPING_ADDR_COLS | SHIPPING_CITY_COLS | SHIPPING_STATE_COLS | SHIPPING_ZIP_COLS |
    SUGGESTED_ADDR_COLS | SUGGESTED_CITY_COLS | SUGGESTED_STATE_COLS | SUGGESTED_ZIP_COLS |
    E911_CONFIRMED_COLS | SITE_NAME_COLS | SITE_CODE_COLS
)


def _find_col(row: dict, candidates: set) -> str:
    """Return the value from the first matching column name found in row."""
    for col in candidates:
        if col in row and row[col].strip():
            return row[col].strip()
    return ""


def _extract_address(row: dict, street_cols: set, city_cols: set,
                     state_cols: set, zip_cols: set) -> AddressBlock:
    return AddressBlock(
        street=_find_col(row, street_cols),
        city=_find_col(row, city_cols),
        state=_find_col(row, state_cols),
        zip_code=_find_col(row, zip_cols),
    )


def _is_truthy(val: str) -> bool:
    return val.lower().strip() in {"yes", "true", "1", "confirmed", "y", "verified"}


# ── Core enrichment ──────────────────────────────────────────────────

def enrich_row(row: dict, row_number: int) -> EnrichedRow:
    """Resolve addresses and determine E911 status for a single CSV row."""
    # Normalize all keys to lowercase
    row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}

    site_name = _find_col(row, SITE_NAME_COLS)
    site_code = _find_col(row, SITE_CODE_COLS)

    # Extract candidate addresses
    service = _extract_address(row, SERVICE_ADDR_COLS, SERVICE_CITY_COLS,
                               SERVICE_STATE_COLS, SERVICE_ZIP_COLS)
    billing = _extract_address(row, BILLING_ADDR_COLS, BILLING_CITY_COLS,
                               BILLING_STATE_COLS, BILLING_ZIP_COLS)
    shipping = _extract_address(row, SHIPPING_ADDR_COLS, SHIPPING_CITY_COLS,
                                SHIPPING_STATE_COLS, SHIPPING_ZIP_COLS)
    suggested = _extract_address(row, SUGGESTED_ADDR_COLS, SUGGESTED_CITY_COLS,
                                 SUGGESTED_STATE_COLS, SUGGESTED_ZIP_COLS)

    # Check if explicitly confirmed
    explicitly_confirmed = _is_truthy(_find_col(row, E911_CONFIRMED_COLS))

    # Collect extra fields not consumed by enrichment
    extra = {k: v for k, v in row.items() if k not in CONSUMED_FIELDS and v}

    result = EnrichedRow(
        row_number=row_number,
        site_name=site_name,
        site_code=site_code,
        service_address=service.as_oneline(),
        billing_address=billing.as_oneline(),
        shipping_address=shipping.as_oneline(),
        suggested_address=suggested.as_oneline(),
        extra=extra,
    )

    # Priority resolution
    if service.is_populated:
        _apply_address(result, service, "service")
        if explicitly_confirmed:
            result.e911_status = "confirmed"
            result.e911_confirmation_required = False
            result.address_notes = "Service address confirmed as E911 address"
        else:
            result.e911_status = "temporary"
            result.e911_confirmation_required = True
            result.address_notes = "Service address present but not explicitly confirmed as E911"

    elif shipping.is_populated:
        _apply_address(result, shipping, "shipping")
        result.e911_status = "temporary"
        result.e911_confirmation_required = True
        result.address_notes = "Using shipping address as fallback — service address missing"

    elif billing.is_populated:
        _apply_address(result, billing, "billing")
        result.e911_status = "temporary"
        result.e911_confirmation_required = True
        result.address_notes = "Using billing address as fallback — service and shipping addresses missing"

    elif suggested.is_populated:
        _apply_address(result, suggested, "suggested")
        result.e911_status = "needs_review"
        result.e911_confirmation_required = True
        result.address_notes = "Using machine-suggested address (Google Places) — requires manual verification"

    else:
        result.address_source = "none"
        result.e911_status = "unverified"
        result.e911_confirmation_required = True
        result.address_notes = "No address data found in any field"

    return result


def _apply_address(result: EnrichedRow, addr: AddressBlock, source: str) -> None:
    result.final_address_street = addr.street
    result.final_address_city = addr.city
    result.final_address_state = addr.state
    result.final_address_zip = addr.zip_code
    result.address_source = source


# ── Batch processing ─────────────────────────────────────────────────

def enrich_csv(csv_text: str) -> list[EnrichedRow]:
    """Parse a CSV string and enrich every row. Returns list of EnrichedRow."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return []
    return [enrich_row(row, i) for i, row in enumerate(reader, 1)]


# ── Export helpers ───────────────────────────────────────────────────

EXPORT_COLUMNS = [
    "row_number", "site_name", "site_code",
    "service_address", "billing_address", "shipping_address", "suggested_address",
    "final_address_street", "final_address_city", "final_address_state", "final_address_zip",
    "address_source", "e911_status", "e911_confirmation_required", "address_notes",
]


def _row_to_dict(row: EnrichedRow) -> dict:
    d = asdict(row)
    d.pop("extra", None)
    d["e911_confirmation_required"] = "yes" if row.e911_confirmation_required else "no"
    return d


def export_main_csv(rows: list[EnrichedRow]) -> str:
    """Export all enriched rows as the main cleaned CSV."""
    output = io.StringIO()
    # Collect any extra columns that appear across rows
    extra_keys = sorted({k for r in rows for k in r.extra})
    all_cols = EXPORT_COLUMNS + extra_keys
    writer = csv.DictWriter(output, fieldnames=all_cols, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        d = _row_to_dict(row)
        d.update(row.extra)
        writer.writerow(d)
    return output.getvalue()


def export_review_needed_csv(rows: list[EnrichedRow]) -> str:
    """Export rows needing review (non-service source or needs_review status).

    Operational format: site name, current address, source, what's needed.
    """
    review_rows = [
        r for r in rows
        if r.e911_status in ("needs_review", "unverified") or r.address_source == "none"
    ]
    if not review_rows:
        return ""

    output = io.StringIO()
    cols = [
        "row_number", "site_name", "site_code",
        "final_address_street", "final_address_city", "final_address_state", "final_address_zip",
        "address_source", "e911_status", "address_notes",
        "service_address", "billing_address", "shipping_address", "suggested_address",
    ]
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for row in review_rows:
        writer.writerow(_row_to_dict(row))
    return output.getvalue()


def export_e911_confirmation_csv(rows: list[EnrichedRow]) -> str:
    """Export rows needing E911 confirmation — operational worklist format.

    Includes all rows where e911_confirmation_required is True.
    Columns are ordered for field-work: site, current address, what to confirm.
    """
    confirm_rows = [r for r in rows if r.e911_confirmation_required]
    if not confirm_rows:
        return ""

    output = io.StringIO()
    cols = [
        "site_name", "site_code",
        "final_address_street", "final_address_city", "final_address_state", "final_address_zip",
        "address_source", "e911_status", "address_notes",
        "e911_confirmation_required",
        "confirmed_street", "confirmed_city", "confirmed_state", "confirmed_zip",
        "confirmation_date", "confirmed_by",
    ]
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for row in confirm_rows:
        d = _row_to_dict(row)
        # Add blank columns for field workers to fill in
        d["confirmed_street"] = ""
        d["confirmed_city"] = ""
        d["confirmed_state"] = ""
        d["confirmed_zip"] = ""
        d["confirmation_date"] = ""
        d["confirmed_by"] = ""
        writer.writerow(d)
    return output.getvalue()


def print_summary(rows: list[EnrichedRow]) -> dict:
    """Return summary statistics for a batch of enriched rows."""
    total = len(rows)
    by_source = {}
    by_status = {}
    confirmation_needed = 0

    for r in rows:
        by_source[r.address_source] = by_source.get(r.address_source, 0) + 1
        by_status[r.e911_status] = by_status.get(r.e911_status, 0) + 1
        if r.e911_confirmation_required:
            confirmation_needed += 1

    return {
        "total_rows": total,
        "by_source": by_source,
        "by_status": by_status,
        "confirmation_needed": confirmation_needed,
        "confirmed": by_status.get("confirmed", 0),
    }
