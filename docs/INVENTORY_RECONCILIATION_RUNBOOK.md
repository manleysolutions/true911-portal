# True911+ — Inventory Reconciliation Runbook (EPIC-GEN-003)

> Customer- and vendor-agnostic **read-only** reconciliation: compare an external
> carrier/vendor inventory (via a pluggable adapter) against True911 inventory and emit
> `INVENTORY_RECONCILIATION.csv` + `.json` + summary stats. **No DB writes, no feature
> flags, no production mutation.** Reusable for RH, R&R, Benson, Integrity, USPS, and any
> future vendor.
>
> **Authority Level:** 4 — Process. **Governed by:** `CONSTITUTION.md` (§4.2 read-only
> first; §4.7 tenant isolation). **Engine:** `app/services/reconciliation/`. **Runner:**
> `python -m app.reconcile_inventory`. Prepared: 2026-06-23.

---

## What it is
A **reusable engine** (`services/reconciliation/engine.py`) that matches canonical
`VendorRecord`s (produced by a per-vendor **adapter**) against canonical `True911Item`s
(loaded read-only from the DB), classifies each, and writes the artifacts. The engine
knows **nothing** about NAPCO or any customer — new vendors are new adapters; new
customers are just a different `--tenant` scope.

## Matching hierarchy (strongest first)
| # | Basis | Confidence |
|---|---|---|
| 1 | **ICCID** exact | 1.0 |
| 2 | **RadioNumber** exact | 0.9 |
| 3 | **SubscriberName** normalized exact | 0.6 → REVIEW |
| 4 | **Site/address** token similarity (≥0.5) | ~0.4 → REVIEW |

## Result enum
| Result | Meaning |
|---|---|
| `MATCHED` | strong-key match **and** full True911 linkage (site + service unit) |
| `PARTIAL` | strong-key match but missing site/service-unit linkage (gaps in Notes; E911-unverified is noted) |
| `MISSING_IN_TRUE911` | vendor radio has no True911 device |
| `MISSING_IN_VENDOR` | True911 device (in scope) absent from the vendor export |
| `DUPLICATE` | ICCID duplicated in the vendor export, or a key matches >1 True911 device |
| `REVIEW` | only a weak (name/site) match — needs a human |

## Output — `INVENTORY_RECONCILIATION.csv` (+ `.json`)
Columns: `Customer, Site, RadioNumber, ICCID, SubscriberName, True911DeviceID,
True911Site, True911Customer, ServiceUnitID, E911Status, LastTelemetry, Confidence,
Result, Notes`. The `.json` adds **summary statistics** (counts by result, vendor record
count, match rate). Carrier account numbers, CS-receiver phone numbers, and dealer email
from the vendor export are **never** carried into the artifacts.

---

## Run (READ-ONLY)
```bash
# NAPCO, all tenants:
python -m app.reconcile_inventory --vendor napco --vendor-export /path/to/Radiolist.xlsx

# scoped to one customer/tenant + custom output base:
python -m app.reconcile_inventory --vendor napco --vendor-export /path/to/Radiolist.tsv \
    --tenant restoration-hardware --out /tmp/INVENTORY_RECONCILIATION
```
- `--vendor` selects the adapter (currently: `napco`).
- `--vendor-export` is the vendor file (NAPCO: `.xlsx`, or tab/comma-delimited text).
- `--tenant` (optional) scopes the True911 side to one customer; omit for all.
- `--out` is the output base → writes `<out>.csv` and `<out>.json`.

The runner loads inventory with `db.rollback()` and **never writes**. It must run where
the True911 DB is readable (prod or a read replica — `DATABASE_URL` set).

## Adding a new vendor adapter
1. Add `app/services/reconciliation/adapters/<vendor>.py` exposing `parse(path) ->
   list[VendorRecord]` and `base.register("<vendor>", <Adapter>())`.
2. Map only the canonical fields (`radio_number`, `iccid`, `subscriber_name`,
   `customer_hint`, `site_hint`); **do not** retain sensitive carrier/account fields.
3. Add a unit test with a synthetic fixture (never commit real customer exports).
The engine, CSV/JSON export, and runner need no changes.

## Reuse across customers
The engine + adapters are customer-agnostic; `--tenant` (or no scope) selects the
customer. RH is simply the first dataset reconciled; R&R / Benson / Integrity / USPS use
the same engine with their own tenant and (if a different carrier) a new adapter.

## Safety
Read-only · no DB writes · no feature flags · no production mutation · no sensitive vendor
fields in artifacts · tenant-scopable. The real reconciliation CSV is produced by running
the tool against the True911 DB + the vendor export; this repo ships the engine, the NAPCO
adapter, and tests (synthetic fixtures only).

---

*Runbook — read-only reconciliation. Writes only the requested CSV/JSON artifacts, never
production data; changes no behavior; enables no flag.*
</content>
