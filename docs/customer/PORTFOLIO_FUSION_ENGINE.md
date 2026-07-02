# True911 — Portfolio Fusion Engine

> Extends the RH Portfolio Certification Engine from a single Zoho↔True911 check
> into a **multi-source Portfolio Fusion Engine** that fuses four trusted sources
> into one canonical **Building Digital Twin** per location.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.6 no green without evidence), `../CUSTOMER_DATA_BOUNDARY.md`. Companions:
> `RH_PORTFOLIO_CERTIFICATION.md`, `RH_GO_LIVE_RUNBOOK.md`. Prepared: 2026-07-01.

---

## 1. Sources (all READ-ONLY)

| # | Source | Contributes | Adapter |
|---|---|---|---|
| 1 | **Zoho CRM** | subscription / billing / location context, store #, address | reuses `rh_portfolio_certification` (CSV or live) |
| 2 | **Napco StarLink** | alarm-radio inventory (RadioNumber / ICCID / SubscriberName) | reuses `inventory_reconciliation.adapters.napco` |
| 3 | **T-Mobile Genesis** | MS130v4 cellular modems (MSISDN / ICCID / IMEI) | `load_genesis_csv` (tolerant columns); optional API stub |
| 4 | **True911** | authoritative sites / devices / service units / lines / E911 | reuses `rh_portfolio_certification.load_true911` |

`api/scripts/rh_portfolio_fusion.py`. Sources are individually optional, but at
least one non-True911 source is required (**True911 is always loaded from the
tenant DB as the fusion spine**).

## 2. Normalization

Each adapter emits normalized **SourceRecords** carrying building identity —
**store number · canonical name · address · site type · building category** — and
the **devices / services** it contributes. Store number, site type, and the known
special-location registry are reused from the certification engine, so RH aliases
(MDC, RHNYC, Patterson Warehouse, …) canonicalize identically here.

Building category is derived from site type: Retail (store/gallery/outlet),
Hospitality (guest house), Warehouse, Distribution, Corporate, Special, else Commercial.

## 3. Device matching (cross-source entity resolution)

All source records are clustered into **buildings** by shared join keys:

- **store number** (numeric) — joins Zoho ↔ True911
- **normalized address** (street + city + state)
- **device identifiers** — radio number, IMEI, ICCID, MSISDN, StarLink ID, serial

Device identifiers are the strongest join: a radio whose ICCID appears in Zoho,
Napco, and True911 collapses those three records into one building. Within a
building, device rows are then merged by shared identifier into one unified device
each (kind, all identifiers, contributing sources, `in_true911`).

Phone numbers are normalized to their last 10 digits and identifiers to
alphanumerics, so `(614) 209-8841` and `6142098841`, or `89-0126:0882` and
`8901260882`, still match.

## 4. Building Digital Twin

Each fused building produces a Digital Twin:

- **building** — canonical name, store #, address, site type, building category
- **services** — union of inferred + True911 service types
- **devices** — unified cross-source device list (kind, identifiers, sources, `in_true911`)
- **e911** — status + verified flag + True911 site id (real only; never auto-verified)
- **source_confidence** — corroboration weighted by trust
  (True911 40 · Zoho 25 · Napco 20 · Genesis 15), capped at 100
- **missing_assets** — no True911 site · no Zoho record · device present in a vendor
  but not True911 · no service unit · E911 unverified
- **duplicate_assets** — multiple True911 sites fused into one building · two
  buildings sharing an address

## 5. Outputs

- **CSV** — one row per building (id, store #, name, category, sources, confidence,
  service/device counts, devices-missing-in-True911, E911, missing/duplicate counts).
- **JSON** — full report: `{summary, buildings[<twin>]}`.
- **Markdown** — the **Building Fusion Report**: executive dashboard, per-building
  Digital-Twin table, missing-assets and duplicate-assets sections.
- **Executive dashboard summary** — buildings fused, fully-fused (all 4 sources),
  per-source coverage, by-category counts, buildings missing True911 / E911, device
  gaps, duplicates, average source confidence.

## 6. Usage

```bash
cd api && python -m scripts.rh_portfolio_fusion \
    --tenant restoration-hardware \
    --zoho-csv /path/to/Subscription_Mgmnt.csv \
    --napco-csv /path/to/napco_radiolist.csv \
    --genesis-csv /path/to/genesis_ms130.csv \
    --csv /tmp/rh_fusion.csv --json /tmp/rh_fusion.json --report /tmp/rh_fusion.md
# live Zoho instead of a CSV:
cd api && python -m scripts.rh_portfolio_fusion --tenant restoration-hardware \
    --zoho-live --module Accounts --napco-csv /path/napco.csv --report /tmp/rh_fusion.md
```

Exit codes: `0` ok · `3` error (bad input / DB or Zoho not configured). `--genesis-api`
is a read-only stub — T-Mobile TAAP is a per-ICCID inquiry, not a bulk list, so live
Genesis needs a seed ICCID set; use `--genesis-csv` for the bulk MS130 export.

## 7. Guarantees

- **Read-only** — never writes Zoho, Napco, Genesis, or True911 (parse / SELECT only).
- **No false green** — E911 is never marked verified; missing data is never
  fabricated; unknown sources lower confidence rather than inventing values.
- Sensitive vendor data (dealer email, carrier account numbers) is dropped by the
  Napco adapter and never enters the fusion artifacts.

## 8. Files

- Engine: `api/scripts/rh_portfolio_fusion.py`.
- Tests: `api/tests/test_rh_portfolio_fusion.py`.
- Reused: `api/scripts/rh_portfolio_certification.py`,
  `api/app/services/inventory_reconciliation/adapters/napco.py`.
