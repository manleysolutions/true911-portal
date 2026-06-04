# Zoho Staging Coverage Audit

**Read-only.** Explains why Zoho `Subscription_Mgmnt` data that exists in Zoho CRM
is missing from the staging tables the reconciliation reads. For each customer it
compares the **live Zoho count** against the **staged count** and gives the exact
fix.

## Root cause it surfaces
Staging is populated only by:
1. the **webhook ingest** — which captures events that arrive *after* the flag was
   enabled; it **never backfills history**, and
2. the **backfill** (`app.backfill_zoho_subscription_staging`) — which stages only
   the customers it is *run for*.

So a customer whose subscriptions predate the webhook and was never backfilled
(Restoration Hardware, Integrity, R&R) shows `staged=0` even though Zoho has
records. Only **Webber** was backfilled, which is why only Webber reconciles.

## Command
```bash
python -m app.audit_zoho_staging_coverage
python -m app.audit_zoho_staging_coverage --customer "R&R Realty" --export-json cov.json
```
Defaults to `Restoration Hardware, Integrity, R&R Realty, Webber Infra`.

## Per-customer output
Zoho `Subscription_Mgmnt` count, staged `zoho_subscription_records` count,
`external_record_map` count, account names found (Zoho + staged), account ids,
staging first-seen / last-updated, coverage verdict, and whether a backfill is
required + the exact command.

## Coverage verdicts
| Verdict | Meaning |
|---|---|
| `complete` | staged ≥ Zoho (>0) |
| `missing_backfill_required` | Zoho > 0, staged = 0 (never backfilled) |
| `partial_backfill_required` | 0 < staged < Zoho |
| `staged_no_zoho` | staged rows but Zoho returned 0 — likely an account-name mismatch (Account vs Parent_Account / normalization) |
| `none_either_side` | no Zoho subscriptions and none staged |
| `zoho_unavailable` | could not query Zoho — staged count still reported |

## Recommended fix (for `missing_*` / `partial_*`)
Run the staging backfill **per customer**, dry-run first:
```bash
python -m app.backfill_zoho_subscription_staging --customer "Restoration Hardware"
FEATURE_ZOHO_BACKFILL=true \
  python -m app.backfill_zoho_subscription_staging --customer "Restoration Hardware" --apply
```
Then re-run this coverage audit and the reconciliation.

## Safety
Read-only — only SELECTs + read-only Zoho GETs. No writes, no backfill, no imports,
no status changes. Zoho is queried best-effort (unreachable → `zoho_unavailable`,
staging still reported). No migration.
