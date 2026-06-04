# R&R Site Inventory Diagnostic

**Read-only.** Before applying the device→site correction (PR #105), verify the
proposed destination sites are truly **distinct properties** and not **duplicate
site records**. The #105 dry-run showed 54 destination sites all named
`"R&R REALTY GROUP - West Des Moines, IA - Main Office"` — this tool checks whether
they share an address (duplicate records) or have distinct addresses (distinct
properties).

## Command
```bash
python -m app.audit_rr_site_inventory --customer "R&R Realty Group"
python -m app.audit_rr_site_inventory --customer "R&R Realty Group" --export-json rr_sites.json
```

## Per-site output
`site_id` · `site_name` · address (`e911_street`/`city`/`state`/`zip`) ·
`customer_id` · `device_count` · `line_count` · `msisdns` · `dids` · occupancy
(empty / line_only / device_only / both) · classification.

## Classification
| Class | Meaning |
|---|---|
| `valid_distinct_site` | unique name, real occupancy |
| `duplicate_site_name_unique_address` | shares a name with others but **distinct address** → distinct property |
| `duplicate_site_name_same_address` | shares a name **and** the same/duplicate (or missing) address → **duplicate record** |
| `placeholder_site` | address-less, device-only, holding ≥5 devices → bulk-import dump |
| `empty_site` | no devices, no lines |
| `line_only_site` / `device_only_site` | only one side present |

## Recommendation logic — is PR #105 apply safe?
- **`duplicate_site_name_same_address` > 0 → NOT SAFE.** The destinations are
  duplicate site records (same name + same/missing address). Applying #105 would
  scatter devices across duplicate records. **Merge/consolidate the duplicate sites
  first**, then re-run the correction.
- **only `duplicate_site_name_unique_address` → LIKELY SAFE.** The destinations
  share a generic name but have distinct addresses (distinct properties). Verify a
  sample, then apply.
- otherwise → **REVIEW** manually.

## Example (worst case — 54 same-name, no-address destinations)
```
duplicate_site_name_same_address  : 54
placeholder_site                  : 1
TOP DUPLICATE SITE-NAME GROUPS:
  54x 'R&R REALTY GROUP - West Des Moines, IA - Main Office'  distinct_addresses=1  with_address=0
RECOMMENDATION:
  NOT SAFE to apply PR #105 yet: 54 destination site(s) appear to be DUPLICATE records …
  Consolidate/merge the duplicate sites first, then re-run.
```

## Safety
Read-only — only SELECTs. No writes, no migrations, no device reassignment, no site
merge, no deletes.
