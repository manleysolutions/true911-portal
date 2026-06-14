# True911+ — ARCHITECTURE

> Living document. Last reviewed: 2026-06-13. Reflects the repository as of branch
> `feat/tmobile-async-callback-location`. Counts below were measured from the repo;
> if you change structure, update them. Items the author could not fully confirm
> are marked **Needs Verification**.
>
> **Product context:** this doc describes *how the system is built*. For *what we
> are building and why*, see the product constitution —
> `docs/PRODUCT_MANIFESTO.md` (philosophy), `docs/ASSURANCE_PLATFORM_SPEC.md` (the
> assurance model + proof contract), and `docs/ASSURANCE_ENGINE.md` (the
> deterministic engine that is the architectural spine every customer surface
> reads). The evidence/proof model (`View Proof`, the Assurance Timeline) is
> served read-only from existing tables — no new operational columns; see the
> Assurance Engine spec.

## 1. System Architecture

True911+ is a multi-tenant web platform with three runtime tiers plus a scheduled
job, all deployed on Render (`render.yaml` is authoritative).

```
                         Cloudflare (edge, WAF for T-Mobile callback)
                                       │
        ┌──────────────────────────────┴───────────────────────────────┐
        │                                                               │
  true911-web-prod (static)                                    true911-api (web)
  React + Vite + Tailwind                                  FastAPI + SQLAlchemy async
  served as static dist/                                   uvicorn, /api/* + /tmobile/*
        │  VITE_API_URL ─────────────── HTTPS /api ───────────────►│
                                                                   │
                                  ┌────────────────────────────────┼───────────────┐
                                  │                                 │               │
                          true911-db (Postgres 16)        true911-redis (RQ)   external APIs
                                  │                                 │         (Zoho, VOLA,
                                  │                                 │          Verizon, T-Mobile,
                          true911-worker (RQ) ◄─────── enqueues ────┘          Telnyx, Anthropic)
                                  │
                          true911-device-health-sync (cron */5 min)
                                  └── updates Device/SIM health fields
```

### Render services (`render.yaml`)
| Service | Type | Role |
|---|---|---|
| `true911-db` | Postgres 16, starter | Primary datastore |
| `true911-redis` | Redis, starter | RQ job queue + LLM cache backing |
| `true911-api` | Python web | FastAPI app (`app.main:app`) |
| `true911-worker` | Python worker | RQ consumer (`worker.py`) |
| `true911-device-health-sync` | Cron `*/5 * * * *` | `python -m app.sync_device_health` |
| `true911-web-prod` | Static | Vite build, SPA rewrite `/* → /index.html` |

> **Needs Verification:** project memory references DB name `true911-prod-db` and
> service `true911-api`; `render.yaml` declares `true911-db`. Confirm the live
> Render dashboard names before relying on either.

### API start command
`alembic upgrade head && python -m app.seed && uvicorn app.main:app …`
Migrations run on every deploy; the seed step is a no-op unless `APP_MODE=demo` /
`SEED_DEMO=true` (prod sets `APP_MODE=production`, `SEED_DEMO` unset). See SWAT
note in `BACKLOG.md` about seed-on-critical-path.

### Backend scale (measured)
~64 SQLAlchemy models, 54 routers, 47 Alembic migrations (001–047), 80 pytest
files. Frontend: 55 page components. This is a large, mature surface — favor
reuse and read existing code before adding.

## 2. Data Flow

### 2a. Telemetry → Health → Assurance (the spine)
```
Heartbeats (POST /api/devices/{id}/heartbeat)
Carrier events (Verizon poll, T-Mobile callback)           ┌─ services/health/ (Health Normalizer)
Telnyx CDR liveness                              ──────────►│   fuses signals → CanonicalDeviceState
VOLA TR-069 sync timestamps                                └─ → NormalizedStatus (Online/Offline/
                                                                  Attention/Unknown)
                                                                       │
   Commercial lifecycle (Zoho) ─┐                                      ▼
   Deployment/install lifecycle ─┼──────────────────────────► services/assurance/ (Assurance Engine)
   E911 / compliance ───────────┘                              composes axes → Assurance Label
                                                               (Protected / Attention / Critical /
                                                                Inactive / Pending / Unknown)
```
Both the Health Normalizer and Assurance Engine are **read-only and flag-gated**
(`FEATURE_HEALTH_NORMALIZER`, `FEATURE_ASSURANCE_ENGINE`). Today the Health
Normalizer's only consumer is the AI Health Summary; the Assurance Engine is
backend-first and off by default.

