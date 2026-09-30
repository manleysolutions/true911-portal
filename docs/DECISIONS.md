# True911+ — DECISIONS LOG

> Append-only record of every architectural, business, workflow, and philosophy
> decision. **Never edit or delete a past entry** — supersede it with a new one
> (`Status: Superseded by D-NNN`). Required by `CONSTITUTION.md` P2/P3. Entry IDs
> are stable and referenced from other documents.

| Metadata | |
|---|---|
| **Authority Level** | 2 — Architecture (canonical, immutable record) |
| **Owner** | Product Owner + Principal Architect |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Append-only (frequent additions; entries never edited) |
| **Status** | Active — D-001 … D-020 recorded; latest ID: D-020 |
| **Governed By** | `CONSTITUTION.md` |
| **Detailed In** | the document each decision affects |
| **Related Decisions** | — |

**Entry format:** ID · Date · Status (Accepted / Superseded / Reversed) · Context ·
Decision · Consequences.

---

### D-001 — Adopt the constitutional rules P1–P5
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** Load-bearing knowledge was accumulating only in conversation; no
  formal governance existed for documentation or slice size.
- **Decision:** Adopt P1 Single Source of Truth, P2 Documentation Freshness, P3 No
  Conversation Dependency, P4 AI Session Rule, P5 Smallest Safe Slice
  (`CONSTITUTION.md` §5).
- **Consequences:** All future work follows these rules; `OPERATING_LOOP.md`
  enforces them; this log becomes mandatory.

### D-002 — Defer T-Mobile PIT private-key rotation (accepted PIT-only risk)
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** An RSA private key was committed to git history (BACKLOG C1). Repo
  cleanup merged (PR #112); history rewrite is approval-gated and out of scope.
- **Decision:** Treat the key as a PIT/testing-only credential and **defer
  rotation** while the integration stays in PIT, tracking mandatory rotation as the
  C3 pre-production gate.
- **Consequences:** Key in history remains compromised; must rotate before any
  production/external/customer/gov exposure. See `TMOBILE_PRIVATE_KEY_REMEDIATION.md`.

### D-003 — C3 pre-production gate (hard go-live blocker)
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** The D-002 deferral is safe only within PIT.
- **Decision:** Rotation of the T-Mobile key is a hard gate before external
  evaluators, customer pilots, production traffic, carrier certification, or
  gov/customer demos.
- **Consequences:** `TMOBILE_ENV=prod` / live calls for a real account are blocked
  until closed.

### D-004 — Customer label wording: "Protected (as of <time>) + disclaimer"
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** "911 Ready" risked reading as a guarantee (liability).
- **Decision:** Customer string is **"Protected"** with an "as of" timestamp +
  disclaimer; internal/clinical equivalent "Active & Verified." No guarantee 911
  will connect (`CONSTITUTION.md` §7.3).
- **Consequences:** All assurance surfaces use this wording. Detail in
  `ASSURANCE_ENGINE.md`.

### D-005 — Six-label assurance vocabulary
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Protected · Attention Needed · Critical · Pending Install ·
  Inactive/Deactivated · Unknown. No customer-facing numeric score
  (`CONSTITUTION.md` §7.1).
- **Consequences:** Fixed vocabulary across all surfaces; detail in
  `ASSURANCE_PLATFORM_SPEC.md` / `ASSURANCE_ENGINE.md`.

### D-006 — Separate-axes invariant
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Operational, commercial-lifecycle, E911/compliance, and
  deployment-lifecycle are separate axes with one owner each; reads compose, writes
  never overwrite another axis. Missing data ≠ healthy.
- **Consequences:** Constitutional (`CONSTITUTION.md` §4.3); enforced in
  `DATA_MODEL.md` and the Assurance/Truth engines.

### D-007 — Truth Engine is read-only-first; event bus deferred
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Build the Truth Engine resolve-and-report (shadow) before
  resolve-and-write; defer a true event bus until write-time resolution is proven.
- **Consequences:** First slice writes nothing; everything flag-gated
  (`FEATURE_TRUTH_ENGINE`). See `TRUTH_ENGINE.md`.

### D-008 — CI secret scanning via gitleaks in working-tree mode (CI-1A)
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** No secret scanning existed (the gap behind C1).
- **Decision:** Add a blocking gitleaks job using **`gitleaks dir`** (working-tree),
  not history mode (which would re-flag the accepted C1 key), via a pinned binary
  (avoids the org-license requirement), with a tuned `.gitleaks.toml` allowlist.
- **Consequences:** PR #116. No file type blanket-excluded; verified to block on
  planted `.pem`/`.env`/`.key`/PAT secrets.

### D-009 — Documentation migration as two grouped doc-only PRs
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Establish the DocOS via PR A (new governing docs) + PR B (integrate
  existing docs). Documentation-only; preserve history; cross-reference not copy.
- **Consequences:** This document set; `PRODUCT_MANIFESTO.md` promoted to
  `CONSTITUTION.md` via `git mv`.

### D-010 — Four-level Documentation Operating System
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Adopt the four-level authority hierarchy (Governance / Architecture
  / Execution / Process) with `README.md` as the required entry point and the
  North Star (in `PRODUCT_VISION.md`) as the success statement.
- **Consequences:** See `README.md`; authority flows top-down; conflicts resolved by
  level then by the priority order.

### D-011 — Phase 0 / PR-1 scope: read-only Identity Resolution Audit
- **Date:** 2026-06-14 · **Status:** Accepted (plan)
- **Decision:** First Truth Engine slice = pure `IdentityResolver` + read-only audit
  + SuperAdmin endpoint behind `FEATURE_TRUTH_ENGINE`; no writes, no migration, no
  frontend, no `permissions.json` change (reuse `GLOBAL_ADMIN`). Recommended split:
  PR-1a pure resolver + tests, then PR-1b audit + endpoint.
- **Consequences:** Implementation pending approval. Design in `TRUTH_ENGINE.md`.

### D-012 — Layered engine architecture; "Identity Engine" subsystem
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Adopt the stack **Reality → Identity Engine → Truth Engine →
  Assurance Engine → AI → Automation.** The identity-resolution subsystem is the
  **Identity Engine**; its pure deterministic core is the **IdentityResolver**.
  Documented within `TRUTH_ENGINE.md` for now; promote to a dedicated
  `IDENTITY_ENGINE.md` only if it grows.
- **Consequences:** Naming/framing; the Truth Engine's **Truth Score** (composite:
  Identity, Hierarchy, Data Completeness, API Freshness, E911 Completeness)
  unifies with the earlier "Data Health Score" — one metric, name "Truth Score";
  definition in `TRUTH_ENGINE.md`, KPI in `PRODUCT_VISION.md`. Not built in PR-1a.

