# True911+ — BACKLOG

> Living document. Categorized by urgency, then ranked within category by the
> **priority order in `CONSTITUTION.md` §3**. Last reviewed: 2026-09-30.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`. The
> standing "never build" vetoes are authoritative in `CONSTITUTION.md` §7
> (rationale in `ASSURANCE_PLATFORM_SPEC.md`). Entry point: `README.md`.
>
> This backlog is derived from the codebase audit. Items marked **Needs
> Verification** require confirming a fact before acting. Nothing here authorizes
> implementation — see `OPERATING_LOOP.md` §3 Hard Stops.

---

## 📥 Public acquisition — deferrals from the durable-acquisition PR (D-030..D-033) [2026-10-01]

Out of scope by decision in "Fix: Establish Durable Public Acquisition Foundation"
(see `ACQUISITION.md`):
- **A1. Conversion truth remediation (needs approval).** Conversion currently writes
  `Site.status="Connected"` and copies the prospect address into `e911_*`. Proposed fix
  in ACQUISITION.md §9; characterization tests in
  `api/tests/test_conversion_truth_characterization.py`.
- **A2. Internal acquisition review UI.** List/filter records and set `under_review` /
  `qualified` / `closed`. Today the read is API-only (`GET /api/acquisition/records`).
- **A3. Configure SMTP for internal notifications.** Production rows read
  `not_configured` until it is set. Operator step; do not invent configuration.
- **A4. Prospect acknowledgement email.** Design only. Must never claim to have been
  sent unless the transport accepted it.
- **A5. Zoho lead sync** as a recorded side effect. Not authorised yet.
- **A6. Shared rate limiter** (the current one is in-process per API instance).
- **A7. CAPTCHA review**, only if `acquisition_records` shows abuse.
- **A8. Analytics vendor.** The event boundary exists; no vendor is approved.
- **A9. Homepage redesign** on sanitized product proof (hero O1, "Product UI · Sample data").
- **A10. Remaining blanket claims outside the touched flow.** "NDAA-TAA Compliant" and
  "True911+" in the Reports/SyncStatus export footers; "True911+" in internal UI titles.
- **A12. Idempotent wizard create.** If the connection drops after the server
  commits but before the response arrives, the client has no id or token, and a
  retry creates a second draft. Fixing it needs a client idempotency key on create
  plus a safe resume-token re-issue (the key must not become a bearer credential
  stored in plaintext). Found by the failure-boundary hardening.
- **A13. Vendor 502 passthrough text.** Authenticated operator consoles (`vola`,
  `zoho_crm`, `carrier_verizon`, `sims`) return upstream error text in 502 bodies.
  It contains no SQL, but should be reviewed for URLs or credentials. Decide
  sanitize-and-log or keep for operator debugging.
- **A14. PUBLIC RATE-LIMIT CLIENT IDENTITY (deferred, split out of #199 on
  2026-10-02).** The current key is the first `X-Forwarded-For` entry. Honest
  browsers get a correct key, but a client can rotate it.
  - **Topology:** Cloudflare → Render load balancer → application. Render says to
    read `X-Forwarded-For`. Cloudflare appends the connecting client to an existing
    header.
  - **Still to establish:** what Render's load balancer appends, i.e. the
    trustworthy parsing boundary for our deployment. Ask Render support, or capture
    masked header shape with a flag-gated diagnostic.
  - **Constraints:** do NOT guess a hop count, and do not weaken or remove rate
    limiting. A Cloudflare-range-aware parser is one candidate design, not
    approved. See `ACQUISITION.md` §6a.
- **A11. Wizard billing/plan steps vs D-032.** The `/register` wizard still collects plan
  and billing fields. Align the assessment with "no billing in the assessment".

## 🗣️ Customer terminology / internal-language findings (D-028) [2026-10-01]

Found during the generic-terminology pass (branch `feat/customer-generic-terminology`).
These are data or follow-ups, deliberately NOT solved with presentation logic:
- **T1. `RESEARCH REQUIRED Gallery #653` — certification needed.** The customer name
  is built from `PortfolioBuilding.canonical_name`, which Fusion took from a source
  record name carrying an internal research flag. The flag is now stripped from the
  customer name ("Gallery #653"). The building still needs certifying (true name,
  city, address) under #189 building certification. The correct name was not
  invented.
- **T2. Category labels are RH-shaped in a generic serializer.**
  `serialize._BUILDING_CATEGORY_LABEL` maps `store`/`special` → "Gallery" and
  `portfolio_registry_view._CATEGORY` maps store/gallery/outlet → "Retail". Correct
  for RH today. It belongs in the future per-tenant vocabulary layer (`CUSTOMER_NOUNS`
  is the seam), not hard-coded for every customer.
- **T3. Stored activity summaries read like statuses.** `customer_activity_events.summary`
  stores "X requested" / "X: under review". The UI renders them past tense
  (`activityText`). If the API gains other consumers, render from `event_type` +
  request type server-side; stored rows are append-only and stay as written.
- **T4. Legacy Site-mode names rely on the render guard only.** Registry names are
  cleaned in `building_display_name`. Legacy `Site.site_name` names are cleaned only
  by `customerLocationName` in the web UI.
- **T5. `confidence` bucket ("Needs review") is in the customer API payload**
  (`portfolio_building`). It is not rendered today. Remove it or rename it before any
  UI shows it.
- **T6. Operational-state copy exists in two places** (`serialize.OPERATIONAL_STATES`
  and `selfService.js` `OPERATIONAL`, where the UNKNOWN states use the web copy).
  Keep them in step, or make the API keys-only.
- **T7. Location record still shows legacy per-location service / telephone counts.**
  The location record header ("2 monitored life-safety services · 2 telephone lines")
  and the location list API (`life_safety_services_count`, `phone_number_count`) still
  come from legacy service units and distinct numbers. That is how Gallery #653
  shows "Monitored · 0 life-safety services · 0 telephone lines". The Command Center
  (PR #194) shows no service or connection totals until the canonical inventory is
  certified (D-023). The location record must follow, with canonical services →
  required connections → assets, as part of the canonical location-record work. It was
  deliberately not changed in #194.

## 🗺️ RH map — coordinate source defects found during the basemap fix (D-027) [2026-10-01]

The basemap now renders (PR `fix/customer-basemap`). **RH mapping is NOT complete.**
Basemap availability and canonical location geocoding are separate concerns (D-027).
These are data-model items for **#190 (canonical geocoding)** / **#192 (one-marker map)**,
deliberately NOT patched in the frontend:
- **M1. Map point = first linked legacy Site, picked from an unordered set.**
  `portfolio_registry_view._map_point(b, linked)` returns the first linked `Site`
  with lat/lng. `linked` is built from `_resolve_building_site_ids()`, which returns a
  Python `set` of string site_ids, so the order depends on the process hash seed.
  When a building links Sites with different coordinates, the pin can move between
  API restarts/workers. `building_dispatch_address()` has the same
  first-of-unordered-set pattern for the dispatch address, which matters more because
  it is E911-adjacent. Fix: canonical approved coordinates on `PortfolioBuilding`
  (it has no lat/lng today), plus deterministic ordering until those exist.
- **M2. Registry `_map_point` does not validate coordinates.** Unlike
  `serialize._map_point` (range check, rejects 0,0), the registry path passes any
  non-null lat/lng. The frontend now refuses invalid points and counts them as "not
  shown", so they cannot crash Leaflet or appear as fabricated pins. The API should
  apply the same rule.
- **M3. Pending (unapproved) buildings can be plotted under the preview flag.**
  With `CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS` or
  `CUSTOMER_PORTFOLIO_PREVIEW_PENDING` on, pending buildings flow into
  `/customer/locations` and therefore onto the map. Intended for preview only.
  Confirm both flags are off for RH before any customer invite.
- **M4. 16 RH locations have no coordinates.** The notice is truthful. Resolve via
  certified address → approved geocode (#190), never by inference from name/ZIP/city.
- **M5 (minor UX).** The list↔map toggle unmounts and recreates the Leaflet map each
  time. Acceptable for now: it avoids hidden-container sizing bugs, and the refit is
  now signature-gated.

## ⭐ PRIMARY (RH) — RH Customer Completion Program: #187 → #193 [2026-09-30]

Program: `docs/customer/RH_COMPLETION_PROGRAM.md` (D-025). Do not invite Judy; do
not enable the canonical read model for her.
- **#187 (IN REVIEW):** source snapshot store + importers (D-024). After merge:
  import NAPCO, Infatrac/T-Mobile, Verizon exports (Red Pocket when available).
- **#188:** lifecycle + carrier reconciliation; preview Jacksonville decisions,
  record only with explicit operator authorisation.
- **#189:** building certification (Edina #159, Raleigh #178, Leawood, Beverly
  Modern / Hollywood, San Rafael, Memphis, Roseville / Dawsonville / Long Beach).
- **#190:** canonical geocoding (certified address first).
- **#191:** E911 completion + safety fixes; SUPER_ADMIN launch exceptions (max 30 days).
- **#192:** canonical customer read model + one-marker map (flag-gated).
- **#193:** RH Customer Acceptance Audit + RH Test (`test@manleysolutions.com`,
  verify in production first) + invite guard.

## (superseded by the program above) NEXT (RH) — Canonical service inventory: PR #186a review → production DRY-RUN → decisions → #186b [2026-09-30]

