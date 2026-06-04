# Zoho Subscription_Mgmt → Staging Backfill

Pulls existing Zoho CRM `Subscription_Mgmt` records into the additive shadow
tables (`zoho_subscription_records` + `external_record_map`) so the
reconciliation audit has a Zoho side to compare. Needed because the webhook
ingest only captures records that arrive **after** it was enabled — pre-existing
records (e.g. **Webber Infra**) are missing from the mirror.

## Why this exists
The reconciliation audit found `NO ZOHO MIRROR RECORDS FOUND FOR WEBBER INFRA`.
The webhook (`FEATURE_ZOHO_SUBSCRIPTION_INGEST`) never fired for Webber's
already-existing subscription, so staging is empty for it. This backfill reads
those records from the Zoho API and stages them through the **same** upsert the
webhook uses.

## Safety contract
- **Reads** from Zoho CRM (OAuth via `app.services.zoho_crm`).
- **Writes only** to `zoho_subscription_records` and `external_record_map`.
  **Never** `customers` / `sites` / `devices` / `lines` / `subscriptions`.
- **Never deletes.**
- **Dry-run by default** — prints what *would* be staged, writes nothing.
  The APPLY path additionally requires **`FEATURE_ZOHO_BACKFILL=true`**.
- **Idempotent** by `(org_id, subscription_mgmt_id)` — re-runs update in place.
- **Lifecycle unchanged** — `lifecycle_state` stays NULL unless the separate
  `FEATURE_ZOHO_STATUS_NORMALIZER` is enabled (same rule the webhook follows).

## Zoho module + fields (Render-confirmed)
- The live CRM module API name is **`Subscription_Mgmnt`** (misspelled in Zoho —
  this is now the default; override with `--module`). It is intentionally
  distinct from the webhook payload label in `ZOHO_SUBSCRIPTION_MODULES`.
- Zoho v5 custom-module reads **require a `fields` param** (otherwise
  `400 REQUIRED_PARAM_MISSING fields`). The backfill sends a safe default set:
  `id, Account_Name, FacilityName, Mobile_Number, Device_Activation_Status,
  Subscription_Type, Connection_Type, Monthly_Recurring_Charge,
  Service_Term_Ends, Modified_Time`. Override via `--fields` or the
  `ZOHO_SUBSCRIPTION_FIELDS` env var (precedence: `--fields` > env > default).

## Pagination (Zoho v5 > 2000 records)
Zoho v5 offset pagination (`page`/`per_page`) only covers the first **2000**
records — beyond that it returns `DISCRETE_PAGINATION_LIMIT_EXCEEDED` and requires
a `page_token`. The backfill uses `page`/`per_page` until a response carries
`info.next_page_token`, then **follows the token** (preferred whenever present),
and stops when `more_records` is false with no token left. Use **`--max-records N`**
to bound how many records are *scanned* during a dry-run (omit for a full backfill).

## Commands
```bash
# Dry-run a single customer (no writes, no flag needed):
python -m app.backfill_zoho_subscription_staging --customer "Webber Infra"

# Bounded dry-run (scan at most 100 Zoho records — safe quick peek):
python -m app.backfill_zoho_subscription_staging --customer "Webber Infra" --max-records 100

# Dry-run everything:
python -m app.backfill_zoho_subscription_staging --all

# Override fields or module if needed:
python -m app.backfill_zoho_subscription_staging --customer "Webber Infra" \
  --module "Subscription_Mgmnt" --fields "id,Account_Name,Device_Activation_Status,Modified_Time"

# APPLY for one customer (requires the flag; writes only staging tables):
FEATURE_ZOHO_BACKFILL=true \
  python -m app.backfill_zoho_subscription_staging --customer "Webber Infra" --apply
```
`--apply` without `FEATURE_ZOHO_BACKFILL=true` is refused and falls back to
dry-run. `DRY_RUN=true` forces dry-run even with `--apply`.

## Tables affected
| Table | Dry-run | Apply |
|---|---|---|
| `zoho_subscription_records` | read-only (existence check) | insert/update (idempotent) |
| `external_record_map` | — | insert if new (`map_status='unmapped'`, never auto-confirmed) |
| customers / sites / devices / lines / subscriptions | — | **never touched** |

## After backfill
1. Re-run the mirror validation (`zoho_subscription_records` count for Webber).
2. Re-run the reconciliation audit:
   `python -m app.audit_zoho_true911_customer_reconciliation --customer "Webber"`.
3. Confirm Webber now produces `deactivated_in_zoho_active_in_true911` if Zoho
   shows De-activated.

## Migration impact
**None** — no schema change, no migration. Adds the env flag `FEATURE_ZOHO_BACKFILL`
(default off) and `ZOHO_BACKFILL_ORG_ID` (optional). Writes only existing staging
columns.