### D-013 — Proof Chain is the canonical resolver artifact
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** The resolver builds **Facts → Proof Chain → Decision**. The
  `proof_chain` (ordered, explainable evidence links) is the canonical output;
  resolution status is **derived** from it. `proof_chain` is part of the canonical
  contract from PR-1a (locking it now avoids a later breaking change to a
  foundational component).
- **Consequences:** Output set is `status · proof_chain · reason_codes ·
  match_basis · suggestions · confidence` + hierarchy projections; confidence is a
  ranking aid only, not the primary justification.

### D-014 — Internal vs external resolution vocabularies (separate layers)
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** The resolver emits only the **internal** machine verdict
  (Resolved / Ambiguous / Orphan). The **external** vocabulary
  (Verified / Supported / Suggested / Unknown) is a presentation mapping applied in
  a later layer, never inside the pure resolver.
- **Consequences:** PR-1a stays internal-only; mapping (Resolved→Verified;
  weaker-basis→Supported; suggestion→Suggested; else→Unknown) recorded for the
  audit/console PR. Both vocabularies added to `GLOSSARY.md` later.

### D-015 — E911: report three distinct dimensions; never collapse
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** The Identity Audit must surface E911 readiness without overstating
  it. A populated address is not the same as a verified one (life-safety
  distinction).
- **Decision:** The audit reports **three separate** E911 dimensions, never
  collapsed into one boolean:
  - `e911_address_present` = `e911_street` + `e911_city` + `e911_state` +
    `e911_zip` are populated.
  - `e911_verified` = `e911_status` indicates verified/validated
    (set `{validated, verified}`, case-insensitive).
  - `e911_confirmation_required` = `sites.e911_confirmation_required` is true.
  Audit gaps include `missing_e911_address`, `unverified_e911` (address present but
  not verified), and `e911_confirmation_required`.
