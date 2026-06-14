# True911+ — PROJECT STATE

> **Read this first.** This document is written so a future Claude session (or any
> engineer) can resume work from it alone. Keep it accurate — update it at the end
> of every session (Operating Loop step 16).
>
> Last updated: 2026-06-13. Branch at time of writing: `feat/tmobile-async-callback-location`.

## 1. Current Objective

Stand up the **project operating system** (this docs set) and use it to drive the
next phase of work safely. No application behavior is being changed by this task —
it is documentation and analysis only.

The active product direction is to mature True911 into an **Emergency
Communications Assurance Platform** (see `docs/MISSION.md` and
`docs/ASSURANCE_ENGINE.md`): a read-only, deterministic, explainable Assurance
Label per device → site → customer, layered on the existing telemetry, health,
lifecycle, and E911 data.

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

- **BACKLOG C1 (private-key remediation)** — repo cleanup committed in this branch;
  awaiting operator key rotation + Render secret update (not yet pushed / no PR).
- **This operating-system docs set** (MISSION / OPERATING_LOOP / MASTER_PLAN /
  PROJECT_STATE / BACKLOG / ARCHITECTURE) — created 2026-06-13.
- **T-Mobile async callback location** — on the current branch; verify merge state.
- **Integrity / Belle Terre onboarding** — `app/seed_integrity.py` built and tested,
  **not yet applied to prod** (3 LM150 VoLTE elevator phones; first managed-POTS-
  style pilot dataset for the hardware-agnostic health layer).

## 4. Blockers

- **LLLM Phase 1b** (external egress, `LLLM_ALLOW_EXTERNAL=true`) — blocked on
  **governance approval** per `docs/AI_OPERATIONAL_SAFETY.md` §3 and
  `docs/LLLM_PHASE1_ROLLOUT.md` §4. Do not flip without it.
- **Zoho lifecycle source-of-truth** — additive staging plan exists; promotion to
  an additive `lifecycle_status` is a separate, later, explicitly-gated phase.
- **Red Tag Line / US Courts Tampa** — first managed-POTS deployment; readiness
  review + phased plan pending (see project memory).

## 5. Known Risks (snapshot — full list with severity in BACKLOG.md)

1. **Committed private key (C1)** — ⏳ repo cleanup DONE (file removed, `.gitignore`
   hardened, placeholder + remediation doc added); **key rotation still pending as a
   manual operator step** (generate new pair, register with T-Mobile, set
   `TMOBILE_PRIVATE_KEY_PEM` Render secret). Leaked key in history must be treated as
   compromised. See `docs/TMOBILE_PRIVATE_KEY_REMEDIATION.md`. *(Critical/Security)*
2. **T-Mobile PIT callback unauthenticated at app layer** — life-safety-adjacent
   inbound webhook relies solely on Cloudflare WAF + passive IP audit. *(Safety/Security)*
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
