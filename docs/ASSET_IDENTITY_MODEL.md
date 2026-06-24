# Asset Identity Model

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Companion to `AI_CUSTOMER_OPERATIONS_CENTER.md`. Status: Phase 1 implemented.

## 1. Problem

A caller usually has **no account number**. They have whatever is printed on,
or associated with, the physical equipment. `AssetIdentity`
(`asset_identities` table) is a flexible **identifier → asset** index so any
such field can resolve to the right device / site / service unit / line.

Multiple identities point at the same asset — one elevator phone has an
MSISDN *and* an elevator phone number *and* a device label *and* an elevator
number *and* a site name *and* a building name.

## 2. Supported identifier types

Defined in `app/schemas/ops_center.py::IDENTIFIER_TYPES`.

### Elevator / analog line
`elevator_phone` · `msisdn` · `device_label` · `elevator_number` ·
`site_name` · `building_name`

### FACP / fire alarm communicator
`starlink_id` · `napco_radio` · `iccid` · `central_station_account` ·
`panel_location` · `site_name` · `building_name`

### Gate / area of refuge / emergency phone
`phone_number` · `msisdn` · `device_label` · `site_name` · `building_name`

### Generic extras (used by native-field fallback)
`imei` · `serial_number` · `unit_name` · `did`

## 3. Table shape (`asset_identities`)

| Column | Notes |
|--------|-------|
| `id` | int PK |
| `tenant_id` | indexed; scope |
| `identifier_type` | one of the types above |
| `identifier_value` | as supplied (display) |
| `identifier_value_normalized` | **match key** (see §4) |
| `asset_kind` | `device` \| `site` \| `service_unit` \| `line` |
| `asset_ref` | business id of the asset |
| `site_id` / `device_id` / `service_unit_id` | loose cross-links (strings) |
| `label` / `category` | human label + `elevator`\|`facp`\|`gate`\|`area_of_refuge`\|`emergency_phone`\|`other` |
| `source` | `import` \| `manual` \| `derived` |
| `is_active` | soft-disable |
| `meta` | JSONB |
| **Unique** | `(tenant_id, identifier_type, identifier_value_normalized)` |

The row carries **no sensitive data** — it is an index, not a record. Billing
and sensitive device fields stay on `Device`/`Site`/`Customer` and are exposed
only after caller verification.

## 4. Normalization (matching)

`app/services/ops_center/normalize.py`:

- **Phone-like** (`elevator_phone`, `msisdn`, `phone_number`, `did`): reduced to
  digits; an 11-digit `1XXXXXXXXXX` collapses to the trailing 10. So
  `+1 (856) 308-1391`, `18563081391`, and `8563081391` all match.
- **Name-like** (`site_name`, `building_name`, `panel_location`, `device_label`,
  `unit_name`): lower-cased, internal whitespace collapsed.
- **Token** (everything else — `iccid`, `imei`, `serial_number`, `starlink_id`,
  `napco_radio`, `central_station_account`, `elevator_number`): upper-cased,
  separators (` -_./`) stripped. So `8901 2402 0421 9434 247` matches
  `8901240204219434247`.

## 5. Lookup precedence (`lookup.py`)

1. **`asset_identities` index** — match on `identifier_value_normalized` (across
   the candidate normalizations; constrained to the supplied `identifier_type`
   when given).
2. **Native-field fallback** — targeted matches against existing columns so
   lookup is useful **before** the index is populated:
   - phone → `Device.msisdn`, `Line.did`
   - token → `Device.iccid` / `imei` / `serial_number` / `device_id`,
     `ServiceUnit.unit_id`, `Site.site_id`
   - name → `ServiceUnit.unit_name`, `Site.site_name` (case-insensitive)
3. **Contact resolution** — each match resolves the owning `Site` POC
   (`poc_name` + `poc_phone`) as the authorized contact for OTP.

Matches are returned **raw** to the router (full contact + tenant); the router
redacts before anything reaches a caller (masked phone, tenant hidden from
non-platform callers).

## 6. Populating identities

- **Now:** `POST /api/ops-center/asset-identities` (perm
  `OPS_CENTER_MANAGE_ASSETS`) registers one identity; `GET` lists per tenant.
- **Native fallback** means many lookups already work with zero identities
  registered (phones, ICCIDs, site/unit names).
- **Future (Phase 2+):** bulk import / derivation from existing
  Device/Sim/ServiceUnit data, and a dedicated **authorized-contact** model
  (multiple contacts per asset with explicit authorization), replacing the
  single Site-POC resolution used today.
