# True911+ — PROJECT STATE

> **Read this first** (after `CONSTITUTION.md` and `DECISIONS.md` — the AI Session
> Rule, `CONSTITUTION.md` P4; entry point `README.md`). Written so a future session
> can resume from it alone. Keep it accurate — update at the end of every session
> per the Documentation Freshness rule (P2 / Operating Loop §0a).
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Last updated: 2026-06-14. Branch at time of writing: `docs/docos-integrate-existing`
> (documentation-only; not committed at time of writing).

## 1. Current Objective

**Phase 0 / PR-1a — Identity Engine foundation.** Implement the pure, deterministic
`IdentityResolver` (`api/app/services/identity/`): proof-chain-first
(`Facts → Proof Chain → Decision`), Resolved/Ambiguous/Orphan derived from the
chain, never guesses. **Inert** — nothing in the running app imports it (no
router/endpoint/flag/write/migration). Table-driven tests added; full suite green
(2343 passed). See `TRUTH_ENGINE.md` and `DECISIONS.md` D-011…D-014.

Completed since last update: the **Documentation Operating System** is live
(PRs #117/#118 merged) — Constitution, Product Vision (+North Star), Data Model,
Truth Engine, Decisions, Glossary, README; existing docs defer to it. **CI secret
scanning** (gitleaks, PR #116) is live and blocking.

The active product direction is the **operating system for life-safety
communications assurance** (`CONSTITUTION.md`, `PRODUCT_VISION.md`): a read-only,
deterministic, explainable Assurance Label per device → site → customer, with
evidence/proof behind every status. The **Identity Engine** is the first layer
(Reality → Identity Engine → Truth Engine → Assurance Engine → AI → Automation).

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

1. Get user approval of this operating-system docs set and the priority order.
2. Triage the **Critical** items in `BACKLOG.md` (private key, callback auth) into a
   single smallest-safe-change PR plan each.
3. Confirm Render service/DB names and DB backup posture (close the §11 ARCHITECTURE
   verifications).
4. Pick the first safe implementation phase with the user (recommended:
   CI hardening, then the private-key remediation).

## 9. How to Resume

1. Read `docs/MISSION.md` (§3 priority order), this file, then `docs/BACKLOG.md`.
2. `git status` clean; identify branch.
3. Run the Operating Loop (`docs/OPERATING_LOOP.md`) for the chosen objective.
4. Verify with `cd api && python -m pytest -q` and `cd web && npm run build`.
5. Update this file before you stop.
