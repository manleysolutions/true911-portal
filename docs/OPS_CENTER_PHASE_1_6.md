# Ops Center Phase 1.6 — Resolution Intelligence (Foundations)

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Status: **foundations IMPLEMENTED** (additive, inert, flag-gated). Authored
> 2026-06-24; landed 2026-08-11. Builds on `OPS_CENTER_PHASE_1_5.md`.

## 1. Scope

Phase 1.6 adds a structured, **deterministic** library of operational knowledge
for the people who actually fix life-safety communications — Manley technicians,
NOC, carrier support, installers, customer support:

- **known issues** — symptoms and probable causes, per vendor / carrier / hardware
- **diagnostic workflows** — the ordered troubleshooting sequence
- **resolution workflows** — the actual fix procedure
- **resolution outcomes** — what actually happened

…plus a **rules-based recommendation engine** that maps an inbound issue to the
matching known issues, the right diagnostic and resolution workflow, and an
escalation queue, with an **explainable** confidence score.

Foundations only, on the same terms as Phase 1.5: **no UI, no voice AI, no new
HTTP routes, no customer exposure**, and nothing reads it at runtime yet.
Everything stays under `FEATURE_OPS_CENTER` (default **OFF**).

**No LLM.** The engine is pure rules over a static catalog — `CONSTITUTION.md`
§4.4 deterministic-before-AI. A later phase may add an AI layer *on top of* this,
never in place of it.

## 2. What was added

### Enums / constants — `app/services/ops_center/resolution_intelligence/constants.py`
- **`OutcomeType`** — `resolved | partially_resolved | escalated | vendor_issue |
  carrier_issue | customer_issue | hardware_failure`.
- **`EscalationQueue`** — `NOC | Carrier | Vendor | Tier2Voice | E911 | Installer |
  CustomerSupport`. Internal operational queues; not a customer-facing concept.
- **`OUTCOME_TYPES` / `ESCALATION_QUEUES`** — the plain value lists, for
  validation without importing the enums.
- **Severity is re-exported, not redefined** — `IncidentSeverity` comes from
  Phase 1.5 (`CONSTITUTION.md` P1, single source of truth). A test pins the
  identity so a competing severity ladder cannot appear later.

### The catalog — `.../resolution_intelligence/catalog.py`
Immutable dataclasses (`KnownIssueSpec`, `DiagnosticSpec`, `ResolutionSpec`)
holding **22 known issues** across four domains:

| Domain | Entries |
|---|---|
| `elevator_phone` | 5 |
| `fire_alarm_communicator` | 5 |
| `gate_phone` | 3 |
| `carrier` | 9 |

Covering vendors FlyingVoice and NAPCO, and carriers T-Mobile, Verizon, Telnyx
and Red Pocket. Each entry carries a stable `code`, so seeding is idempotent and
workflows cross-link by code rather than by a generated id.

The catalog is deliberately **both** the seed source for the DB tables **and**
the in-memory catalog the engine reads — so a recommendation needs neither a
database nor a network call. Adding knowledge = edit this file and re-run the
seeder.

### Models — `app/models/ops_center_resolution.py` (migration `052`, additive)
- **`OpsKnownIssue`** (`ops_known_issues`) — symptoms/probable causes JSONB, with
  vendor / carrier / hardware_model indexed for lookup.
- **`OpsDiagnosticWorkflow`** (`ops_diagnostic_workflows`) — `ordered_steps`,
  `expected_results`, `failure_paths` JSONB.
- **`OpsResolutionWorkflow`** (`ops_resolution_workflows`) — `resolution_steps`,
  `estimated_time_minutes`, `escalation_trigger`, `success_criteria`.
- **`OpsResolutionOutcome`** (`ops_resolution_outcomes`) — what actually
  happened, with `outcome_type` and a `confidence_score`.

**Tenant posture is deliberate and tested.** The three knowledge tables are
**global shared operational knowledge — not customer data — so they carry no
`tenant_id`.** `OpsResolutionOutcome` records a real customer engagement and so
carries an *optional* `tenant_id` (+ `session_ref`), honoring tenant isolation
without coupling the library to a tenant.

Cross-links are loose UUID/string references (no FK). Enum-valued columns stay
plain `String` per the no-native-PG-enum convention — also tested.

### Matching — `.../resolution_intelligence/known_issues.py`
`find_matching_issues(...)` scores each catalog entry across five weighted
dimensions and returns explainable matches (score + the list of reason codes):

| Dimension | Weight |
|---|---|
| `issue_category` | 0.40 |
| `carrier` | 0.25 |
| `vendor` | 0.20 |
| `hardware_model` | 0.10 |
| `severity` | 0.05 |

Two rules matter:

- **The score is normalized over the dimensions the caller actually supplied**,
  so a full match on three provided dimensions scores 1.0 rather than 0.70.
  Confidence means "how well this matched what you told me", not "how much did
  you tell me".
