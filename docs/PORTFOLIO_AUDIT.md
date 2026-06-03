# Portfolio Audit Framework (PR #78)

Generic, **read-only** audit that evaluates every True911 tenant with the same
methodology we used for Integrity. **No production changes, no migrations, no
cleanup** — SELECT-only.

Two tools:
- `app/audit_integrity_tenants.py` — Integrity-specific, now **archive-aware**.
- `app/portfolio_audit.py` — generic framework for **all** customers.

## Operational vs Archived

A record is **archived** when its `status` is `archived` or `retired` (set by the
cleanup flow). Everything else is **operational**. The audit now reports the two
separately, so a retired tenant holding only archived rows reads as
`RETIRED / ARCHIVE ONLY` instead of the old, misleading "would need migration".

## Tenant status definitions

| Status | Meaning |
|---|---|
| **ACTIVE** | `is_active=true` and has operational records, with an owning customer. |
| **ORPHANED** | Active, has operational sites/devices but **no operational customer**. |
| **ARCHIVE ONLY** | Active but **no operational records** — only archived rows remain. |
| **EMPTY** | Active with **no records at all** — purge-empty eligible. |
| **RETIRED / ARCHIVE ONLY** | `is_active=false`, no operational records (only archived). Final-purge eligible once confirmed. |
| **RETIRED (has operational records)** | `is_active=false` but still holds operational records — **investigate**, do not purge. |

**Flags** (non-exclusive): `active`, `retired`, `archive-only`, `empty`,
`duplicate-name`, `orphaned`, `healthy`.

## Tenant Health Score (0–100)

Deterministic, life-safety-weighted. `None` when the tenant has no operational
records (score is not applicable to empty/retired tenants).

| Component | Weight | Definition |
|---|---|---|
| **E911** | 40 | fraction of operational sites with a **verified** dispatchable address (`validated`/`verified`/`confirmed`) |
| **Device health** | 30 | fraction of operational devices with a **fresh heartbeat** (≤ `PORTFOLIO_DEVICE_FRESH_DAYS`, default 7) |
| **Ownership** | 20 | has at least one operational customer |
| **Hygiene** | 10 | −5 for a duplicate tenant name, −5 for orphaned operational records |

> The device-health and assurance readiness here are **data proxies** computed
> directly from `Device.last_heartbeat` and the E911 fields — the audit does NOT
> import the Assurance/Health engines (keeps it read-only and dependency-light).

## Operational Risks & Cleanup Opportunities
Each tenant lists, e.g.: *active site(s) without verified E911*, *device(s)
without a fresh heartbeat*, *active sites but no devices*, *orphaned records*; and
opportunities like *archive-only but still active — consider retiring*, *retired
with archived rows — eligible for final purge*, *empty + active — purge-empty
eligible*.

## Commands

```bash
# All tenants (portfolio sweep)
python -m app.portfolio_audit

# One tenant (confirm the slug in Admin → Tenants)
PORTFOLIO_AUDIT_TENANT=integrity-pm python -m app.portfolio_audit

# Archive-aware Integrity audit
python -m app.audit_integrity_tenants
```

## PART 4 — Wave 1 customer audits

Run each (read-only). **Confirm the exact tenant slug** in Admin → Tenants first
(the slugs below are best-guess; substitute the real one):

```bash
PORTFOLIO_AUDIT_TENANT=restoration-hardware python -m app.portfolio_audit   # 1
PORTFOLIO_AUDIT_TENANT=benson-systems        python -m app.portfolio_audit  # 2
PORTFOLIO_AUDIT_TENANT=rr-realty             python -m app.portfolio_audit  # 3
```

### Expected output structure (per tenant)
```
Tenant: <slug>  (<name>)
  Status: <ACTIVE|ORPHANED|...>   flags=[...]
  Health Score: <0-100>   {e911, device_health, ownership, hygiene}
  Operational: customers=, sites=, service_units=, devices=, sims=, users=, subscriptions=, registrations=
  Archived:    customers=, sites=
  E911: <verified>/<active sites> verified (<with_address> have an address)
  Device Health: <fresh>/<devices> fresh (<ever reported>)
  Operational Risks:  ! ...
  Cleanup Opportunities:  ~ ...
```
…followed by a PORTFOLIO SUMMARY ranking tenants by score (worst first).

### Risk categories to watch
- **Compliance:** active sites without verified E911 (life-safety — highest priority).
- **Reachability:** devices without a fresh heartbeat; active sites with no devices.
- **Data integrity:** orphaned records (no owning customer); cross-tenant references.
- **Duplication:** duplicate tenant names / customers (consolidation candidates).
- **Lifecycle:** archive-only-but-active, retired-with-operational-records, empty tenants.

### Recommended audit sequence
1. **Restoration Hardware** — largest portfolio (most sites/devices) → highest
   operational + compliance surface; validates the framework at scale and finds
   the most impactful gaps first.
2. **Benson Systems** — mid-size; confirm the methodology generalizes.
3. **R&R Realty** — smallest; quick confirmation + close out Wave 1.

## PART 5 — Recommended next customer

**Restoration Hardware.** It is the largest active portfolio (the prior audit
showed ~12 sites / ~45 devices), so it carries the most E911-compliance and
device-reachability risk and the greatest customer value. Auditing it first
surfaces the highest-impact issues and stress-tests the scoring before the
smaller Benson Systems and R&R Realty audits.

*Audit only — these scripts write nothing.*