- **#186a (IN REVIEW, branch `feat/canonical-foundation`):** migration 054,
  canonical engine, operator-decision ledger, dry-run backfill, customer relabel
  of the false "28 connections". Merge only on explicit instruction.
- **After merge (read-only):** `python -m scripts.canonical_service_backfill
  --tenant restoration-hardware` on the Render api shell; review SOURCES
  (Zoho must be `ok`), MEMPHIS RECONCILIATION, findings and the watchlist
  (Edina #159, Raleigh #178, Leawood 119th St, San Rafael 20 Front St, Beverly
  Modern / Hollywood, Roseville / Dawsonville / Long Beach duplicates).
- **Operator decisions (external file, never committed):** Memphis
  BUILDING_IDENTITY_SUSPECT; Jacksonville CARRIER_MIGRATION (6 legacy
  DECOMMISSIONED, 7 CURRENT) + SERVICE_CLASSIFICATION Elevator 1 / Elevator 2.
  Preview with `--decisions-file`, record with `canonical_operator_decisions`.
- **Then, separately authorised:** first `--apply --confirm-tenant`.
- **#186b (NOT STARTED):** canonical customer read model behind
  `FEATURE_CANONICAL_SERVICE_MODEL` + tenant allowlist; only once the projection
  is approved for customer use. No Judy invite until then.

## ✅ DONE — QueryNetwork live PIT certified on a carrier-directed re-test [2026-09-30]

T-Mobile Engineering asked for a re-test after receiving the 09-01 trace ids;
one request returned HTTP 200 / `SUCCESS` / `100`. `query_network` is
`PIT_TESTED`, still `SINGLE_RUN_ONLY` (D-026, `TMOBILE_PIT_CERTIFICATION_20260930.md`).
Carrier question §4 resolved; questions §1–§3 remain — remove §4 from the draft
before sending. Lifecycle evidence is now an explicit per-operation declaration.

**Next T-Mobile step (not authorized by this work):** QuerySubscriberUsage — still
`MOCK_CERTIFIED`, never sent live; it needs its own deliberate one-shot grant and
inherits nothing from Network Profile. `query_transaction_status` stays blocked
on the `transactionId` question. Confirm the private evidence store survives a
redeploy.

## (historical) NEXT — Send the four carrier questions; QueryNetwork PIT is paused on the answer [2026-09-01]

**QueryNetwork was attempted once on 2026-09-01 and failed.** OAuth returned
HTTP 200; the resource request returned **HTTP 500 / `GENS-0005`**. It is **NOT
certified** and remains `MOCK_CERTIFIED`. There was no retry, no polling, no
Usage request, no mutation, and no ledger reconciliation from the failed read.
Record: `TMOBILE_PIT_CERTIFICATION_20260901.md`.

**The next action is a carrier question, not another request.** Re-attempting
with nothing changed is a retry with extra steps, and `GENS-0005` is generic
enough that a second identical result would teach us nothing.

1. **Send `TMOBILE_CARRIER_QUESTIONS_OPEN.md` — now four questions.** §4 asks
   whether the Network Profile endpoint is enabled for our partner in PIT,
   whether more provisioning is required, whether the supplied active test
   subscriber is valid for it, and whether anything is missing from our request.
   Drafted, **not sent**; sending is Stuart's action. Quote the correlation,
   work-flow, service-transaction and partner-transaction ids from the private
   evidence store — they are not in this repository.
2. **Archive the evidence bundle off Render.** It sits in `/tmp/pit-evidence/`
   and `~/tmobile-pit-evidence/` on the instance; **neither survives a
   redeploy** without a persistent disk. Not yet done.
3. **Then, and only then, decide about a second QueryNetwork attempt.**

**QuerySubscriberUsage stays unattempted.** It is still `MOCK_CERTIFIED` and has
never been sent live. Running it now would advance past an unclassified failure
— exactly what the harness's STOP guidance exists to prevent — and would leave
two uninterpreted results instead of one. Its authorization is independent: the
`query_network` grant never covered it.

When a run is eventually authorized, derive the ICCID inline from
`TMOBILE_PIT_READONLY_ICCID_ALLOWLIST` rather than a shell-local variable
(`TMOBILE_PIT_OPERATOR_RUNBOOK.md` §2c) — two attempts on 2026-09-01 reached the
explicit-subscriber gate with no selector because `$PIT_ICCID` did not survive
between copied command blocks. Nothing was sent; the gate held. Explicit
nomination is unchanged and there is still no default subscriber.

