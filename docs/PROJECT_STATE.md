# True911+ — PROJECT STATE

> **Read this first** (after `CONSTITUTION.md` and `DECISIONS.md` — the AI Session
> Rule, `CONSTITUTION.md` P4; entry point `README.md`). Written so a future session
> can resume from it alone. Keep it accurate — update at the end of every session
> per the Documentation Freshness rule (P2 / Operating Loop §0a).
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Last updated: 2026-10-01. Branch at time of writing:
> `fix/customer-basemap`.
>
> **PR #181 has MERGED** (`bbde649`) — the carrier-state reconciliation and the
> maturity/authorization split are on `main`, which is what Render is running.
> The note below describing it as open was accurate on 2026-08-28.
>
> **PR #180 has MERGED** (`5cc3cf0`, 2026-08-11) — Ops Center Phase 1.6 and the
> un-branched Alembic chain are on `main`. Sections below that describe it as
> "open" or "pending merge" were accurate when written and are stale; the
> section headers have been corrected, the body prose has not been rewritten.
>
> **Correction to the prior revision:** the read-only certification harness has
> since **MERGED** as **PR #179** (`306f359`, tooling commit `eadf8b0`) — the
> sections below that describe it as "PR open, NOT merged" were accurate on
> 2026-07-21 and are stale. `main` is at `306f359`; the certification *tooling*
> is landed. What remains blocked is *execution*, and only on operator inputs.

## 0·IN REVIEW — Customer basemap fix: CARTO "API KEY REQUIRED" tiles (D-027) [2026-10-01]

Branch `fix/customer-basemap`. **Frontend only.** No change to portfolio, canonical
inventory, E911, registry, snapshots, permissions or coordinates.
- **Cause:** both Leaflet maps hard-coded keyless CARTO `light_all`. CARTO now
  returns a 200 placeholder PNG ("API KEY REQUIRED") for every keyless tile.
- **Fix:** shared tile config `web/src/lib/mapTiles.js`, defaulting to keyless OSM
  standard tiles with the required attribution, overridable via `VITE_MAP_TILE_*`.
  The customer map also gets a quiet "map background unavailable" notice when tiles
  fail to load.
- **Small map defects fixed:** the map refit on every render (hover, 60 s poll),
  which yanked the customer's pan/zoom; it now refits only when the plotted point set
  changes. Markers are de-duplicated by `location_ref`. Invalid points (non-finite,
  out of range, 0,0) are excluded and counted, never plotted.
- **Unchanged:** "N locations not shown on the map (no coordinates on file)" stays
  truthful (16 for RH). Status semantics Monitored / Needs attention / Being
  reconciled are unchanged.
