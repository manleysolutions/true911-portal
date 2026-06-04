# RH NAPCO RadioNumber Match Audit + ICCID Backfill Plan

**Read-only.** Tests whether Restoration Hardware NAPCO device IDs are actually
NAPCO **RadioNumbers**, and — where they are — produces a **dry-run ICCID
backfill plan** compatible with the existing RH identity importer (PR #81).

## Why ICCID coverage is currently 0
The RH ICCID coverage audit found `devices_with_iccid: 0` / `import_ready: 0` —
so the NAPCO import (which matches strongest on **ICCID**) can't bind a single RH
device. Yet the NAPCO export carries an ICCID for **every** radio. The missing
link is the join key.

## Why RadioNumber may solve it
Many RH NAPCO `device_id` values look like NAPCO RadioNumbers (e.g. `15474214`,
`5483291`, `13864`). If `Device.device_id` (or `serial_number`) equals the
export's `RadioNumber`, we can read that radio's ICCID straight from the export
and propose it as a backfill — turning 0% coverage into a matchable fleet.

## Command
```bash
NAPCO_EXPORT_FILE=/path/to/Radiolist.xlsx python -m app.audit_rh_napco_radio_match
python -m app.audit_rh_napco_radio_match --napco-export /path/to/Radiolist.xlsx
python -m app.audit_rh_napco_radio_match --tenant restoration-hardware   # default
```

### Export the plan
```bash
python -m app.audit_rh_napco_radio_match \
  --napco-export /path/to/Radiolist.xlsx \
  --export-plan /tmp/rh_napco_iccid_backfill_plan.json
```
The JSON document has two key parts:
- **`importer_mapping`** — rows of `{device_id + whitelisted identity fields}`
  (`iccid`, `serial_number`). **Feed this directly** to `RH_DEVICE_MAP_FILE`.
- **`review_plan`** — rich, human-reviewable rows (RadioNumber, Plan, GenTech,
  SubscriberName, notes) — *not* fed to the importer.

It also lists `review_required`, `refused`, and `unmatched` devices.

## Match statuses
`exact_device_id_match` · `exact_serial_match` · `exact_name_match` *(N/A — no
name column)* · `metadata_match` *(N/A — no metadata column)* · `no_match` ·
`ambiguous_match` · `duplicate_radio_number` · `non_napco_device` · `data_conflict`

## Safety rules — a backfill is REFUSED when
1. Export ICCID is missing or malformed.
2. *(review)* Device already has a **different** ICCID → `review_required`.
3. The same RadioNumber appears in **multiple export rows** → `refused`.
4. **Multiple RH devices** match the same RadioNumber → `refused`.
5. Export `SubscriberName` is not clearly Restoration Hardware → `review_required`.
6. Device is not a NAPCO candidate → `skipped_non_napco`.
7. Match is not exact → never auto-proposed (only `review_required`).

Proposed ICCIDs are validated with the **same rule the RH identity importer
enforces** (digits only, 18–20), so a proposed value can never be refused
downstream. A backfill row only sets **empty** fields (the importer also refuses
to overwrite non-empty identity).

### Review-required cases
name/address fuzzy match · SubscriberName mismatch · duplicate radio number ·
device has an existing (different) ICCID · model mismatch · export row unrelated
to RH.

## Example JSON backfill row (importer-compatible)
```json
{ "device_id": "10107087", "iccid": "89148000007194217721", "serial_number": "10107087" }
```
Rich review row:
```json
{
  "device_id": "10107087", "site_id": "SITE-...", "current_model": "SLELTE - Fire",
  "suggested_vendor": "napco", "suggested_model": "SLELTE - Fire",
  "serial_number": "10107087", "iccid": "89148000007194217721",
  "napco_radio_number": "10107087", "napco_plan": "SLF-SVC-10-LSVI",
  "napco_gentech": "4G:LTE", "napco_subscriber_name": "Restoration Hardware #351 …",
  "operator_notes": "Matched by exact RadioNumber/device_id from NAPCO export"
}
```

## Feeding the plan into the identity importer
```bash
# 1. Dry-run the importer against the plan's importer_mapping (extract that array
#    to its own JSON file, or point at it directly if you split the document):
RH_DEVICE_MAP_FILE=rh_napco_iccid_mapping.json python -m app.backfill_rh_device_identity
# 2. Apply ONLY after review:
DRY_RUN=false RH_DEVICE_MAP_FILE=rh_napco_iccid_mapping.json \
  RH_DEVICE_ACTOR="you@manleysolutions.com" python -m app.backfill_rh_device_identity
```
The importer backfills only empty identity fields, refuses conflicts/unknown
fields, and audit-logs every change.

## Expected workflow
1. **Run this radio-match audit** (`--export-plan`).
2. **Review** the plan (`review_plan`, `review_required`, `refused`).
3. **Dry-run** the RH identity importer on `importer_mapping`.
4. **Apply** the identity importer only after review (`DRY_RUN=false`).
5. **Re-run the ICCID coverage audit** — confirm `import_ready` climbs.
6. **Re-run the NAPCO import in DRY_RUN** — confirm devices now match by ICCID.
7. **Re-run the portfolio/readiness audit**.

## Migration impact
**None.** No schema change, no migration, no DB writes. Pure SELECTs + an
optional operator-requested JSON file.

> This PR also re-lands the NAPCO importer's real-format detection
> (RadioNumber/ICCID/LastSignalReceived), which was orphaned by a stacked-merge
> and never reached `main` — without it the export parses as empty.
