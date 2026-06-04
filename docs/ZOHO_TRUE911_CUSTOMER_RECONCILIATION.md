# Zoho CRM ↔ True911 Customer Reconciliation Audit

**Read-only.** Compares the staged Zoho CRM lifecycle data against True911
customer / site / device / line data, **customer-by-customer**, so we can find
and fix setup/status mismatches **before** enabling any automated Zoho → True911
sync.

## What it does NOT do
Strictly read-only — only SELECTs. **No** writes, backfill, import, automation,
schema change, migration, API change, webhook/auth change, or UI change.
`--export-json` / `--export-csv` write an operator-requested report file only.

The Zoho side is read from the **staged mirror** (`zoho_subscription_records` +
`external_record_map`) that the gated webhook ingest already populates — this
audit does **not** call the live Zoho API. Lifecycle is derived with the existing
pure `zoho_status_normalizer`, so it works even if `lifecycle_state` was never
populated (normalizer flag off).

## Command
```bash
python -m app.audit_zoho_true911_customer_reconciliation --customer "Webber"
python -m app.audit_zoho_true911_customer_reconciliation --customer "Restoration Hardware" --customer "Integrity"
python -m app.audit_zoho_true911_customer_reconciliation --all
python -m app.audit_zoho_true911_customer_reconciliation --all \
    --export-json /tmp/zoho_recon.json --export-csv /tmp/zoho_recon.csv
```

## What is compared (per customer)
| Zoho (staged) | True911 |
|---|---|
| Account / `account_name` | Customer / Tenant name |
| `Subscription_Mgmt` records | Subscriptions / lines |
| Device Activation Status (raw) | device/line operational status |
| normalized lifecycle (`lifecycle_state`) | tenant active + device/line health |
| `MSISDN` / Mobile Number | `Device.msisdn`, `Line.did` |
| `FacilityName` | `Site.site_name` |
| `external_record_map.map_status` | (mapping confidence) |

## Classifications
| Class | Meaning |
|---|---|
| `matched_ok` | Zoho and True911 agree (lifecycle + identifiers) |
| `missing_in_true911` | Zoho has an MSISDN / facility with no True911 device/line/site |
| `missing_in_zoho` | True911 device/line MSISDN has no Zoho record |
| `status_mismatch` | matched MSISDN but Zoho lifecycle ≠ True911 operational state |
| `identifier_mismatch` | matched by name but identifiers don't line up |
| `needs_mapping` | Zoho record not `confirmed` in `external_record_map`, or no True911 entity resolves |
| `duplicate_candidate` | same MSISDN on >1 Zoho record or >1 True911 entity |
| `deactivated_in_zoho_active_in_true911` | **Zoho De-activated but True911 still active/monitored** |
| `active_in_zoho_inactive_in_true911` | Zoho Active but True911 inactive/not monitored |

## Webber — first explicit test case
Zoho shows **Device Activation Status = De-activated** while True911 still treats
Webber as active/monitored. The audit flags this clearly:
```
### Webber  (tenant=webber)
    [deactivated_in_zoho_active_in_true911] customer:Webber — Zoho lifecycle is De-activated but True911 still treats this customer as active/monitored
    [status_mismatch] msisdn:8563081391 — Zoho De-activated but the matched True911 entity is active
    [missing_in_zoho] msisdn:7542697860 — True911 line WEB-L1 has an MSISDN with no Zoho record
    [missing_in_true911] site:Webber Plant 5 — Zoho FacilityName has no matching True911 site
```
This matches the project rule that lifecycle (Zoho-owned) and operational status
(True911 telemetry) are **separate axes**: a De-activated subscription must never
present as healthy active monitoring.

## Recommended customer-by-customer cleanup process
1. **Run** `--customer "<name>"` (or `--all --export-csv …`).
2. **Triage** the headline cross-axis flags first
   (`deactivated_in_zoho_active_in_true911`, `active_in_zoho_inactive_in_true911`).
3. **Confirm mappings** (`needs_mapping`) in the read-only Zoho review surface
   before trusting any match.
4. **Resolve identifiers** (`duplicate_candidate`, `identifier_mismatch`,
   `missing_in_*`) — align MSISDN/facility between systems.
5. **Decide the True911 action** per customer (e.g. mark Webber inactive) — done
   through the normal product surfaces, **not** this audit.
6. **Re-run** the audit until a customer is `matched_ok`.
7. Only after the portfolio is clean, consider enabling the gated automated sync.

## Migration impact
**None** — no schema change, no migration, no DB writes. Pure SELECTs + optional
operator-requested report files.
