# Canonical Life-Safety Service & Connection Model (D-023)

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`,
> `DECISIONS.md` D-023. PR #186a (foundation & reconciliation). The customer read
> model is PR #186b and does not exist yet.

## 1. Why

The customer dashboard showed "28 telephone connections" for Restoration Hardware.
That number was the count of **distinct telephone numbers** mapped to buildings —
not a count of life-safety connections. Audits then showed the underlying facts are
richer and messier: FACPs that need two communications paths, elevator lines, lines
whose purpose no source records, legacy lines replaced by a carrier migration
(Jacksonville) and a building whose records were historically merged with other
locations (Memphis). No single honest "connections" total exists until the evidence
is reconciled, so #186a **retires the 28 from the customer view** and builds the
canonical model underneath.

## 2. The model — SERVICE ≠ CONNECTION ≠ ASSET

```
PortfolioBuilding
  └─ LifeSafetyService      the protected function (FACP / ELEVATOR / EMERGENCY_PHONE)
      └─ LifeSafetyConnection   a REQUIRED communications path of that service
          └─ CommunicationsAsset (via ConnectionAssetLink)
                                telephone number / NAPCO radio / SIM / IMEI
                                → observed operational state (later)
```

* **Cardinality** is a domain rule applied only to CONFIRMED (or operator-APPROVED),
  not REJECTED, CURRENT services: **ELEVATOR 1, EMERGENCY_PHONE 1, FACP 2**.
* A connection states what the service **requires**. It does not need its own
  evidence and no telephone number is ever fabricated for an FACP path. Assets
  linked to it decide, later, whether each path is provisioned or impaired
  (`provisioning`: `ASSET_LINKED` / `NO_ASSET_LINKED` / `NOT_EVALUATED` for FACP
  paths in #186a).
* A multi-number device's equipment type is **never** propagated to its individual
  numbers. Desk / fax / POS / data lines are `OTHER_NON_LIFE_SAFETY` and never
  create a service. An unlabeled line is an `UNCLASSIFIED` telephone service —
  reported, never counted, never assumed to be an emergency phone.

## 3. Three independent axes

| Axis | Values | Set by |
|---|---|---|
| `confidence` | CONFIRMED · PROBABLE · UNRESOLVED | evidence (never self-promoting) |
| `approval` | NONE · APPROVED · REJECTED | operator decision only |
| `lifecycle` | CURRENT · DECOMMISSIONED · REPLACED · SUSPENDED · HISTORICAL · UNKNOWN | operator > Zoho > True911 status |

A service contributes to CURRENT counts only when `approval != REJECTED`, it is
CONFIRMED **or** APPROVED, and its lifecycle is CURRENT. PROBABLE and UNRESOLVED
never contribute; probable services are reported separately as "probable
additional connections". Evidence-CONFIRMED services do **not** need an individual
approval (Decision 1).

## 4. Placement priority

| # | Basis | Notes |
|---|---|---|
| 0 | `OPERATOR_DECISION` | carrier migration / classification decisions place their numbers |
| 1 | `ASSET_IDENTIFIER` | exact NAPCO / ICCID / IMEI registry mapping |
| 2 | `TELEPHONE_MAPPING` | exact telephone registry mapping |
| 3 | `FACILITY_NAME` | building-specific source record (FacilityName, site name) |
| 4 | `STORE_NUMBER` | unique store number |
| 5 | `ADDRESS` | exact normalised address |
| 6 | `ACCOUNT_ALIAS` | a specific (non-generic) account alias |
| 7 | `EXISTING_MAPPING` | historical site link — **supporting only, never sole placement** |
| 8 | `GENERIC_ALIAS` | Parent_Account / generic customer name — **never places** |

* A mapping (1–2) that contradicts the source record's own location (3–6) is a
  **conflict → UNRESOLVED**, not a silent choice.
* A historical site link alone gives at most PROBABLE placement.
* **Suspect buildings** (`BUILDING_IDENTITY_SUSPECT`, e.g. Memphis): the registry's
  own aliases, number/identifier mappings and site links for that building are
  demoted to supporting evidence. Only the building's intrinsic identity (canonical
  name, store number, address) or an operator decision can place a record there.
  Records with a legacy tie to it are listed in the `<NAME> RECONCILIATION` report
  with their source-building candidates. Nothing is moved or deleted automatically.

## 5. FACP joins

Per building, FACP evidence is joined across sources with a union-find over NAPCO
radio id, serial, ICCID, IMEI, approved registry linkage (fused device groups) and
shared numbers. NAPCO id + joined FACP record → CONFIRMED (one service per NAPCO
id). A unique one-to-one pairing in a building → CONFIRMED. Several NAPCO ids and
FACP records without a join → PROBABLE (pairing ambiguous). A NAPCO id with no FACP
evidence, or a count mismatch → UNRESOLVED. Service confidence is capped by the
weakest placement of its evidence.

## 6. Operator decisions (Decision 2)

Durable, auditable, reversible rows in `operator_decisions`, supplied in an
**external JSON file that is never committed** (the script refuses a path inside
the repository). A changed decision **supersedes** the earlier one
(`superseded_by_id`, `superseded_at`; the new row carries the old `new_state` as
`previous_state`). Identical re-submission is a no-op. Each row records type, key,
subject, previous state, new state, effective date, reason, `recorded_by`,
`recorded_at`, `source = OPERATOR` and an input fingerprint.

| Type | subject | new_state |
|---|---|---|
| `BUILDING_IDENTITY_SUSPECT` | `building` | `{"suspect": true\|false}` |
| `CARRIER_MIGRATION` | `building`, `legacy_numbers[]`, `replacement_numbers[]` | `legacy_carrier`, `replacement_carrier`, optional `legacy_lifecycle` (DECOMMISSIONED), `replacement_lifecycle` (CURRENT) |
| `ASSET_LIFECYCLE` | `asset_type` (TELEPHONE_NUMBER…), `value` | `lifecycle`, optional `reason` |
| `SERVICE_CLASSIFICATION` | `building`, `number` | `service_type` ∈ ELEVATOR, EMERGENCY_PHONE, FACP_ASSET, OTHER_NON_LIFE_SAFETY, UNCLASSIFIED; optional `label` |
| `SERVICE_APPROVAL` | `building`, `service_key` | `approval` ∈ APPROVED, REJECTED, NONE |

`building` is the exact canonical building name (or `building_id`). Template
(synthetic numbers — real ones belong only in the external file):

```json
{"tenant": "restoration-hardware",
 "decisions": [
  {"type": "BUILDING_IDENTITY_SUSPECT", "subject": {"building": "<Memphis building name>"},
   "new_state": {"suspect": true}, "reason": "historically merged with other RH locations"},
  {"type": "CARRIER_MIGRATION", "effective_date": "2026-06-01",
   "subject": {"building": "<Jacksonville building name>",
               "legacy_numbers": ["2025550101", "2025550102"],
               "replacement_numbers": ["2025550201", "2025550202"]},
   "new_state": {"legacy_carrier": "Red Pocket", "replacement_carrier": "T-Mobile"},
   "reason": "operator-confirmed carrier migration"},
  {"type": "SERVICE_CLASSIFICATION",
   "subject": {"building": "<Jacksonville building name>", "number": "2025550201"},
   "new_state": {"service_type": "ELEVATOR", "label": "Elevator 1"},
   "reason": "operator-confirmed"}
 ]}
