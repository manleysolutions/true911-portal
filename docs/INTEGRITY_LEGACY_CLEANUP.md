# Integrity Legacy Tenant Cleanup (PR #77)

Retire the duplicate legacy tenant **`ipm`** after consolidation (PR #76).
**Dry-run-first, refusal-gated, no hard deletes** — soft-archive + retire only, so
the full audit trail is preserved and every change is reversible.

Script: `app/cleanup_legacy_ipm_tenant.py` (`DRY_RUN` defaults **true**).

## What it does (APPLY mode)
- Duplicate customers `#81`, `#82` → `status = "archived"`.
- Duplicate sites `TIFFANY-GARDENS-EAST` / `-NORTH` → `status = "archived"`, `onboarding_status = "retired"`.
- Tenant `ipm` → `is_active = False` (hidden from active dropdowns, kept for audit).
- Every change is written to the audit log (`tenant_cleanup` category). **No rows deleted.**

## Refusal gates (writes nothing if any fail)
1. `ipm` still has ANY operational records — `service_units / devices / sims / users / registrations / subscriptions > 0`.
2. `ipm` has an UNEXPECTED site (anything other than the two Tiffany duplicates).
3. A customer looks real — has a Zoho id, or a name that isn't the known duplicate.
4. A duplicate customer is still REFERENCED outside the archive set (a site in another tenant, a line, or a subscription).

## Never touched
`integrity-pm`, customer `#83`, Belle Terre, Vola devices, SIMs, the already-moved service units, Assurance data, T-Mobile/Vola integrations.

## Expected dry-run output
```
====================================================================
Legacy tenant cleanup: retire 'ipm' (survivor 'integrity-pm')   [DRY RUN]
====================================================================
Pre-flight counts (must all be 0):
    service_units : 0
    devices       : 0
    sims          : 0
    users         : 0
    registrations : 0
    subscriptions : 0

ARCHIVE customers:
    - customer#81 'Integrity Property Management' → status=archived
    - customer#82 'Integrity Property Management' → status=archived
ARCHIVE sites:
    - TIFFANY-GARDENS-EAST  'Tiffany Gardens East'  → status=archived, onboarding_status=retired
    - TIFFANY-GARDENS-NORTH 'Tiffany Gardens North' → status=archived, onboarding_status=retired
RETIRE tenant:
    - ipm → is_active=False (hidden from active dropdowns, kept for audit)

DRY RUN — safe to proceed, but nothing written. Re-run with DRY_RUN=false to apply.
```
If any gate fails the script prints `REFUSALS:` and writes nothing.

## Admin → Tenants update
`TenantOut` now includes `is_active`. The frontend filters the operational
dropdowns (Act-as / Cleanup target / Reset-keep) to **active** tenants, and the
main table shows a greyed **Retired** badge for `is_active=false` — so `ipm`
disappears from the working dropdowns but stays visible/traceable in the list.

## Apply command (DO NOT RUN YET)
```bash
# Render → true911-api → Shell (rootDir=api), only after reviewing the live dry run
DRY_RUN=false python -m app.cleanup_legacy_ipm_tenant
```

## Audit-after-cleanup
```bash
python -m app.audit_integrity_tenants          # confirms ipm is archived/retired (PR #75 script)
# Or check the audit log for the tenant_cleanup entries.
```

## Rollback
No deletes occurred, so rollback is a flag flip (recorded in the audit detail):
- `Tenant(ipm).is_active = True`
- `Customer(81/82).status = "active"`
- `Site(TIFFANY-*).status = "active"`, `onboarding_status = "active"`
Or `git revert` the PR (the script is additive tooling).

## Migration impact
**None.** No schema change (uses existing `status` / `onboarding_status` / `is_active` columns). `TenantOut` gained an optional field (additive).

## Risk
Low. Default dry-run + four hard refusal gates + soft-archive (no deletes) make
an accidental destructive run effectively impossible; everything is reversible
and audit-logged. The tenant is retired (not deleted), so it remains auditable.