- **A match must include at least one *strong* dimension** (category, carrier,
  vendor, hardware). Severity alone is a coincidence, not a match, and returns
  nothing.

`issue_category` matches either the catalog domain or one of the entry's
`ops_issue_categories` aliases, so an Ops Center category like `no_dial_tone`
reaches across domains — an elevator LM150 fault *and* a carrier IMS
registration failure both present that way.

Matching is **deterministic**: sorted by score descending, and ties preserve
catalog order.

### Recommendation engine — `.../resolution_intelligence/recommendations.py`
`recommend(...)` returns probable causes, diagnostic steps, resolution steps, an
escalation queue (falling back to the diagnostic's queue when the issue declares
none), the confidence, the scored `matched_issues`, and a `note` naming the best
match and the reasons it won — `CONSTITUTION.md` §5, explainable.

With no match it returns empty lists, `confidence: 0.0`, and a note to gather
more detail and route to a human queue. It does not guess.

> **`confidence` is INTERNAL** (tech/NOC) only. It is **not** a customer-facing
> readiness score (§7.1) and no customer surface reads it. The note says so in
> the payload itself.

### Seeder — `.../resolution_intelligence/seed.py`
`seed_resolution_intelligence(db)` loads the catalog into the three knowledge
tables, **idempotent by `code`** (insert-if-absent), so re-running is safe.

**Not wired into any startup or deploy command** — it is a manual/CLI action an
operator runs when the feature is being prepared. It writes only to the new
Phase-1.6 tables, and never writes outcome rows (an outcome is a real engagement
result, not seed data).

## 3. Migration `052` — and the fork it resolved

This work was authored against an uncommitted revision `050` whose
`down_revision` was `049`. `051_portfolio_registry` (PR #162) also chained off
`049`, so the Alembic graph had **two heads**. That fork is the documented reason
lifecycle-transaction persistence was deferred, which in turn gates promoting the
typed T-Mobile callback rules out of shadow mode — so an uncommitted migration
was blocking unrelated work.

Landing this rebases the revision to **`052`, chained off `051`**, and the chain
is linear again.

`api/tests/test_alembic_single_head.py` now guards this structurally: it parses
every version file (no DB, no Alembic import) and asserts a single head, a single
base, no two revisions sharing a parent, no dangling `down_revision`, and that a
walk from base to head visits every revision exactly once. A branched chain is
not a syntax error and nothing caught it before — it surfaced only as an
`alembic upgrade head` failure at deploy time.

## 4. Safety posture

- **Additive + inert:** four new tables; no existing table or column touched;
  nothing reads the module at runtime; no behavior change with the flag off.
- **Existence-guarded** migration for idempotency; clean drop on downgrade.
- **No LLM, no external calls, no secrets, no customer/public surface.**
- **No new routes** — nothing to expose.
- The knowledge library is global; only outcomes are tenant-scoped.

## 5. Tests

`api/tests/test_ops_center_resolution_intelligence.py` (**107 tests**):

- **Catalog integrity** (parametrized per entry) — unique issue and workflow
  codes across all three namespaces; valid severity and escalation queues;
  non-empty symptoms, probable causes, expected results and success criteria;
  every issue has both a diagnostic and a resolution; workflow steps numbered
  `1..N` contiguously; every `failure_paths.escalate_to` is a real queue.
- **Matching** — domain and alias matching, the strong-dimension rule
  (severity alone never matches), score normalization, qualified-hardware-name
  tolerance (`"NAPCO StarLink"` → `"StarLink"`), determinism, tie order, `limit`,
  and catalog injection.
- **Recommendation** — full payload shape, content drawn from the best match,
  confidence equal to the best score, the honest no-match path, explainability,
  the internal-only marker, queue fallback, and non-mutation of the catalog.
- **Model posture** — knowledge tables carry no `tenant_id`, outcomes do, and no
  column uses a native PG enum.
- **Seeder** — seeds a full empty DB, is a no-op when everything is present,
  inserts only what is missing, maps spec fields onto rows, defers commit on
  request, and writes no outcome rows.

`api/tests/test_alembic_single_head.py` (**7 tests**) — the revision-graph guard
described in §3.

Full backend suite green (**4414 passed**).

## 6. Next (later phases, not in this PR)

- Wire `recommend` into the Phase-1.5 `escalate`/triage path, still flag-gated
  and internal-only.
- Persist `OpsResolutionOutcome` when a real engagement closes, and feed observed
  outcomes back as Phase-1.5 `OpsResolutionPattern` candidates.
- Grow the catalog beyond the four domains (Inseego, Cisco ATA, MS130) as the
  hardware-agnostic health layer adds vendors.
- Only after the outcome corpus is real: consider weighting matches by observed
  resolution success rather than the fixed dimension weights.