```powershell
cd api
python ../scripts/tmobile_pit.py query-network --iccid <PIT_ICCID>   # preview
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "true"
python ../scripts/tmobile_pit.py query-network --iccid <PIT_ICCID> `
    --execute --confirm-live --confirm-subscriber-approved --operator <you>
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "false"
```

One at a time, reconciling before advancing. Afterwards check
`state --iccid <ICCID>`: a successful read carrying a `subscriberStatus` also
reconciles the ledger, and a `CONFLICT` there is a stop condition. **The live
run must happen where PIT credentials, the read-only allowlist entry, and
`TMOBILE_PIT_LIVE_CALLS_ENABLED=true` all exist** — a workstation without them
is refused at the allowlist gate.

## ✅ RESOLVED — certification maturity is not send authorization [2026-08-28]

Readiness no longer authorizes anything. `SendAuthorization` is an explicit
per-operation declaration; maturity can veto a send and can never grant one;
`PRODUCTION` needs `PRODUCTION_APPROVED` and is still not a bypass; a
certification blocker outranks both. Enforced at import and pinned by
`test_tmobile_send_authorization_matrix.py` (63 tests).

`subscriber_inquiry` is consequently promoted to `PIT_TESTED` on its real
2026-08-28 evidence **and remains not generally sendable**. Detail:
`TMOBILE_PIT_CERTIFICATION_20260828.md` §5.3.

Follow-on, not urgent: nothing is `PRODUCTION_APPROVED` yet, so the `PRODUCTION`
authorization tier is declared and tested but unused. Promoting anything to it
is a separate decision with its own evidence bar.

## ⛔ BLOCKED ON A CARRIER ANSWER — QueryTransactionStatus [2026-08-28]

Not merely un-run: the harness now **refuses to issue a single-run grant** for
it. `transactionId` could be any of the four identifiers our activation
returned, and a wrong id returns "not found" exactly as a correct id does for an
expired transaction — the run would be uninterpretable either way.

Send question 1 of `TMOBILE_CARRIER_QUESTIONS_OPEN.md` (drafted, **not sent**).
Unblocking is: record the written answer, clear `certification_blockers` in
`app/integrations/tmobile_operations.py`, pin the contract with a test.

**Unchanged by the 2026-09-01 failure.** That 500 returned four carrier trace
identifiers, and none has been confirmed as the `transactionId` this operation
expects. Seeing more identifiers is not an answer, and the blocker outranks both
maturity and any one-shot grant. Pinned by
`test_tmobile_pit_network_failure.py::TestTransactionStatusStaysBlocked`.

**Downstream, still blocked until more real responses exist:**
carrier-observation persistence, the internal super-admin view, the manual sync
control, and the filled certification report for T-Mobile.

## 🔗 BLOCKED — Promote typed callback rules to authoritative

Wired in shadow mode (default off). Cannot become authoritative until, in order:

1. **Un-branch the Alembic chain** — two heads currently share `049`
   (`050` untracked Ops Center work, `051` committed). Needs an owner decision.
2. **Persist lifecycle transactions** (`LifecycleTransaction` has no ORM model).
3. **Create transactions on the operator path**, so callbacks have something to
   correlate against.
4. **Review the recorded agreement rate** from a shadow soak.

Only then flip the rules to authoritative. Doing it earlier stops device
liveness promotion.

## ✅ DONE — Execute the read-only PIT inquiry [2026-08-28]

Executed against a carrier-confirmed `Active` line: HTTP 200, `status: SUCCESS`,
result `100`, `subscriberStatus: Active`. One request, no retry, no polling, no
mutation; the single-run grant was consumed and cleared. Record:
`TMOBILE_PIT_CERTIFICATION_20260828.md`.

Still open from this step: reconcile the observed shape against
`tests/fixtures/tmobile_subscriber_inquiry_shapes.json` (fabricated, and now
*checkable* against a real response). The readiness question is settled — the
registry now reads `PIT_TESTED`, and the operation is still not generally
sendable.

If the operator host still holds the 2026-08-28 evidence bundle, settle the
ledger from it rather than resending:
`python ../scripts/tmobile_pit.py reconcile --iccid <ICCID> --evidence <bundle>.json`.
If the bundle is gone (ephemeral `/tmp`), leave the ledger alone and take the
carrier state from the certification record — **do not resend an activation or
an inquiry to rebuild a local file.**

**After that:** QueryNetwork and QuerySubscriberUsage, using the same single-run
mechanism — see the NEXT item above.

## ✅ SUPERSEDED — T-Mobile read-only PIT certification [2026-07-21]

The typed contract and lifecycle foundation is merged-ready. The next task is
the first supervised live read.

**Scope:** `SubscriberInquiry` only, against one explicitly nominated subscriber,
operator-approved, preview first, single request, no bulk mode, no scheduler.
Advance its readiness only on real evidence.

**Prerequisites:** confirm the read-only allowlist tier names the target SIM;
confirm the operator gates; keep `TMOBILE_PIT_LIVE_CALLS_ENABLED` closed except
for the single supervised run.

**Also open:** durable persistence for lifecycle transactions is deferred until
the alembic chain is un-branched (two revisions currently share a parent, one
uncommitted). Callback correlation gaps from the earlier review are now addressed
in the typed layer but not yet wired into the live ingest path.

## ✅ RESOLVED — T-Mobile contract obtained and reconciled [2026-07-21]

Authorized vendor documentation obtained and reviewed privately
(`TMO-REST-RECON-001`). Implementation corrected: seven wrong paths, four wrong
HTTP methods, every lifecycle request body wrong. All eight non-activation
operations **remain live-blocked** — documentation is not authorization.

**Next:** the read-only operations are the cheapest to certify. Each still needs
a supervised PIT run before its readiness can advance. Callback correlation gaps
are unchanged (`TMOBILE_CALLBACK_CERTIFICATION.md`), and machine-readable API
definitions are still worth obtaining for automated structural validation.

Confidential vendor material is not committed to this public repository; the
detailed records are in the operator's private evidence store.

## 🔴 URGENT — T-Mobile: 7 of 8 operations blocked, no supplied contract [2026-07-21]

> **SUPERSEDED the same day** by the entry above.

T-Mobile authorized "other API calls to complete your development and testing
cycle." A provenance audit found **no T-Mobile OpenAPI spec, Postman collection,
or written contract in this repository**. Seven of eight wholesale paths are
derived by our own string join — and that derivation is **provably wrong**
(activation works at `/activation`; the derivation yields `/activate`).

Those seven are now **BLOCKED** by `app/integrations/tmobile_operations.py`.
Blocked ≠ broken — they stay implemented and mock-tested. Unblocking requires a
T-Mobile-supplied contract recorded here plus a reviewed provenance change;
**config cannot lift it**.

### Next action — a documentation request, not an API call

1. `python ../scripts/tmobile_pit.py show <operation>` for each of the seven →
   send T-Mobile the exact question list (8 standard + operation-specific).
   Priority order: `subscriber_inquiry` (unblocks status verification),
   `suspend`/`restore` (the reversible lifecycle pair), then `deactivate`.
2. Also ask: the **full activation result-code vocabulary** (we have only ever
   seen `100`), and whether an activation callback should have fired for
   `true911-pit-d1475fec-…` on 2026-07-21.

### Ready to run today (no network, no state change)

`python ../scripts/tmobile_callback_inspect.py --iccid <ICCID> --partner-transaction-id <ptx>`
— settles the outstanding callback question from the activation closeout.

### Callback certification — 6 of 10 properties met

Gaps, in dependency order (`TMOBILE_CALLBACK_CERTIFICATION.md`): **transaction-id
correlation** (nothing ties a callback to the request that caused it) → then
**replay dedupe inside the window**, **quarantine of unknown callbacks**, and
**job idempotency keys**. Do not implement these by guessing which id T-Mobile
echoes back — confirm the callback payload schema first.

Harness, allowlists, state machine, and 85 new tests are on
`feat/tmobile-pit-api-certification-harness` — **PR open, NOT merged**. No live
call was made.

---

## ✅ CLOSED — T-Mobile PIT activation succeeded [2026-07-21]

> **Supersedes** "🔴 URGENT — T-Mobile PIT: BLOCKED on Partner Foundation ID
> [2026-07-16]". The historical record is preserved in
> `TMOBILE_PIT_ACTIVATION_PAYLOAD.md`; the hypotheses below are marked closed,
> not deleted.

**`POST /wholesale/v1/subscriber/activation` → HTTP 201 · `status=SUCCESS` ·
result code `100`**, `2026-07-21T03:18:33.694749Z`, deployed commit `1766f51`.
MSISDN assigned, account ID generated. Details:
`TMOBILE_PIT_ACTIVATION_PAYLOAD.md` · operator identifiers:
`TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md`.

Resolved by T-Mobile gateway configuration recreation. The available evidence
indicates the client request contract was valid at the time of the successful
activation, and no additional Partner Foundation header was required. Exact
internal T-Mobile root cause is not independently observable from the client.

### Hypotheses closed by this evidence

| Was believed | Now |
|---|---|
| Partner Foundation ID is required | **No** — never configured, never sent, activation succeeded. Config stays **inert**; wiring it remains a deliberate code change if T-Mobile ever asks. |
| The PoP contract is unverified | **Verified** — the supplied reference contract was accepted. |
| `sender-id` transmission is unverified | **Verified** — sent unsigned on both the token and resource calls, accepted. |
| GENS-0003 is active / blocking | **Closed.** |
| `senderId` / `channelId` absent from the access token blocks activation | **Not blocking** — activation succeeded regardless. Whether the claims are now present is still unconfirmed and no longer worth a live cycle to find out; `--token-only` reports it for free if ever needed. |

The "never guess a header name" rule (#165 PoP claims, #167 signed `sender-id`,
#168 `Content-Type;uri;http-method` — each plausible, each cost a live PIT cycle)
**still stands** and is now doubly justified: none of them was the cause.

### ⚠️ Open — carried forward from this success

1. **Callback verification — UNVERIFIED.** No callback confirmed for the
   successful activation; the account ID was recovered from the **synchronous
   201 body**. Run the read-only inspector (SELECT only, no network call):
   `python ../scripts/tmobile_callback_inspect.py --iccid <ICCID> --partner-transaction-id <id> --work-flow-id <id>`
2. **Subscriber status — UNVERIFIED.** `scripts/tmobile_subscriber_status.py`
   (SubscriberInquiry + NetworkQuery, `--confirm-read-only`) has not been run.
3. **Synchronous activations persist nothing** — `tmobile_callback_processor`
   writes `sims.meta` only on the callback path.
4. **Destructive lifecycle methods are ungated** — `suspend_subscriber`,
   `restore_subscriber`, `deactivate_subscriber` have no `live_calls_enabled`
   check, unlike `activate_subscriber`. Highest-risk open item.
5. **19 of 20 production gates remain open** —
   `TMOBILE_PRODUCTION_READINESS.md` is the authoritative list (replay
   protection, idempotency, reconciliation, pilot ICCID allowlist, monitoring,
   operator RBAC, key rotation).

⛔ **Do not re-activate the PIT ICCID and do not modify the activated line.**

---

## ⭐ PRIMARY OBJECTIVE — EPIC-RH-GO-LIVE (RH Customer Go-Live)

> **The current top business objective:** place **Restoration Hardware (Judy)** into
> production as the first customer **actively using True911 every week**, scoped to
> **assurance + support** (billing/QuickBooks/invoicing deferred). Planning is
> **complete** (design done, nothing implemented). Authoritative design docs:
> `RH_PRODUCTION_GO_LIVE.md`, `RH_GO_LIVE_EXECUTION_PLAN.md`, `RH_SECURITY_READINESS.md`,
> `RH_ROLE_MATRIX.md`, `CUSTOMER_EXPERIENCE_BOUNDARY.md`, `CUSTOMER_DATA_BOUNDARY.md`,
> `CUSTOMER_API_CONTRACTS.md`, `FEATURE_CUSTOMER_API_ROLLOUT.md`.
>
> **Reprioritization (this review):** all `EPIC-RH-GO-LIVE` work ranks **ahead of the
> PRODUCT EXPERIENCE (PE) epics and all future platform initiatives.** The Constitution
> sequencing rule still holds — Phase 1 **is** the Track-A foundation (isolation/RBAC)
> that gates customer exposure; no customer surface (Phase 3) ships before Phase 2's
> E911 data sweep. **Status recorded:** customer boundary architecture complete · tenant
> isolation audited (no CRITICAL) · customer RBAC design complete · customer API contract
> design complete · `FEATURE_CUSTOMER_API` rollout design complete.

### Phase 1 — Foundation (gates Judy's credentials; smallest-safe-slice, additive)
- **RH-P1.1 — Tenant-isolation fixes (PR-S1).** H1 (`/subscriber-import/batches/{id}/rows`
  tenant scope), L1 (`/sites/{id}/infrastructure` child filter), L2 (`/devices/{id}/sims`
  filter), L3 (vendor-name lookups), M2 (gate `/api/zoho/config`). Per
  `RH_SECURITY_READINESS.md` §5. *Security / Safety.*
- **RH-P1.2 — `INTERNAL_OPS` guard (PR-B1).** Add `INTERNAL_OPS` (granted to all six
  existing roles → behavior-preserving) to every bare-`get_current_user` internal GET so
  customers are excluded. No-regression test gate. *Security.*
- **RH-P1.3 — `CUSTOMER_ADMIN` + customer roles (PR-B2).** Add `CUSTOMER_ADMIN`,
  `CUSTOMER_USER`, `CUSTOMER_BILLING`, `CUSTOMER_READONLY` + `CUSTOMER_*` perms to
  `permissions.json`; Bucket-B customer guards. Per `CUSTOMER_EXPERIENCE_BOUNDARY.md`. *Security / CX.*

### Phase 2 — RH Data Remediation (parallel; Sivmey proposes, Eng applies, Stuart approves)
- **RH-P2.1 — E911 verification.** 42/42 RH sites `address_complete_needs_validation →
  validated`, evidence captured (PR #80, dry-run-first). *Safety. Gating.*
- **RH-P2.2 — Device mapping.** 51/51 devices → vendor adapters + keyed identifiers (PR #81).
- **RH-P2.3 — Telemetry enablement.** Heartbeat/health sync so `last_heartbeat` populates (PR #82).
- **RH-P2.4 — Service-unit creation.** ~51 emergency service units from install data (PR #83).
- **RH-P2.5 — Re-audit.** Confirm Health Score 30 → ~80+; 0 active sites Critical-for-unverified-E911 (PR #84).

### Phase 3 — Customer API (gated behind Phase 1 + Phase 2; `FEATURE_CUSTOMER_API` off)
- **RH-P3.1 — Serializer + namespace (PR-C1/C2).** Allow-list customer serializer +
  read-only `/api/customer/*` (double-gated 404-off). *Per `CUSTOMER_API_CONTRACTS.md`.*
- **RH-P3.2 — Dashboard / Morning Test** (`/api/customer/dashboard`).
- **RH-P3.3 — Locations** (list + detail).
- **RH-P3.4 — E911 summary** (read-only; correction-request is request-only, Manley-gated).
- **RH-P3.5 — Support** (read + create; `customer_safe_summary` only).
- **RH-P3.6 — Billing visibility** (read-only MRR/MRC over existing data).
- **RH-P3.7 — Reports** (portfolio JSON + PDF); + frontend PR-F1…F8 (customer nav + pages).

### Phase 3.5 — RH Login Preview (IMPLEMENTED, flag-gated OFF; urgent go-live)
- **RH-P3.5-PREVIEW — Active/Green operational preview.** ✅ *Implemented.* A
  tenant-scoped **preview mode** presents the customer **operational axis**
  (location · service · device protection + equipment health) as **Protected/Online**
  so RH (Judy) can be given a login **before** carrier/vendor telemetry is live.
  - Two-key gate: `FEATURE_CUSTOMER_PREVIEW` + `CUSTOMER_PREVIEW_TENANT_ALLOWLIST`
    (default OFF; mirrors `FEATURE_CUSTOMER_API`). Set both on api **and** worker.
  - **Presentation-only:** no raw `Device`/`Site`/vendor state overwritten;
    internal/admin/assurance views unchanged. Green carries an honest
    **operator-attestation** evidence signal (not fabricated telemetry); no
    "API/telemetry pending" labels reach the customer.
  - **E911 excluded (life-safety):** `verified` true only when stored `e911_status`
    is verified; active+unverified = Critical. Customer E911 record enumerates real
    per-endpoint detail (unit/floor, callback/BTN/line id, service type) from
    `ServiceUnit` + linked `Line.did`/`Device.msisdn` — "where applicable", never faked.
  - **Internal correction worklist:** `GET /api/e911-changes/gaps` (`UPDATE_E911`).
  - **Rollback:** flip `FEATURE_CUSTOMER_PREVIEW=false` or drop RH from the allowlist
    → instant, no deploy/migration; RH sees real assurance labels again.
  - Code: `services/customer/preview.py`, `services/e911_gaps.py`,
    `services/customer/{portfolio,serialize}.py`, `routers/{customer,e911}.py`,
    `config.py`. Tests: `tests/test_rh_customer_preview.py`. Docs:
    `CUSTOMER_EXPERIENCE_BOUNDARY.md` §F, `CUSTOMER_DATA_BOUNDARY.md` §6a.
  - **Follow-up:** preview is a bridge — retire it per location as Track-A telemetry
    lands and real assurance evidence supersedes the operator attestation.
- **RH-P3.5-GOLIVE — Customer login wired to /api/customer (Judy = CUSTOMER_ADMIN).**
  ✅ *Implemented 2026-07-01 (D-016).* The isolated customer plane is wired end-to-end:
  - RBAC: `CUSTOMER_*` granted VIEW_SITES/DEVICES/ASSURANCE (customer pages) + new
    roles `CUSTOMER_MANAGER/VIEWER/SUPPORT`; still no INTERNAL_OPS/COMMAND_*.
  - Frontend: `UserDashboard` customer branch → `CustomerAssuranceView` reads
    `/api/customer/dashboard|locations|…/e911` (preview-green + real E911, no
    pending language); 8 internal pages gated behind INTERNAL_OPS.
  - Provisioning: `admin.py` invite accepts `CUSTOMER_*`; script
    `scripts/create_customer_user.py`. Readiness: `scripts/rh_customer_readiness_check.py`.
  - Docs: `docs/customer/ASSURANCE_ENGINE.md`, `docs/customer/RH_GO_LIVE_RUNBOOK.md`,
    DECISIONS D-016. Tests: `test_customer_rbac_posture.py`, `test_rh_readiness_check.py`
    (full suite green, 3623; web build green).
  - **Remaining ops step:** set the 4 env vars on api+worker, create Judy, run the
    readiness check, verify login (runbook). E911 gaps stay blockers to clean READY.

### Phase 3.6 — Customer Command Center (IMPLEMENTED, Phase 1; additive)
- **RH-P3.6-CC — Enterprise Life-Safety command center.** ✅ *Implemented 2026-07-01.*
  Service-first dashboard (Enterprise→Portfolio→Location→Service→Equipment→Carrier):
  executive metrics + evidence-graded health, zoom-to-fit map w/ legend + list↔map
  sync, enterprise search, and a Location Command Center drawer (Overview · Life
  Safety Services w/ grouped equipment · E911 + history · Timeline · Documents/
  Billing/Notes placeholders). Service-first nav with "Soon" items.
  - New APIs: `/customer/portfolio/summary|health`, `/customer/search`,
    `/customer/locations/{ref}/services|timeline` (additive, CUSTOMER_* guarded).
    Code: `services/customer/command_center.py`, `serialize.py`,
    `components/customer/{CustomerAssuranceView,LocationCommandCenter}.jsx`.
    Tests: `test_customer_command_center.py` (suite green 3644; web build green).
  - Doc: `docs/customer/CUSTOMER_COMMAND_CENTER.md`.
  - **Roadmap:** marker clustering (`leaflet.markercluster`), Reports pages+CSV/PDF
    export, Documents/Billing integrations, timeline event types (install/service/
    inspection/carrier), store#/per-location health, AI confidence scoring.

### Phase 3.7 — Location Digital Twin (IMPLEMENTED; additive)
- **RH-P3.7-DT — Every location a complete operational record.** ✅ *Implemented 2026-07-01.*
  Location Workspace (Overview · Digital Twin Health · Life Safety Services w/ grouped
  equipment + service facts · Equipment · E911 · Documents · Photos · Inspection History ·
  Recent Activity · Site Contacts · Emergency Procedures · Service Requests · Billing ·
  Notes) with breadcrumb + permanent `?location=<ref>` shareable deep-link.
  - New APIs (CUSTOMER_VIEW_LOCATIONS, additive): `/locations/{ref}/documents|photos|
    contacts|inspections|health`; enriched service model (carrier name, phone numbers,
    equipment count, last test/inspection, attention items). Code:
    `command_center.py`, `serialize.py`, `components/customer/{LocationCommandCenter,
    CustomerAssuranceView}.jsx`. Tests: `test_location_digital_twin.py` (suite green 3656).
  - Doc: `docs/customer/LOCATION_DIGITAL_TWIN.md`.
  - **Roadmap:** documents/photos storage (signed URLs), timeline event sources,
    real inspection ingest, health inputs (service requests/alarm tests/carrier/AI),
    Service Requests/Emergency Procedures/Billing integrations, Vitest runner.

### Phase 3.8 — Life Safety Service Intelligence (IMPLEMENTED; additive)
- **RH-P3.8-SVC — Equipment → Life Safety Services.** ✅ *Implemented 2026-07-01.*
  Inference engine classifies equipment into first-class services (Fire Alarm,
  Elevator, Area of Refuge, Emergency Phone, BDA/DAS, Generator Monitoring, Mass
  Notification, Burglar Alarm) with confidence; groups multi-device services;
  location & portfolio health derive from **service** health. New
  `/customer/portfolio/services`; internal approve/override/merge/split
  (`MANAGE_SERVICE_CLASSIFICATION`, append-only ActionAudit, CUSTOMER_* isolated).
  Code: `services/customer/service_inference.py`, `services/service_classification.py`,
  `routers/service_classification.py`, `command_center.py`, `serialize.service_card`.
  Tests: `test_service_inference.py` (suite green 3690). Doc:
  `docs/customer/LIFE_SAFETY_SERVICE_MODEL.md`.
  - **Roadmap:** override→ServiceUnit promotion, richer rules (vendor/customer
    metadata), real last-test/inspection sources, per-service history, AI-assisted
    confidence, merge/split UI in the internal console.

### Phase 3.9 — Customer E911 confirmation & correction (IMPLEMENTED; additive)
- **RH-P3.9-E911REVIEW — Customers validate E911 without owning it.** ✅ *Implemented 2026-07-01.*
  CUSTOMER_* users **confirm** or **request a correction** to the emergency record;
  Manley operators review/approve/reject. Never overwrites official E911; append-only
  audited (ActionAudit; migration-free). Endpoints: `POST /customer/locations/{ref}/
  e911/confirm|correction-request`, `GET …/e911/review-status`; internal
  `GET /api/e911-changes/reviews`, `POST …/reviews/{id}/approve|reject`.
  RBAC: submit = new `CUSTOMER_SUBMIT_E911_REVIEW` (ADMIN/MANAGER/SUPPORT/USER;
  read-only roles view only); review = `UPDATE_E911` OR `MANAGE_SERVICE_CLASSIFICATION`.
  Code: `services/e911_review.py`, `routers/customer.py`, `routers/e911.py`,
  `dependencies.require_any_permission`, `LocationCommandCenter.jsx`. Tests:
  `test_e911_review.py` (suite green 3716). Doc:
  `docs/customer/E911_CUSTOMER_REVIEW_WORKFLOW.md`.
  - **Roadmap:** approved-correction → E911ChangeLog draft; decision notifications;
    per-review internal detail view.

### Phase 3.10 — Collaborative Building Workspace (IN PROGRESS; branch `feat/building-workspace`, PR open, additive)
- **RH-P3.10-WORKSPACE — Location Digital Twin → collaborative Building Workspace.** 🔧 *PR open 2026-07-01, not merged.*
  Refines the customer experience (no architecture/API redesign). Reorganised into
  four workspaces (Building Summary · Operations · Compliance · Administration);
  **services primary**, equipment de-emphasised. New **contribution workflow**
  (append-only `customer_contribution` ActionAudit; contact/inspection/photo/
  document/procedure/note/service_request) — never writes protected data; endpoints
  `POST|GET /customer/locations/{ref}/contributions`; new perm `CUSTOMER_CONTRIBUTE`
  (ADMIN/MANAGER/SUPPORT/USER). **Separated health** (4 factors, composite after) +
  **maturity tier** (Bronze/Silver/Gold/Platinum, 7 dimensions). Full **de-branding**
  of the customer plane (neutral status vocabulary). Code: `services/customer/
  contributions.py`, `serialize.{separated_health,building_maturity}`,
  `command_center.load_location_health`, `routers/customer.py`, `permissions.json`,
  `LocationCommandCenter.jsx`. Tests: `test_customer_contributions.py`. Docs:
  `customer/{WORKFLOW_ENGINE,DIGITAL_TWIN_MATURITY_MODEL,LOCATION_DIGITAL_TWIN}.md`.
  - **Roadmap:** operator review queue for contributions; real blob storage for
    photo/document/procedure uploads; approved contribution → applied record.

### Phase 3.11 — RH Portfolio Certification Wizard (IN PROGRESS; branch `feat/rh-portfolio-certification`, PR open, read-only)
- **RH-P3.11-CERTIFY — Certify the full RH portfolio before Judy's invite.** 🔧 *PR open 2026-07-01, not merged.*
  Read-only go-live gate. `api/scripts/rh_portfolio_certification.py` takes the latest
  Zoho subscription CSV export as the immediate source of truth, detects all RH rows
  (aliases + weird labels: guest houses, warehouses, outlets, galleries, MDC,
  corporate/special), normalizes each into a **canonical portfolio record** (store#,
  site_type, address, phones, device ids, confidence, manual_review), groups device
  rows into canonical locations, reads True911 prod (sites/devices/units/lines/E911),
  **matches** by store#/address/city-state-zip/phone/device-id/name, and **classifies
  A–L**. Emits CSV+JSON+MD with a **PASS/CONDITIONAL/BLOCKED** verdict, top-25 issues,
  and an operator punch list. Read-only (never writes Zoho/True911, never marks E911
  verified, never fabricates). Blocking gates C/F/I/J/K must reach 0. Tests:
  `test_rh_portfolio_certification.py`. Docs: `customer/RH_PORTFOLIO_CERTIFICATION.md`,
  `RH_GO_LIVE_RUNBOOK.md` §4b. **Dry run (2026-07-01 export):** 377 rows → 70 RH → 44
  canonical locations (20 manual-review). Live match runs on Render.
  - **Roadmap:** approved punch-list items feed the existing controlled create/update
    flows; re-run to confirm PASS before the invite is sent.
  - ✅ **v1 base wizard merged** (PR #155, `1712d17`); **v1.1 live Zoho mode merged**
    (PR #156, `3b0b374`); **page_token pagination hotfix merged** (PR #157, `d9f3b7a`).

### Phase 3.12 — RH Certification v2: known special-location registry (IN PROGRESS; branch `feat/rh-cert-known-locations`, PR open, read-only)
- **RH-P3.12-KNOWN — Treat operator-confirmed RH specials as legitimate.** 🔧 *PR open 2026-07-01, not merged.*
  Adds `KNOWN_RH_LOCATIONS` (Greenwich 265, RHNYC, Beverly Modern, Patterson
  Warehouse, MDC, Linden House): each canonicalized with a definitive site_type
  (special/gallery/warehouse/distribution_center), counted as a real RH location, and
  **no longer flagged "weird RH label"** — still checked for missing/address/dup/
  device/service-unit/E911. Matching: known-alias recognition is a positive
  high-precision signal (bumps confidence, strong-match when the alias is in the
  True911 site name); name matching ignores the generic "Restoration Hardware" tokens
  and won't force a match on a bare short city token, so **RHNYC doesn't overmatch a
  generic NYC record**. Report adds a **"Known special RH locations"** section +
  `known_special_locations` count. Read-only; no auto-create; E911 never verified.
  Tests: `test_rh_portfolio_certification.py` (42). **Dry run (2026-07-01 export):**
  manual-review canonicals drop 20 → 14; 6 specials now recognized. Docs:
  `customer/RH_PORTFOLIO_CERTIFICATION.md` §3a, `RH_GO_LIVE_RUNBOOK.md` §4b.
  - **Roadmap:** add further confirmed specials to the registry as the operator
    validates them.

### Phase 3.13 — Portfolio Fusion Engine (IN PROGRESS; branch `feat/portfolio-fusion-engine`, PR open, read-only)
- **RH-P3.13-FUSION — Fuse four sources into one Building Digital Twin.** 🔧 *PR open 2026-07-01, not merged.*
  `api/scripts/rh_portfolio_fusion.py` extends the certification engine into a
  multi-source fusion engine over **Zoho CRM · Napco StarLink · T-Mobile Genesis
  (MS130v4) · True911**. Four read-only adapters (Zoho reuses cert CSV/live; Napco
  reuses `inventory_reconciliation.adapters.napco`; Genesis = tolerant MS130 CSV +
  read-only API stub; True911 reuses `cert.load_true911`) → normalized SourceRecords.
  **Entity resolution** clusters records into buildings by store#/address/device-id
  (radio#/IMEI/ICCID/MSISDN/StarLink/serial); device rows merge by shared identifier.
  Emits a **Building Digital Twin** (building · services · devices · E911 · source
  confidence [True911 40/Zoho 25/Napco 20/Genesis 15] · missing assets · duplicate
  assets) and a **Building Fusion Report** in CSV/JSON/Markdown + an executive
  dashboard (buildings, fully-fused-all-4, per-source coverage, category mix, gaps).
  Read-only — never writes any source, E911 never verified, nothing fabricated;
  Napco sensitive fields dropped. Tests: `test_rh_portfolio_fusion.py` (19). Docs:
  `customer/PORTFOLIO_FUSION_ENGINE.md`, `RH_GO_LIVE_RUNBOOK.md` §4c.
  - **Roadmap:** live Genesis pull from a seed ICCID list via TAAP; feed fused gaps
    into the operator punch list; graph view of source coverage per building.
  - ✅ **Merged**: engine (#159), Genesis RH filter (#160), Napco RH filter + over-split (#161).

### Phase 3.14 — Portfolio Registry & Persistent Digital Twin (IN PROGRESS; branch `feat/portfolio-registry`, PR open)
- **RH-P3.14-REGISTRY — Persistent Portfolio Registry powering the Digital Twin.** 🔧 *PR open 2026-07-02, not merged.*
  Evolves the Fusion Engine from rediscovery to reconciliation against an operator-
  approved registry. New tables (migration 051): `portfolio_buildings`,
  `portfolio_aliases`, `portfolio_device_mappings` (kind ∈ napco_radio/genesis_msisdn/
  iccid/imei/phone/true911_device/zoho_account), `portfolio_review_items`. Service
  `app/services/portfolio_registry.py`: read-only `load_registry`, pure `reconcile`
  (approved mappings **before** heuristics: device → alias → store# → address; else a
  review item — new_building/possible_merge/duplicate_building/address_conflict/
  device_conflict/unknown_alias), and the approval workflow (approve_new_building/
  approve_alias/approve_device_mapping/reject_review_item/sync_review_queue) as the ONLY
  registry writers. `fuse_portfolio(registry=)` tags each building known/new/ambiguous
  and reports Portfolio Buildings/Known Aliases/Pending Review/Approved Mappings/
  Rejected Suggestions/Coverage by Source/Confidence Distribution + review-queue section.
  Read-only (never writes sources or the registry; E911 never verified). Tests:
  `test_portfolio_registry.py` (16) + fusion integration. Docs:
  `customer/PORTFOLIO_REGISTRY.md`, `PORTFOLIO_FUSION_ENGINE.md` §7,
  `LOCATION_DIGITAL_TWIN.md` §10, `RH_GO_LIVE_RUNBOOK.md` §4d.
  - **Roadmap:** operator UI for the review queue; auto-suggest aliases/mappings with
    confidence; registry-backed customer Digital Twin read path.
  - ✅ **Merged** (PR #162, `5638595`).

### Phase 3.15 — Customer dashboard → Portfolio Registry integration (IN PROGRESS; branch `feat/customer-portfolio-registry-view`, PR open)
- **RH-P3.15-CUSTVIEW — Render the customer view from canonical PortfolioBuildings.** 🔧 *PR open 2026-07-02, not merged.*
  Moves the RH dashboard + Location/Building Workspace from raw `Site` rows to canonical
  buildings (fixes stale 42/42 vs 56 canonical, and 0-services / 0-health KPIs).
  Additive, read-only, flag-gated OFF. New flags: `FEATURE_CUSTOMER_PORTFOLIO_REGISTRY`
  + `CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST`, `CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS`,
  `CUSTOMER_PORTFOLIO_PREVIEW_PENDING` + `CUSTOMER_PORTFOLIO_PREVIEW_TENANT_ALLOWLIST`.
  Customer-safe `serialize.portfolio_building` (confidence bucket; no Zoho/Napco/Genesis/
  ICCID/IMEI/alias/review internals); read model `services/customer/portfolio_registry_view.py`
  (approved+pending buildings → linked True911 sites → derived services/E911/health;
  legacy fallback when off/empty). Endpoints (dashboard/summary/health/services/locations/
  {ref}/services/health/search) render from the registry when enabled; `resolve_site`
  accepts `bldg` refs. Pending policy (approved visible; pending behind flag; calm
  "Portfolio record being finalized"). UI normalizes to building_ref/display_name; no
  source terms leak; Vite build green. Audit `scripts/customer_registry_view_audit.py`.
  Read-only — no registry/source writes, no auto-created Sites, no E911 auto-verify, no
  Judy invite. Tests: `test_customer_portfolio_registry_view.py` (12); full suite 3880.
  Docs: `CUSTOMER_COMMAND_CENTER.md` §8e, `LOCATION_DIGITAL_TWIN.md` §10,
  `RH_GO_LIVE_RUNBOOK.md` §4e.
  - **Roadmap:** internal approval UI to materialize + approve the 56 candidates;
    registry-backed e911/timeline sub-resources; per-building contribution counts.

### Phase 3.16 — RH registry approval operator script (IN PROGRESS; branch `feat/rh-registry-approve`, PR open)
- **RH-P3.16-APPROVE — Approve reviewed candidates into buildings.** 🔧 *PR open 2026-07-02, not merged.*
  `api/scripts/rh_registry_approve_from_review.py` converts pending `PortfolioReviewItem`
  rows into approved `PortfolioBuilding` rows (flips RH from fallback_mode → registry_mode).
  Applies the operator decision table (`--include-known-rh-decisions`): canonical
  overrides + merges (Hollywood, Chicago #147, Beverly Modern, Austin #149, Princeton
  #644, Linden/MDC/Patterson/RHNYC/Memphis…), parent-account exclusion, keep-separate
  guard (Edina #159 / Raleigh #178). Creates aliases + device mappings (collision-safe)
  and decides review items via `approve_new_building`. Flags: `--dry-run` (default) /
  `--apply` / `--limit` / `--only-high-confidence`. Report: created/merged/excluded/
  skipped/unresolved + before/after visible count. Writes ONLY the registry under
  `--apply`; never Site/Device/E911/Zoho/Napco/Genesis; E911 never verified. Tests:
  `test_rh_registry_approve_from_review.py` (13). Docs: `RH_GO_LIVE_RUNBOOK.md` §4e step 3.

### Phase 3.17 — Customer Operations Console / self-service (IN REVIEW; branch `feat/rh-customer-self-service`, PR open)
- **RH-P3.17-SELF-SERVICE — Customer-owned layer + governed requests + E911 attestation.**
  Overlay for contacts/notes/connection labels; `CustomerServiceRequest` lifecycle;
  E911 self-service states (never self-certified); Action Center; internal queue
  `/api/customer-requests`; migration `053`; flags `FEATURE_CUSTOMER_SELF_SERVICE`
  (+ tenant / user allowlists). Spec `customer/CUSTOMER_SELF_SERVICE.md`, D-021.
- **RH-P3.17-DEVICES — Devices KPI = 0 + false-green banner (fixed in the same PR).**
- **RH-P3.17-AUDIT — `scripts/rh_customer_go_live_audit.py`.** Run on Render after
  deploy; resolve SYSTEM BLOCKERS before the invite.
- **Follow-ups (not in the slice):** internal UI for the request queue (API only
  today) · notification delivery for stored preferences · link the ~16 unlinked
  RH buildings to monitoring records · E911ChangeLog draft from an approved
  correction · request SLA timers · document/photo storage.

### Phase 3.18 — Calm customer experience / trust rule (IN REVIEW; branch `feat/rh-customer-calm-ux`, PR open)
- **RH-P3.18-CALM — UNKNOWN ≠ FAILED ≠ PROTECTED (D-022).** Portfolio hero with
  separate dimensions (no blended health score), tiered + owned Action Center,
  location page in four places (Overview · Connections · Compliance · Records) with
  ≤2 primary actions. Presentation only; no scoring / E911 / registry change.
- **Follow-ups:** link the ~16 unlinked RH buildings to monitoring (turns "Being
  reconciled" into evidence) · supply the 10 missing E911 dispatch addresses ·
  internal UI for the request queue · a browser-level test harness (Playwright) for
  customer screens · marker clustering.

### Phase 4 — Launch
- **RH-P4.0 — Go-live audit gate.** `rh_customer_go_live_audit` verdict `READY` or
  `READY_WITH_CUSTOMER_ACTIONS` (zero SYSTEM BLOCKERS) before the invite.
- **RH-P4.1 — Judy onboarding.** Create Judy user, assign `CUSTOMER_ADMIN`, RH tenant scope.
- **RH-P4.2 — Go-live validation.** Run the §6 operational checklist + §5 gates in
  `FEATURE_CUSTOMER_API_ROLLOUT.md`; serialization safety net + 403/404 matrix green.
- **RH-P4.3 — Launch.** Enable `FEATURE_CUSTOMER_API` + `CUSTOMER_API_TENANT_ALLOWLIST=
  restoration-hardware`; issue credentials; schedule weekly digest; Day-1 monitoring.

**Gating dependencies:** P1 before any customer login · P2 (esp. E911) before P3 surface
is enabled · P4 launch only on the go/no-go GO (no false green; 42/42 E911 or affected
sites shown honestly Critical). C3 (T-Mobile key rotation) is **not** an RH blocker unless
live T-Mobile activation enters RH's path.

---

## CRITICAL

- **C1 — Committed private key (`api/tmobile_private.pem`).** ✅ *Repo cleanup MERGED
  (PR #112, 2026-06-14).* ⚠️ *Key rotation INTENTIONALLY DEFERRED — accepted
  temporary risk; see C3 gate.* An RSA *private* key was tracked in git (commit
  `a65d7a3`, ancestor of `main` + ~90 branches, pushed to `origin`). **Done:**
  removed both `.pem` files from the tree, added `api/tmobile_private.pem.example`
  placeholder, hardened `.gitignore` (root + api), documented env-var loading. No
  code/behavior changed (env-var loading already existed and is preferred).
  **Accepted-risk decision (2026-06-14):** the leaked key is a **PIT/testing-only**
  credential in a non-production, non-customer-facing environment, so rotation is
  deferred. The key in history must still be treated as compromised. **Mandatory
  before any production exposure → tracked as C3 (pre-production gate).** Full plan +
  rotation steps in `docs/TMOBILE_PRIVATE_KEY_REMEDIATION.md`. Git history rewrite
  remains out of scope (approval-gated). *Security / Safety.*
- **C3 — PRE-PRODUCTION GATE: rotate the T-Mobile key before any non-PIT exposure.**
  🚧 *Hard gate. Blocks go-live.* The PIT key leaked in C1 is accepted as a
  temporary risk **only** while the T-Mobile integration stays in PIT/testing. The
  key **MUST be rotated** (new pair → register new public key with T-Mobile +
  deregister old → set `TMOBILE_PRIVATE_KEY_PEM` as a Render secret → verify with
  `scripts/test_tmobile_taap.py --dry-run`) **before ANY of the following:**
  - external evaluators / third-party assessment,
  - customer pilots,
  - production traffic (real subscribers / live activations),
  - carrier certification,
  - government or customer demonstrations.
  Do not flip `TMOBILE_ENV=prod` or `TMOBILE_PIT_LIVE_CALLS_ENABLED=true` for a
  real account until this is closed. Owner: operator (manual). Steps:
  `docs/TMOBILE_PRIVATE_KEY_REMEDIATION.md` §5. *Security / Safety.*
- **C2 — T-Mobile PIT callback app-layer authentication.** ✅ *Implemented behind
  `FEATURE_TMOBILE_CALLBACK_AUTH` (default off); PR pending review.* Ingest is now
  gated on a shared-secret token (`X-True911-Callback-Token` header or `?token=`
  query, constant-time) plus optional enforced IP allowlist
  (`TMOBILE_CALLBACK_IP_ENFORCE`); a failed check is logged and dropped while the
  endpoint still returns HTTP 200. The token is redacted from query logs. Closes
  the spoofing / false-state-injection vector without depending on T-Mobile
  signing. **Follow-ups:** add HMAC verification when T-Mobile publishes a callback
  signing spec (`services/webhook_auth.py` helper ready); enable the flag with a
  provisioned token before any internet-exposed ingest. See
  `docs/TMOBILE_CALLBACK_AUTH.md`. *Safety / Security.*
- **C4 — T-Mobile PIT activation blocked on `GENS-0003 Invalid partnerID`.**
  ✅ **CLOSED 2026-07-21 — activation succeeded** (`HTTP 201`, `status=SUCCESS`,
  result `100`, deployed commit `1766f51`). Resolved by T-Mobile gateway
  configuration recreation; the client contract was valid and **no Partner
  Foundation header was required**. Exact internal T-Mobile root cause is not
  independently observable from the client. The history below is retained
  verbatim as the record of how the contract was arrived at — **every hypothesis
  in it about the cause of GENS-0003 is superseded**. Successor items (callback
  verification, subscriber-status verification, persistence, ungated lifecycle
  methods, production gates) are in §CLOSED at the top of this file and in
  `TMOBILE_PRODUCTION_READINESS.md`.
  <details><summary>Historical record (superseded)</summary>
  🚧 *External dependency — waiting on T-Mobile Engineering (Aman).* Activation now
  reaches the T-Mobile activation service (`POST /wholesale/v1/subscriber/activation`)
  with validated OAuth/PoP, the corrected endpoint, and the required `partner-id` /
  `sender-id` headers (PR #122) plus correlation-ID + partner-transaction-ID logging
  (PR #121). T-Mobile rejects `partnerID=128` with `400 GENS-0003`. **Done (True911
  side):** headers renamed to `partner-id`/`sender-id`; diagnostics in place; trace IDs
  logged. **UPDATE 2026-07-07 (branch `fix/tmobile-partner-sender-pop-claims`, PR open,
  NOT merged):** T-Mobile Engineering (Aman) reviewed the live retest
  (UTC `2026-07-07T14:59:50Z`, work-flow-id `99a2b4f7-…_P`) and found **sender-id was
  absent from the PoP auth claims** — we sent it only as an HTTP header. Fix: resource
  PoP now signs `Authorization;uri;http-method;partner-id;sender-id` and carries
  `partner-id`/`sender-id` as PoP JWT claims (token-endpoint PoP unchanged); failure
  logs now surface `work-flow-id`/`service-transaction-id`. **Open (retest):** run one
  live PIT activation with the fix while T-Mobile watches logs, capture the trace ids.
  **Follow-up (small, env or 1-line):** if T-Mobile also requires lowercase `account-id`
  for post-activation ops, rename `X-Account-Id` (currently unchanged). Do not re-fire
  live activations to guess a value. See `TMOBILE_PIT_ACTIVATION_PAYLOAD.md` (finding +
  retest) and `PROJECT_STATE.md` §0·URGENT. *Revenue / Reliability.*
  </details>

---

## HIGH

- **H1 — Harden CI.** Current CI runs only `pytest -q` and `vite build`. Add: a
  Python linter (ruff/flake8), a frontend smoke test, a coverage floor on
  safety-critical modules (health, assurance, rbac, webhook auth), and a
  dependency/secret scan (e.g. pip-audit + a secret scanner — would have caught
  C1). Switch `npm install` → `npm ci` for reproducible builds. *Reliability /
  Security / Maintainability.*
- **H2 — Verify and rehearse DB backup/restore.** Single starter Postgres 16.
  Confirm automated backups, PITR availability on the plan, and run a restore
  drill. Document RPO/RTO in `docs/RENDER_DB_RECOVERY.md`. *Reliability / Data
  integrity. Needs Verification.*
- **H3 — Move JWT out of `localStorage`.** Tokens in `localStorage` are readable by
  any XSS. Plan migration to httpOnly cookies (with CSRF protection) or a hardened
  store. Larger change — design carefully, flag-gate the rollout. *Security.*
- **H4 — Confirm CORS can never ship wildcard to prod.** Default is
  `allow_origin_regex=".*"` + credentials. Add a startup assertion or deploy guard
  that refuses wildcard when `APP_MODE=production`. *Security.*
- **H5 — Refuse-to-start on default `JWT_SECRET` in production.** Today startup only
  *warns*. In `production` mode it should hard-fail. *Security / Reliability.*
- **H6 — E911 correctness regression suite.** E911 is the platform's reason to
  exist. Ensure there is an explicit, comprehensive test + monitoring path proving
  E911 address state and change-log integrity. *Safety. Needs Verification of
  current coverage.*

---

## MEDIUM

- **M1 — Single canonical status normalization per axis.** Status mapping appears
  in Zoho normalizer, health states, and assurance labels. Audit for drift; ensure
  one authoritative mapping per axis with shared tests. *Data integrity.*
- **M2 — Per-flag graduation/removal plan.** ~16 `FEATURE_*` flags. Each should have
  an owner, a soak-exit criterion, and a removal target so flags don't accumulate.
  *Maintainability.*
- **M3 — Restrict/disable public debug endpoints.** `GET /api/debug/cors` and
  `GET /api/config/features` are public. Gate `debug/cors` behind SuperAdmin or
  remove. *Security (low data sensitivity, but unnecessary surface).*
- **M4 — Worker/api flag-parity guard.** Add a check or doc that any behavior flag
  must be set on both `true911-api` and `true911-worker` (PR #63 pitfall).
  *Reliability.*
- **M5 — Move demo seed off the prod start command.** `python -m app.seed` runs on
  every API boot; it is gated but on the critical startup path. Make it a one-time
  job or guard earlier. *Reliability.*
- **M6 — Assurance Engine backend MVP** (read-only, `FEATURE_ASSURANCE_ENGINE`
  off). The product spine; ~80% of inputs already exist. Backend-first with
  table-driven tests per `docs/ASSURANCE_ENGINE.md`. *Customer experience (but
  built safety-first).*
- **M7 — Graduate Health Normalizer / LLLM soaks** per their runbooks once exit
  criteria are met; LLLM Phase 1b requires governance approval (blocker). *Reliability.*

---

## LOW

- **L1 — Frontend automated tests.** No test runner today (build-only). Add a
  minimal Vitest + component-smoke layer for safety-relevant components
  (AssuranceBadge, status badges, auth gating). *Reliability.*
- **L2 — Lockfile hygiene.** CI note says `package-lock.json` regenerates on every
  install; stabilize so `npm ci` becomes viable (ties to H1). *Maintainability.*
- **L3 — Structured request/audit log retention policy.** Confirm log retention,
  PII posture, and that secrets are never logged across all integrations.
  *Security / Compliance. Needs Verification.*
- **L4 — Documentation index.** A `docs/README.md` index of the ~50 docs would aid
  navigation. *Internal convenience.*

---

## PRODUCT EXPERIENCE (Track B epics)

> **Reprioritized 2026-06-22:** these PE epics now rank **behind `EPIC-RH-GO-LIVE`**
> (top of this file). RH go-live operationalizes the spine these epics generalize — the
> customer surfaces here are the platform-wide version of what RH receives first. Resume
> PE sequencing after RH launch (Phase 4) or where an item is a shared dependency of
> `EPIC-RH-GO-LIVE` (e.g. Assurance graduation, E911 sweep, Support spine).
>
> Derived from the product constitution (`docs/PRODUCT_MANIFESTO.md`,
> `ASSURANCE_PLATFORM_SPEC.md`, `CUSTOMER_EXPERIENCE.md`, `SCREEN_BY_SCREEN_SPEC.md`,
> `DESIGN_SYSTEM.md`). Sequencing + dependencies in
> `docs/IMPLEMENTATION_MASTER_PLAN.md` (Track B). Each ships flag-gated, read-only
> first, behind the Track-A foundation gate. **Do not start a customer surface
> while a Critical (C*) item is open** and not before the E911 data sweep (PE7).

- **PE0 — Truth Engine / Identity Engine.** *In progress.*
  - **PR-1a DONE** (merged #119) — pure `IdentityResolver` core (proof-chain-first;
    Resolved/Ambiguous/Orphan; inert, flag-free, fully tested).
  - **PR-1b1 DONE** — read-only Identity Audit (loader + pure aggregation): totals,
    gaps, E911 three-dimension metrics (D-015), Truth Score component seeds,
    bounded samples. Inert; +13 tests.
  - **PR-1b2 NEXT (next implementation slice)** — SuperAdmin, read-only endpoint
    `GET /api/data-health/identity-audit` behind `FEATURE_TRUTH_ENGINE` (default
    off → 404), RBAC `GLOBAL_ADMIN`, + internal→external label mapping (D-014).
  - **PR-1c** — Truth Score composite (Identity + Hierarchy + Completeness + API
    Freshness + E911) + Data Health console read API.
  See `TRUTH_ENGINE.md`, `DECISIONS.md` D-011…D-015. *Data integrity / Safety.*
- **PE1 — Assurance Engine graduation** (build on the implemented PR1; portfolio +
  attention endpoints). Depends on M1 (canonical normalization). *CX, safety-first.*
- **PE2 — View Proof** — evidence bundle per status (the trust mechanism; answers
  "Why should I believe this?"). Depends on the Assurance Engine + E911 regression
  (H6). *Safety / CX.*
- **PE3 — Morning Test dashboard (Home)** — <15s portfolio snapshot. Depends on
  PE1 + the E911 data sweep. *CX.*
- **PE4 — Site experience** — four-axis breakdown + E911 checklist + status +
  proof. *CX.*
- **PE5 — Assurance Timeline** — customer / support / audit versions + proof
  export (read-only aggregation, no new capture). *CX / Support / Compliance.*
- **PE6 — Installer mobile workflow** — live-online + test-call + E911 verify +
  "Site Accepted" (ships the managed-POTS playbook; unblocks PR #51). *Safety / CX.*
- **PE7 — E911 data normalization sweep** — validate active-site addresses before
  any customer label is exposed (active + unverified E911 = Critical by rule).
  *Safety. Gating dependency for PE3/PE4.*
- **PE8 — Support workflow console** — reason codes → recommended action, gated
  remediation, Zoho Desk escalation. Depends on M4 (worker flag parity). *Support.*
- **PE9 — Executive dashboard + monthly PDF** — trend, Protected %, Lives
  Protected, revenue at risk. *Revenue / CX.*
- **PE10 — Revenue & business-impact layer** — revenue at risk, upsell, churn-risk
  (read-only over Zoho lifecycle; never writes commercial state). *Revenue.*

> **Standing veto — Features That Should Never Be Built:** the authoritative list
> is in `docs/ASSURANCE_PLATFORM_SPEC.md §7` (e.g. customer-facing numeric score,
> autonomous AI life-safety decisions, 911-will-always-connect guarantee, green
> without explanation, cross-tenant benchmarking, raw vendor telemetry as the
> primary customer experience). Adding any requires overturning the manifesto.

---

## PLATFORM GENERALIZATION (post-pilot; ranked BEHIND EPIC-RH-GO-LIVE)

> RH is the **pilot** that validates the **generic** customer plane (boundary statement
> in `CUSTOMER_API_CONTRACTS.md` §0). These epics generalize the plane for all customers
> (R&R, Benson, Integrity, schools, healthcare, airports, government). **Neither gates RH
> go-live.**

- **EPIC-GEN-001 — Generic Customer Portfolio Display.** *Purpose:* customer-facing
  dashboard identity works for single- **and** multi-customer tenants. *Slice 1 (done,
  PR #130):* `portfolio.company_name` no longer uses an arbitrary `LIMIT 1` — single
  Customer → its name (RH path), else tenant org name, else `"Your Portfolio"`. *Remaining:*
  the **user→Customer resolution** that activates the "resolved customer context" preference
  (needs a `User.customer_id` or Person/Contact link from D-024). *CX / Data integrity.*
- **EPIC-GEN-002 — Generic Service Unit Builder.** *Purpose:* a generalized service-unit
  builder supporting **1 device→1 service · 1 device→many services · many devices→1 service ·
  device-less services · line-based services · port-based services · customer-specific
  mapping profiles.** ⛔ **Explicitly NOT required for RH go-live** — RH uses the
  intentionally device-anchored P3 tool (`P3_SERVICE_UNIT_CREATION_SPEC.md`); EPIC-GEN-002
  is the post-pilot generalization and **does not gate P3 or RH launch.** *Scalability / CX.*
- **EPIC-GEN-003 — Inventory Reconciliation Framework.** ✅ **IMPLEMENTED (merged, PRs
  #134–#137).** Customer- and vendor-agnostic, **read-only** engine
  (`api/app/services/inventory_reconciliation/`) that compares an external carrier/vendor
  inventory (pluggable adapter) against True911 inventory → `INVENTORY_RECONCILIATION.csv`
  + `.json` + summary stats. Matching hierarchy ICCID → RadioNumber → SubscriberName →
  site similarity; results MATCHED/PARTIAL/MISSING_IN_TRUE911/MISSING_IN_VENDOR/DUPLICATE/
  REVIEW. **NAPCO StarLink** adapter ships first; runner `python -m app.reconcile_inventory`
  (no DB writes, no flags, tenant-scopable). Runbook `docs/INVENTORY_RECONCILIATION_RUNBOOK.md`.
  No real customer export committed (synthetic test fixtures; pre-existing real NAPCO
  identifiers scrubbed, PRs #135–#137). *Reusable for RH/R&R/Benson/Integrity/USPS + any
  future vendor.* **Remaining:** operator runs the CLI against prod-read DB + the vendor
  export to produce the real artifacts; add further vendor adapters as needed. *Data
  integrity / Scalability.*

---

## EPIC-OPS-CENTER — AI Customer Operations Center / Support Center

> Caller-facing Tier-1 support workflow: a caller WITHOUT an account number is
> matched by a real-world field identifier (elevator phone number, MSISDN, Napco
> radio number, ICCID, Starlink ID, site/building name, …), verified by **SMS
> OTP** to an authorized contact on file, then given a temporary verified support
> session with triage diagnostics and a human-handoff summary. Distinct from the
> internal **AI Support Assistant** (`/api/support`, authenticated users). Design
> + Phase-1 backend authoritative in `AI_CUSTOMER_OPERATIONS_CENTER.md`,
> `SUPPORT_CENTER_ARCHITECTURE.md`, `ASSET_IDENTITY_MODEL.md`,
> `SUPPORT_VERIFICATION_WORKFLOW.md`, `SUPPORT_ESCALATION_MATRIX.md`.
>
> **Status:** Phase 1 (backend foundation) **IMPLEMENTED** behind `FEATURE_OPS_CENTER`
> (default OFF → all `/api/ops-center/*` routes 404; migration `048` additive). Not
> yet enabled in any environment. Does **not** gate EPIC-RH-GO-LIVE.

### Phase 1 — Backend foundation (IMPLEMENTED, flag-gated, additive)
- **OPS-P1.1 — Data model + migration `048`.** `asset_identities`, `ops_support_sessions`,
  `ops_otp_challenges`, `ops_session_events`. *Done.*
- **OPS-P1.2 — Asset lookup.** `asset_identities` index + native-field fallback
  (Device/Site/ServiceUnit/Line); redacted matches; contact-on-file resolution. *Done.*
- **OPS-P1.3 — Verification.** SMS-OTP issue/verify; salted-hash codes (never stored
  plaintext); attempt-limit + expiry; sensitive fields withheld until verified. *Done.*
- **OPS-P1.4 — Triage hooks.** Device health / last-seen / carrier-SIM / SIP-ATA /
  signal / events / tickets / billing — graceful-degrade stubs; verified-only. *Done.*
- **OPS-P1.5 — Escalation.** Handoff summary + optional incident; emergency life-safety
  incident allowed while unverified. *Done.*

### Phase 1.5 — Operational-intelligence foundations (IMPLEMENTED, additive, inert)
> Schema + library scaffolding only — no UI, no routes, no workflow change, no
> public exposure; entirely inert until a later phase wires it. Migration `049`
> additive. Doc: `OPS_CENTER_PHASE_1_5.md`.
- **OPS-P1.5.1 — Canonical `IncidentSeverity` + status enums** + issue-category→
  severity / priority mapping. *Done.*
- **OPS-P1.5.2 — `OpsEscalationQueue` model + `enqueue_escalation` helper** (not
  yet wired to `escalate`). *Done.*
- **OPS-P1.5.3 — Support knowledge stubs:** `OpsKnowledgeArticle`, `OpsPlaybook`,
  `OpsResolutionPattern` models. *Done.*
- **OPS-P1.5.4 — `CustomerHealthSnapshot` service stub** (read-only, tenant-scoped,
  graceful-degrade; may later delegate to the Assurance Engine). *Done.*
- **OPS-P1.5.5 — Carrier/`VendorContext` service output** (normalized; no new
  Device/Sim columns). *Done.*
- **OPS-P1.5.6 — (later)** wire the queue into `escalate`; author KB/playbooks;
  learn resolution patterns — all still internal + flag-gated.

### Phase 2 — UI (Support Center surface)
- **OPS-P2.1 — Customer/internal Support Center placeholder** (flag-gated nav).
- **OPS-P2.2 — Asset lookup interface, session detail, verification-state display,
  handoff-summary display.**

### Phase 3 — Real OTP provider
- **OPS-P3.1 — Twilio/Telnyx `OtpProvider` implementation** behind the existing
  `app/services/ops_center/otp` abstraction (stub is the safe default today).
- **OPS-P3.2 — Rate-limiting + abuse controls** on lookup + OTP send before any
  internet/customer-portal exposure (see `SUPPORT_VERIFICATION_WORKFLOW.md` "Follow-ups").

## IDEAS (unprioritized; validate against MISSION before promoting)

- Customer-facing Assurance portal with the "Recent Manley Activity" timeline
  (§9 of the Assurance spec) — "what has Manley done to protect us".
- Executive portfolio summary / revenue posture dashboards.
- Mobile-optimized installer flow (Day-0 onboarding on a phone).
- Mapping/geographic health overlay beyond the current Leaflet `DeploymentMap`.
- Public API strategy for enterprise customers (Judy) to pull their own status.
- Scheduled compliance PDF/report generation (deferred in Assurance MVP).
- AI-assisted support remediation suggestions (deterministic-first, gated).

---

## TECHNICAL DEBT (tracked)

- **TD1 — Audit/backfill script sprawl.** ~15 `audit_*` / `backfill_*` / one-off
  remediation modules live in `app/` alongside runtime code (plus `scripts/`).
  Triage which are still operationally needed; archive the historical ones to keep
  `app/` runtime-focused. *Needs Verification of which are live.*
- **TD2 — Two T-Mobile modules.** `integrations/tmobile.py` (IoT, X-API-Key, stub)
  vs `integrations/tmobile_taap.py` (Wholesale, live-gated). Decide if the IoT stub
  is still wanted; remove if not.
- **TD3 — Status normalization duplication** (see M1).
- **TD4 — Flag sprawl without removal plan** (see M2).
- **TD5 — Stale references in project memory** — e.g. DB name `true911-prod-db` vs
  `render.yaml`'s `true911-db`; migration list in MEMORY.md notes it is stale.
  Reconcile. *Data integrity of docs.*
- **TD6 — No reproducible frontend build** (`npm install` not `npm ci`) (see H1/L2).
