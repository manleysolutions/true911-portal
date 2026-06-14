# True911+ — MISSION

> Living document. Last reviewed: 2026-06-13. Update on any change to product
> positioning, priority order, or non-negotiable principles.

## 1. What True911 Is

True911+ is a **mission-critical, life-safety emergency-communications assurance
platform**. It exists to answer one question for every protected location, on
demand and truthfully:

> **"If someone needs to call 911 from this location right now, will it work — and
> can we prove it?"**

It is **not** a device-monitoring dashboard. Customers do not think in SIMs,
ICCIDs, SIP registrations, or firmware versions. They think in *locations* and
*protection*. The platform's job is to turn the low-level telemetry it already
collects (heartbeats, carrier events, call-detail records, TR-069 sync, E911
records, commercial lifecycle) into **calm, trustworthy, explainable answers**.

The product direction is codified in `docs/ASSURANCE_ENGINE.md`: True911 is an
**"Emergency Communications Assurance Platform"** whose spine is a read-only,
deterministic, explainable **Assurance Label** per device → site → customer
portfolio (Protected / Attention Needed / Critical / Inactive-Deactivated /
Pending Install / Unknown).

## 2. Who We Serve

| Persona | Who they are | What they need from us |
|---|---|---|
| **Judy** | Enterprise telecom manager, hundreds of locations | Portfolio-wide truth at a glance; "what needs attention" without noise; defensible compliance reporting. |
| **Cindy** | Property manager, many communities | Per-community protection status in plain language; no telecom jargon; clear "who do I call". |
| **Installers** | Field techs deploying hardware | Fast, guided onboarding; immediate confirmation a site is live and E911 is correct before they leave. |
| **Support technicians** | Tier 1/2 support | One screen that explains *why* a site is unhealthy and the safest remediation; minimal context-switching. |
| **Dispatch personnel** | Emergency / NOC operators | Real, current state; no false alarms on intentionally-inactive sites; clear escalation. |
| **Enterprise administrators** | Customer-side admins | Manage their own users/sites within their tenant; never see other tenants. |
| **Internal operations staff** | Manley Solutions ops | Reconciliation, onboarding review, data stewardship, carrier provisioning. |
| **Executive leadership** | Manley + customer execs | Portfolio health, revenue posture, "what has Manley done to protect us". |

## 3. Priority Order (Non-Negotiable)

Every decision, trade-off, and review is resolved in this order. When two goals
conflict, the higher one wins — always.

1. **Safety** — a 911 call must work; never present a false "all good".
2. **Reliability** — the platform and its truth must be available and correct.
3. **Security** — protect credentials, tenant isolation, and customer data.
4. **Data integrity** — one source of truth per axis; additive, never destructive.
5. **Customer experience** — calm, honest, plain-language answers.
6. **Support efficiency** — fewer escalations, faster safe remediation.
7. **Scalability** — grow to thousands of locations without re-architecture.
8. **Revenue generation** — dashboards and reporting that support the business.
9. **Internal convenience** — never at the expense of anything above it.

## 4. Non-Negotiable Principles

These are enforced patterns already visible in the codebase. New work must honor
them.

- **Production-safe by default.** `APP_MODE` defaults to `"production"`; every new
  capability ships behind a feature flag that defaults **off** (`FEATURE_*` in
  `api/app/config.py`). Turning a flag on is a deliberate, reviewed act.
- **Read-only first, additive always.** New intelligence (Health Normalizer,
  Assurance Engine, Zoho lifecycle ingest) **computes and stages; it never
  overwrites** a source-of-truth axis. Operational status, commercial lifecycle,
  E911 status, and device status each have exactly one owner.
- **Separate axes never collapse.** Commercial-active ≠ operationally healthy. A
  live heartbeat never hides a compliance gap. Missing data ≠ healthy.
- **Deterministic before AI.** Every AI surface has a deterministic fallback and
  external egress is independently gated (`FEATURE_LLLM` *and*
  `LLLM_ALLOW_EXTERNAL`). The platform must behave identically with AI disabled.
- **Smallest safe change.** Mission-critical systems change incrementally, behind
  flags, with soak periods and documented rollback recipes.
- **Explainable.** Any status the platform asserts must come with the reason
  codes / signals that produced it. No black-box life-safety claims.
- **Tenant isolation is sacred.** A customer must never see another tenant's data;
  internal-only surfaces are gated by real tenant context, not role alone.

## 5. What "Done" Means Here

A change is done when it is: correct, verified by tests, flag-gated (if it alters
behavior), documented (including rollback), reviewed against the priority order
above, and leaves `PROJECT_STATE.md` accurate for the next session.

## 6. Related Documents

- `docs/OPERATING_LOOP.md` — how every development session must proceed.
- `docs/MASTER_PLAN.md` — long-term roadmap.
- `docs/PROJECT_STATE.md` — resumable current state (read this first each session).
- `docs/BACKLOG.md` — prioritized work.
- `docs/ARCHITECTURE.md` — system architecture and design decisions.
- `docs/ASSURANCE_ENGINE.md` — the product spine specification.
