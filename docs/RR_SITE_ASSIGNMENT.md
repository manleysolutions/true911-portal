# R&R Device→Site Assignment Diagnostic

**Read-only.** Determines whether R&R device records were imported with incorrect
site assignments, by comparing each device's `site_id` to the site of its matching
line (same MSISDN, same customer).

## Finding (the bulk-import pattern)
The pairing audit's 54 `site_mismatch` pairings resolve to: **devices were
bulk-imported onto a single placeholder site** (e.g. `SITE-1776963371486`, a
timestamp-style generated id) while the **lines carry the real per-property
sites**. The diagnostic confirms with:
- a **single device site dominating** (~98% of devices on one `site_id`),
- **lines spread across many distinct sites** (`line_distinct_sites` ≫
  `device_distinct_sites`),
- `lines_more_realistic = True`.

## Command
```bash
python -m app.audit_rr_site_assignment
python -m app.audit_rr_site_assignment --customer "R&R Realty Group" --export-json rr_sites.json
```

## Per-device report
`device_id` · `msisdn` · `device.site_id` · `device.site_name` · matching
`line.did` · `line.site_id` · `line.site_name` · `customer_id` · `customer_name` ·
classification · `proposed_site_id`.

Also: device count by site, line count by site, devices sharing a site, dominant
site + dominance %, distinct-site counts, and `lines_more_realistic`.

## Classification
| Class | Rule |
|---|---|
| `likely_correct` | `device.site_id == line.site_id` |
| `likely_wrong_site` | same MSISDN + customer, **different** site → line's site is the likely truth |
| `unassigned` | device has no `site_id` |
| `ambiguous` | no matching line, or MSISDN on >1 line |

## Proposed correction plan (NOT applied)
For each `likely_wrong_site` device, propose `device.site_id := matching
line.site_id` (the `proposed_site_id` column). This would be executed by a
**separate, gated, dry-run-first** remediation (feature-flagged, customer-scoped,
audited, no deletes) — not in this PR.

## Recommendation: correct site assignments BEFORE matcher changes
**Yes — fix the device site assignments first.** The earlier idea of relaxing the
collapse matcher to ignore `line.device_id` would **not** fix R&R, because these
pairs are `site_mismatch`, not merely `device_id`-missing: a matcher that still
requires same-site will keep seeing two different sites and won't collapse.

Correct sequence:
1. **Correct device→site assignments** (gated remediation: `device.site_id ←
   line.site_id` for `likely_wrong_site`). This also fixes location/E911 context,
   not just the duplicate count.
2. **Then** the existing collapse works (device + line now share the site); the
   `duplicate_candidate` inflation resolves without loosening the matcher.
3. A matcher relaxation (collapse by MSISDN+site+customer when `device_id` is NULL)
   is still a reasonable, separate hardening — but it is **secondary** to the site
   correction and not sufficient on its own for R&R.

## Safety
Read-only — only SELECTs (via the reconciliation customer-scoped loader). No
writes, no migrations, no matcher changes, no tenant changes. The correction is a
proposal only.
