# True911 — Portfolio Registry & Persistent Digital Twin

> The Portfolio Fusion Engine no longer **rediscovers** the portfolio on every run.
> It reconciles incoming Zoho / Napco / Genesis / True911 data against a permanent,
> operator-**approved** **Portfolio Registry** — the identity spine that powers every
> customer Digital Twin. Approved mappings are permanent and are consulted BEFORE any
> heuristic.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.6 no green without evidence), `../CUSTOMER_DATA_BOUNDARY.md`. Companions:
> `PORTFOLIO_FUSION_ENGINE.md`, `LOCATION_DIGITAL_TWIN.md`, `RH_GO_LIVE_RUNBOOK.md`.
> Prepared: 2026-07-02.

---

## 1. Why a registry

Reconciliation-only fusion re-clustered the portfolio from scratch every run, so a
building's identity was only as stable as the latest export. The registry makes
identity **persistent**: once an operator approves a building and its mappings, every
future run resolves to the same building instantly — new/ambiguous data surfaces as
**review items** instead of silently reshaping the portfolio.

## 2. Tables (migration `051`, additive)

| Table | Purpose | Key fields |
|---|---|---|
| `portfolio_buildings` | canonical building (Digital-Twin spine) | canonical_name, store_number, site_type, status, address/city/state/zip, tenant_id, notes, **approved / approved_by / approved_at** |
| `portfolio_aliases` | approved label → building | building_id, alias, source, confidence, active |
| `portfolio_device_mappings` | approved identifier → building | building_id, **kind**, value, source, confidence, active |
| `portfolio_review_items` | the review queue | review_type, status, signature, candidate, suggested_building_id, detail |

`PortfolioDeviceMapping.kind` ∈ `napco_radio · genesis_msisdn · iccid · imei · phone
· true911_device · zoho_account`.

## 3. Reconciliation order (approved mappings before heuristics)

For each fused candidate building the Fusion Engine tries, **in order**:

1. **Exact / device mapping** — a candidate identifier (radio / MSISDN / ICCID / IMEI
   / phone / True911 site / Zoho account) matches an approved `PortfolioDeviceMapping`.
2. **Alias mapping** — the candidate label matches an approved `PortfolioAlias`.
3. **Store-number mapping** — the store number matches an approved building.
4. **Address mapping** — the normalized address matches an approved building.

Resolving to exactly one building → **known**. Otherwise a **review item** is proposed.
The engine **never** writes the registry.

## 4. Review queue

| Review type | Raised when… |
|---|---|
| `new_building` | no approved building maps to the candidate |
| `possible_merge` | the candidate maps to more than one building |
| `duplicate_building` | two approved buildings share a store # (or address) |
| `address_conflict` | matched, but the candidate address differs from the registry |
| `device_conflict` | a device identifier is approved-mapped to a *different* building |
| `unknown_alias` | resolved by store/address/device, but the label is not yet an approved alias |

Nothing enters the registry automatically. Items are persisted (dedup by signature)
only on the explicit `--sync-review-queue` opt-in.

## 5. Approval workflow (the only registry writers)

`app.services.portfolio_registry`:

- `approve_new_building(...)` — create + approve a building (with aliases / device
  mappings), stamp `approved_by` / `approved_at`, and mark the review item approved.
- `approve_alias(...)` / `approve_device_mapping(...)` — extend an existing building.
- `reject_review_item(...)` — mark a suggestion rejected (counts toward *Rejected
  Suggestions*).

These are the **only** functions that mutate the registry, and only on an explicit
operator approval. A plain Fusion run calls `load_registry` + `reconcile` only.

## 6. Reporting additions

The fusion report now includes: **Portfolio Buildings**, **Known Aliases**,
**Pending Review** (+ by type), **Approved Mappings**, **Rejected Suggestions**,
**Coverage by Source**, and a **Confidence Distribution** — plus a
**"Portfolio Registry — review queue (pending)"** section (review type · candidate ·
store # · suggested building · detail), and per-building `registry` status
(known / new / ambiguous) with the resolving method.

## 7. Read-only guarantees

- The Fusion run is **read-only**: it never writes Zoho, Napco, Genesis, carrier
  APIs, True911, **or the Portfolio Registry**.
- The registry changes **only** through the explicit approval workflow.
- E911 is never marked verified; missing data is never fabricated.

## 8. Usage

```bash
# read-only fusion reconciled against the approved registry
cd api && python -m scripts.rh_portfolio_fusion --tenant restoration-hardware \
    --zoho-csv sub.csv --napco-csv napco.csv --genesis-csv genesis.csv \
    --report /tmp/rh_fusion.md
# bootstrap/discovery (ignore the registry):        --no-registry
# persist pending review items to the queue (opt-in): --sync-review-queue
```

## 9. Files

- Models: `api/app/models/portfolio_registry.py` · migration `api/alembic/versions/051_portfolio_registry.py`.
- Service: `api/app/services/portfolio_registry.py` (load / reconcile / approve).
- Engine: `api/scripts/rh_portfolio_fusion.py`.
- Tests: `api/tests/test_portfolio_registry.py`, `api/tests/test_rh_portfolio_fusion.py`.
