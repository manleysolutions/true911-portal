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

Per building, FACP evidence is joined across sources with a union-find over radio
id, serial, ICCID, IMEI, approved registry linkage (fused device groups) and
shared numbers. Radio id + joined FACP record → CONFIRMED (one service per radio
id). A unique one-to-one pairing in a building → CONFIRMED. Several radio ids and
FACP records without a join → PROBABLE (pairing ambiguous). A radio id with no FACP
evidence, or a count mismatch → UNRESOLVED. Service confidence is capped by the
weakest placement of its evidence. Joins use exact normalised identifiers only:
there is no fuzzy, prefix or dropped-digit matching (`1187020` ≠ `11187020`).

### 5a. Radio identity (fix after the 2026-10-02 RH dry-run)

- **Only a radio-typed field can yield a radio id.** The sources are:
  - **A Zoho field** whose API name **or display label** names the
    Starlink/radio, and where neither the API name nor the label names a serial,
    IMEI, SIM, phone, plan, type, status, date or name. Zoho custom fields keep
    the API name they were created with, so a field labelled "Starlink ID" can
    have an API name that says nothing about Starlink.
  - **True911** `Device.starlink_id`.
  - **Registry** `napco_radio` mappings.

  A device serial, IMEI or ICCID is never a radio id, whatever field it was
  typed into. Discovered radio fields are requested ahead of the 50-field cap,
  and the SOURCES line reports them as `radio_fields=[<api> (<label>)]`. A live
  pull that finds none raises `ZOHO_RADIO_FIELD_MISSING` (HIGH): without it,
  every Zoho FACP record would split from its radio's service.
- **Shape rule** (`normalize.radio_id`, generic): 4–12 characters after
  normalisation, and not a 10/11-digit NANP telephone number. This rejects:
  - 13+ character device serials (the MS130 `2023…`/`2021…` shapes);
  - 15-digit IMEIs;
  - 19/20-digit ICCIDs.

  A rejected value stays an ordinary identifier, so it can still link records
  of the same device. It never becomes a `NAPCO_RADIO` asset or an FACP service,
  and it produces a `RADIO_ID_REJECTED` finding (INFO).
- **Service key.** It is `FACP:radio:<id>`, whichever source reported the radio,
  so the key is stable when NAPCO evidence arrives later. Before this fix the key
  was `FACP:napco:<id>`; nothing was ever applied, so no persisted key changes.
- **Provenance.** Each FACP service carries `provenance`:
  - `radio_ids`;
  - `sources` (ZOHO / TRUE911 / REGISTRY / NAPCO);
  - `napco_evidence`: PRESENT / ABSENT / NOT_LOADED / NO_RADIO;
  - `napco_backed`.

  A Zoho record carrying the same normalised radio id as another source's radio
  joins that service as supporting provenance; it is not a second service.
- **NAPCO evidence** means only the tenant's latest NAPCO radiolist snapshot
  that the D-024 importer has **already stored**. It is read from
  `source_snapshots` / `source_snapshot_records` (`source_system = 'NAPCO'`),
  using the importer's own `latest_snapshot` ordering. Any parser version is read,
  because every version stores `napco_radio` the same way. The engine never
  imports anything; the source is reported as `napco_snapshot` (not required).
  - A Zoho, True911 or registry radio id is never "NAPCO-backed".
  - With no stored snapshot, every radio is `NOT_LOADED`, and the run reports
    `NAPCO_EVIDENCE_NOT_LOADED`.
  - The importer stores only rows it attributed to the tenant. "Absent" therefore
    means *not among the tenant-attributed rows*: a radio the importer judged
    ambiguous or excluded is also absent.
  - A radio absent from the snapshot is capped at PROBABLE
    (`RADIO_NOT_IN_NAPCO`). **Its lifecycle is not changed**: absence from NAPCO is
    not decommissioning.
- **A Zoho-only radio id is Zoho evidence.** A radio that no NAPCO snapshot,
  True911 device or registry mapping corroborates is capped at PROBABLE
  (`FACP_RADIO_SINGLE_SOURCE`).