- **Not complete:** RH mapping. Basemap availability and canonical location geocoding
  are separate concerns. Coordinate-source defects M1–M5 are in BACKLOG (→ #190/#192).
- Judy **not** invited. Staged T-Mobile snapshot work untouched.

## 0·IN REVIEW — RH Completion Program PR #187: operational source snapshots [2026-09-30]

**Program:** `docs/customer/RH_COMPLETION_PROGRAM.md` (D-025) — RH becomes the
reference customer; PRs #187–#193; Judy not invited, canonical read model not
enabled for her until READY_FOR_CUSTOMER. Baseline: first untouched #186a
production dry-run (26 confirmed services / 35 required connections; active
operator decisions = 0). 45 locations is not a target.

Branch `feat/source-snapshots` (PR open, **not merged**; no production import run).
Decision **D-024**; spec `docs/customer/SOURCE_SNAPSHOTS.md`.
- Migration **055**: `source_snapshots`, `source_snapshot_records` (immutable,
  SHA-256 de-duplicated, fail-loud on pre-existing tables).
- `app/services/source_snapshots/`: versioned status maps (unmapped -> UNKNOWN),
  CSV/XLSX reader, adapters built to the ACTUAL production export structures -
  NAPCO `napco_radiolist.v1`, Infatrac `tmobile_infatrac.v2`, Verizon
  `verizon_inventory.v2` (index / billing / username columns dropped) - and Red
  Pocket `redpocket.v0-provisional`; effective time OPERATOR > SOURCE > FILENAME
  (only with an established timezone) > UNDATED; tenant
  attribution (exact identifier HIGH / RH label rule MEDIUM / ambiguous never
  stored); allow-listed private attributes; 7-day freshness helper.
- `scripts.source_snapshot_import` (dry-run default; `--apply --imported-by`;
  `--list`, `--show`; export must be outside the repo).
- **Next:** after merge, import the NAPCO / Infatrac / Verizon exports via /tmp ->
  dry-run -> review -> `--apply` -> `--show` -> delete the file. Then #188.

## 0·DONE — Canonical Life-Safety Service & Connection model (PR #186, MERGED `1c69798`) [2026-09-30]

(The section below was written while PR #186 was open; it has since merged.)

## 0·IN REVIEW — Canonical Life-Safety Service & Connection model: foundation & reconciliation (PR #186a) [2026-09-30]

Branch `feat/canonical-foundation` (PR open, **not merged**, nothing applied in
production). Decision **D-023**; spec `docs/customer/CANONICAL_SERVICE_MODEL.md`.

- **Why:** the customer "28 telephone connections" was the count of distinct
  telephone numbers per building, not life-safety connections. Read-only audits
  (A/B/C) found FACPs needing two paths, unlabeled lines, the Jacksonville carrier
  migration (6 legacy -> 7 replacement lines) and Memphis records historically
  merged with other RH locations.
- **What landed on the branch:** migration **054** (eight additive tables; fails
  loudly if any target table pre-exists);
  `api/app/services/canonical/` (vocab, normalize, decisions ledger, PURE engine,
  read-only loader with live Zoho + retrieval metadata, apply-only writer, report);
  `scripts.canonical_service_backfill` (dry-run default; `--apply
  --confirm-tenant`; a degraded projection is never persisted — no override) and `scripts.canonical_operator_decisions`
  (external file only; supersede, never destroy); customer relabel — hero fact
  "Telephone connections" -> "Portfolio inventory: Being reconciled", "telephone
  lines" wording, tab "Services & Lines", action "Manage Telephone Lines"; audit
  label "Telephone numbers". Flags `FEATURE_CANONICAL_SERVICE_MODEL` +
  `CANONICAL_SERVICE_MODEL_TENANT_ALLOWLIST` reserved OFF for #186b.
- **Not done (by design):** no canonical totals exposed to Judy; no production
  `--apply`; no operator decisions recorded; no registry approvals; E911 untouched;
  Judy not invited. #186b (customer read model) not started.
- **Next (after merge):** run the production DRY-RUN (read-only), review the
  MEMPHIS RECONCILIATION + findings + watchlist, prepare the external decision file
  (Memphis suspect, Jacksonville migration + Elevator 1/2), dry-run it, then decide
  on `--apply` separately.
- **Audit C production facts (for reference, internal):** 45 buildings; FACP
  confirmed 32 / probable 4 / unresolved 13; confirmed elevators 17; emergency
  phones 0; unclassified telephone 22; confirmed services 49; confirmed connection
  floor 81; probable additional 8. No single precise total is stated.

## 0·DONE — Calm customer experience: trust rule UNKNOWN ≠ FAILED ≠ PROTECTED (PR #185, MERGED `a628066`) [2026-09-30]

Branch `feat/rh-customer-calm-ux` (PR open, **not merged**). PR #184 is **MERGED**
(`4eb822f`) and the RH Test production smoke test passed. Reviewed from the RH
customer admin's seat, the portal read as "mostly broken" (29/45 "protected", 0%
E911, ~45/100 health) although the data only shows missing linkage / verification
evidence. Presentation-only pass (decision **D-022**):

- **Trust rule:** KNOWN GOOD ("Monitored") · KNOWN PROBLEM ("Needs attention") ·
  UNKNOWN ("Being reconciled" when no monitoring link, "Status being confirmed"
  otherwise) — neutral, never red or green; a known problem always wins.
  `serialize.operational_state`; API adds `operational_state`,
  `monitoring_linked`, `operational_states`, `e911_verified_locations`,
  action-center `tiers` + `being_reconciled`, workspace
  `monitored_service_count`.
- **Dashboard:** portfolio hero (locations · physical devices · connections) +
  four separate dimensions; **no blended health score** for customers; "For you"
  vs "True911 is working on"; Action Center tiered Urgent / Action needed / In
  progress / Portfolio setup (contacts collapsed, never at problem severity).
- **Location page:** four places (Overview · Connections · Compliance · Records),
  ≤2 primary actions + More; E911, contacts, requests, activity each in one place
  (previously up to 4×); composite building-health score removed from the
  customer view; roadmap items compacted to one disabled row.
- Tests: `test_customer_trust_rule.py` (17) + web helper tests (25 total). Full
  backend suite **4768**; build + eslint clean. No screenshots (no local stack).

## 0·DONE — RH go-live UX / action-semantics pass (PR #184, MERGED `4eb822f`) [2026-09-30]

Branch `fix/rh-go-live-ux-semantics` (PR open, **not merged**). PR #183 is
**MERGED** (`bf068ff`) and deployed; production RH Test showed 45 buildings,
29/45 protected, 73 physical devices, 28 connections, 0% E911 verified, audit
`READY_WITH_CUSTOMER_ACTIONS`. This pass fixes what the first customer session
would have got wrong, with no redesign and no scoring change:

- **"45 E911 confirmations" (defect).** The Action Center put
  `customer_confirmation_required` (35) and `not_verified` (10, no dispatch
  address) in one list headlined as confirmations, and the UI offered Verify E911
  on records with no address. Now two buckets — *E911 confirmations needed*
  (actionable, opens Verify E911) and *E911 records being prepared*
  (informational); `not_verified` is labelled "E911 record being prepared" and is
  not a customer action. The dashboard, location page, wizard and audit now read
  ONE `dispatch_address` per building (they previously disagreed when only the
  linked site carried the address).
- **100/100 vs Bronze 0/7 (labels).** "Digital Twin Completeness · 25%" was a
  health factor with its WEIGHT next to its value. Renamed **Data Completeness**
  (weight shown as "weight 25%"); the tier card is **Operational Readiness · 0 of 7
  readiness items in place**. Customer-supplied contacts now count toward the
  *Site contacts* readiness item (previously ignored).
- **Chicago 1 service / 2 connections (labels).** Correct: one Elevator service
  plus a registry number not linked to a service. That line was named "Life
  Safety Line" (read as a second service); now "Additional line", service "Not yet
  linked to a life-safety service", with a "2 connections across 1 service"
  summary.
- **Controls.** Upload Photo / Upload Document stored only a filename — now
  disabled *Soon*. "Upload Procedure" → "Add Procedure" (text, works). With
  self-service on, the older Add Contact / Create Request contribution controls
  are replaced by the governed flows (one path each). Billing stays *Soon*.
- Tests: `test_customer_go_live_semantics.py` (9, real DB) + web helper tests
  (17 total). Full backend suite **4751** passed; web build + eslint clean.

## 0·DONE — RH Customer Operations Console (self-service) + Devices KPI fix (PR #183, MERGED `bf068ff`) [2026-09-30]

Branch `feat/rh-customer-self-service` (PR open, **not merged**). Moves the RH
customer plane from "dashboard + email support" to "customer operations console +
governed escalation". Spec: `customer/CUSTOMER_SELF_SERVICE.md`; decision
**D-021**; runbook `customer/RH_GO_LIVE_RUNBOOK.md` §4f.

- **Ownership boundary** — customer-managed (contacts, notes, display name,
  connection name/purpose, notification prefs) writes a customer **overlay**
  directly with old/new audit; request-based (name/address/store #, numbers,
  service type, add/remove/move, replace equipment, problems, E911) creates a
  `CustomerServiceRequest`; system-managed (ICCID/IMEI/SIM/carrier/SIP/network/
  device identity/verified E911/registry mappings) is refused 403, whole-payload.
- **E911 self-service** — attestation with provenance → `e911_verification`
  request + the existing E911 review queue; states `not_verified ·
  customer_confirmation_required · customer_submitted · requires_review ·
  verification_pending · failed · verified`; `verified` only from the official
  record. Attestation is `CUSTOMER_ADMIN`-only.
- **Action Center** on the dashboard + **Manage this location** panel (Manage
  Location · Manage Connections · Verify E911 · Add Service · Request Service
  Change · Report a Problem · Update Contacts); support is a secondary line.
- **Migration `053`** (off the single head `052`): `customer_service_requests`,
  `customer_managed_fields`, `customer_activity_events`. Internal queue
  `/api/customer-requests` (`MANAGE_CUSTOMER_REQUESTS`).
- **Flags (default OFF):** `FEATURE_CUSTOMER_SELF_SERVICE`,
  `CUSTOMER_SELF_SERVICE_TENANT_ALLOWLIST`, `CUSTOMER_SELF_SERVICE_USER_ALLOWLIST`
  (RH Test first).
- **Devices = 0 root cause (fixed):** the UI read `summary.devices`; registry mode
  returned only `total_devices` and omitted `critical_sites` /
  `sites_requiring_attention` — which **also rendered the "All listed locations
  are currently protected" banner at 29/45 (false green)**. Registry mode also
  counted only linked-site equipment. Now: physical devices from registry mappings
  + approved fused payloads + True911 devices, merged by identifier; banner green
  only when protected == total. Placeholder store numbers (Hollywood `#0`) are
  hidden from the customer display.
- **Go-live audit** `python -m scripts.rh_customer_go_live_audit --tenant
  restoration-hardware` — SYSTEM BLOCKERS vs WARNINGS vs CUSTOMER ACTIONS;
  verdict `READY · READY_WITH_CUSTOMER_ACTIONS · BLOCKED`. **Not yet run against
  production** (needs the Render shell).
- **Tests:** real-DB suite `test_customer_self_service.py` (first SQLite harness,
  `tests/_customer_db.py`; `aiosqlite` added to requirements), device counting,
  audit verdicts, RBAC matrix; web `npm test` (Node built-in runner, now in CI) +
  build green.

**Next:** merge → deploy → enable for RH Test → run the audit on Render → resolve
any SYSTEM BLOCKERS → open to the tenant → send Judy's invite (not before).
Known likely audit findings to confirm on Render: ~16 approved buildings with no
linked True911 monitoring record (the 29/45 protected gap — shown honestly as
Unknown), pending registry review items, and store-number checks.

## 0·IN REVIEW — T-Mobile Network Profile PIT certified after a carrier-directed re-test [2026-09-30]

Branch `feat/tmobile-network-profile-certified` (PR open, **not merged**).
Decision **D-026**; record `TMOBILE_PIT_CERTIFICATION_20260930.md`.

- T-Mobile Engineering received the 09-01 failure's trace identifiers and asked
  in writing for a re-test. **Exactly one** Network Profile request (one-shot
  grant consumed and cleared) returned OAuth HTTP 200, resource **HTTP 200 /
  `SUCCESS` / `100`**, `iccidStatus INUSE`, `subscriberStatus ACTIVE`,
  `simNetworkType M2M`, for the approved subscriber `…2715`; parsed cleanly. No
  retry, polling, mutation, Usage or Transaction Status request.
- `query_network`: `MOCK_CERTIFIED` → **`PIT_TESTED`**; authorization unchanged,
  **`SINGLE_RUN_ONLY`**. `query_usage` untouched (never sent live);
  `query_transaction_status` still blocked; destructive operations unchanged;
  reserve SIMs untouched.
- The 09-01 Network Profile carrier question (§4) is resolved by observation —
  GENS-0005 not reproduced; no claim about carrier-side changes.
- **Reconciliation audit:** Network Profile reconciling the ledger was intended
  (class-C evidence model) but eligibility had been inferred from the
  `subscriberStatus` field's presence. Now an explicit per-operation declaration
  (`Operation.lifecycle_evidence` = inquiry + network only, read-only enforced at
  import); live and replay paths refuse undeclared operations. Today's result is
  unchanged.
- Private evidence (`tmobile-pit-evidence-20260930T183727Z.*`) is in the
  operator's private Render-side store — not in git.

## 0·HISTORY — ⚠️ ATTEMPTED, NOT CERTIFIED — Network Profile live PIT run returned HTTP 500 / GENS-0005 [2026-09-01]

*(Superseded 2026-09-30 by the carrier-directed re-test above; kept as written.)*

One controlled live request to `POST /wholesale/v1/subscriber/network-profile`
for the carrier-provided PIT subscriber (`…2715`, independently confirmed
`Active` on 2026-08-28). **OAuth succeeded (HTTP 200); the resource request
returned HTTP 500, carrier code `GENS-0005`, "Unexpected Exception: Please
notify your system administrator".** Full record:
`TMOBILE_PIT_CERTIFICATION_20260901.md`.

**`query_network` remains `MOCK_CERTIFIED`.** A failed live carrier attempt is
not PIT certification: `PIT_TESTED` means *successfully* exercised with
acceptable evidence retained, and neither half is true here. Send authorization
also did not move — it is still `SINGLE_RUN_ONLY`. No new state was invented to
say "attempted and failed"; the existing `test_status` / `pit_restrictions`
fields carry it, which keeps `query_usage`'s "Never sent live." legibly
different.

**Classify it as a carrier/resource endpoint failure after successful
authentication** — and no further. It is *not* an auth failure (OAuth returned
200 and the request reached the Network Profile gateway, which answered with a
structured carrier error), and it is *not* established that the fault is inside
T-Mobile. `GENS-0005` is a generic unexpected-exception code; a PIT backend
issue, partner/account provisioning, subscriber test data, an endpoint
entitlement, or an undocumented request requirement on our side are all still
possible. The run proves *reach* — credentials, PoP, partner headers and the
exact vendor path get a structured answer from the right gateway — which is not
evidence about operation behaviour.

**What did not happen:** no retry · no polling · no Usage request · no
Transaction Status request · no subscriber mutation · no reserve-SIM activity ·
no ledger reconciliation from the failed read · no Render env-var change. The
one-shot grant was consumed and cleared, an evidence bundle was written on
failure, and the harness printed its STOP guidance, which was followed.

**Certification sequence is PAUSED at step 2.** `query_usage` has **not** been
sent live and must not be until this is understood — advancing would turn one
uninterpreted result into two. `query_transaction_status` stays blocked: today's
failure surfaced four carrier trace identifiers and **none** of them has been
confirmed as the `transactionId` that operation expects, so the blocker stands.

**Carrier questions are now four**, not three — `TMOBILE_CARRIER_QUESTIONS_OPEN.md`
§4 asks whether the Network Profile endpoint is enabled for our partner in PIT,
whether further provisioning is required, whether the supplied test subscriber
is valid for it, and whether anything is missing from our request. Still
**drafted, NOT sent**.

**Operator ergonomics.** Two live attempts before the successful invocation were
refused at the explicit-subscriber gate with no nominated selector — a
shell-local `$PIT_ICCID` that did not survive between copied command blocks. No
carrier request was sent by either. The runbook now recommends deriving the
ICCID inline from `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST` at invocation time
(`TMOBILE_PIT_OPERATOR_RUNBOOK.md` §2c): still explicit, still allowlist-checked,
still masked in the preflight the operator reads. Explicit nomination was **not**
weakened and no "latest subscriber" exists.

**Evidence is not yet durable — open action.** The bundle was written to
`/tmp/pit-evidence/` on the Render instance and copied to `~/tmobile-pit-evidence/`
in the same session. **Neither survives a redeploy** without a persistent disk.
It must be downloaded to the operator's private evidence store before the next
deploy; that has **not** been done. Nothing raw is committed — the repository
carries only this sanitized record.

**Failure-path invariants are now pinned** by
`api/tests/test_tmobile_pit_network_failure.py` (43 tests): a carrier 500 writes
evidence, records failure, consumes the grant, does not retry, does not poll,
does not advance maturity, does not reconcile the ledger, does not run the next
operation, and cannot leak authorization to `query_usage`; the transaction-status
blocker outranks a one-shot grant; and an explicit ICCID survives parser →
preview → execute dispatch.

## 0·DONE — Ops Center Phase 1.6 landed; Alembic chain un-branched (PR #180, MERGED `5cc3cf0`) [2026-08-11]

Lands the Phase 1.6 **Resolution Intelligence** foundations that had been sitting
**uncommitted in the working tree since 2026-06-24**, and resolves the branched
migration graph in the same change.

**The migration fork is the reason this mattered.** The work was authored as
revision `050` chained off `049`; `051_portfolio_registry` (PR #162) also chains
off `049`, leaving **two heads**. That fork was the stated reason
lifecycle-transaction persistence was deferred, which gates promoting the typed
T-Mobile callback rules out of shadow mode — so an *uncommitted* migration was
blocking unrelated work. Rebased to **`052` off `051`**; the chain is linear.

**What the module is:** a deterministic library of operational knowledge for
technicians / NOC / carrier support / installers — **22 known issues** across
`elevator_phone` (5) · `fire_alarm_communicator` (5) · `gate_phone` (3) ·
`carrier` (9), each with an ordered diagnostic and resolution workflow, plus a
**rules-based, explainable** recommendation engine. **No LLM** (§4.4
deterministic-before-AI); a later phase may add AI *on top of* this, never in
place of it.

**Posture:** additive and inert — four new tables, nothing reads it at runtime,
no new routes, behind `FEATURE_OPS_CENTER` (default off). The three knowledge
tables are **global shared knowledge and carry no `tenant_id`**; only
`OpsResolutionOutcome`, which records a real engagement, is tenant-scoped. The
`confidence` score is an **internal** tech/NOC signal, never customer-facing
(§7.1). The seeder is idempotent by `code` and is **not** wired into any startup
or deploy command.

**New structural guard:** `api/tests/test_alembic_single_head.py` parses every
version file (no DB, no Alembic import) and asserts one head, one base, no two
revisions sharing a parent, no dangling `down_revision`, and a base→head walk
covering every revision. A branched chain is not a syntax error and nothing
caught it before — it surfaced only as an `alembic upgrade head` failure at
deploy time. Mutation-tested: re-forking `052` onto `049` fails 4 of its 7 tests.

Tests: `test_ops_center_resolution_intelligence.py` (**107**) + the graph guard
(**7**). Full backend suite green (**4414**). Doc: `OPS_CENTER_PHASE_1_6.md`.

**Downstream effect:** a new table is now structurally safe to add. Durable
lifecycle-transaction persistence — chained off `052` — is the highest-value
unblocked engine task, and the first step toward taking the typed callback rules
authoritative.

## 0·✅ DONE — First carrier-backed activation + independent readback [2026-08-28]

Two live PIT requests, one each, no retry. Full record:
`TMOBILE_PIT_CERTIFICATION_20260828.md`.

**Live proven:** OAuth · PoP · partner headers ·
`POST /wholesale/v1/subscriber/activation` (HTTP 201, `SUCCESS`, result `100`) ·
MSISDN assignment · `accountId` assignment ·
`POST /wholesale/v1/subscriber/profile` · carrier `subscriberStatus: Active`
readback. Reserve PIT ICCIDs were **not** touched and are on no allowlist.

**The defect this exposed.** After the 201, the operator ledger still read
`activation_requested` while an independent carrier read said `Active`. Neither
call was wrong — there was **no code path by which any observation could settle
the ledger**. `cmd_run` wrote `observed = expected` and never classified the
response body; `tmobile_lifecycle.settle()` had no caller outside a test; the
read-only path wrote an evidence bundle and never touched the ledger. A second,
quieter defect sat beside it: `bundle["ok"]` came from "no exception raised",
and `_request` raises only on HTTP ≥ 400 — so a 2xx carrying `status: FAILURE`
would have been recorded as a successful activation.

**What changed.** State and evidence are now recorded separately (classes A–G),
and `state --iccid` prints both. A synchronous acceptance stays class **B** and
settles nothing — that principle was right. What was missing is that an
**independent carrier read now settles the line, with no callback required**: a
read is not a transition, so it is gated by neither the transition table nor the
pending-duplicate rule (gating a query on already knowing the state is
circular). Unrecognised status words raise rather than being guessed;
contradictions set `reconciliation_required` and leave the state alone; an
apparent success we cannot parse fails closed.

**Recorded, not normalized:** activation was sent with `marketZip` **30338** as
instructed and the profile returned **99722**. Untouched in code, and question 2
in `TMOBILE_CARRIER_QUESTIONS_OPEN.md`.

**Separate open issue:** no callback was observed or persisted for the
activation. That is not proof none was sent — persistence needs both the ingest
flag and the authenticity gate, and the logging architecture cannot prove a
negative. It does not block the state determination, because the synchronous
result was complete and an independent read confirms it.

**Rebuilding the ledger costs no carrier call.** `tmobile_pit.py reconcile
--iccid <ICCID> --evidence <bundle>.json` replays an already-captured read
offline — same reconciler, no socket, `carrier_verified_source` recording that
it was replayed rather than watched. It refuses an activation bundle (class B),
a failed run, another subscriber's evidence, a truncated body, or a bundle with
no exchange on the operation's exact wire path. This exists so that a stale local
file is never a reason to resend anything.

**Certification maturity is now separate from send authorization**, and
`subscriber_inquiry` is `PIT_TESTED` **and still not generally sendable**.

Readiness used to double as authorization (`LIVE_SENDABLE_READINESS =
{PIT_TESTED, PRODUCTION_APPROVED}`), so honestly recording a successful
*controlled, one-shot* PIT run would have converted the operation into one that
could be sent freely — one certified call buying unlimited uncertified ones, as
a side effect of bookkeeping rather than a decision.

Two axes now. `ReadinessState` is maturity only, on the unchanged canonical
ladder `IMPLEMENTED → MOCK_CERTIFIED → PIT_TESTED → PRODUCTION_APPROVED`.
`SendAuthorization` is an explicit per-operation declaration — `NONE`,
`SINGLE_RUN_ONLY`, `OPERATOR_HARNESS_ONLY`, `PRODUCTION`. **Maturity can veto a
send and can never grant one**; `PRODUCTION` additionally needs
`PRODUCTION_APPROVED`, which is necessary for ordinary sendability and
sufficient for nothing. A certification blocker outranks maturity and route
alike. `_validate_authorization_policy()` enforces this at import, so a bad edit
fails the process rather than a reviewer's attention.

`activate_subscriber` keeps exactly the policy it had, now declared
`OPERATOR_HARNESS_ONLY` instead of inferred — preserved, not broadened, and not
reachable through the read-only grant path.

**QueryNetwork / QuerySubscriberUsage previewed 2026-08-28**, every gate
inspected, request body carrying the ICCID alone (usage takes no date range),
preview audited to open no outbound socket and perform no DNS lookup. **Neither
was sent.** A live run needs an environment with PIT credentials, the ICCID on
the read-only allowlist, and the live switch on; a workstation without them is
refused at the allowlist gate, which is the intended behaviour.

**Operator-experience defect fixed:** the harness printed
`python -m scripts.tmobile_callback_inspect …`, which cannot work from `api/` —
a second, unrelated `api/scripts` package wins the import there. Every emitted
instruction and every doc now uses the path form, pinned by a test that actually
runs it.

## 0·BLOCKED — Read-only certification sprint: tooling complete, 1 of 4 executed [2026-08-28]

All four read-only operations (SubscriberInquiry, QueryNetwork,
QuerySubscriberUsage, QueryTransactionStatus) are implemented, typed,
mock-certified, and each has its own single-run PIT authorization with preview
by default. **SubscriberInquiry has been executed** (2026-08-28); the other
three have not.

| # | Operation | Status |
|---|---|---|
| 1 | SubscriberInquiry | ✅ executed 2026-08-28 |
| 2 | QueryNetwork | ⏳ certification-ready, unexecuted — **no code change needed** |
| 3 | QuerySubscriberUsage | ⏳ certification-ready, unexecuted — **no code change needed** |
| 4 | QueryTransactionStatus | ⛔ **not authorizable** pending a carrier answer |

Steps 2 and 3 meet every prerequisite step 1 met: vendor-documented exact path,
reconciled schema, mock-certified, read-only, no callback, proven OAuth/PoP, and
a target ICCID that is carrier-confirmed `Active` and read-only allowlisted. The
existing single-run grant already covers them, so certifying them is an operator
decision rather than a code change. Neither was promoted to generally sendable.

Step 4 is now refused **at the point a grant is cut**, via a new
`Operation.certification_blockers` field. `transactionId` could be any of the
four identifiers our activation returned, and a wrong id returns "not found"
exactly as a correct id does for an expired transaction — so the run would prove
nothing either way. Clearing it needs T-Mobile's written answer plus a reviewed
code change, never a config toggle.

The prior blocker list is resolved except for the transaction id, which is no
longer the operative blocker: a nominated PIT subscriber is present and
carrier-confirmed `Active`, and PIT credentials are configured.

**Deliberately not built:** carrier-observation persistence, the internal
super-admin view, and the manual sync control. All three would be designed
against a response shape nobody has observed — the guessing this integration has
spent four PRs eliminating.

> **Update [2026-08-11]:** the second reason given here — "the Alembic graph
> also still has two unresolved heads sharing `049`, so a new table would
> compound the branch" — **no longer holds.** The fork is resolved in PR #180
> (see §0 above). A new table is now structurally safe to add; the
> unobserved-response-shape reason stands on its own and still blocks.

**Authorization isolation:** each operation needs its own grant. An inquiry
grant does not authorize a network query; a transaction-status grant binds to
one exact transaction id. All grants are single-use and PIT-only, and none can
cover a lifecycle mutation.

Unchanged: activation is the sole generally sendable operation (operator
harness only), all four mutations are blocked, and the callback shadow remains
non-authoritative and off.

Plan and exact commands: `TMOBILE_READONLY_GO_LIVE_PLAN.md`. Open carrier
questions, drafted and **not sent**: `TMOBILE_CARRIER_QUESTIONS_OPEN.md`.

## 0·DONE — Typed callback rules wired in shadow mode [2026-07-21]

The typed callback rules now run **alongside** the deployed ingest path behind
`FEATURE_TMOBILE_CALLBACK_TYPED_SHADOW` (default **off**). When enabled they
record what they would have decided and whether that agrees with what actually
happened. They change nothing.

**Why shadow and not authoritative.** Nothing creates lifecycle transactions —
there is no persistence for them and every mutation is blocked — so the
correlation set is always empty and every callback resolves to
`quarantined_no_correlation`. Making that authoritative would stop device
liveness promotion, which feeds the health surfaces. Today's callbacks are also
network liveness, not results of mutations we initiated, which is what the
correlation rules are built for.

**Safety.** Flag off costs nothing, not even an extra read. Evaluation gets a
throwaway state object and no session, so it is structurally incapable of side
effects. Two layers of exception absorption keep a broken shadow from ever
failing ingest. Identifiers are masked in the observation and in logs.

**To promote to authority**, in order: ~~un-branch the Alembic chain~~ **(done —
PR #180, pending merge)** → persist lifecycle transactions → have the operator
path create them → review the recorded agreement rate → then flip the rules to
authoritative. **The next step is now the first unblocked one:** a migration
adding durable lifecycle-transaction persistence, chained off `052`.

## 0·BLOCKED — Read-only PIT certification prepared, NOT executed [2026-07-21]

The tooling to certify `SubscriberInquiry` in PIT is complete and tested. **The
run did not happen**, and two independent stop conditions are why:

1. **No subscriber was nominated.** The read-only ICCID allowlist is empty and no
   identifier was supplied. There is deliberately no default and no "latest"
   subscriber.
2. **No PIT credentials are configured** in the environment where this was
   prepared (`is_configured` is false — no consumer key, secret, or signing key),
   so a live request is impossible and the environment cannot be proven against a
   live gateway.

`SubscriberInquiry` therefore remains **mock-certified and live-blocked**.
Readiness advances only on real evidence.

**What is ready:** a preview-by-default `subscriber-inquiry` operator command,
and a single-run authorization covering one read-only operation, one nominated
subscriber, one request — PIT-only, 15-minute expiry, consumed the moment the
client boundary spends it, auditable, and incapable of covering a lifecycle
mutation. A missing or mismatched grant falls through to the normal refusal, so
it cannot widen access.

**To execute**, an operator supplies a nominated PIT subscriber, adds it to
`TMOBILE_PIT_READONLY_ICCID_ALLOWLIST`, configures PIT credentials, and runs the
command in `TMOBILE_PIT_OPERATOR_RUNBOOK.md` §2a.

## 0·DONE — Typed T-Mobile contracts and lifecycle foundation [2026-07-21]

Typed request/response models, a normalized subscriber lifecycle, a transition
registry, centralized preconditions, callback application rules, and a
carrier-agnostic snapshot. Foundation only — **no PIT execution, no live call,
no subscriber state change.**

The organizing idea: **a synchronous acceptance is not a result.** The carrier
answers immediately to say a request authenticated and validated; provisioning
finishes later and is reported asynchronously. Every mutation therefore moves a
line into an explicit `*_pending` state and only an asynchronous result settles
it. (Suspension is the documented exception — its synchronous answer is
terminal.)

**Callbacks apply only on exact correlation** — partner-transaction-id, then
workflow id, then service-transaction id. There is deliberately no
"latest pending transaction" and no timestamp-proximity fallback: both look
reasonable and both misattribute results under replay or concurrency. Anything
uncorrelatable, duplicated, superseded, conflicting, or not understood is
quarantined with its evidence intact and leaves state untouched.

Five state facets are tracked separately rather than collapsed into one string
(carrier-reported, workflow, expected, last-confirmed, reconciliation), because
they legitimately disagree — and the disagreement is the signal.

**Mutations fail closed on unknown or unconfirmed state.** Reads do not: a query
is how you learn the state, so gating it on knowing the state is circular.

**Activation remains the sole live-sendable operation; eight remain blocked.**
Typed models explicitly do not weaken the registry — a test pins that having a
model confers no permission to send.

**Deferred:** durable persistence for lifecycle transactions. ~~The alembic chain
is currently branched (two revisions share a parent, one of them uncommitted),
so migration ownership is unclear and adding one would entangle this work with
an unrelated in-flight migration.~~ **[2026-08-11] That blocker is cleared** — the
uncommitted revision was the ops-center `050`, now landed as `052` off `051`
(PR #180), and `test_alembic_single_head.py` guards against a recurrence. The
transaction structures are typed and persistence-ready; **this is now the
highest-value unblocked engine task.**

**Next:** read-only PIT certification — SubscriberInquiry against one explicitly
nominated subscriber, operator-approved, no bulk mode.

## 0·DONE — T-Mobile contract reconciled against authorized documentation [2026-07-21]

Authorized vendor documentation was obtained and **reviewed privately**;
implementation was reconciled against it (evidence reference
`TMO-REST-RECON-001`). The corrections were substantial: the previously derived
paths were wrong for **every** operation, **four** operations used the wrong HTTP
method, and **every** lifecycle request body was wrong (a required identifier was
omitted and an undocumented one was sent). Activation — the only operation ever
confirmed by a live response — was the sole one already correct.

This vindicates the blocking decision (D-018). Had those seven been sendable,
every one would have failed, and the wrong-verb cases would likely have failed in
ways that mimic an auth fault.

**All eight non-activation operations remain LIVE-BLOCKED.** Readiness is now a
gate distinct from provenance: knowing a contract says what to send, not whether
this client sends it correctly. Only real PIT evidence opens it. A fail-closed
guard now runs inside the client before the OAuth token is fetched, so a direct
method call cannot bypass the operator gates.

**Confidentiality.** This repository is public; the vendor material is
confidential and is NOT committed. Only the minimum wire facts needed to function
are published. The contract matrix, response-code analysis, citations and
document hashes live in the operator's private evidence store, outside version
control, enforced by automated guards.

**No live call was made and no subscriber state changed.** Status:
`TMOBILE_OPERATION_READINESS.md`.

## 0·URGENT FINDING — 7 of 8 T-Mobile operations have NO supplied contract [2026-07-21]

> **SUPERSEDED the same day** by the reconciliation above — the documentation was
> subsequently obtained. Retained as the record of why the operations were
> blocked, which the reconciliation proved correct.

T-Mobile authorized us to "run other API calls to complete your development and
testing cycle." Building the certification harness surfaced why we largely
cannot yet.

**There is no T-Mobile OpenAPI spec, Postman collection, PDF, or reference
implementation anywhere in this repository.** Every subscriber-family path is
produced by our own string join in `tmobile_taap._subscriber_path()`.

**That derivation is provably wrong.** Activation works at
`/wholesale/v1/subscriber/activation` only because `TMOBILE_ACTIVATION_PATH`
overrides it — the derived default is `/wholesale/v1/subscriber/activate`. Had we
trusted the derivation, the successful activation would have gone to a
non-existent path. So `/suspend`, `/restore`, `/deactivate`, `/inquiry`, and
`/changesim` are **guesses**, and no response schema for any of them has ever
been observed.

**Consequence:** `activate_subscriber` is the only sendable operation. The other
seven are BLOCKED by `app/integrations/tmobile_operations.py` — a refusal that
config cannot lift, only a T-Mobile-supplied contract plus a reviewed code
change. Blocked ≠ broken: they stay implemented and mock-tested.

**Next action is a documentation request, not an API call.** Run
`python ../scripts/tmobile_pit.py show <operation>` for the exact question list
and send it to T-Mobile. See `TMOBILE_API_INVENTORY.md` and
`TMOBILE_PIT_CERTIFICATION_PLAN.md` §2.

**The one live-ready step today** touches no network: confirm whether a callback
ever arrived for the 2026-07-21 activation —
`python ../scripts/tmobile_callback_inspect.py --iccid <ICCID> --partner-transaction-id <ptx>`.

## 0·✅ DONE — T-Mobile PIT ACTIVATION SUCCEEDED [2026-07-21]

**`POST /wholesale/v1/subscriber/activation` → HTTP 201, `status=SUCCESS`,
result code `100`**, at `2026-07-21T03:18:33.694749Z` on deployed commit
`1766f51`. An MSISDN was assigned (`******6851`) and an account ID generated
(`*******3214`) for ICCID `**************7538`. GENS-0003 is **closed**.

Full table (trace ids, validated contract): `TMOBILE_PIT_ACTIVATION_PAYLOAD.md`.
Unmasked identifiers: `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md`
(operators only). Machine-readable record:
`api/tests/fixtures/tmobile_pit_success_20260721T031833Z.json`.

**Root cause — stated exactly as far as the evidence goes.** T-Mobile Engineering
recreated the gateway configuration immediately before this request. *Resolved by
T-Mobile gateway configuration recreation. The available evidence indicates the
client request contract was valid at the time of the successful activation, and
no additional Partner Foundation header was required. Exact internal T-Mobile
root cause is not independently observable from the client.*

The **same deployed client contract** had returned `400 GENS-0003 Invalid
partnerID` days earlier with **no code change in between**, `partner-id`/
`sender-id` both `128` on each, and **no Partner Foundation header ever sent**.

**Hypotheses now closed (superseded, not erased):**

- Partner Foundation ID required → **no**; it was never sent. Config stays inert.
- PoP contract unverified → **verified**; the reference contract was accepted.
- `sender-id` transmission unverified → **verified**; sent and accepted on both
  the token and resource calls.
- GENS-0003 active → **closed.**

**⚠️ Still unverified — do not read success as readiness:**

- **Callback: UNVERIFIED.** No callback confirmed for this activation; the
  account ID came from the synchronous 201 body. Read-only check (SELECT only,
  no network): `python ../scripts/tmobile_callback_inspect.py --iccid <ICCID> …`
- **Subscriber status: UNVERIFIED.** `scripts/tmobile_subscriber_status.py`
  exists (read-only, `--confirm-read-only`) and has not been run.
- **Persistence gap:** a synchronous-201 activation writes nothing to our DB.
- **19 of 20 production gates open** — `TMOBILE_PRODUCTION_READINESS.md`.

⛔ **Do not re-activate the PIT ICCID; do not suspend/deactivate/SIM-swap the
line.** It is the only end-to-end evidence we have.

## 0·DONE — T-Mobile TAAP restored to the supplied reference contract (PR #170, MERGED as `1766f51`) [2026-07-16]

**T-Mobile Engineering supplied the complete PoP Token Builder reference.** It is
now the authoritative wire contract and supersedes PRs #165–#168, which were
reconstructions from partial evidence during `400 GENS-0003 "Invalid partnerID /
Empty PartnerID/SenderID"` debugging (UTC `2026-07-07T14:59:50Z`, work-flow-id
`99a2b4f7-…_P`, service-transaction-id `9b8f65ad-…`).

**Root cause:** the OAuth endpoint worked and returned a token, so each failed
activation was misread as a T-Mobile-side registration gap. The real defect was
that our PoP had drifted from T-Mobile's builder on **six** axes at once, and we
were verifying our reconstruction against itself.

Authoritative contract (see `tmobile_taap_setup.md` § "Authoritative PoP
contract" for the full table):

- JWT header `{"alg":"RS256","typ":"JWT"}` — **not** `typ="pop"`
- Claims exactly `iat, exp (=iat+60), ehts, edts, jti, v="1"` — **no `iss`**
- **Both** OAuth and resource PoPs sign
  `Content-Type;Authorization;uri;http-method;body`
- `edts` = base64url(SHA-256(values concatenated, **no separator**)), body **not**
  pre-hashed and carried as its **exact wire bytes**
- OAuth body compact `{"cnf":"..."}`; grant type moved to a `grant-type` header
- `sender-id` stays an **unsigned** lowercase header (the one finding that
  survived every revision)
- `id_token`, when returned, is cached paired with the access token and replayed
  as `X-Auth-Originator`

`generate_pop_token()` now has `create_oauth_pop_token()` / `create_api_pop_token()`
wrappers so the two flows cannot drift apart again. The body is serialized **once**
(`separators=(',', ':')`) and that same string is signed and sent.

Golden tests: `test_tmobile_reference_contract.py` pins the supplied vector
(`SHA-256("application/json" + "Basic TEST" + "/oauth2/v1/tokens" + "POST" +
'{"cnf":"TEST_PUBLIC_KEY"}')`), the JWT shape, id_token handling, and the
no-secret guarantees. Removing `iss` also removed the consumer key from a
decodable JWT.

Retest outcome: **still GENS-0003** — see §0 above. The contract is correct; the
failure is elsewhere. **Merged as `1766f51`.**

## 0·PREV — RH registry approval operator script (**PR #164, MERGED**) [2026-07-02]

> **Corrected 2026-08-11:** this was recorded as "PR open, NOT merged"; GitHub
> confirms **MERGED**. Verified open PRs are only **#180** (this work), **#169**
> (gitleaks CI allowlist), and **#166** (draft, superseded PoP fix).

Turns the 56 pending `PortfolioReviewItem` candidates into approved `PortfolioBuilding`
rows so RH flips from `fallback_mode` → `registry_mode` (approved buildings 0 → N).
New `api/scripts/rh_registry_approve_from_review.py`:

- Reads pending review items, parses the fused candidate payloads, applies the operator
  **decision table** (`--include-known-rh-decisions`): canonical-name overrides + merges
  of duplicate candidates (Hollywood, Chicago #147, Beverly Modern, Austin #149,
  Princeton #644, Linden/MDC/Patterson/RHNYC/Memphis…), and the parent-account exclusion.
  **Edina #159 and Raleigh #178 stay separate** (keep-separate guard).
- For each approved candidate it creates the building + aliases (from source names) +
  device mappings (radio/ICCID/IMEI/MSISDN/true911_device/zoho_account), collision-safe
  against the registry unique keys, and marks the review item(s) decided — via the
  existing `approve_new_building` workflow.
- Flags: `--tenant`, `--dry-run` (default; writes nothing), `--apply`, `--limit N`,
  `--only-high-confidence`, `--include-known-rh-decisions`. Report: created / merged /
  excluded / skipped / unresolved + **before/after visible count** (and mode flip).
- **Scoped writes:** only the Portfolio Registry, only under `--apply`; NEVER Site /
  Device / E911 / Zoho / Napco / Genesis; E911 never verified; no Judy invite.
- Tests: `test_rh_registry_approve_from_review.py` (13); full suite green (**3893**).
  Docs: `RH_GO_LIVE_RUNBOOK.md` §4e step 3.

Go-live gate unchanged: run fusion → sync queue → **approve (this script)** → enable
the registry-view flags → verify the RH Test dashboard → only then send Judy's invite.
**Judy invite remains BLOCKED.**

## 0·PREV — Customer Dashboard → Portfolio Registry integration (**PR #163, MERGED**) [2026-07-02]

Moves the RH customer dashboard + Location/Building Workspace from raw `Site` rows to
canonical **PortfolioBuildings** (fixes the stale 42/42 vs 56-canonical count and the
0-services / 0-health KPIs). Additive, read-only, flag-gated **OFF** by default.

- **Config flags** (default OFF): `FEATURE_CUSTOMER_PORTFOLIO_REGISTRY` +
  `CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST` (two-key), plus
  `CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS` and `CUSTOMER_PORTFOLIO_PREVIEW_PENDING` +
  `CUSTOMER_PORTFOLIO_PREVIEW_TENANT_ALLOWLIST` (pending policy).
- **Serializer** `serialize.portfolio_building` — customer-safe canonical building
  (building_ref, canonical/display name, store#, category, status,
  customer_visible_status, address, map_point, confidence bucket, protection,
  services, equipment/phone counts, E911, separated health, maturity). Never exposes
  Zoho/Napco/Genesis ids, ICCID, IMEI, radios, aliases, or review payloads.
- **Read model** `services/customer/portfolio_registry_view.py` — loads approved
  (+ pending under flag) buildings, links each to its True911 Site(s) via
  device-mapping/store#/address, derives services/E911/health (reusing assurance +
  service inference); returns `None` → **legacy fallback** when off or no visible
  buildings (internal log only, no customer-facing fallback language).
- **Endpoints** (registry mode): dashboard, /portfolio/summary, /portfolio/health,
  /portfolio/services, /locations, /locations/{ref}, /locations/{ref}/services,
  /locations/{ref}/health, /search render from the registry; `resolve_site` also
  accepts a `bldg` ref so e911/timeline/contributions keep working. Pagination ≤100,
  search by canonical name/store/city/state/phone.
- **Pending policy**: approved visible; pending hidden by default; preview flag shows
  all for the internal RH test user; calm wording "Portfolio record being finalized"
  (never "pending review").
- **UI**: `CustomerAssuranceView.jsx` + `LocationCommandCenter.jsx` normalize to
  `building_ref`/`display_name` (works in both modes); canonical names; no source
  terms in the customer surface. Vite build green.
- **Audit script** `scripts/customer_registry_view_audit.py` — reports flag state,
  approved/pending/legacy counts, and the effective mode (legacy_site/registry/fallback).
- **Read-only**: no writes to registry or any source; no auto-created Sites; E911
  never verified; no Judy invite.
- Tests: `test_customer_portfolio_registry_view.py` (12) + full suite green (**3880**).
  Docs: `CUSTOMER_COMMAND_CENTER.md` §8e, `LOCATION_DIGITAL_TWIN.md` §10,
  `RH_GO_LIVE_RUNBOOK.md` §4e, `PORTFOLIO_REGISTRY.md`.

**Judy invite remains BLOCKED** — pending fusion → sync → approve → enable flag →
verify RH Test dashboard count (runbook §4e).

## 0·PREV — Portfolio Registry & Persistent Digital Twin (PR #162, MERGED `5638595`) [2026-07-02]

Evolved the Fusion Engine from a reconciliation tool into the permanent **Portfolio
Registry** that powers every customer Digital Twin — it no longer rediscovers the RH
portfolio each run; it reconciles against an operator-**approved** registry. Additive,
read-only fusion; registry writes only via an explicit approval workflow.

- **Models + migration 051** (`app/models/portfolio_registry.py`): `PortfolioBuilding`
  (canonical_name/store_number/site_type/status/address/city/state/zip/tenant_id/notes/
  approved/approved_by/approved_at), `PortfolioAlias` (building_id/alias/source/
  confidence/active), `PortfolioDeviceMapping` (kind ∈ napco_radio/genesis_msisdn/iccid/
  imei/phone/true911_device/zoho_account → building), `PortfolioReviewItem` (queue).
  Chains off committed head 049 (ops-center 050 is separate WIP).
- **Service** (`app/services/portfolio_registry.py`): `load_registry` (read-only
  snapshot), pure `reconcile` (approved mappings **before** heuristics: device → alias
  → store# → address; else a review item), and the approval workflow
  (`approve_new_building`/`approve_alias`/`approve_device_mapping`/`reject_review_item`
  /`sync_review_queue`) — the ONLY registry writers.
- **Review types**: new_building · possible_merge · duplicate_building · address_conflict
  · device_conflict · unknown_alias.
- **Fusion integration**: `fuse_portfolio(..., registry=)` reconciles each candidate,
  tags it known/new/ambiguous, and reports Portfolio Buildings · Known Aliases · Pending
  Review · Approved Mappings · Rejected Suggestions · Coverage by Source · Confidence
  Distribution + a review-queue section. CLI `--no-registry` / `--sync-review-queue`.
- **Read-only preserved**: never writes Zoho/Napco/Genesis/carrier APIs/True911 **or the
  registry**; E911 never verified; nothing fabricated.
- Tests: `test_portfolio_registry.py` (16) + `test_rh_portfolio_fusion.py` registry
  integration (39). Full suite green (**3868**).
- Docs: `customer/PORTFOLIO_REGISTRY.md` (new), `PORTFOLIO_FUSION_ENGINE.md` §7,
  `LOCATION_DIGITAL_TWIN.md` §10, `RH_GO_LIVE_RUNBOOK.md` §4d.

**Prior fusion PRs merged:** #159 (engine), #160 (Genesis filter), #161 (Napco filter +
over-split). This branches off main with all three.

## 0·PREV — Portfolio Fusion Engine (PRs #159/#160/#161, MERGED) [2026-07-01]

Extended the RH Certification Engine into a **multi-source Portfolio Fusion Engine**:
fuses **Zoho CRM · Napco StarLink · T-Mobile Genesis (MS130v4) · True911** into one
canonical **Building Digital Twin** per location. Additive, read-only, new script.

- `api/scripts/rh_portfolio_fusion.py` — four read-only source adapters (Zoho reuses
  the cert CSV/live loaders; Napco reuses `inventory_reconciliation.adapters.napco`;
  Genesis = tolerant MS130 CSV + read-only API stub; True911 reuses
  `cert.load_true911`). Each emits normalized SourceRecords (store#, canonical name,
  address, site type, building category, devices, services).
- **Entity resolution** clusters records into buildings by store# / address / device
  identifier (radio# / IMEI / ICCID / MSISDN / StarLink / serial); within a building,
  device rows merge by shared identifier into one unified device each.
- **Building Digital Twin**: building · services · devices · E911 · **source
  confidence** (True911 40 · Zoho 25 · Napco 20 · Genesis 15, capped 100) · **missing
  assets** (device in vendor not in True911, no service unit, E911 unverified) ·
  **duplicate assets** (dup True911 sites, shared address).
- **Outputs**: CSV + JSON + Markdown Building Fusion Report + **executive dashboard**
  (buildings, fully-fused-all-4, per-source coverage, category mix, gaps, avg confidence).
- Read-only: never writes any source, never marks E911 verified, never fabricates;
  Napco sensitive fields dropped by the existing adapter.
- Tests: `test_rh_portfolio_fusion.py` (19) — adapters, cross-source matching by
  every identifier, twin identity/category/confidence, missing/duplicate, outputs,
  CLI validation. Full fusion/cert/reconciliation/zoho slice green (**412**).
- Docs: `customer/PORTFOLIO_FUSION_ENGINE.md`, `RH_GO_LIVE_RUNBOOK.md` §4c.

**Stacks on the certification engine** (PRs #155/#156/#157 merged; #158 known-alias
registry open — this branch includes it and reuses `KNOWN_RH_LOCATIONS`).

## 0·PREV — RH Certification v2: known special-location registry (**PR #158, MERGED**) [2026-07-01]

Teaches the certification engine that operator-confirmed RH special locations are
legitimate (were previously flagged "weird RH label"). Additive, read-only.

- New `KNOWN_RH_LOCATIONS` registry (Greenwich 265, RHNYC, Beverly Modern,
  Patterson Warehouse, MDC, Linden House) → each canonicalized with a definitive
  `site_type` (special / gallery / warehouse / distribution_center), counted as a
  real RH location, and **not** flagged L. Still checked for missing/address/
  duplicate/device/service-unit/E911.
- Matching improvements: known-alias recognition is a **positive, high-precision
  signal** (bumps confidence, strong-matches when the alias is in the True911 site
  name); name matching now **ignores the generic "Restoration Hardware" tokens**
  (matches on the distinctive part only) and won't force a match on a bare short
  city token — so **RHNYC no longer overmatches a generic NYC record**.
- Report adds a **"Known special RH locations"** section (alias · canonical · site
  type · match status · confidence) and a summary `known_special_locations` count.
- **Dry run (2026-07-01 export):** the 6 confirmed specials are now recognized;
  manual-review canonicals drop **20 → 14**; still 44 canonical locations.
- Tests: `test_rh_portfolio_certification.py` now **42** (+14: each alias, not-weird,
  still-require-match, warehouse/distribution/special typing, RHNYC non-overmatch,
  generic-name-match guard). Reconciliation/readiness/zoho slice green (**325**).
- Docs: `RH_PORTFOLIO_CERTIFICATION.md` §3a, `RH_GO_LIVE_RUNBOOK.md` §4b.

**Prior certification PRs merged to main:** #155 (base wizard, `1712d17`), #156
(live Zoho mode, `3b0b374`), #157 (page_token pagination, `d9f3b7a`).

## 0·PREV — RH Portfolio Certification: live Zoho mode (PR #156, MERGED `3b0b374`; pagination hotfix PR #157, MERGED `d9f3b7a`) [2026-07-01]

Upgraded the certification wizard to read from **either** an offline CSV **or**
**live Zoho CRM**, so it no longer requires a CSV export. Additive, read-only.

- `--zoho-live` fetches RH records live via the **existing** authenticated client
  (`zoho_crm.fetch_records`) — same OAuth token refresh + pagination, **no
  duplicated auth**. `--module` (default `Accounts`) + `--fields` select what is
  read; a live record maps to the SAME normalized shape as a CSV row, so the
  canonical → match → classify → report pipeline is byte-identical.
- `--zoho-csv` is now **optional**; **exactly one** of `--zoho-live` / `--zoho-csv`
  is required (both, or neither → usage error). CSV mode is fully backward compatible.
- Same CSV / JSON / Markdown outputs and PASS/CONDITIONAL/BLOCKED verdict in both modes.
- Tests: `test_rh_portfolio_certification.py` now **28** (added live mapping,
  pagination reuse, field selection, auth reuse, CLI source validation, CSV back-compat).
  Reconciliation/readiness/zoho slice green (**304**).
- Docs: `customer/RH_PORTFOLIO_CERTIFICATION.md`, `RH_GO_LIVE_RUNBOOK.md` §4b.

**PR #155 (base wizard) is MERGED to main (`1712d17`).** This branch stacks the
live-mode upgrade on top.

## 0·PREV — RH Portfolio Certification Wizard (PR #155, MERGED to main `1712d17`) [2026-07-01]

Read-only **go-live gate** for RH: certifies that every RH location / subscription /
line / device in a Zoho export is represented correctly in
True911 **before Judy's invite**.

- Script `api/scripts/rh_portfolio_certification.py` — parses the Zoho CSV, detects
  RH rows (aliases + weird labels), normalizes each into a **canonical portfolio
  record** (store#, site_type, address, phones, device ids, confidence,
  manual_review), groups device rows into canonical locations, reads True911 prod
  (sites/devices/units/lines/E911), **matches** (store#/address/city-state-zip/phone/
  device-id/name), and **classifies A–L**.
- Executive report with **PASS / CONDITIONAL / BLOCKED** verdict + top-25 issues +
  operator punch list; CSV + JSON + MD artifacts. Exit 0/1/2/3.
- **Read-only** — SELECTs + the supplied CSV only; never writes Zoho/True911, never
  marks E911 verified, never fabricates data. Blocking gates C/F/I/J/K must reach 0.
- Tests: `test_rh_portfolio_certification.py` (19; normalization, store#, alias,
  dedup, matching, missing-site/unit, E911-unverified, verdict, CSV/JSON/MD). Script
  slice green (**295** in the reconciliation/readiness/zoho slice).
- Docs: `customer/RH_PORTFOLIO_CERTIFICATION.md`; `RH_GO_LIVE_RUNBOOK.md` §4b.
- **Dry run against the provided 2026-07-01 export:** 377 rows → 70 RH → **44
  canonical locations** (20 need manual review). Live matching runs on Render (prod
  DB). Judy's invite **remains blocked** pending a PASS/CONDITIONAL-with-sign-off run.

**Guarantees held:** read-only · no E911 auto-verify · no fabrication · PR opened,
**awaiting review** (do not auto-merge).

## 0·PREV — Building Workspace (PR #154, MERGED to main `3747c69`) [2026-07-01]

The Location Digital Twin was refined into a **collaborative Building
Workspace** — additive, same APIs, no architecture change:

- **Reorganised** the Location Workspace into four workspaces — *Building Summary ·
  Operations · Compliance · Administration*; **services are the primary objects**,
  supporting equipment de-emphasised under a collapsible.
- **Contribution workflow** (`services/customer/contributions.py`) — append-only
  `customer_contribution` audit events (contact/inspection/photo/document/
  procedure/note/service_request); **never writes protected data**. New endpoints
  `POST|GET /api/customer/locations/{ref}/contributions`, new permission
  `CUSTOMER_CONTRIBUTE` (ADMIN/MANAGER/SUPPORT/USER).
- **Separated health** (`serialize.separated_health`) — 4 factors (Operational 40 ·
  Completeness 25 · Compliance 20 · Documentation 15), composite shown *after* the
  factors; unknowns lower confidence. **Maturity tier**
  (`serialize.building_maturity`) — Bronze/Silver/Gold/Platinum over 7 dimensions.
- **De-branding** — no operating-company references in the customer plane; neutral
  status vocabulary (Verification Pending/Requested · Awaiting Review · Verified).
- **Tests** — `test_customer_contributions.py` (+ updated twin/e911 tests); full
  customer suite green (**1421** in the customer/e911/twin slice); web build green.
- Docs: `customer/WORKFLOW_ENGINE.md`, `customer/DIGITAL_TWIN_MATURITY_MODEL.md`,
  updated `customer/LOCATION_DIGITAL_TWIN.md`.

**Guarantees held:** additive · no internal-workflow exposure · RBAC unchanged/not
weakened · no API redesign. Merged as **PR #154**.

## 0. MERGED TO MAIN — the RH Customer Stack is live in `main` [2026-07-01]

The full customer surface has landed on `main` across these merged PRs (in order):

| PR | Merge | What |
|---|---|---|
| **#142** | `8af5c29` (login layer) | RH customer login wired to `/api/customer` — **Judy = `CUSTOMER_ADMIN`** (isolated `CUSTOMER_*` plane, not legacy `User`); Customer Assurance/Preview Mode. |
| **#143** | `8597d97` | Customer Command Center — service-first executive dashboard (metrics + evidence-graded portfolio health, map w/ legend + list↔map sync, enterprise search) **+ the map/search/richer-drawer polish that #142's merge had dropped** (recovered here). |
| **#144** | `603ff19` | Location Digital Twin — each building a complete operational record (14-section Location Workspace; enriched service model; `/locations/{ref}/documents\|photos\|contacts\|inspections\|health`; permanent `?location=<ref>` deep-link). |
| **#146** | `4779bff` | Hotfix — blank Command Center: page `/customer/locations` at ≤100 and accumulate (backend caps `page_size` at 100). |
| **#147** | `acccb24` | Life Safety Service Intelligence — equipment inferred into first-class services (8 types) with confidence; location/portfolio health from **service** health; internal approve/override/merge/split (`MANAGE_SERVICE_CLASSIFICATION`, append-only audit). |
| **#148** | `5c143f3` | Customer E911 confirmation & correction — customers confirm/request-correction without overwriting official E911; internal review queue (`/api/e911-changes/reviews`); append-only audited. |

*(Also #145 `366da5d` — docs-only PROJECT_STATE update.)*

**Net state on `main`:** the isolated `CUSTOMER_*` roles (ADMIN/MANAGER/VIEWER/
SUPPORT/USER/BILLING/READONLY) reach a read-only, flag-gated, service-first
Life-Safety Command Center + per-building Digital Twin via `/api/customer/*`, with
**equipment inferred into services** and a **customer E911 confirm/correction**
workflow. `CUSTOMER_*` hold **no** `INTERNAL_OPS`/`COMMAND_*`/`MANAGE_SERVICE_CLASSIFICATION`
(isolation enforced by `test_customer_rbac_posture.py`). E911 is never fabricated and
never customer-overwritten (append-only reviews; `verified` stays Manley-gated);
operational green is Preview-Mode operator-attestation; health scores use real signals
only (unknowns lower confidence). Full backend suite green (**3716**); web build green;
all CI checks green on each PR. Detail docs: `docs/customer/{CUSTOMER_COMMAND_CENTER,
LOCATION_DIGITAL_TWIN,LIFE_SAFETY_SERVICE_MODEL,E911_CUSTOMER_REVIEW_WORKFLOW,
ASSURANCE_ENGINE,RH_GO_LIVE_RUNBOOK}.md`; `DECISIONS.md` D-016.

**Remaining before Judy logs in (ops action, not code):** set the 4 env vars on
`true911-api` + `true911-worker` (`FEATURE_CUSTOMER_API`, `CUSTOMER_API_TENANT_ALLOWLIST`,
`FEATURE_CUSTOMER_PREVIEW`, `CUSTOMER_PREVIEW_TENANT_ALLOWLIST=restoration-hardware`),
create Judy as `CUSTOMER_ADMIN`, run `python -m scripts.rh_customer_readiness_check`,
verify login — per `docs/customer/RH_GO_LIVE_RUNBOOK.md`. **Top roadmap:** documents/
photos storage, real timeline/inspection ingest, added health inputs, Reports pages +
CSV/PDF, marker clustering, and a frontend Vitest runner (none exists yet).

> Sections **0d–0** below are the per-PR change notes (now all merged), kept for detail.

## 0f. Customer E911 confirmation & correction — MERGED (PR #148, `5c143f3`) [2026-07-01]

CUSTOMER_* users can now participate in E911 validation **without overwriting the
official record**. Additive; append-only audited (ActionAudit; migration-free).
- **Customer endpoints:** `POST /customer/locations/{ref}/e911/confirm`,
  `POST …/e911/correction-request`, `GET …/e911/review-status`. **Internal:**
  `GET /api/e911-changes/reviews`, `POST …/reviews/{id}/approve|reject`.
- **Service** `services/e911_review.py`: confirm snapshots the server-shown record;
  correction stores a *request* (never applied); status derives from the event
  chain (Not yet verified / Customer confirmed / Correction requested / Under Manley
  review / Verified). Applying to the official record stays the existing UPDATE_E911
  flow.
- **RBAC:** new `CUSTOMER_SUBMIT_E911_REVIEW` (ADMIN/MANAGER/SUPPORT/USER; read-only
  roles view only). Internal guard = `require_any_permission("UPDATE_E911",
  "MANAGE_SERVICE_CLASSIFICATION")`. CUSTOMER_* isolated from the internal queue.
- **UI:** `LocationCommandCenter.jsx` E911 section — Confirm / Request Correction
  (form) + friendly status; read-only roles see status only.
- **Data safety:** never fabricates or overwrites official E911; opaque refs;
  existing E911 APIs unchanged. Full suite green (**3716**); web build green.
  Doc: `docs/customer/E911_CUSTOMER_REVIEW_WORKFLOW.md`. **MERGED (PR #148).**

## 0e. Life Safety Service Intelligence — MERGED (PR #147, `acccb24`) [2026-07-01]

The backend now converts an equipment inventory into a **Life Safety Service**
model — services are first-class; equipment supports them. Additive on the
Command Center + Digital Twin; no UI redesign.
- **Inference engine** `services/customer/service_inference.py` (pure): classifies
  equipment (model/type/notes/manufacturer/carrier + line label + ServiceUnit) into
  Fire Alarm/Elevator/Area of Refuge/Emergency Phone/BDA·DAS/Generator/Mass
  Notification/Burglar Alarm, groups multi-device services, with **confidence**
  (Confirmed/High/Medium/Low); unclassified → generic + Low (honest, never faked).
- **Health from services:** `_build_location_services` sources
  `/locations/{ref}/services` (inferred); **location health derives from service
  health**; portfolio stays building/service-derived. New `/customer/portfolio/services`
  (service inventory). `serialize.service_card` (additive; carries confidence).
- **Internal ops (Phase 8):** `routers/service_classification.py` +
  `services/service_classification.py` — approve/override/merge/split guarded by
  new perm **`MANAGE_SERVICE_CLASSIFICATION`** (Admin/Manager/DataSteward/UX_QA;
  **no `CUSTOMER_*`**). Overrides persist + log as append-only **`ActionAudit`**
  records (no new table/migration); the inference engine applies the latest override
  per device.
- **Frontend:** minimal — the drawer already renders `services.services` (now
  inferred); added a small "Inferred · <confidence>" hint. No redesign.
- **Truth/isolation:** no fabricated E911/telemetry/last-test; carrier *name* only;
  CUSTOMER_* isolation intact. Full suite green (**3690**); web build green. Doc:
  `docs/customer/LIFE_SAFETY_SERVICE_MODEL.md` (new). **MERGED (PR #147).**

## 0d. Location Digital Twin — MERGED (PR #144, `603ff19`) [2026-07-01]

The Location tier of the Command Center is now a **Digital Twin** — each customer
building is a complete operational record. Additive on `/api/customer/*`:
- **New endpoints (CUSTOMER_VIEW_LOCATIONS):** `/locations/{ref}/documents`,
  `/photos`, `/contacts`, `/inspections`, `/health` (per-location building health).
- **Enriched service model** (`serialize.service_with_equipment`, additive): carrier
  **name**, telephone numbers, equipment count, last test/inspection, attention items.
  New serializers: `carrier_label`, `timeline_entry`, `location_contacts`,
  documents/photos/inspections placeholders + `TIMELINE_KINDS`/`DOCUMENT_CATEGORIES`/
  `INSPECTION_KINDS`. Loaders in `command_center.py`.
- **Frontend:** `LocationCommandCenter.jsx` is now the full Location Workspace
  (Overview · Health · Services+Equipment · E911 · Documents · Photos · Inspections ·
  Timeline · Contacts · Emergency Procedures · Service Requests · Billing · Notes);
  breadcrumb + **permanent `?location=<ref>` shareable deep-link** + quick actions
  in `CustomerAssuranceView.jsx`.
- **Truth/isolation:** no fabricated E911/telemetry/inspections; per-location health
  uses real signals only (unknowns lower confidence); carrier *name* only (never
  credentials/IMEI/ICCID/firmware/SIM); CUSTOMER_* isolation unchanged. Full suite
  green (3656); web build green. Docs: `docs/customer/LOCATION_DIGITAL_TWIN.md` (new).

## 0c. Customer Command Center (Phase 1) — MERGED (PR #143, `8597d97`) [2026-07-01]

The RH customer dashboard is now the first version of the **Customer Command
Center** — an enterprise Life-Safety Operating System (service-first, understand
the whole portfolio in <30s), built additively on `CUSTOMER_*` + `/api/customer/*`.
- **Hierarchy:** Enterprise → Portfolio → Location → **Life Safety Service** →
  Equipment → Carrier. Services (Fire Alarm, Elevator, Area of Refuge, …) are the
  unit; equipment is grouped beneath them. Never device models.
- **New APIs (additive, flag-gated, CUSTOMER_* guarded):**
  `/customer/portfolio/summary` (exec metrics + health), `/customer/portfolio/health`,
  `/customer/search`, `/customer/locations/{ref}/services`,
  `/customer/locations/{ref}/timeline`. Aggregation in
  `services/customer/command_center.py`; serializers in `serialize.py`
  (service catalog, `health_score`, `portfolio_summary`, service grouping, timeline).
- **Frontend:** `CustomerAssuranceView` (executive dashboard, zoom-to-fit map +
  legend + list↔map sync, enterprise search) + new `LocationCommandCenter.jsx`
  drawer (Overview/Services+Equipment/E911+history/Timeline/Documents·Billing·Notes
  placeholders); service-first nav with "Soon" items.
- **Truth held:** no fabricated E911/telemetry; health uses real signals only,
  unknowns lower *confidence*; E911 "Not yet verified" is calm amber. CUSTOMER_*
  isolation unchanged (no INTERNAL_OPS/COMMAND_*). Full suite green (3644); web build green.
- **Docs:** `docs/customer/CUSTOMER_COMMAND_CENTER.md` (new). **Stubs/roadmap:**
  marker clustering, Reports pages+export, Documents/Billing, timeline event types.

## 0b. RH Login GO-LIVE wiring (Judy = CUSTOMER_ADMIN) — MERGED (PR #142, `8af5c29`)

**2026-07-01.** Finalized the path for Judy/RH to log in via the isolated
customer plane (Option 1). Key facts a resumer must know:
- **Two parallel customer surfaces existed:** the legacy `User`-role dashboard
  (`/command/summary`, needs `INTERNAL_OPS`) and the new isolated `CUSTOMER_*` +
  `/api/customer/*` API. Judy is **`CUSTOMER_ADMIN` (never `User`)**, so her
  dashboard is now **wired to `/api/customer/dashboard` + `/api/customer/locations`
  + `/api/customer/.../e911`** via a contained customer branch in
  `web/src/pages/UserDashboard.jsx` → `web/src/components/customer/CustomerAssuranceView.jsx`.
- **RBAC (additive):** `permissions.json` grants `CUSTOMER_*` the customer-page
  read perms (`VIEW_SITES/VIEW_DEVICES/VIEW_ASSURANCE`) and adds three roles
  `CUSTOMER_MANAGER/VIEWER/SUPPORT`; `admin.py ALLOWED_ROLES` now accepts
  `CUSTOMER_*` (invite/create). `CUSTOMER_*` still hold **no `INTERNAL_OPS`/
  `COMMAND_*`** (verified by `test_customer_rbac_posture.py`).
- **Isolation:** 8 unguarded internal operator pages (Command, CommandSite,
  OperatorView, Overview, NetworkDashboard, AutoOps, SimManagement, Containers)
  are now gated behind `INTERNAL_OPS` in `web/src/App.jsx` (blocks `CUSTOMER_*`,
  zero regression for internal roles); Layout shows a minimal `CUSTOMER_NAV`.
- **Provisioning:** `api/scripts/create_customer_user.py` (dry-run-first,
  invite-token, no hardcoded creds) or `POST /api/admin/users/invite`.
- **Readiness:** `api/scripts/rh_customer_readiness_check.py` (`--json`; exit
  0/1/2) verifies flags/allowlists, customer users, counts, and the E911 posture.
- **Docs:** `docs/customer/ASSURANCE_ENGINE.md`, `docs/customer/RH_GO_LIVE_RUNBOOK.md`,
  `DECISIONS.md` D-016. Full backend suite green (3623); web build green.
- **Remaining before Judy logs in:** set the 4 env vars on api+worker (see runbook
  §1), create Judy, run the readiness check, verify login. E911 gaps (unverified
  addresses) remain BLOCKERS to a clean READY and are worked via `/api/e911-changes/gaps`.

## 0. Earlier change — RH Login Preview (IMPLEMENTED, flag-gated OFF)

**Urgent RH go-live enabler.** A tenant-scoped **customer preview mode** lets RH
(Judy) log in *now* and see all locations/services/devices as **Active/Green**
before carrier/vendor telemetry is live — while **E911 stays truthful** (never
fabricated). Presentation-only in the customer composition layer; **no raw
device/API state is overwritten and internal/admin views are unchanged.**

- Flags: `FEATURE_CUSTOMER_PREVIEW` + `CUSTOMER_PREVIEW_TENANT_ALLOWLIST`
  (default OFF; two-key gate mirroring the customer API). Enable for RH:
  `FEATURE_CUSTOMER_PREVIEW=true` + `CUSTOMER_PREVIEW_TENANT_ALLOWLIST=restoration-hardware`
  on **both** `true911-api` and `true911-worker`.
- Green is **evidenced by operator attestation** (not fabricated telemetry) so the
  no-false-green invariant holds; **no "API/telemetry pending" labels** reach RH.
- **E911 excluded from preview:** `verified` true only when stored `e911_status`
  is verified; active+unverified = Critical. Customer E911 record now enumerates
  real per-endpoint detail (unit/floor, callback/BTN/line id, service type) from
  `ServiceUnit` + linked `Line.did`/`Device.msisdn`.
- **Internal correction worklist:** `GET /api/e911-changes/gaps` (`UPDATE_E911`)
  lists every location with missing/unverified E911 data to fix before verification.
- Code: `api/app/services/customer/preview.py`, `services/e911_gaps.py`, updates to
  `services/customer/{portfolio,serialize}.py`, `routers/{customer,e911}.py`,
  `config.py`. Tests: `api/tests/test_rh_customer_preview.py` (full suite green, 3282).
- **Rollback:** flip `FEATURE_CUSTOMER_PREVIEW=false` or drop RH from the allowlist —
  instant, no deploy/migration; RH then sees the real assurance labels again.
- Docs: `CUSTOMER_EXPERIENCE_BOUNDARY.md` §F, `CUSTOMER_DATA_BOUNDARY.md` §6a.

## 1. Current Objective

**PRIMARY BUSINESS OBJECTIVE — RH Customer Go-Live.** Place **Restoration Hardware
(Judy)** into production as the **first production customer actively using True911
every week**, scoped to the **assurance + support** use case (billing/QuickBooks/
invoicing explicitly deferred). Tracked as **`EPIC-RH-GO-LIVE`** in `BACKLOG.md`
(four phases). This is now the top of the execution stack; the engine work below
continues underneath it as the substrate the customer surface reads.

**Customer-go-live planning is COMPLETE (design phase done; nothing implemented yet).**
The full customer boundary architecture is documented and ready to build:
- `RH_PRODUCTION_GO_LIVE.md` — per-area readiness (Green/Yellow/Red); ~32% all-areas,
  ~40% assurance-scoped with a 1-month path to ~80%.
- `RH_GO_LIVE_EXECUTION_PLAN.md` — four tracks (A Data · B Customer Experience ·
  C Assurance · D Billing Visibility) + 30-day plan.
- `RH_SECURITY_READINESS.md` — **tenant isolation audited** across ~140 GET endpoints:
  **no CRITICAL findings**, isolation core sound; 1 HIGH (subscriber-import batch rows)
  + bounded MED/LOW fix set; CONDITIONAL GO.
- `RH_ROLE_MATRIX.md` — **customer RBAC design complete**: the existing "User" role is
  unsafe for a customer; needs a scoped `CUSTOMER_*` role + guards on bare-auth GETs.
- `CUSTOMER_EXPERIENCE_BOUNDARY.md` — four customer roles (ADMIN/USER/BILLING/READONLY),
  the `INTERNAL_OPS` guard strategy, the eight-item customer nav.
- `CUSTOMER_DATA_BOUNDARY.md` — field-level SHOW/HIDE/DERIVE/AGGREGATE per entity (Device
  is ~100% HIDE/DERIVE — the §7 jargon veto holds).
- `CUSTOMER_API_CONTRACTS.md` — **customer API contract design complete**: a dedicated
  read-only `/api/customer/*` namespace, allow-list serializer, evidence-on-green invariant.
- `FEATURE_CUSTOMER_API_ROLLOUT.md` — **rollout design complete**: two-key flag
  (`FEATURE_CUSTOMER_API` + `CUSTOMER_API_TENANT_ALLOWLIST`), default OFF, RH-only
  enablement, instant flag rollback, go/no-go matrix.

**Engine substrate (continues underneath EPIC-RH-GO-LIVE):** the **Identity Engine**
core (`IdentityResolver`, PR #119) + read-only Identity Audit (PR #120, inert) are
merged; **Assurance Engine PR1** is merged but `FEATURE_ASSURANCE_ENGINE` is off. The
RH go-live graduates these for the RH tenant once Track-A data is clean. The active
product direction remains the **operating system for life-safety communications
assurance** (`CONSTITUTION.md`, `PRODUCT_VISION.md`): Reality → Identity → Truth →
Assurance → AI → Automation. **Next implementation slice: `EPIC-RH-GO-LIVE` Phase 1**
(tenant-isolation fixes → `CUSTOMER_ADMIN` role → `INTERNAL_OPS` guards).

**Platform-vs-customer boundary (binding):** RH is the **pilot** that validates the
**generic** customer plane — not a one-off portal. RH-specific *data remediation* scripts
are allowed; the **customer API, roles, permissions, serializer, and navigation stay
reusable** across all customers (statement in `CUSTOMER_API_CONTRACTS.md` §0). The only
runtime generality gap (dashboard `company_name` single-customer `LIMIT 1`) is fixed
(PR #130); broader generalization is tracked as **EPIC-GEN-001** (portfolio display) and
**EPIC-GEN-002** (generic service-unit builder) — neither gates RH go-live.

**Inventory Reconciliation (EPIC-GEN-003) — IMPLEMENTED (merged, PRs #134–#137).** A
customer- and vendor-agnostic, **read-only** reconciliation engine
(`api/app/services/inventory_reconciliation/`) compares an external carrier/vendor
inventory (pluggable adapter; **NAPCO StarLink** first) against True911 inventory →
`INVENTORY_RECONCILIATION.csv`/`.json` + summary (matching: ICCID → RadioNumber →
SubscriberName → site similarity; results MATCHED/PARTIAL/MISSING_IN_TRUE911/
MISSING_IN_VENDOR/DUPLICATE/REVIEW). Runner `python -m app.reconcile_inventory`; runbook
`docs/INVENTORY_RECONCILIATION_RUNBOOK.md`. No DB writes, no flags. **Status:** code
merged + tests green (3170 passed); real RH NAPCO identifiers scrubbed from tests/docs
(PRs #135–#137). **Remaining:** operator runs the CLI against the prod-read DB + the RH
NAPCO export to produce the real reconciliation artifacts (part of Operation Green Phase 2/P1).

## 2. Completed Work (recent, from git history + project memory)

- **T-Mobile async callback location header** (latest commit `b7b5d56`) — attaches
  `call-back-location` header to async-capable T-Mobile Wholesale calls.
- **UX_QA_ANALYST role** (`48770f1`) — additive RBAC role for a Platform Operations
  / UX & QA analyst; permissions in `permissions.json`.
- **Portfolio-wide customer reconciliation dashboard** (`5736705`) — read-only.
- **RH Zoho subscription classification** (`73520f7`) — explains "91 subs vs 51
  devices" via classification.
- **T-Mobile callback ingest MVP** — PRs #59–#63, FULLY LIVE end-to-end since
  2026-05-26 (first verified prod promotion `+18563081391` → device `8563081391`);
  Phase 1a soak with daily runbook (`docs/TMOBILE_CALLBACK_SOAK_RUNBOOK.md`).
- **Health Normalizer MVP** — merged (PR #56) + Phase 1a soak (PR #57);
  `FEATURE_HEALTH_NORMALIZER=true` in production; only consumer is the AI Health
  Summary.
- **LLLM Phase 1a** — deterministic-soak LIVE (`FEATURE_LLLM=true`,
  `LLLM_ALLOW_EXTERNAL=false`); no external Anthropic calls in prod yet.
- **Assurance Engine** — spec saved (`docs/ASSURANCE_ENGINE.md`); backend MVP
  planned, `FEATURE_ASSURANCE_ENGINE` off.

## 3. In Progress

- **T-Mobile Wholesale PIT activation** *(2026-06-17)* — activation now **reaches the
  T-Mobile activation service** and returns `400 GENS-0003 Invalid partnerID`.
  Validated end-to-end: OAuth token acquisition, PoP signing, activation **endpoint
  correction** (`POST /wholesale/v1/subscriber/activation` — not `/activate`),
  diagnostic logging + correlation-ID capture (PR #121 merged), Service/partner
  transaction-ID capture, and the **`partner-id` / `sender-id`** header
  implementation (PR #122 merged — replaced the rejected `X-Partner-Id`/`X-Sender-Id`).
  **Current blocker:** awaiting T-Mobile Engineering (Aman) review of the `partnerID`
  value/format — see §4. **Trace identifiers for support:**
  - failing call: `POST /wholesale/v1/subscriber/activation` (PIT host)
  - ICCID: `8901240204219434247`; rejected `partnerID=128` (sent as `partner-id`)
  - error: `400 GENS-0003 Invalid partnerID`
  - correlation: `X-Correlation-Id` (now logged per request) + `partner_transaction_id`
    captured from the response on failure (PR #121).
- **Product constitution docs** — created 2026-06-14 on branch
  `docs/product-constitution` (documentation-only; **not yet committed**). 6 new
  docs + 5 updated. Awaiting user approval before commit/PR.
- **Integrity / Belle Terre onboarding** — `app/seed_integrity.py` built and tested,
  **not yet applied to prod** (3 LM150 VoLTE elevator phones; first managed-POTS-
  style pilot dataset for the hardware-agnostic health layer).
- **Assurance Engine PR1** — implemented on branch `feat/assurance-engine-pr1`
  (backend, read-only, `FEATURE_ASSURANCE_ENGINE` default off); verify merge state
  and graduate per `docs/IMPLEMENTATION_MASTER_PLAN.md` Track B.

## 3a. Recently Completed (merged 2026-06-14 — verified on GitHub)

- **C1 (private-key repo cleanup)** — ✅ MERGED (PR #112, merge `d6cb9a9`). Key
  rotation deferred as accepted PIT-only risk → tracked as **C3 pre-production
  gate**.
- **Operating-system docs set** (MISSION / OPERATING_LOOP / MASTER_PLAN /
  PROJECT_STATE / BACKLOG / ARCHITECTURE) — ✅ MERGED (PR #113, merge `ad6b940`).
- **C2 (T-Mobile callback authentication)** — ✅ MERGED (PR #114, merged
  04:41Z; merge commit `4b4f27d`). Behind `FEATURE_TMOBILE_CALLBACK_AUTH` (default
  off); full suite green (2319 passed). HMAC deferred to T-Mobile spec.
  **Residual:** enable the flag with a provisioned token before any internet-
  exposed ingest (Track A item A6). See `docs/TMOBILE_CALLBACK_AUTH.md`.
- **T-Mobile async callback location** — ✅ MERGED (PR #111).

> Note: a local `git fetch` was stale at audit time (origin/main showed pre-#114);
> GitHub confirms all of the above merged. Local `main` may need a fetch to catch
> up — no work was lost.

## 4. Blockers

- **T-Mobile PIT activation — `GENS-0003 Invalid partnerID`** *(external dependency)* —
  blocked on **T-Mobile Engineering (Aman)** reviewing the activation logs/payload and
  confirming the correct `partnerID` value/format (and whether `partner-id`/`sender-id`
  are now read correctly). True911 side is implemented and logging the trace IDs;
  no further code change pending T-Mobile's answer. Do not re-fire live activations
  to brute-force the value. *(Also note: real/prod activation still gated by C3 key
  rotation.)*
- **LLLM Phase 1b** (external egress, `LLLM_ALLOW_EXTERNAL=true`) — blocked on
  **governance approval** per `docs/AI_OPERATIONAL_SAFETY.md` §3 and
  `docs/LLLM_PHASE1_ROLLOUT.md` §4. Do not flip without it.
- **Zoho lifecycle source-of-truth** — additive staging plan exists; promotion to
  an additive `lifecycle_status` is a separate, later, explicitly-gated phase.
- **Red Tag Line / US Courts Tampa** — first managed-POTS deployment; readiness
  review + phased plan pending (see project memory).

## 5. Known Risks (snapshot — full list with severity in BACKLOG.md)

1. **Committed private key (C1)** — ✅ repo cleanup MERGED (PR #112). ⚠️ **Key
   rotation INTENTIONALLY DEFERRED as an accepted temporary risk (decided
   2026-06-14):** the leaked key is **PIT/testing-only**, in a non-production,
   non-customer-facing environment. The key in history remains compromised and
   **MUST be rotated before any production exposure — hard gate tracked as BACKLOG
   C3** (external evaluators / customer pilots / production traffic / carrier
   certification / gov or customer demos). Do not set `TMOBILE_ENV=prod` or
   `TMOBILE_PIT_LIVE_CALLS_ENABLED=true` for a real account until C3 closes. See
   `docs/TMOBILE_PRIVATE_KEY_REMEDIATION.md`. *(Critical/Security — risk accepted for PIT)*
2. **T-Mobile PIT callback authenticity (C2)** — ✅ app-layer auth now available
   (`FEATURE_TMOBILE_CALLBACK_AUTH`, default off): shared-secret token + optional
   enforced IP allowlist gate ingest. **Residual:** flag must be enabled with a
   provisioned token before any internet-exposed ingest; HMAC sig still pending
   T-Mobile spec. *(Safety/Security — mitigation built, enablement pending)*
3. **JWT in `localStorage`** — exposed to XSS token theft. *(Security)*
4. **CORS wildcard default + credentials** — safe in prod (explicit origins) but a
   foot-gun if the default ever ships. *(Security)*
5. **Thin CI** — only `pytest -q` + `vite build`; no lint, no frontend tests, no
   coverage gate, no dependency/security scan; `npm install` (not `npm ci`) →
   non-reproducible frontend builds. *(Reliability/Maintainability)*
6. **DB resilience unverified** — single starter Postgres; backup/PITR/restore-test
   cadence not confirmed. *(Reliability/Data integrity)*
7. **Feature-flag sprawl (~16) + per-service drift** — already bit prod once (PR #63).
8. **Demo seed on prod start command** — `python -m app.seed` runs every deploy
   (gated, but on the critical path).

## 6. Technical Debt (top items; full list in BACKLOG.md)

- Status-normalization logic exists on multiple axes — guard against drift.
- ~15 `audit_*`/`backfill_*` one-off modules in `app/` mixed with runtime code.
- No per-flag graduation/removal plan.
- Frontend has no automated test suite (build-only).

## 7. Recommendations (ranked by priority order)

1. **Secure the T-Mobile private key** and **add app-layer auth (or signed-token
   verification) to the PIT callback** — top of Safety+Security.
2. **Harden CI** — add lint, frontend smoke tests, a coverage floor, and a
   dependency/secret scan; switch to `npm ci`.
3. **Verify and rehearse DB backup/restore** — document RPO/RTO.
4. **Move JWT off `localStorage`** (httpOnly cookie or hardened storage) — larger
   change; plan it.
5. **Graduate Health Normalizer / LLLM soaks** per their runbooks once criteria met.
6. **Begin Assurance Engine backend MVP** (read-only, flag-off) — the product spine.

## 8. Next Actions (do these next, in order)

> **Rewritten 2026-08-11.** The prior list was stale: it named **PR-B1**
> (`INTERNAL_OPS` guard) and **PR-B2** (four `CUSTOMER_*` roles) as to-do, but
> both landed via PRs #142–#148 — `permissions.json` contains `INTERNAL_OPS` and
> `CUSTOMER_ADMIN/MANAGER/VIEWER/SUPPORT` today, and §0b describes the work.
> **PR-S1 (tenant-isolation fixes) was NOT re-verified** in this pass and is
> carried forward as unconfirmed.

**Engine track — unblocked by PR #180, do this first:**
1. **Merge PR #180** (Ops Center Phase 1.6 + the un-branched Alembic chain).
2. **Durable lifecycle-transaction persistence** — a migration chained off `052`.
   This was blocked on the migration fork and is now the highest-value unblocked
   engine task. It is step 2 of 5 toward taking the typed T-Mobile callback rules
   authoritative (see the typed-callback-shadow section above for the full order).

**T-Mobile track — blocked on operator inputs, not on code:**
3. Read-only PIT certification: **0 of 4 operations executed.** Needs a nominated
   PIT subscriber in `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST`, a known PIT
   transaction id, and PIT credentials in the executing environment
   (`is_configured` is false). Commands: `TMOBILE_READONLY_GO_LIVE_PLAN.md`.

**RH go-live track (`EPIC-RH-GO-LIVE`; see `BACKLOG.md` for the four-phase epic):**
4. **Verify PR-S1 tenant-isolation fixes** actually landed (H1 subscriber-import
   batch rows; L1/L2/L3 child-query tenant filters; M2 gate `/api/zoho/config`)
   per `RH_SECURITY_READINESS.md` §5 — confirm before treating Phase 1 as closed.
5. **Phase 2** RH data remediation (E911 42/42, device mapping 51/51, telemetry,
   service units) via Sivmey + Eng; **Phase 3** customer API gated behind it;
   **Phase 4** Judy onboarding + launch per `FEATURE_CUSTOMER_API_ROLLOUT.md`.
   The go-live gate is unchanged: fusion → sync queue → approve → enable the
   registry-view flags → verify the RH Test dashboard → **only then** Judy's
   invite. **Judy invite remains BLOCKED.**

**Housekeeping:**
6. Two stale open PRs need a decision: **#169** (gitleaks CI allowlist, open since
   2026-07-16) and **#166** (draft PoP fix, superseded by the reference contract
   in PR #170 — likely close).
7. **15 untracked docs** sit in `docs/` uncommitted (`OPERATIONS_CENTER.md`,
   `SUBSCRIBER_RESOLUTION.md`, `SUPPORT_CASE_SPINE.md`, the RH go-live set, …).
   They are a separate design thread from PR #180 and were deliberately left
   untracked; decide whether they land as a docs PR.

## 9. How to Resume

1. Read `docs/MISSION.md` (§3 priority order), this file, then `docs/BACKLOG.md`.
2. `git status` clean; identify branch.
3. Run the Operating Loop (`docs/OPERATING_LOOP.md`) for the chosen objective.
4. Verify with `cd api && python -m pytest -q` and `cd web && npm run build`.
5. Update this file before you stop.
