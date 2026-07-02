# True911 — Portfolio Fusion Engine

> Extends the RH Portfolio Certification Engine from a single Zoho↔True911 check
> into a **multi-source Portfolio Fusion Engine** that fuses four trusted sources
> into one canonical **Building Digital Twin** per location.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.6 no green without evidence), `../CUSTOMER_DATA_BOUNDARY.md`. Companions:
> `RH_PORTFOLIO_CERTIFICATION.md`, `PORTFOLIO_REGISTRY.md`, `RH_GO_LIVE_RUNBOOK.md`.
> Prepared: 2026-07-01.
>
> **Update (2026-07-02):** the engine is now backed by a persistent **Portfolio
> Registry** — it reconciles each run against an operator-approved registry instead
> of rediscovering the portfolio, and proposes review items for anything unmapped.
> See `PORTFOLIO_REGISTRY.md` and §7 below.

---

## 1. Sources (all READ-ONLY)

| # | Source | Contributes | Adapter |
|---|---|---|---|
| 1 | **Zoho CRM** | subscription / billing / location context, store #, address | reuses `rh_portfolio_certification` (CSV or live) |
| 2 | **Napco StarLink** | alarm-radio inventory (RadioNumber / ICCID / SubscriberName) | reuses `inventory_reconciliation.adapters.napco` + **RH row filter** (§3b) |
| 3 | **T-Mobile Genesis** | MS130v4 cellular modems (MSISDN / ICCID / IMEI) | `load_genesis_csv` (tolerant columns) + **RH row filter** (§3a); optional API stub |
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

### 3a. Genesis RH filtering (before fusion)

A raw Genesis export is the **whole Infatrac subscriber book**, not just RH — so
the Genesis rows are filtered to RH **before** fusion (otherwise the engine invents
thousands of non-RH buildings). Two stages:

- **Stage A — direct RH label.** The row's label matches `Restoration Hardware`, a
  `KNOWN_RH_LOCATIONS` alias, or a standalone `RH` token corroborated by a store
  number (`RH 150`), a known RH store number, or a known RH **city** drawn from the
  other sources (`RH Hollywood`, `RH San Francisco`). A bare "rh" **substring** in
  an unrelated word (Overhead, Fairhaven, Marsh) never matches — only a standalone
  `RH` token.
- **Stage B — phone / identifier context.** A non-RH label is kept only when its
  MSISDN / ICCID / IMEI is already known to belong to RH from Zoho, Napco, or
  True911.

Everything else is excluded. The RH footprint (store numbers, city tokens, device
identifiers) is built from the already-RH sources, so filtering is contextual to the
actual RH portfolio. The report records `genesis_rows_total`,
`genesis_rows_rh_matched`, and `genesis_rows_excluded`, and a **"Genesis RH rows
included"** section lists each kept row (MSISDN · status · label · match reason ·
inferred canonical).

### 3b. Napco RH filtering (before fusion)

A Napco Radiolist is the **dealer's whole book** (schools, apartments, other
retailers, individuals, municipalities), so Napco rows are filtered to RH the same
two ways: **Stage A** the subscriber label is RH (`Restoration Hardware`, a known
alias, or a corroborated standalone `RH`), **Stage B** the radio number / ICCID is a
known RH device from Zoho or True911. The context is built from the RH spine
(Zoho + True911) first, then extended with the RH-matched Napco devices so Genesis
can also match on Napco-proven identifiers. The report records `napco_rows_total`,
`napco_rows_rh_matched`, `napco_rows_excluded`, and a **"Napco RH rows included"**
section (radio number · subscriber name · ICCID · matched canonical · match reason).

### 3c. Building identity keys (no over-splitting)

Records cluster on the **strongest identity key** — numeric store #, alpha store
code, known alias, or a distinctive location-token set (generic "Restoration
Hardware" alone yields no key, so it never overmatches) — in addition to address and
device identifiers. As a result **multiple radios / modems at one RH location fuse
into a single building** (devices under it), rather than one building per device.
Store numbers are recognized from both `#177` and bare `RH 177` / `RH -506` forms.
Duplicate True911 sites collapse into **one** building carrying a duplicate finding
(not separate canonical buildings), and *"Missing True911"* is measured per
**building**, not per device row.

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
- **Executive dashboard summary** — **source row counts (separate from building
  counts)**, canonical building count, fully-fused (all 4 sources), per-source
  building coverage, **device counts by source**, by-category counts, buildings
  missing True911 / E911, device gaps, duplicates, average source confidence, and
  Napco / Genesis rows total / RH-matched / excluded.
- **Duplicate / ambiguous clusters** — buildings fused from more than one True911
  site or a shared address (de-duplication candidates).
- **Napco RH rows included** / **Genesis RH rows included** — every kept vendor row
  with its identifiers, match reason, and inferred canonical location.

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

## 7. Portfolio Registry (persistent Digital Twin)

The engine reconciles each run against a permanent, operator-**approved** Portfolio
Registry rather than rediscovering the portfolio. For every fused candidate it tries
approved mappings **before** any heuristic — **device mapping → alias → store number
→ address** — and resolves to a known building or proposes a **review item**
(`new_building` · `possible_merge` · `duplicate_building` · `address_conflict` ·
`device_conflict` · `unknown_alias`). The run is read-only and **never writes the
registry**; changes happen only through the explicit approval workflow
(`approve_new_building` / `approve_alias` / `approve_device_mapping` /
`reject_review_item`). The report adds Portfolio Buildings · Known Aliases · Pending
Review · Approved Mappings · Rejected Suggestions · Coverage by Source · Confidence
Distribution, plus a review-queue section. Full spec: `PORTFOLIO_REGISTRY.md`.

`--no-registry` runs in bootstrap/discovery mode (everything is a new-building
suggestion); `--sync-review-queue` persists new pending items to the queue (queue
only, never the approved registry).

**Customer rendering.** Once buildings are approved, the customer dashboard +
Location/Building Workspace render from the registry (canonical buildings, not raw
Site rows) behind `FEATURE_CUSTOMER_PORTFOLIO_REGISTRY` — see
`CUSTOMER_COMMAND_CENTER.md` §8e and `RH_GO_LIVE_RUNBOOK.md` §4e for the go-live gate.

## 8. Guarantees

- **Read-only** — never writes Zoho, Napco, Genesis, True911, carrier APIs, or the
  Portfolio Registry (parse / SELECT only). Registry changes require explicit approval.
- **No false green** — E911 is never marked verified; missing data is never
  fabricated; unknown sources lower confidence rather than inventing values.
- Sensitive vendor data (dealer email, carrier account numbers) is dropped by the
  Napco adapter and never enters the fusion artifacts.

## 9. Files

- Engine: `api/scripts/rh_portfolio_fusion.py`.
- Registry: `api/app/models/portfolio_registry.py`,
  `api/app/services/portfolio_registry.py`, migration `051_portfolio_registry.py`.
- Tests: `api/tests/test_rh_portfolio_fusion.py`, `api/tests/test_portfolio_registry.py`.
- Reused: `api/scripts/rh_portfolio_certification.py`,
  `api/app/services/inventory_reconciliation/adapters/napco.py`.