- **FACP evidence is a genuine fire-alarm / FACP service type only.** These are
  *not* FACP evidence:
  - a device or plan SKU in `Subscription_Type` ("SLELTE - Fire (Dual Line)",
    "SLEMAXVI-FIRE (Dual Line 5G)", "MS130v4", "… Service Pack"), which is ignored
    (`normalize.is_sku_label`);
  - "Voice";
  - a carrier;
  - a telephone number;
  - a serial or a NAPCO-like number;
  - Zoho `Emergency_Line` or the "Validated" tag (neither is read).
  - **True911 equipment typing:** a device type or model naming fire-alarm
    hardware, or a service unit inferred from it. It says what the hardware is,
    not what service it provides.
  - **An operator placement (`SOURCE_RECORD` BUILDING) or lifecycle
    (`ASSET_LIFECYCLE`) decision.** These establish placement and lifecycle only:
    PLACEMENT ≠ LIFECYCLE ≠ SERVICE CLASSIFICATION ≠ CERTIFICATION.

  A CONFIRMED FACP needs one of three kinds of genuine service-type evidence:
  - a Zoho fire-alarm / FACP label;
  - an operator `FACP_SERVICE` decision;
  - an operator service-classification override ("Fire Alarm").

  Equipment typing alone caps the service at PROBABLE
  (`FACP_TYPE_EQUIPMENT_ONLY`), so it is never counted.

  A Zoho telephone-line record (a valid MSISDN and no radio) labelled "Alarm
  Panel" is FACP *equipment*: its number is `FACP_ASSET`, and it never creates an
  FACP service.
- **Unchanged:** an FACP still requires exactly 2 connections, and only once the
  service is counted (§5b).

### 5b. Deployment: its own axis

A service has four independent axes:
- **confidence:** identity and classification evidence;
- **approval:** the operator's decision;
- **lifecycle:** CURRENT / SUSPENDED / DECOMMISSIONED / … / UNKNOWN;
- **deployment:** `DEPLOYED` or `NOT_ESTABLISHED`.

`source_status` records what an administrative source *says* (e.g.
`ZOHO:CURRENT`) and nothing more.

- **An administrative status never makes anything CURRENT.** These are CRM or
  provisioning bookkeeping, not proof that equipment is installed and serving
  the building:
  - Zoho Subscription_Mgmnt "Activated";
  - a True911 device or line status of "active";
  - a carrier or NAPCO SIM status of "Active".

  Spare, staged, moved, stale or never-installed equipment can carry any of
  these. With only such a status, lifecycle is `UNKNOWN` with reason
  `ADMIN_STATUS_ONLY`.
