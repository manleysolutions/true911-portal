# Integrity Tenant Consolidation Plan (PR #76)

Consolidate the duplicate Integrity tenant **`ipm`** into the survivor
**`integrity-pm`**. **First pass = move/merge/re-point only — NO deletes.**
Duplicate customers and duplicate Tiffany sites are flagged for a separate,
reviewed purge PR.

Script: `app/consolidate_integrity_tenants.py` — `DRY_RUN` defaults to **true**.

## Audit inputs (provided)

| | `ipm` | `integrity-pm` (survivor) |
|---|---|---|
| customers | 2 (id=81, id=82, no Zoho) | 1 (id=83, Zoho 337391000069074135) |
| sites | TIFFANY-GARDENS-EAST, TIFFANY-GARDENS-NORTH | IPM-BELLE-TERRE, IPM-POMPANO, IPM-TIFFANY-EAST, IPM-TIFFANY-NORTH |
| service units | 4 | 3 (Belle Terre EL1–3) |
| devices / sims | 0 / 0 | 3 / 3 |
| users | 0 | 2 |
| subscriptions | 1 (inactive) | — |

## Duplicate detection (by normalized site name)

- `TIFFANY-GARDENS-EAST` (ipm) ≡ `IPM-TIFFANY-EAST` (survivor) — same name.
- `TIFFANY-GARDENS-NORTH` (ipm) ≡ `IPM-TIFFANY-NORTH` (survivor) — same name.
- Customers id=81 / id=82 ≡ canonical id=83 (same name; 81/82 have no Zoho).

## Records to MOVE
- **4 service units** from the ipm Tiffany sites → the matching survivor sites
  (`IPM-TIFFANY-EAST` / `IPM-TIFFANY-NORTH`), re-tenanted to `integrity-pm`.
  The survivor Tiffany sites currently have **0** units, so these are the only
  emergency endpoints for those properties — they must be preserved.
  *(A unit is DISCARDED instead of moved only if the survivor site already has a
  unit of the same `unit_type`.)*

## Records to MERGE
- **E911 address (blank-fill only):** if an ipm Tiffany site has a street/city/
  state/zip the survivor site is missing, copy it into the survivor — **never
  overwrites** existing survivor data, and **does not touch `e911_status`** (that
  stays with the audited E911 flow).
- **Subscription (1, inactive):** re-point `customer_id` → canonical **id=83**
  and `tenant_id` → `integrity-pm`. Status preserved (stays inactive). Billing
  history is kept, not deleted.

## Records to ARCHIVE — DEFERRED (not touched this pass)
- **Customers id=81, id=82** — duplicates of canonical id=83 (Zoho-linked).
- **Sites TIFFANY-GARDENS-EAST / -NORTH** — duplicates of the survivor Tiffany
  sites (after their units have moved off).
These are **flagged only**. A follow-up purge PR removes them once this pass is
verified and nothing references them — then `ipm` is empty and can be retired.

## UNTOUCHED (hard guards)
- **IPM-BELLE-TERRE** and its devices / SIMs / 3 service units.
- **Vola devices** (ipm has 0; the script never updates any device row).
- **Assurance / lifecycle / `e911_status`** fields.
- All `integrity-pm` devices / SIMs / users.

## Expected dry-run output

```
====================================================================
Integrity tenant consolidation: ipm → integrity-pm
  mode: DRY RUN (no writes)
====================================================================

MOVE service units: 4
    - <TGE unit 1> Elevator 1  TIFFANY-GARDENS-EAST→IPM-TIFFANY-EAST @ integrity-pm
    - <TGE unit 2> Elevator 2  TIFFANY-GARDENS-EAST→IPM-TIFFANY-EAST @ integrity-pm
    - <TGN unit 1> Elevator 1  TIFFANY-GARDENS-NORTH→IPM-TIFFANY-NORTH @ integrity-pm
    - <TGN unit 2> Elevator 2  TIFFANY-GARDENS-NORTH→IPM-TIFFANY-NORTH @ integrity-pm

MERGE site E911 (fill blanks only): 0–2   (only if an ipm Tiffany site has an address the survivor lacks)

MOVE sites (no survivor match): 0

RE-POINT subscriptions: 1
    - sub#<id> (status=inactive) → customer 83 @ integrity-pm

ARCHIVE candidates — customers (DEFERRED): 2
    - customer#81 'Integrity Property Management' — duplicate of canonical customer id=83 (Zoho 337391000069074135)
    - customer#82 'Integrity Property Management' — duplicate of canonical customer id=83 (Zoho 337391000069074135)

ARCHIVE candidates — sites (DEFERRED): 2
    - TIFFANY-GARDENS-EAST (merged into IPM-TIFFANY-EAST) — duplicate; archive after units moved (deferred to purge PR)
    - TIFFANY-GARDENS-NORTH (merged into IPM-TIFFANY-NORTH) — duplicate; archive after units moved (deferred to purge PR)

DISCARD duplicate units: 0
SKIPPED / untouched: 0

DRY RUN — nothing written. Re-run with DRY_RUN=false to apply (move/merge/repoint only).
```
*(The exact unit ids and the E911-merge count come from the live data — run the
dry run to confirm before applying. The script never guesses.)*

## Risks
- **Service-unit `unit_id` collision:** units keep their `unit_id` when moved; if
  an ipm unit_id happened to equal a survivor unit_id the move would violate the
  unique key. The live dry run surfaces this (it lists each unit). Mitigation:
  inspect the printed ids first; rename in a one-off if needed.
- **Wrong duplicate match:** matching is by normalized site *name*. If the two
  Tiffany pairs are genuinely different buildings, the merge would be wrong.
  Mitigation: the dry run prints which source maps to which survivor — confirm
  before applying.
- **E911 blank-fill:** only fills missing fields and never `e911_status`, so a
  filled address still reads as *unverified* until the audited E911 flow
  validates it — no false "validated" is introduced.
- **Leaves `ipm` non-empty:** after this pass `ipm` still holds the 2 duplicate
  customers + 2 archived sites, so it is intentionally NOT yet purgeable — that
  is the follow-up PR's job.

## Rollback
- **Before apply:** nothing to roll back (dry run writes nothing).
- **After apply:** every change is reversible and audit-logged
  (`tenant_consolidation` category in the audit log). To reverse: re-point the
  moved units back (`site_id`/`tenant_id`), clear the blank-filled E911 fields,
  and re-point the subscription to its original customer/tenant — all recorded
  in the audit detail. No rows are deleted, so there is no data-loss to recover.
- Or `git revert` the PR (the script is additive; reverting removes the tool).

## Apply command (DO NOT RUN YET)
After reviewing the live dry-run output:
```bash
# Render → true911-api → Shell (rootDir=api)
DRY_RUN=false python -m app.consolidate_integrity_tenants
```
This moves the 4 units, merges blank E911, and re-points the subscription —
**never deletes**. Purging the now-redundant `ipm` customers/sites and retiring
the empty `ipm` tenant is a **separate follow-up PR** run only after this is
verified.
