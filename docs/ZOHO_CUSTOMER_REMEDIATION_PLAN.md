# Zoho ↔ True911 Customer Remediation Plan
### Integrity Property Management · Restoration Hardware · R&R Realty Group

**Read-only / proposal only.** This documents root causes, a normalization plan,
an automated mapping strategy, and a phased remediation. The migration scripts in
`proposals/zoho_customer_remediation/` are **proposals** — they are NOT wired into
Alembic and do NOT run on deploy. Nothing here modifies data.

---

## A. Root cause analysis

### A1. Why R&R Realty resolves to `tenant=default`
The R&R `customers` row has `tenant_id = "default"` — R&R was onboarded as a
*customer under the shared `default` tenant*, never given a dedicated tenant
(same shape as Webber). Before #96 the reconciliation scoped by `tenant_id`, so it
loaded the entire `default` tenant. After #96 it scopes by **ownership**
(`customer → sites.customer_id → devices.site_id`), so the 55 devices / 55 lines it
reports are R&R's real footprint — but they physically live under `default`.

**Root cause:** missing dedicated tenant; R&R (and likely RH, Integrity) sit in the
shared `default` tenant. Not a code bug — a tenancy/data-onboarding gap.

### A2. Why Restoration Hardware has 91 Zoho subscriptions but only 51 devices
The 40-record gap is the sum of three independent effects:
1. **Lifecycle records with no live device** — Zoho counts *billing* subscriptions
   including De-activated/cancelled ones; many have no corresponding True911 device
   anymore. (Mirrors the Webber pattern: De-activated in Zoho, asset retired.)
2. **Devices not yet in True911** — RH's NAPCO StarLink fleet is only partially
   represented in True911 (the RH ICCID audit found 51 device rows, 34 NAPCO
   candidates, **0 with ICCID**; the NAPCO export had ~33 RH radios). Subscriptions
   exist in Zoho for radios that were never imported as True911 devices.
3. **Multiple subscriptions per device** — a device/site can carry >1 Zoho
   subscription (e.g. separate data + voice/line subscriptions), so the Zoho count
   exceeds the device count even where coverage is complete.

**Root cause:** Zoho counts commercial subscriptions (active + deactivated + multi-
per-asset); True911 holds a smaller, incomplete operational device inventory.
91 ≠ 51 is expected and must be reconciled per-record, not by count.

### A3. Why duplicate-candidate counts are high for R&R
R&R has **55 devices and 55 lines** — i.e. one line per device, and the device's
cellular number (`devices.msisdn`) is the same value stored as the line's DID
(`lines.did`). The reconciliation flattens devices + lines into one MSISDN index
(`_t911_msisdn_entities`), so **every MSISDN matches 2 entities (its device *and*
its line)** and is flagged `duplicate_candidate`. These are mostly **false
positives** — a device and its own line legitimately share the MSISDN.

**Root cause:** device↔line are the same logical service sharing one MSISDN; the
matcher counts them as two. Fix is in the matcher (collapse a device and its linked
line), not in the data.

### A4. Why FacilityName values don't match True911 Sites
Zoho `FacilityName` is **device/line-level descriptive text**, not a site key:
`"Dodge Island - White Phone"`, `"Dodge Island - Red Phone"`,
`"Operations Building at Watson Island (RED)"`, `"Port Miami - DODGE ISLAND"`. True911
`sites.site_name` uses a coarser/different convention (often the site or address,
e.g. `"Dodge Island"`). The current normalized-substring match misses because:
- the facility name encodes a *per-phone* suffix (`- White Phone`, `(RED)`) that no
  site name contains;
- case/punctuation/abbreviation differences (`DODGE ISLAND` vs `Dodge Island`);
- one True911 site maps to *many* Zoho facilities (white/red phone, ops bldg, etc.).

**Root cause:** FacilityName is finer-grained than Site and uses descriptive naming;
matching needs suffix-stripping + token overlap, not exact/substring equality.

---

## B. Customer normalization plan

### B1. Canonical customer identity
Establish one canonical record per customer and an **alias set** spanning Zoho and
True911 spellings:

| Canonical | Known aliases (Zoho Account / Parent_Account / True911) |
|---|---|
| `restoration-hardware` | "Restoration Hardware", "RESTORATION HARDWARE #NNN", "RH", store-numbered names |
| `integrity-pm` | "Integrity Property Management", "Integrity", "Integrity PM" |
| `rr-realty` | "R&R Realty Group", "R&R Realty", "R & R Realty", "R and R Realty" |

Normalization rules (extend the existing `normalize_name`):
- lowercase, strip punctuation, collapse whitespace, drop legal suffixes;
- map `&` ↔ `and`; drop trailing store/site numbers (`#351`, `632`);
- match against **both** `Account.name` and `Parent_Account.name`.