- **DEPLOYED requires BOTH of the following.** Activity proves the equipment
  is alive, never where it is.
  - **(a) Liveness**, one of:
    1. an operator `ASSET_LIFECYCLE` decision of CURRENT (including a carrier
       migration's replacements);
    2. a True911 device `last_heartbeat` within `DEPLOYMENT_ACTIVITY_DAYS` (30)
       of the run;
    3. recent activity in an already-imported snapshot, from
       `DEPLOYMENT_ACTIVITY_SOURCES` only: NAPCO `LastSignalReceived` or T-Mobile
       `Last CDR date`, within 30 days, where the record's own source lifecycle
       is not not-current. Verizon and Red Pocket exports carry inventory status
       only and never count. Usage minutes are not read.
  - **(b) Deterministic placement** at that building (`DEPLOYMENT_PLACEMENT_BASES`):
    - an operator placement (carrier migration or service classification
      decision); or
    - an exact registry identifier or telephone mapping (`ASSET_IDENTIFIER`,
      `TELEPHONE_MAPPING`), with placement confidence CONFIRMED.

    These do **not** count as placement: Zoho facility, store-number, address
    or account text; a True911 site name; or a historical site link. All of them
    describe where a record *says* the equipment is.
  - **What liveness without (b) gives:** lifecycle `UNKNOWN` (reason
    `ACTIVE_PLACEMENT_UNVERIFIED`), with the liveness kept separately on the
    asset (`liveness_source`, `liveness_at`) and an INFO finding
    `ACTIVE_PLACEMENT_UNVERIFIED`. A heartbeat counts only through an exactly
    mapped identifier of that device.
- **Source labels.** A carrier or NAPCO label naming the same store only
  *supports* placement. A blank, generic or even matching label never
  establishes it. A label naming a different store raises
  `DEPLOYMENT_LOCATION_CONFLICT` (the equipment may have been moved), and that
  activity is never carried to this building.
- **Operator CURRENT without deterministic placement** keeps lifecycle CURRENT
  (operator truth) but is not DEPLOYED (`DEPLOYMENT_PLACEMENT_UNVERIFIED`).
- **Durability:**
  - Source-derived (inferred) liveness ages out: once an export no longer shows
    activity within 30 days of the run, that service returns to UNKNOWN.
  - Governed operator truth never ages out. An operator CURRENT decision with
    deterministic placement stays DEPLOYED until it is superseded or retired, or
    stronger evidence is raised for review.
  - The engine never modifies decisions, so customer certification does not
    decay merely because a source export gets old.
- **Negative statuses are still honoured:** de-activated or suspended stays
  not-current when nothing shows activity. Recent activity against a
  de-activated record raises `LIFECYCLE_CONFLICT` for the operator.
- **Counted** = life-safety type, not REJECTED, CONFIRMED (or APPROVED),
  lifecycle CURRENT **and** deployment `DEPLOYED`. A confirmed service that is
  not deployed is reported (`LIFECYCLE_UNKNOWN` / `DEPLOYMENT_NOT_ESTABLISHED`),
  never counted.

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
| `FACP_SERVICE` | `building`, `service_ref` (stable operator handle) | `radios[]` (radio-shaped ids only; serial / IMEI / ICCID / phone refused), optional `label` |
| `SOURCE_RECORD` | `source` ∈ ZOHO, TRUE911; `record_id` | `disposition` ∈ DUPLICATE, PLACEHOLDER, BUILDING (+ `building`); optional `duplicate_of` |
| `SERVICE_POOL` | `building`, `pool_ref` (stable operator handle) | `numbers[]`, `service_types[]` ⊆ ELEVATOR, EMERGENCY_PHONE, OTHER (alias FAX), optional `label` |

**Operator decisions are their own evidence class.** They are kept as
`OPERATOR` provenance and never rewritten as Zoho or NAPCO evidence. They need
no source corroboration to be recognised in True911, and they never edit a
source system. Correcting Zoho is a separate, separately reviewed operation.

- **`FACP_SERVICE`: service ≠ communications asset.** One decision is one FACP
  service; its `radios` are that service's communicators.
  - The service key is `FACP:radio:<id>[+<id>…]`: one radio gives the inferred
    key, two radios give one service with two `NAPCO_RADIO` assets.
  - Identity and classification are CONFIRMED (operator). No fire label is
    needed, and the service is not capped by NAPCO silence (`RADIO_NOT_IN_NAPCO`
    is still reported).
  - Each radio is operator-placed at the building. Every record carrying that
    radio follows it, so a source naming another building creates no service
    there.
  - Two decisions are two services. A radio named by two decisions is a
    `DECISION_CONFLICT`, and neither decision applies.
  - The radio set lives in `new_state`, so changing it supersedes the decision.
  - The decision does **not** imply CURRENT: deployment still needs §5b
    liveness. An old "last signalled" radio is placed and CONFIRMED, but its
    lifecycle is UNKNOWN until an `ASSET_LIFECYCLE` decision or new activity.
- **`SOURCE_RECORD`.** `DUPLICATE` and `PLACEHOLDER` remove one record from the
  projection. It is listed under "EXCLUDED SOURCE RECORDS" for audit and is
  never deleted. Other sources' evidence of the same number or radio still
  stands, because the disposition is per record. `BUILDING` operator-places the
  record, its identifiers and every other record of the same radio, which beats
  any CRM or registry association.
- **`SERVICE_POOL`.** It records aggregate knowledge, e.g. "these five lines are
  emergency phone / fax, but which is the fax is unknown".
  - The numbers are operator-placed. A per-line class is **never** inferred
    from the pool.
  - A source label inside the pool is capped at PROBABLE, because the operator
    says the set is mixed. A class outside the pool's types is a
    `POOL_CLASSIFICATION_CONFLICT`.
  - An explicit `SERVICE_CLASSIFICATION` for one number holds.
  - Unassigned members are reported (`SERVICE_POOL_UNASSIGNED`), never counted
    one by one.
- **History without invented lineage.** `CARRIER_MIGRATION` records sets of
  legacy and replacement numbers with an effective date, never 1:1 pairs. A move
  is the old radio set to `ASSET_LIFECYCLE HISTORICAL` (it keeps its historical
  placement) and the new one as the building's service. A building has one
  registry address, so a move updates the registry address (registry
  remediation) and never adds a second current location.

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
HIGH `SOURCE_UNAVAILABLE` finding is raised, and `--apply` is **always** refused
(enforced inside `writer.apply_projection`; there is no CLI override). A degraded
dry-run still prints the full reconciliation and exits 2. Stale data is never
presented as current or persisted.

## 8. Persistence

Migration `054` creates eight tables (and fails loudly if any already exists): `projection_runs`, `communications_assets`,
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

### 10a. #186b canonical customer service inventory (implemented, flag OFF)

`app/services/customer/canonical_view.py` is a read-only reader over the
**latest** APPLY projection. If that run is degraded or unfinished, nothing is
served; there is no fallback to an older run.

**Gating.** The view is active only when all of these hold:
- `FEATURE_CANONICAL_SERVICE_MODEL == "true"`;
- the tenant is in `CANONICAL_SERVICE_MODEL_TENANT_ALLOWLIST`;
- the durable `CUSTOMER_REF_SECRET` is configured;
- registry mode is on.

If any of these fails, the view fails closed: the `service_inventory` field is
absent and every customer payload is byte-for-byte unchanged. Rollback is the
flag or the allowlist, with no deploy and no data change.

**This is inventory truth.** It is never regulatory certification, E911
verification, monitoring certification or customer attestation, so the word
"certified" is not used anywhere in the customer API or UI.

**READY.** A service is READY only when all of these hold:
- it is in the latest clean APPLY run;
- its type is FACP, ELEVATOR or EMERGENCY_PHONE;
- it is not REJECTED;
- it is CONFIRMED, or APPROVED by the operator;
- it is CURRENT;
- it has at least one REQUIRED connection. The writer creates connections only
  for counted services, so this is the persisted "counted" signal and no
  migration is needed;
- its building is approved, active, not pending and not
  `BUILDING_IDENTITY_SUSPECT`.

**Other services:**
- HISTORICAL, DECOMMISSIONED and REJECTED services are never shown.
- Every other current record (PROBABLE, UNRESOLVED, UNCLASSIFIED, or CONFIRMED but
  not counted) only makes its building "being finalized". It is never listed or
  counted as inventory.

**Per-building `service_inventory` states:**

| State | Customer message |
|---|---|
| `READY` | Service inventory confirmed by True911 |
| `PARTIALLY_READY` | Some service inventory is confirmed. Additional records are being finalized by True911. |
| `BEING_FINALIZED` | Being finalized by True911 |
| `NO_SERVICES_ON_RECORD` | No life-safety services on record |

Each block also carries `ready_services[]`, where every entry has:
- `service_ref` (opaque `lss_…`);
- `service` (Fire Alarm / Elevator / Emergency Phone);
- `name`;
- `required_paths`: a requirement only; a path is never named, numbered or given
  an IP;
- `telephone_number`: only for a READY Elevator / Emergency Phone service, taken
  from its own active CARRIER_LINE link. It is **always null for an FACP**, and is
  never a Device or SIM MSISDN, ICCID, IMEI or radio identity.

**Portfolio roll-up.** It reports location counts per state,
`ready_services_by_type` and `records_being_finalized`. There is **no** service
grand total, **no** connection total and **no** probable or unresolved count.

**E911** is never an input or an output of this reader.

**Operator preview** (read-only, ignores the flag, includes a leak scan):
`python -m scripts.canonical_customer_preview --tenant restoration-hardware`.

**CG-1 fixes.** These apply always, whatever the flag:
- **L1 refs:** opaque AES-SIV refs (see `CUSTOMER_API_CONTRACTS.md`).
- **L2 names:** internal record-name markers are stripped from every customer
  name.
- **L3 numbers:** `Device.msisdn` and `genesis_msisdn` (SIM MSISDN) are never
  customer numbers. Only `Line.did` and registry `phone` mappings are. The E911
  callback endpoint is unchanged.
- **L4 buildings:** only `status == active` buildings are shown.