- **Consequences:** The shipped resolver is **untouched** — its
  `SiteFacts.e911_present` maps to *address present* only (identity gap), while
  verification is reported as a data-quality metric by the audit, not an identity
  gate. See `TRUTH_ENGINE.md` and `api/app/services/identity/{loader,audit}.py`.

### D-016 — Customer Assurance Mode may green operational status when tenant-scoped + evidence-backed; E911 excluded
- **Date:** 2026-07-01 · **Status:** Accepted
- **Context:** RH (Judy) must be able to log in and see a calm, Active/Green
  portfolio before carrier/vendor telemetry is live, without weakening life-safety
  truth or exposing internal surfaces.
- **Decision:**
  1. **Customer Assurance Mode** (the "preview") is allowed to present the
     **operational axis** (location/service/device) as **Protected/Active** — but
     ONLY when (a) tenant-scoped via a two-key gate
     (`FEATURE_CUSTOMER_PREVIEW` + `CUSTOMER_PREVIEW_TENANT_ALLOWLIST`, default OFF)
     AND (b) evidence-backed by an honest **operator attestation** (not fabricated
     telemetry), satisfying the no-green-without-evidence rule (§4.6).
  2. **E911 is excluded from the preview override** — verification derives only
     from the stored record (`e911_status ∈ {validated, verified}`); active +
     unverified stays **Critical** (D-006/D-015). Missing E911 is surfaced
     internally (`/api/e911-changes/gaps`, readiness check) for correction.
  3. **Raw/internal status is unchanged** — the override is presentation-only,
     mutates nothing, and internal/operator views read the real state.
  4. **Customer roles are `CUSTOMER_*` (never legacy `User`)** and are isolated
     from `INTERNAL_OPS`/`COMMAND_*`; their dashboard reads `/api/customer/*`, not
     `/command/summary`.
- **Consequences:** `permissions.json` grants `CUSTOMER_*` the customer read perms
  (VIEW_SITES/DEVICES/ASSURANCE) and adds `CUSTOMER_MANAGER/VIEWER/SUPPORT`; the
  admin invite path accepts `CUSTOMER_*`; the customer dashboard branch is wired to
  `/api/customer/*`; internal operator pages are gated behind `INTERNAL_OPS`. See
  `docs/customer/ASSURANCE_ENGINE.md`, `docs/customer/RH_GO_LIVE_RUNBOOK.md`,
  `api/app/services/customer/preview.py`. Preview is a bridge — retired per location
  as real evidence supersedes attestation.

