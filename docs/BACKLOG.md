# True911+ — BACKLOG

> Living document. Categorized by urgency, then ranked within category by the
> **priority order in `CONSTITUTION.md` §3**. Last reviewed: 2026-06-23.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`. The
> standing "never build" vetoes are authoritative in `CONSTITUTION.md` §7
> (rationale in `ASSURANCE_PLATFORM_SPEC.md`). Entry point: `README.md`.
>
> This backlog is derived from the codebase audit. Items marked **Needs
> Verification** require confirming a fact before acting. Nothing here authorizes
> implementation — see `OPERATING_LOOP.md` §3 Hard Stops.

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

### Phase 4 — Launch
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
  🚧 *External dependency — waiting on T-Mobile Engineering (Aman).* Activation now
  reaches the T-Mobile activation service (`POST /wholesale/v1/subscriber/activation`)
  with validated OAuth/PoP, the corrected endpoint, and the required `partner-id` /
  `sender-id` headers (PR #122) plus correlation-ID + partner-transaction-ID logging
  (PR #121). T-Mobile rejects `partnerID=128` with `400 GENS-0003`. **Done (True911
  side):** headers renamed to `partner-id`/`sender-id`; diagnostics in place; trace IDs
  logged. **Open (T-Mobile side):** confirm the correct `partnerID` value/format and
  that the headers are now read. **Follow-up (small, env or 1-line):** if T-Mobile
  also requires lowercase `account-id` for post-activation ops, rename `X-Account-Id`
  (currently unchanged). Do not re-fire live activations to guess the value. See
  `PROJECT_STATE.md` §3/§4 for trace identifiers. *Revenue / Reliability.*

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
