# True911+ — RH Portfolio Certification

> The **RH Portfolio Certification Wizard** is the read-only go-live gate for
> Restoration Hardware. It guarantees that every RH-related **location,
> subscription, line, and device** in the latest Zoho subscription export is
> represented correctly in True911 **before Judy receives her invite**.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.6 no green without evidence), `../CUSTOMER_DATA_BOUNDARY.md`. Companions:
> `RH_GO_LIVE_RUNBOOK.md` (§4b), `LOCATION_DIGITAL_TWIN.md`. Prepared: 2026-07-01.

---

## 1. What it does

`api/scripts/rh_portfolio_certification.py` (read-only). It reads from **either**
an offline CSV export **or** live Zoho CRM — the downstream pipeline is identical:

1. **Ingests** the Zoho data from one of two sources (exactly one required):
   - `--zoho-csv <path>` — an offline Zoho subscription CSV export, **or**
   - `--zoho-live` — a live fetch from Zoho CRM that **reuses the existing
     authenticated client** (`app.services.zoho_crm.fetch_records`): same OAuth
     token refresh, same pagination, no duplicated auth. `--module` (default
     `Accounts`) and `--fields` select what is read.
2. **Detects** all RH-related rows (aliases: "Restoration Hardware", "RH", store
   codes, and weird labels — guest houses, warehouses, outlets, galleries,
   distribution centers, corporate/special locations).
3. **Normalizes** each row into a canonical portfolio record: canonical name, raw
   Zoho name(s), store number, site type, address, city/state/zip, phone/callback,
   carrier/connection, device identifiers, a **confidence score**, and a
   **manual_review_required** flag.
4. **Groups** the per-device subscription rows into canonical RH locations.
5. **Reads** True911 production for the tenant (sites, devices, service units,
   lines, E911 status, phone numbers, addresses).
6. **Matches** Zoho → True911 by store number, street address, city/state/zip,
   phone number, device identifiers (IMEI / SIM-ICCID / Starlink / serial), and
   normalized name similarity.
7. **Classifies** every result into buckets **A–L** (below).
8. **Emits** an executive report + CSV + JSON, and prints a go-live verdict.

## 2. Inputs & outputs

| Flag | Default | Meaning |
|---|---|---|
| `--tenant` | `restoration-hardware` | True911 tenant to certify |
| `--zoho-csv` | *(optional)* | path to the Zoho subscription CSV export (offline mode) |
| `--zoho-live` | *(off)* | fetch RH records live from Zoho CRM instead of a CSV |
| `--module` | `Accounts` | Zoho CRM module to read in live mode |
| `--fields` | *(safe Accounts default)* | comma-separated Zoho field list for live mode |
| `--csv` | `/tmp/rh_portfolio_certification.csv` | findings CSV |
| `--json` | `/tmp/rh_portfolio_certification.json` | full machine-readable report |
| `--report` | `/tmp/rh_portfolio_certification.md` | executive Markdown report |

Exactly **one** source is required: `--zoho-csv <path>` **or** `--zoho-live`
(supplying both, or neither, is a usage error).

Both modes emit the **identical** CSV, JSON, and Markdown report.

**Live mode** reuses `zoho_crm.fetch_records(module, fields=…)` — the existing
authenticated GET layer — which walks every page (`more_records`) and passes the
`fields` param through. `--fields` defaults to a safe Accounts field set and can be
overridden; non-Accounts modules fall back to Zoho's default field set.

**Offline CSV mode is fully backward compatible** — the original
`--zoho-csv <path>` invocation is unchanged.

**Exit codes:** `0` PASS · `1` CONDITIONAL · `2` BLOCKED · `3` error (CSV unreadable / Zoho not configured).

## 3. Canonical record

Each canonical RH location carries:

`canonical_location_name · raw_zoho_name(s) · store_number · site_type · street ·
city · state · zip · phones · device_ids · device_count · connection_types ·
confidence (0–100) · manual_review_required`.

- **store_number** — extracted from the label (`#177`, `# 177`, `-150`, `#001`);
  leading zeros dropped; alpha codes (`#RHNYC`) upper-cased; ambiguous/address-like
  numbers return None (→ manual review).
- **site_type** — store · gallery · outlet · guest_house · warehouse ·
  distribution_center · corporate · special.
- **confidence** — 30 numeric store# · 30 full address · 20 phone · 20 device id.
- **manual_review_required** — true for non-numeric store#, special/warehouse/etc.
  types, non-US locations, or incomplete addresses.

## 4. Classification (A–L)

| | Class | Meaning | Gate |
|---|---|---|---|
| A | Matched | canonical location ↔ one True911 site, ≥2 signals | — |
| B | Possible / needs review | matched on a single weak signal | conditional |
| C | Missing in True911 | canonical RH location with no True911 site | **blocking** |
| D | Missing in Zoho | True911 site with no canonical Zoho location | conditional |
| E | Duplicate Zoho records | two canonicals share one physical address | conditional |
| F | Duplicate True911 sites | multiple sites share a normalized name | **blocking** |
| G | Address mismatch | matched, but addresses differ | conditional |
| H | Phone / callback mismatch | Zoho phone not present on the site | conditional |
| I | Device mismatch | Zoho device id not found on the site | **blocking** |
| J | Missing service unit | matched site has no Life-Safety unit | **blocking** |
| K | E911 unverified | matched site's E911 not verified | **blocking** |
| L | Weird RH label | canonical needs manual confirmation | conditional |

## 5. Verdict

- **PASS** — no blocking *and* no conditional issues: every RH location matched,
  populated (device + service unit), E911-verified, no duplicates or mismatches.
- **CONDITIONAL** — no blocking gates, but soft issues remain; requires explicit
  operator sign-off before the invite.
- **BLOCKED** — a hard gate (C/F/I/J/K) is tripped; resolve before Judy's invite.

## 6. Operator punch list

For every issue the report recommends the concrete action — *create True911 site ·
update canonical name · attach device · create service unit · verify E911 · review
duplicate · mark non-customer/special · manual review* — with "safe to auto-fix"
(always **no** here) and "operator review required" (**yes**). The wizard changes
nothing; a human executes the corrections through the normal controlled flows.

## 7. Guarantees

- **Read-only** — SELECTs + the supplied CSV only; never writes Zoho or True911.
- **No false green** — E911 is never marked verified; missing data is never
  fabricated; unknowns lower confidence honestly.
- **Judy's invite stays blocked** until certification reads PASS (or CONDITIONAL
  with sign-off).

## 8. Files

- Script: `api/scripts/rh_portfolio_certification.py`.
- Tests: `api/tests/test_rh_portfolio_certification.py`.
- Runbook: `docs/customer/RH_GO_LIVE_RUNBOOK.md` §4b.
- Companion (Zoho-API reconciliation): `api/scripts/rh_zoho_reconciliation.py`.