### 2b. Inbound webhook → archive → worker → device field
```
External POST (Zoho / QB / Telnyx / VOLA / T-Mobile callback)
   → router authenticates (see §6)
   → archive raw to integration_event / integration_payload (idempotency key)
   → enqueue RQ job (webhook.*, integration.process.*)
   → true911-worker dispatches handler → updates Device/SIM/Line fields
```

### 2c. RQ dispatch
`worker.py` → `dispatch(job_id)` loads the `Job` row, marks `running`, increments
attempt, imports the handler from a registry by string, runs it async, marks
`completed`/`failed`. Retry uses exponential backoff (`min(10·2^attempt+jitter,
300s)`, max 3). If Redis is down, the `Job` row is created `queued` but not
enqueued (graceful degradation). Two known historical pitfalls are documented in
project memory: jobs stuck at `queued/attempt=0` (PR #61) and env-var-per-service
drift where a flag is active on `api` but inert on `worker` (PR #63).

## 3. API Design

- FastAPI, routers mounted under `/api/*` in `app/main.py`; the T-Mobile callback
  router is mounted at `/tmobile/wholesale` (no `/api` prefix — it is an external
  carrier callback surface).
- Pydantic schemas in `app/schemas/`. Async SQLAlchemy sessions via
  `app/database.py` / `app/dependencies.py`.
- Cross-cutting: `RequestVisibilityMiddleware` stamps every response with
  `X-Request-ID` and logs one line per request; a global exception handler returns
  JSON 500s so CORS headers survive errors (and the request_id is correlatable).
- Feature surfaces self-gate: routers like `llm`, `device_health`, `assurance`
  are registered unconditionally but return **404 when their flag is off**, so
  deploying the code is a no-op until the env var flips.
- Public, unauthenticated probes exist: `GET /api/health`, `GET /api/config/features`,
  `GET /api/debug/cors`. `GET /api/health/auth` is SuperAdmin-only and returns a
  JWT-secret *fingerprint* (never the secret).

## 4. Integrations

Detailed inventory lives in `docs/INTEGRATIONS.md` and per-vendor audit docs. Summary:

| Integration | Direction | Auth | Status |
|---|---|---|---|
| **Verizon ThingSpace** | Outbound (SIM inventory/status) | OAuth2 (4 selectable modes) | **Live, configurable** |
| **VOLA / FlyingVoice TR-069** | Outbound (device mgmt, reboot, params) | Token-in-body | **Live, gated** (read/write allowlist + denylist) |
| **T-Mobile Wholesale TAAP/PoP** | Outbound (activation, lifecycle) | OAuth2 + per-request RSA PoP JWT | **Live, hard-gated** (`TMOBILE_PIT_LIVE_CALLS_ENABLED`, PIT env) |
| **T-Mobile PIT callback** | Inbound (async activation result) | **None at app layer** (Cloudflare WAF + passive IP audit only) | Logging-only by default; `FEATURE_TMOBILE_CALLBACK_INGEST` archives + promotes |
| **T-Mobile IoT (X-API-Key)** | Outbound | API key | **Stub** (not configured) |
| **AT&T IoT** | Outbound | — | **Stub** (not configured) |
| **Telnyx** | Inbound webhook + outbound (DID/E911/SIM) | Ed25519 (gated by `TELNYX_PUBLIC_KEY`) | Registered; signature verification **gated/partial** |
| **Zoho CRM** | Inbound webhook + outbound (account/deal sync) | `X-Webhook-Secret` (in) / OAuth2 refresh (out) | **Live** |
| **Zoho Subscription_Mgmt ingest** | Inbound webhook | Same as Zoho CRM | **Staging, gated** (`FEATURE_ZOHO_SUBSCRIPTION_INGEST`); writes shadow tables only |
| **Zoho Desk** | Outbound (ticket escalation) | OAuth2 refresh | **Live, optional stub** (empty domain → stub) |
| **QuickBooks** | Inbound webhook only | HMAC-SHA256 (`INTEGRATION_WEBHOOK_SECRET`) | **Live** (inbound only) |
| **Anthropic (LLM)** | Outbound | `x-api-key` | **Live, doubly gated** (`FEATURE_LLLM` + `LLLM_ALLOW_EXTERNAL`) |

## 5. Feature Flags

All `FEATURE_*` flags default **off** in `api/app/config.py`. They are the primary
safety mechanism. Current production overrides come from `render.yaml`.

| Flag | Default | Prod (`render.yaml`) | Effect |
|---|---|---|---|
| `FEATURE_LLLM` | false | **true** | Enables `/api/llm` AI Health Summary surface |
| `LLLM_ALLOW_EXTERNAL` | false | **false** | Hard external-egress switch; off → deterministic only |
| `FEATURE_HEALTH_NORMALIZER` | false | **true** | Routes AI Health Summary through `services/health/` |
| `FEATURE_DEVICE_HEALTH` | false | off | Exposes `/api/device-health` read-only APIs |
| `FEATURE_ASSURANCE_ENGINE` | false | off | Exposes `/api/assurance` read-only label APIs |
| `FEATURE_TMOBILE_CALLBACK_INGEST` | false | off | Archive + promote T-Mobile callbacks |
| `FEATURE_TMOBILE_CALLBACK_IP_AUDIT` | false | off | Passive IP logging on callback URLs |
| `TMOBILE_PIT_LIVE_CALLS_ENABLED` | false | off | Hard switch for real T-Mobile activations |
| `FEATURE_ZOHO_SUBSCRIPTION_INGEST` | false | off | Stage Zoho subscription events (additive) |
| `FEATURE_ZOHO_STATUS_NORMALIZER` | false | off | Populate `lifecycle_state` from status normalizer |
| `FEATURE_ZOHO_BACKFILL` | false | off | Pull-backfill Zoho records (write path) |
| `FEATURE_DEVICE_SITE_CORRECTION` | false | off | Gated write: device→site correction planner |
| `FEATURE_CUSTOMER_RETIREMENT` | false | off | Gated write: customer retirement planner |
| `FEATURE_SAMANTHA` | false | off | AI/Samantha nav item |
| `FEATURE_LINE_INTELLIGENCE` | false | off | Line Intelligence Engine endpoints |
| `ALLOW_PUBLIC_REGISTRATION` | false | off | Public self-registration |

Frontend mirror flags (`VITE_FEATURE_*`) control whether the UI *renders* a
surface; the backend flag controls whether the data exists. Both must agree.
**Pitfall:** flags are set per Render service — a flag on `true911-api` is inert
on `true911-worker` unless also set there (see project memory, PR #63).

## 6. Security Model

- **AuthN:** JWT (HS256) access + refresh tokens. Access TTL 480 min, refresh 30
  days. Tokens stored in browser `localStorage` (`t911_token`, `t911_refresh`).
  401 triggers a single transparent refresh; failure clears tokens → `/login`.
- **AuthZ:** `permissions.json` at repo root is the **single source of truth**,
  loaded by both backend (`services/rbac.py`, via `dependencies.require_permission`)
  and frontend (`AuthContext.jsx` `can()` via the `@permissions` Vite alias). The
  loader raises on a missing/invalid file — the API refuses to start without it.
  SuperAdmin (when not impersonating) bypasses all permission checks.
- **Tenant isolation:** SuperAdmin impersonation sets an `X-Act-As-Tenant` header
  scoping data to the target tenant; impersonated sessions are read-only.
  Internal-only surfaces (Registration review/convert) are gated by *real* tenant
  context (`INTERNAL_TENANT_IDS`, default `default`), not role alone.
- **Webhook auth:** three patterns — `X-Webhook-Secret` constant-time compare
  (Zoho), HMAC-SHA256 with optional timestamp-skew replay protection (QB / generic,
  `INTEGRATION_HMAC_SKEW_SECONDS=300`), and Ed25519 (Telnyx, gated). The T-Mobile
  PIT callback is intentionally **unauthenticated at the app layer** today —
  enforcement is the Cloudflare WAF plus an optional passive IP audit. See risks.
- **CORS:** when `CORS_ORIGINS="*"` (the default) the app uses an
  `allow_origin_regex=".*"` with `allow_credentials=True`; prod sets explicit
  origins. The wildcard default is dev-only and a risk if ever shipped.
- **Secrets:** `JWT_SECRET`, webhook secrets, and bootstrap admin password use
  Render `generateValue`. Vendor creds are dashboard-managed (`sync: false`).
  `app/main.py` logs a non-reversible fingerprint of `JWT_SECRET` at startup and
  warns (but does **not** refuse to start) if the dev default is in use.

## 7. User Roles

Canonical roles (normalized in `services/rbac.py` and `AuthContext.jsx`):

| Role | Level | Purpose |
|---|---|---|
| **SuperAdmin** | 4 | Platform owner; bypasses RBAC when not impersonating; can "View As". |
| **Admin** | 3 | Tenant administrator; most management permissions. |
| **Manager** | 2 | Operational management (incidents, command, verification). |
| **DataSteward** | 1.7 | Onboarding review, data stewardship, import verification. |
| **DataEntry** | 1.5 | Import operator; customer/site/device data entry. |
| **UX_QA_ANALYST** | n/a (additive) | Platform Operations / UX & QA analyst; read + import + export, additive grants. |
| **User** | 1 | Customer end-user; read-mostly, scoped to their tenant. |

Role-specific landing pages and nav are defined in `web/src/App.jsx` /
`Layout.jsx` (e.g. SuperAdmin → `/Command`, DataSteward → `/onboarding-review`).

## 8. External Dependencies

- **Runtime:** Render (web, worker, cron, Postgres 16, Redis), Cloudflare edge.
- **Backend libs:** FastAPI, SQLAlchemy (async), Alembic, pydantic-settings, RQ,
  httpx, asyncpg (see `api/requirements.txt`).
- **Frontend libs:** React, Vite, Tailwind, React Router, TanStack Query, Radix
  UI / shadcn components, Leaflet (maps) (see `web/package.json`).
- **Third-party services:** Zoho CRM + Desk, VOLA (FlyingVoice TR-069), Verizon
  ThingSpace, T-Mobile Wholesale TAAP, Telnyx, Anthropic, SMTP (SendGrid-style).

## 9. Design Decisions (the "why")

- **One permissions file, two consumers.** Eliminates frontend/backend RBAC drift.
- **Flag-gated, 404-when-off routers.** Lets code merge to `main` and deploy
  safely long before a capability is enabled — decouples deploy from release.
- **Deterministic fallback for all AI.** The platform must produce correct,
  explainable output with zero external LLM calls; AI is an enhancement, never a
  dependency. Egress is independently gated from the feature itself.
- **Additive staging tables for lifecycle truth.** Zoho lifecycle lands in
  `zoho_subscription_records` / `external_record_map` / `zoho_payload_observations`
  — never overwriting `sites/devices/lines.status`. Operational and commercial
  status are kept on separate axes by hard preference.
- **Dry-run-first gated write planners.** `plan_device_site_correction.py` and
  `plan_customer_retirement.py` only write with `--apply` *and* their flag *and*
  hard safety gates passing; customer-scoped; never delete.
- **Vendor logic isolated in adapters.** `services/device_health/adapters/*` keeps
  the health core hardware-agnostic; vendors (VOLA, T-Mobile, …) are plug-ins.

## 10. Refactoring Candidates

(See `BACKLOG.md` → Technical Debt for the tracked list.)
- **Status-normalization duplication risk** — Zoho status, health states, and
  assurance labels each normalize status; ensure a single canonical mapping per
  axis and no silent drift.
- **Audit/reconciliation script sprawl** — ~15 `audit_*` / `backfill_*` modules in
  `app/` plus `scripts/`. Many are one-off remediations; candidates for archival
  to keep `app/` focused on runtime code. **Needs Verification** which are still
  operationally needed.
- **Feature-flag count (~16)** — establish a removal/graduation plan per flag so
  flags don't accumulate indefinitely.
- **Two T-Mobile integration modules** (`tmobile.py` IoT stub vs `tmobile_taap.py`
  wholesale) — confirm the IoT stub is still wanted or remove.

## 11. Areas Needing Verification

- Live Render service/DB names vs `render.yaml` (§1).
- Whether the committed `api/tmobile_private.pem` is a throwaway PIT key or a real
  credential (see `BACKLOG.md` → Critical). A private key in git is a red flag
  regardless.
- Telnyx webhook signature enforcement state in production (`TELNYX_PUBLIC_KEY` set?).
- Database backup / PITR / restore-test cadence (a `docs/RENDER_DB_RECOVERY.md`
  exists — confirm it reflects current Render plan and has been rehearsed).
- Which `audit_*`/`backfill_*` scripts are still required vs historical.