### D-017 — T-Mobile PIT closeout: record the root cause only as far as the client can see it
- **Date:** 2026-07-21 · **Status:** Accepted
- **Context:** The first successful T-Mobile PIT activation (`HTTP 201`,
  `status=SUCCESS`, result `100`, `2026-07-21T03:18:33.694749Z`, deployed commit
  `1766f51`) landed on the **same client contract** that had returned `400
  GENS-0003 Invalid partnerID` days earlier, with no code change in between.
  T-Mobile Engineering recreated the gateway configuration immediately before the
  successful request. The leading internal hypothesis — that a "Partner
  Foundation ID" header was required — was **never exercised**: no such header
  was configured or transmitted. Three prior PRs (#165, #167, #168) had each
  attributed GENS-0003 to a plausible client-side cause and each cost a live PIT
  cycle; all three attributions were wrong.
- **Decision:** Record the root cause as *"Resolved by T-Mobile gateway
  configuration recreation. The available evidence indicates the client request
  contract was valid at the time of the successful activation, and no additional
  Partner Foundation header was required. Exact internal T-Mobile root cause is
  not independently observable from the client."* — and no more. Superseded
  hypotheses are **marked superseded, never deleted**. The Partner Foundation
  config stays **inert**; the "never guess a header name" rule survives the
  success. Unmasked subscriber identifiers live in exactly one restricted
  operator document; every other artifact masks to the last four characters via
  the shared `tmobile_evidence.mask_tail`.
- **Consequences:** `TMOBILE_PIT_ACTIVATION_PAYLOAD.md`, `tmobile_taap_setup.md`,
  `TMOBILE_INTEGRATION_AUDIT.md`, `PROJECT_STATE.md`, and `BACKLOG.md` (C4 +
  §URGENT) are revised rather than rewritten. New:
  `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md` (operator-only identifiers),
  `TMOBILE_PRODUCTION_READINESS.md` (20 gates, 1 closed),
  `api/tests/fixtures/tmobile_pit_success_20260721T031833Z.json` (sanitized
  record), and two read-only operator scripts. **PIT success is explicitly not
  production readiness** — production onboarding must be confirmed with T-Mobile
  before the first production attempt, since the PIT gateway itself needed
  explicit recreation to work. D-003 (key rotation gate) is unchanged.

### D-018 — Block T-Mobile operations whose endpoint contract we derived rather than received
- **Date:** 2026-07-21 · **Status:** Accepted
- **Context:** T-Mobile Engineering authorized True911 to "run other API calls to
  complete your development and testing cycle." Building the certification
  harness established that this repository contains **no T-Mobile OpenAPI spec,
  Postman collection, PDF, or reference implementation**. Seven of the eight
  wholesale operations in `tmobile_taap.py` use paths produced by our own string
  join (`_subscriber_path`), and no response schema for any of them has ever been
  observed. That derivation is **provably wrong**: the one operation we can
  verify succeeds at `/wholesale/v1/subscriber/activation` only because
  `TMOBILE_ACTIVATION_PATH` overrides the derived `/wholesale/v1/subscriber/activate`.
  Authorization to call an API is not a specification for it.
- **Decision:** Introduce a provenance-gated operation inventory
  (`app/integrations/tmobile_operations.py`). An operation may be sent only when
  its provenance is `CONFIRMED_BY_LIVE_RESPONSE` or `TMOBILE_WRITTEN_SPEC`, and
  its risk class is understood. Everything else is **blocked in preview and in
  run alike** — previewing a request we may never send only invites sending it.
  A block states the exact questions T-Mobile must answer; lifting one requires
  their written answer recorded in the repository plus a reviewed provenance
  change and a golden test. **It is never a config toggle.** This extends the
  "never guess a header name" rule (D-017) from headers to endpoints.
- **Consequences:** `activate_subscriber` is the only sendable operation; the
  other seven are blocked but remain implemented and mock-tested. The next
  T-Mobile interaction is a documentation request, not an API call, and the
  certification plan's steps 6-11 are gated on it. Adds:
  `tmobile_lifecycle.py` (state machine + three nested ICCID allowlists, empty by
  default, `destructive ⊆ lifecycle ⊆ read-only`, first-activation ICCID
  protected), `scripts/tmobile_pit.py` (single operator entry point, preview by
  default, eight independent gates), and five docs. Client methods
  (`suspend`/`restore`/`deactivate`) remain individually ungated — the safety
  lives in the harness, so a direct call still bypasses it; adding a fail-closed
  guard to the client itself is tracked in `TMOBILE_PRODUCTION_READINESS.md` #15.

### D-019 — Reconcile against authorized vendor documentation without publishing it
- **Date:** 2026-07-21 · **Status:** Accepted
- **Context:** Authorized T-Mobile Wholesale documentation was obtained. Reconciling
  against it found the previously derived paths wrong for **every** operation, four
  wrong HTTP methods, and a wrong request body on every lifecycle call — confirming
  D-018's blocking decision. But this repository is **public**, and the vendor
  material is confidential to Manley Solutions as the intended recipient, with a
  legend prohibiting retransmission. Committing the contract matrix, the response-code
  catalogue, or sample payloads would disseminate it to the open internet.
- **Decision:** Split the record. The **public repository** carries only the minimum
  facts needed for the integration to function — exact paths, methods, wire field
  names, header names, state logic, safety gates, fabricated tests, and a status-only
  readiness table. The **private evidence store** (`.private-evidence/`, gitignored)
  carries the contract matrix, the full response-code analysis, source citations and
  document hashes. Public references use an opaque evidence reference
  (`TMO-REST-RECON-001`), never a document title, version, page, or quotation.
  Separately: **documentation does not authorize sending.** Readiness became a gate
  distinct from provenance, and only real PIT evidence opens it.
- **Consequences:** All eight non-activation operations remain live-blocked despite
  now being fully documented. A fail-closed guard runs inside the client before the
  OAuth token is fetched, closing the direct-call bypass tracked as readiness item
  #15. The public response-code mapping is a reviewed subset, not an import, and a
  test prevents it growing into a catalogue. Automated confidentiality guards assert
  no vendor binary, hash, reconstructing citation, or absolute operator path is
  committed. Machine-readable API definitions remain desirable for structural
  validation; a few contract questions stay open and their operations stay blocked.

### D-020 — Synchronous acceptance is not completion; callbacks apply only on exact correlation
- **Date:** 2026-07-21 · **Status:** Accepted
- **Context:** The typed contract foundation had to decide when a subscriber's state
  actually changes. The carrier answers a mutation immediately to confirm the request
  authenticated and validated, then reports provisioning completion separately and
  asynchronously. Treating the immediate answer as terminal would record state we have
  no evidence for. Separately, callbacks arrive with several possible correlation
  identifiers, and the tempting fallbacks — "the most recent pending transaction",
  nearest timestamp, matching ICCID alone — all misattribute results under replay,
  retry, or concurrency.
- **Decision:** (1) Every mutation moves a line into an explicit `*_pending` state on
  synchronous acceptance; only an asynchronous result settles it to a terminal state.
  Suspension is the documented exception where the synchronous answer is terminal.
  (2) Callbacks correlate by exact identifier only, in precedence order
  partner-transaction-id → workflow id → service-transaction id. There is no
  latest-pending and no timestamp fallback. Anything uncorrelatable, ambiguous,
  duplicated, superseded, conflicting, or not understood is **quarantined** with its
  evidence and leaves state untouched. (3) Five state facets are tracked separately
  (carrier-reported, workflow, expected, last-confirmed, reconciliation) rather than
  collapsed into one string. (4) Mutations fail closed on unknown or unconfirmed
  state; reads do not, because a query is how the state is learned.
- **Consequences:** A wrong lifecycle result is materially worse than an unapplied
  one, so the system prefers quarantine to a plausible guess and will accumulate
  callbacks needing human reconciliation — an operator surface for that queue is
  required before live synchronization. Duplicate deliveries are idempotent via a
  stable key derived from correlation ids and outcome, never arrival time. Durable
  persistence of lifecycle transactions is deferred while the migration chain is
  branched; the structures are typed and persistence-ready. Typed models confer no
  permission to send — activation remains the sole generally sendable
  operation, and then only through the operator harness.

### D-2026-08-28 — Certification maturity is not send authorization

**Decision.** An operation's certification maturity (`ReadinessState`) and its
authorization to transmit (`SendAuthorization`) are separate, independent
concepts. Maturity may **veto** a send; it may **never grant** one.

**Why.** Readiness previously doubled as authorization
(`LIVE_SENDABLE_READINESS = {PIT_TESTED, PRODUCTION_APPROVED}`). Honestly
recording that an operation had passed one *controlled, single-run* PIT
certification would therefore have converted it into one that could be sent
freely — one certified call buying unlimited uncertified ones, arrived at as a
side effect of bookkeeping rather than as a decision anybody made.

**Consequences.**

- The canonical maturity ladder is unchanged and remains the only one:
  `IMPLEMENTED → MOCK_CERTIFIED → PIT_TESTED → PRODUCTION_APPROVED`.
- `PIT_TESTED` means *live PIT certified*: exercised against the carrier PIT
  gateway with evidence retained. It does not mean production authorized.
- Authorization is an explicit, reviewed, per-operation declaration.
  `PRODUCTION` requires `PRODUCTION_APPROVED` — necessary for ordinary
  sendability, sufficient for nothing: provenance, classification, allowlists,
  the lifecycle state machine, operator confirmations, feature flags and
  certification blockers all still apply.
- A certification blocker outranks both maturity and route, at any state.
- Enforced at import by `_validate_authorization_policy()`; pinned by
  `api/tests/test_tmobile_send_authorization_matrix.py`.

### D-021 — Customers own an operational overlay; provisioning, identity and E911 stay governed
- **Date:** 2026-09-30 · **Status:** Accepted
- **Context:** RH is approaching go-live on the registry-backed Command Center, but
  every routine change (a contact, a connection's purpose, "this is our elevator
  line") still meant emailing Manley. The customer needs to administer their own
  portfolio without being able to touch carrier / device / network provisioning or
  assert life-safety verification.
- **Decision:**
  1. **Three classes of data** (`customer/CUSTOMER_SELF_SERVICE.md` §2):
     *customer-managed* (written directly, audited old/new), *request-based*
     (creates a governed `CustomerServiceRequest`; nothing changes until
     operations act), *system-managed* (refused with 403; a mixed payload is
     refused whole).
  2. Customer-managed values live in an **overlay** (`customer_managed_fields`)
     beside the system records — never inside them. The Portfolio Registry
     building remains the canonical identity; a customer display name is a
     preference layered on top.
  3. **E911 is never customer-asserted.** An attestation is stored with
     provenance and routed to the existing E911 review queue; `verified` derives
     only from the official record; completing an E911 request does not verify.
  4. The E911 **attestation** is reserved to `CUSTOMER_ADMIN`; `CUSTOMER_MANAGER`
     keeps contacts + requests; read-only roles stay read-only.
  5. Everything ships behind `FEATURE_CUSTOMER_SELF_SERVICE` + tenant allowlist +
     optional user allowlist (default off).
- **Consequences:** A new migration (`053`, three tables, off the single head
  `052`). Every customer mutation and request transition is an append-only
  `customer_activity_events` row mirrored into `ActionAudit`. Operations work the
  queue through `/api/customer-requests` (API only in this slice). The go-live
  audit distinguishes SYSTEM BLOCKERS from CUSTOMER ACTIONS, so legitimate
  post-login customer work (E911 confirmation, contacts) never blocks an invite.

### D-022 — Customer trust rule: UNKNOWN ≠ FAILED, UNKNOWN ≠ PROTECTED
- **Date:** 2026-09-30 · **Status:** Accepted
- **Context:** Reviewed from the RH customer admin's seat, the portal showed
  "29 of 45 protected", "0% E911 verified" and a ~45/100 health score. A reasonable
  customer would read that as "most of our life-safety infrastructure is broken",
  but the data only says True911 lacks monitoring linkage, documentation or
  verification evidence for part of the portfolio.
- **Decision:**
  1. Every customer-facing status is one of three evidence classes:
     **KNOWN GOOD** (evidence-backed Protected → "Monitored"), **KNOWN PROBLEM**
     (Critical / Attention Needed → "Needs attention"), **UNKNOWN** (no linked
     monitoring → "Being reconciled"; anything else unconfirmed → "Status being
     confirmed"). UNKNOWN renders neutral — never red, never green.
     (`serialize.operational_state`.)
  2. A known problem always wins, even for a location without a monitoring link;
     failures are never hidden.
  3. Customers see **separate dimensions** — service status, monitoring coverage,
     E911 readiness, portfolio setup — never a blended health/completeness score as
     if it were service health. Internal views keep the composite scores.
  4. Work is labelled by **owner**: customer actions (confirm E911, add contacts,
     answer a request) vs True911 / operations actions (prepare E911 records,
     reconcile monitoring, resolve reviews). The customer is never made
     responsible for True911's reconciliation work.
- **Consequences:** Additive API fields (`operational_state`, `monitoring_linked`,
  `operational_states`, `e911_verified_locations`, action-center `tiers` +
  `being_reconciled`); the six-label vocabulary (D-005) is unchanged underneath —
  this is the customer presentation layer over it. No scoring, E911, registry or
  ownership-boundary change.


### D-023 — Life-Safety Service and Connection canonical model
- **Date:** 2026-09-30 · **Status:** Accepted (PR #186a foundation; customer read model is PR #186b)
- **Context:** The RH dashboard's "28 telephone connections" was the count of
  distinct telephone numbers per building, not of life-safety connections. Read-only
  audits showed FACPs needing two paths, elevator lines, unlabeled lines, a carrier
  migration (Jacksonville: six legacy lines replaced by seven) and a building whose
  records were historically merged with other locations (Memphis). Counting numbers
  conflated service, connection and asset.
- **Decision:**
  1. Canonical hierarchy **Building -> LifeSafetyService -> LifeSafetyConnection ->
     CommunicationsAsset**. SERVICE != CONNECTION != ASSET. A connection is a
     REQUIRED path of a CONFIRMED/APPROVED, non-REJECTED, CURRENT service:
     ELEVATOR 1, EMERGENCY_PHONE 1, FACP 2. No number is fabricated for a path.
  2. **Confidence** (evidence), **approval** (operator) and **lifecycle**
     (CURRENT/DECOMMISSIONED/REPLACED/SUSPENDED/HISTORICAL/UNKNOWN) are separate
     axes. Evidence-CONFIRMED services count without per-service approval;
     PROBABLE/UNRESOLVED/REJECTED never count; operator decisions override
     automated reconciliation.
  3. Placement priority: operator > asset identifier > telephone mapping >
     facility name > store number > address > specific account alias. Historical
     mappings and generic/parent names are supporting evidence only. A building an
     operator marks BUILDING_IDENTITY_SUSPECT is reconciled strictly (its own
     registry artefacts are not authoritative).
  4. Operator ground truth lives in an append-only, supersedable
     `operator_decisions` ledger fed from an external, uncommitted file.
  5. Runs read Zoho live (read-only) with retrieval metadata; an unavailable source
     degrades the run; a degraded projection is NEVER persisted (enforced in the
     writer, no override) — never silently stale.
  6. The legacy distinct-number metric is retired from the customer view; no
     canonical total is shown until #186b and customer-use approval.
- **Consequences:** Migration `054` (eight additive tables, off head `053`; fails loudly if any
  already exists rather than adopting an unknown schema);
  `app/services/canonical/`; dry-run-default scripts `canonical_service_backfill`
  and `canonical_operator_decisions`; flags `FEATURE_CANONICAL_SERVICE_MODEL` +
  `CANONICAL_SERVICE_MODEL_TENANT_ALLOWLIST` reserved (off). E911 untouched. Spec:
  `docs/customer/CANONICAL_SERVICE_MODEL.md`.

### D-024 — Operational source snapshots are immutable, tenant-attributed evidence
- **Date:** 2026-09-30 · **Status:** Accepted (PR #187)
- **Context:** Lifecycle reconciliation for RH needs NAPCO, T-Mobile/Infatrac,
  Verizon and Red Pocket inventory evidence. Every existing ingestion path
  (NAPCO portal import, Verizon sync, Zoho staging) overwrites live rows in place;
  T-Mobile and Red Pocket had no inventory ingestion at all. Carrier and dealer
  exports contain many customers.
- **Decision:**
  1. An export is imported as an **immutable snapshot** (migration `055`):
     dry-run by default, explicit `--apply`, SHA-256 de-duplicated per (tenant,
     source), never updated or deleted; newer exports are new snapshots.
  2. Each record stores the **raw source status** beside the interpreted lifecycle
     and the versioned rule; **unmapped statuses are UNKNOWN, never active**.
     Parser, status-map and attribution-rule versions are recorded per snapshot.
  3. A row is stored for a tenant only on an exact identifier match unique to that
     tenant (HIGH) or an explicit, specific tenant-profile label rule (MEDIUM);
     ambiguous rows are reported, never stored; a label never establishes a
     building.
  4. Attributes are allow-listed; dealer and central-station contact/account
     numbers are never stored; a raw-row SHA-256 preserves provability.
  5. Freshness for inventory certification is 7 days from the source effective
     time; it is not a monitoring-health threshold. Effective time precedence:
     operator `--effective-at` > authoritative source-native timestamp > file-name
     timestamp only when its timezone is established > UNDATED (never fresh).
  6. Importing changes nothing else: no source-system writes, no canonical service,
     E911, registry or operator-decision changes.
- **Consequences:** `app/services/source_snapshots/`,
  `scripts.source_snapshot_import`, `SOURCE_SNAPSHOT_FRESHNESS_DAYS`. Spec:
  `docs/customer/SOURCE_SNAPSHOTS.md`. Consumed by #188.

### D-025 — RH Customer Completion Program: reference-customer gates
- **Date:** 2026-09-30 · **Status:** Accepted
- **Context:** The objective moved from "make the RH portal usable" to "make RH the
  reference customer implementation". D-021 treated E911 confirmation as a
  post-login customer action that never blocks an invite.
- **Decision:** RH launches only through the program in
  `docs/customer/RH_COMPLETION_PROGRAM.md` (PRs #187–#193) and its strict
  READY_FOR_CUSTOMER gate. **This supersedes the D-021 consequence that E911 never
  blocks an invite:** every applicable current line must be VERIFIED from
  authoritative provider evidence (legacy "validated"/"confirmed" is insufficient)
  or covered by an unexpired SUPER_ADMIN `E911_LAUNCH_EXCEPTION` (max 30 days,
  never displayed as VERIFIED). E911 applicability, geocoding, monitoring, RH Test
  and Jacksonville rules are recorded in the program document. Operator knowledge
  is persisted only through the governed decision ledger with explicit
  authorisation, never as an engine rule. 45 locations is not a target.
- **Consequences:** Judy is not invited and the canonical read model is not enabled
  for her until READY_FOR_CUSTOMER + RH Test acceptance + explicit approval; a
  fresh invitation is then generated.
