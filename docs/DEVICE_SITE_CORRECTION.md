# Device→Site Correction Planner (gated, dry-run-first)

Corrects the R&R bulk-import artifact (`audit_rr_site_assignment`): devices were
imported onto a placeholder site while their lines carry the real per-property
sites. For each `likely_wrong_site` device this plans `devices.site_id <- the
matching line's site_id` and, only when authorized, applies it.

## Commands
```bash
# DRY RUN (default — writes nothing):
python -m app.plan_device_site_correction --customer "R&R Realty Group"

# APPLY (gated):
FEATURE_DEVICE_SITE_CORRECTION=true \
  python -m app.plan_device_site_correction --customer "R&R Realty Group" --apply

# With exports:
python -m app.plan_device_site_correction --customer "R&R Realty Group" \
  --export-json rr_fix.json --export-csv rr_fix.csv
```

## Per-correction output
`device_id` · `msisdn` · current site (id + name) · proposed site (id + name) ·
reason.

## Safety gates
1. **Dry-run by default** — writes nothing.
2. **`--apply`** must be passed, **and**
3. **`FEATURE_DEVICE_SITE_CORRECTION=true`** — otherwise downgrades to dry-run.
4. **Updates `devices.site_id` only** — never lines, never customers, never deletes.
5. **Customer-scoped** — the proposed site must be one of this customer's sites
   (else refused as a customer mismatch).
6. **Refuses** `ambiguous` (no/multiple matching lines), `unassigned`,
   `no proposed site`, and `customer-mismatch` rows. `likely_correct` rows are
   skipped (nothing to do).
7. Every applied change is **audit-logged** (`device / site_correction`).

## Sample dry-run (R&R)
```
Device→Site Correction Planner — R&R Realty Group — DRY RUN (no writes)
  to_correct=54  skipped=1
  PROPOSED CORRECTIONS (54):
    RR-D0  msisdn=3055500000  site SITE-1776963371486 (imported placeholder) -> SITE-000000 (R&R Property 0)
    ...
  SKIPPED (1): {'already on the correct site': 1}
  DRY RUN — nothing written. Apply needs --apply + FEATURE_DEVICE_SITE_CORRECTION=true.
```

## Expected R&R reconciliation improvement
After applying the 54 corrections, each device shares its line's site → the
device+line collapse fires (same MSISDN + same site) → the 54 false
`duplicate_candidate` entries become `matched_ok`. It also restores each device's
real **location / E911 / site context**, not just the duplicate count. Re-run
`audit_rr_device_line_pairing` (expect ~all `collapsible_exact`/matched) and the
reconciliation (expect `duplicate_candidate` ≈ 0) to confirm.

## Migration impact
**None** — no schema change, no migration. Adds the `FEATURE_DEVICE_SITE_CORRECTION`
flag (default off). Writes only the existing `devices.site_id` column, gated.
