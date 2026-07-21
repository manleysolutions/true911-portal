# True911+ — PROJECT STATE

> **Read this first** (after `CONSTITUTION.md` and `DECISIONS.md` — the AI Session
> Rule, `CONSTITUTION.md` P4; entry point `README.md`). Written so a future session
> can resume from it alone. Keep it accurate — update at the end of every session
> per the Documentation Freshness rule (P2 / Operating Loop §0a).
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Last updated: 2026-07-21. Branch at time of writing:
> `feat/tmobile-pit-api-certification-harness` (PR open, NOT merged; stacked on
> `docs/tmobile-pit-success-closeout`, which is stacked on `main`).

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

**To promote to authority**, in order: un-branch the Alembic chain → persist
lifecycle transactions → have the operator path create them → review the
recorded agreement rate → then flip the rules to authoritative.

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

**Deferred:** durable persistence for lifecycle transactions. The alembic chain
is currently branched (two revisions share a parent, one of them uncommitted),
so migration ownership is unclear and adding one would entangle this work with
an unrelated in-flight migration. The transaction structures are typed and
persistence-ready for whoever resolves that.

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
`python -m scripts.tmobile_callback_inspect --iccid <ICCID> --partner-transaction-id <ptx>`.

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
  no network): `python -m scripts.tmobile_callback_inspect --iccid <ICCID> …`
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

## 0·NEXT — RH registry approval operator script (branch `feat/rh-registry-approve`, PR open, NOT merged) [2026-07-02]

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

## 0·PREV — Customer Dashboard → Portfolio Registry integration (branch `feat/customer-portfolio-registry-view`, PR open, NOT merged) [2026-07-02]

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

## 0·PREV — RH Certification v2: known special-location registry (PR #158, open) [2026-07-01]

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

**`EPIC-RH-GO-LIVE` Phase 1 — the foundation that gates Judy's credentials** (see
`BACKLOG.md` for the full four-phase epic):
1. **PR-S1 — tenant-isolation fixes** (H1 subscriber-import batch rows; L1/L2/L3
   child-query tenant filters; M2 gate `/api/zoho/config`) per `RH_SECURITY_READINESS.md` §5.
2. **PR-B1 — `INTERNAL_OPS` guard** on bare-`get_current_user` internal GETs, granted to
   all six existing roles (behavior-preserving; no-regression test gate).
3. **PR-B2 — four `CUSTOMER_*` roles** + customer perms in `permissions.json`; Bucket-B
   customer guards (`CUSTOMER_EXPERIENCE_BOUNDARY.md` §A).
4. Then **Phase 2** (RH data remediation: E911 42/42, device mapping 51/51, telemetry,
   service units) in parallel via Sivmey + Eng; **Phase 3** (customer API) gated behind it;
   **Phase 4** (Judy onboarding + launch) per `FEATURE_CUSTOMER_API_ROLLOUT.md`.

## 9. How to Resume

1. Read `docs/MISSION.md` (§3 priority order), this file, then `docs/BACKLOG.md`.
2. `git status` clean; identify branch.
3. Run the Operating Loop (`docs/OPERATING_LOOP.md`) for the chosen objective.
4. Verify with `cd api && python -m pytest -q` and `cd web && npm run build`.
5. Update this file before you stop.