```

Jacksonville ground truth recorded this way: six legacy lines DECOMMISSIONED
(reason `CARRIER_MIGRATION`, historically queryable, one `asset_lifecycle_events`
row), seven replacements CURRENT, exactly two classified ELEVATOR (Elevator 1 / 2),
Voice 1–5 left UNCLASSIFIED.

## 7. Sources and degradation (Decision 4)

The loader is SELECT-only on True911 and GET-only on Zoho (`Subscription_Mgmnt`,
live at run time, tenant-scoped by a row filter). Every source records status and
retrieval time; every evidence row records `observed_at`. If a required source
(Zoho) is unavailable the run is **DEGRADED**: CONFIRMED is capped at PROBABLE, a
HIGH `SOURCE_UNAVAILABLE` finding is raised, and `--apply` is refused unless
`--allow-degraded`. Stale data is never presented as current.

## 8. Persistence

Migration `054` adds eight tables: `projection_runs`, `communications_assets`,
`life_safety_services`, `life_safety_connections`, `connection_asset_links`,
`asset_lifecycle_events`, `canonical_evidence`, `operator_decisions`. The writer
(only under `--apply --confirm-tenant`) upserts on natural keys and **never
deletes**: rows a later run no longer produces keep their older
`last_projection_run_id`; their connections become `NOT_REQUIRED`; superseded asset
links become inactive. Findings are stored in the run summary and as `FINDING`
evidence rows (no registry review items are created, so nothing can be approved by
accident). It never writes registry, site, device, line, E911, Zoho, Napco, Genesis
or carrier data.

## 9. Running it

```bash
# dry-run (default) - read-only, prints the full reconciliation
python -m scripts.canonical_service_backfill --tenant restoration-hardware
# preview unrecorded decisions from an external file (not written)
python -m scripts.canonical_service_backfill --tenant restoration-hardware --decisions-file /tmp/rh_decisions.json
# record decisions (dry-run first, then --apply)
python -m scripts.canonical_operator_decisions --tenant restoration-hardware --file /tmp/rh_decisions.json
python -m scripts.canonical_operator_decisions --tenant restoration-hardware --file /tmp/rh_decisions.json --apply --recorded-by <you>
python -m scripts.canonical_operator_decisions --tenant restoration-hardware --history
```

Report sections: SOURCES · PORTFOLIO (internal) · PER BUILDING · SERVICES ·
`<NAME> RECONCILIATION` per suspect building · LIFECYCLE EVENTS + historical assets
· FINDINGS · REVIEW WATCHLIST (Edina #159, Raleigh #178, Leawood 119th Street, San
Rafael 20 Front Street, Beverly Modern / Hollywood, Roseville / Dawsonville / Long
Beach duplicates — evidence and a suggestion only, never an approval).

## 10. Customer surface

#186a shows **no** canonical total. The hero fact "Telephone connections" is
replaced by "Portfolio inventory — Being reconciled"; per-location wording says
"telephone lines", the location tab is "Services & Lines" and the action is
"Manage Telephone Lines". API field names are unchanged. `FEATURE_CANONICAL_SERVICE_MODEL`
+ `CANONICAL_SERVICE_MODEL_TENANT_ALLOWLIST` are reserved (off) for #186b, which
will expose canonical figures only once the projection is approved for customer use.
