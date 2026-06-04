# Customer Portfolio Reconciliation (dashboard)

**Read-only.** A portfolio-wide rollup across **all** customers (those with Zoho
`Subscription_Mgmt` records and/or True911 devices/lines): per-customer
reconciliation counts + a customer-level classification + recommended next action,
ordered low-risk / high-impact first — so remediation is prioritized instead of
done one customer at a time.

It reuses the per-customer reconciliation (`audit_zoho_true911_customer_reconciliation`)
and the RH subscription classifier (`audit_rh_subscription_classification`).

## Command
```bash
python -m app.audit_customer_portfolio_reconciliation
python -m app.audit_customer_portfolio_reconciliation --customer-filter "R&R" --limit 20 \
  --export-json portfolio.json --export-csv portfolio.csv
```
`--customer-filter` (substring), `--limit` (cap customers processed), `--export-json`,
`--export-csv`.

## Per-customer columns
customer · tenant · Zoho subscription count · device/line/site counts ·
`matched_ok` · `needs_mapping` · `missing_in_true911` · `missing_in_zoho` ·
`duplicate_candidate` · `status_mismatch` · `historical_subscription` ·
`missing_iccid` · `missing_site` · classification · recommended next action.

## Customer classification
| Class | Meaning / next action |
|---|---|
| `clean` | reconciles cleanly — no action |
| `needs_mapping_confirmation` | reconciles but mappings unconfirmed (baseline) |
| `needs_site_alignment` | duplicate_candidate / missing_site driven (R&R) — site inventory + gated device→site correction |
| `needs_iccid_backfill` | missing_iccid (RH) — RadioNumber→ICCID backfill |
| `needs_retirement_review` | historical/replacement De-activated subs (Webber) — gated retirement |
| `needs_import_backfill` | missing devices — NAPCO/subscriber import |
| `needs_manual_review` | mixed / insufficient data |

The dominant **structural** issue wins by count (tie-break = low-risk-first order:
retirement → site → iccid → import). `needs_mapping` is a baseline (every
unconfirmed Zoho record counts), so it classifies only when nothing structural
applies.

## Sample dashboard
```
customer                  tenant   zoho dev line mok dup hist icc -> classification
Restoration Hardware      default    91  51   40  51   3   30   7 -> needs_retirement_review
Webber Infra              default     7   4    4   1   0    7   0 -> needs_retirement_review
R&R Realty Group          default   119  55   55   0  54    0   0 -> needs_site_alignment
Integrity Property Mgmt   default     0   3    3   0   0    0   0 -> needs_import_backfill
Benson Systems            benson      6   6    6   6   0    0   0 -> clean

RECOMMENDED REMEDIATION ORDER (low-risk / high-impact first):
  1. Restoration Hardware  [needs_retirement_review]  archive historical subs
  2. Webber Infra          [needs_retirement_review]  gated retirement
  3. R&R Realty Group      [needs_site_alignment]     site inventory + device→site correction
  4. Integrity Property    [needs_import_backfill]    import missing devices
```

## Recommended remediation order (why)
1. **`needs_retirement_review`** — Zoho-side archive of De-activated subs; **lowest
   risk** (no True911 write), **high impact** (clears most of the count gaps).
2. **`needs_site_alignment`** — gated device→site correction (after the duplicate-site
   inventory check). Structural but well-gated.
3. **`needs_iccid_backfill`** — enables matching for active cellular subs.
4. **`needs_import_backfill`** — import the missing devices.
5. **`needs_mapping_confirmation`** — confirm mappings once the above are clean.
6. **`needs_manual_review`** — case-by-case.

Within a class, customers are ordered by impact (subscription, then device count).
A customer may have multiple issues — the dashboard surfaces all counts; the class
is its **dominant** blocker.

## Safety
Read-only — only SELECTs. No writes, no migrations, no mapping confirmations, no
status changes. `--export-*` write only the requested report files.
