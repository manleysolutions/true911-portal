# True911+ — PROJECT STATE

> **Read this first** (after `CONSTITUTION.md` and `DECISIONS.md` — the AI Session
> Rule, `CONSTITUTION.md` P4; entry point `README.md`). Written so a future session
> can resume from it alone. Keep it accurate — update at the end of every session
> per the Documentation Freshness rule (P2 / Operating Loop §0a).
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Last updated: 2026-06-23. Branch at time of writing: `main` (in sync with origin).

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