### B2. Tenancy decision (per customer)
Decide, per customer, between two valid models — **no data change until chosen**:
- **Keep under `default`, rely on customer-scoping** (works today post-#96). Lowest
  risk; reconciliation already reports correct per-customer footprints.
- **Promote to a dedicated tenant** (`restoration-hardware`, `integrity-pm`,
  `rr-realty`) for isolation/branding. Requires a gated tenant-reassignment of the
  customer's sites/devices/lines from `default` → the new tenant (dry-run-first,
  audited) — proposed but not executed here.

Recommendation: **keep under `default` for now** (customer-scoping already isolates
them); revisit dedicated tenants only if multi-tenant isolation/branding is needed.

### B3. Alias storage (additive, proposed)
A proposed additive table `customer_alias` (canonical_key, source, alias, account_id)
lets the mapping cascade resolve any Zoho/True911 spelling deterministically —
see `proposals/zoho_customer_remediation/001_customer_alias_table.sql`. Additive,
nullable, no change to existing tables.

---

## C. Automated mapping strategy (deterministic cascade)

Map each Zoho `Subscription_Mgmnt` record to a True911 entity by trying the
strongest identity first; stop at the first confident hit. Produce a proposed
`external_record_map` row per subscription with a **confidence tier** — never
auto-confirmed.

| Tier | Signal | Rule | Confidence |
|---|---|---|---|
| 1 | **MSISDN** | normalized Zoho `MSISDN` == `devices.msisdn` OR `lines.did` (collapse a device and its own line into ONE asset before counting) | exact |
| 2 | **Device identifier** | Zoho radio/serial/ICCID == `devices.serial_number` / `devices.iccid` (RH NAPCO RadioNumber path) | exact |
| 3 | **Customer + Site name** | within the customer scope, `site_name` token-overlap with FacilityName (after suffix strip) | high |
| 4 | **FacilityName parse** | strip ` - White/Red Phone`, `(RED)/(WHITE)`, `Port Miami - ` prefixes → match remaining site token | medium |
| 5 | **Customer-only** | resolves the owning customer but no specific asset | low → `needs_mapping` |

Key rules:
- **De-duplicate device+line:** when `devices.msisdn == lines.did` and the line is
  linked to that device (`lines.device_id`), treat as one logical asset (kills the
  R&R duplicate-candidate inflation).
- **FacilityName normalization:** `strip_facility_suffix("Dodge Island - White Phone")
  → "Dodge Island"`; then token-overlap against site names.
- **Confidence gating:** only tier-1/2 (exact) are eligible for auto-suggested
  mapping; tiers 3–5 are `review_required`. Nothing is auto-`confirmed`.

This cascade is implementable as a read-only extension of the existing mapping
review (`audit_webber_mapping_review`) — proposed, not built here.

---

## D. Remediation sequence (phased, dry-run-first, gated)

1. **Coverage** *(read-only, exists)* — run `audit_zoho_staging_coverage` to confirm
   RH/Integrity/R&R staged=0, then **backfill** each into staging (dry-run →
   `FEATURE_ZOHO_BACKFILL=true --apply`). Without staged Zoho rows, nothing else can
   reconcile.
2. **Normalize** — load the `customer_alias` set (proposal 001) so the mapping
   cascade resolves all spellings. Additive only.
3. **Reconcile + map** — re-run reconciliation (customer-scoped) and the mapping
   cascade (C) to produce proposed `external_record_map` rows per subscription.
4. **De-dup matcher fix** — apply the device+line MSISDN collapse (a code change to
   the audit, not data) so R&R duplicate counts reflect reality.
5. **Operator review** — confirm tier-1/2 mappings; triage tier-3/5 by hand.
6. **Lifecycle** — for De-activated Zoho subs with stale/absent assets, use the
   gated `plan_customer_retirement` (dry-run → apply) per asset.
7. **Tenancy (optional)** — if dedicated tenants are chosen, run the proposed gated
   tenant-reassignment (proposal 002), dry-run first.

Each write step is feature-flagged, dry-run-first, audited, customer-scoped, and
never deletes.

---

## E. Proposed migration / remediation scripts (NOT applied)

In `proposals/zoho_customer_remediation/` — review-only, not wired to Alembic:
- `000_readonly_discovery.sql` — read-only queries to gather the REAL numbers
  behind A1–A4 (run first; confirms the analysis with live data).
- `001_customer_alias_table.sql` — **proposed** additive `customer_alias` table
  (canonical ↔ Zoho/True911 spellings). Additive, nullable.
- `002_tenant_reassignment_dryrun.sql` — **proposed** gated, transaction-wrapped
  (`ROLLBACK` by default) template to move a customer's sites/devices/lines from
  `default` to a dedicated tenant. Switch `ROLLBACK`→`COMMIT` only after review.

> All write templates default to `ROLLBACK`. Do not change to `COMMIT` without the
> dry-run review and an explicit go-ahead.
