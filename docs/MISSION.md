# True911+ — MISSION

> Living document. Last reviewed: 2026-06-14.
>
> **Authority Level:** 1 — Governance. **Governed by:** `CONSTITUTION.md`.
> **Entry point:** `README.md`. This document is the source of truth for **who we
> serve** and the product's purpose. The **priority order**, **founding
> principles**, and **vetoes** are constitutional — they live in `CONSTITUTION.md`
> and are referenced here, not restated (per `CONSTITUTION.md` P1). Product
> positioning + North Star: `PRODUCT_VISION.md`.

## 1. What True911 Is

True911+ is the **operating system for life-safety communications assurance** — a
mission-critical platform that continuously assures every life-safety
communication path is **operational, compliant, monitored, and provable**. It
exists to answer one question for every protected location, on demand and
truthfully:

> **"If someone needs to call 911 from this location right now, will it work — and
> can we prove it?"**

The **core customer promise** is that the person responsible can answer, in
seconds and with proof: **"Are my people protected, and can I prove it?"** Every
feature supports the assurance chain: **Asset → Communication Path → Protection
Status → Business Impact → Recommended Action → Proof** (see
`docs/ASSURANCE_PLATFORM_SPEC.md`).

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

The priority order (Safety > Reliability > Security > Data integrity > Customer
experience > Support efficiency > Scalability > Revenue > Internal convenience) is
**constitutional and authoritative in `CONSTITUTION.md` §3**. It is the universal
tiebreaker for every decision; it is referenced here, not restated, so it has one
home (P1).

## 4. Non-Negotiable Principles

The founding principles (production-safe by default; read-only/additive; separate
axes never collapse; deterministic before AI; smallest safe change; explainable;
tenant isolation; one authoritative identity) are **authoritative in
`CONSTITUTION.md` §4**, with the governance rules P1–P5 in `CONSTITUTION.md` §5.
Referenced here, not restated.

## 5. What "Done" Means Here

The definition of done is constitutional — see `CONSTITUTION.md` §6 (correct,
tested, flag-gated, documented, reviewed against the priority order, decision
recorded, `PROJECT_STATE.md` left accurate).

## 6. Related Documents

> Full hierarchy and reading order: **`README.md`** (the documentation entry point).

**Governing layer:**
- `docs/CONSTITUTION.md` — supreme law: priority order, principles, P1–P5, vetoes.
- `docs/PRODUCT_VISION.md` — positioning + North Star + success metrics.
- `docs/PRODUCT_MANIFESTO.md` — narrative companion to the Constitution.
- `docs/ASSURANCE_PLATFORM_SPEC.md` — the assurance model, statuses, and proof.
- `docs/CUSTOMER_EXPERIENCE.md` — ideal experience per persona + the Morning Test.
- `docs/SCREEN_BY_SCREEN_SPEC.md` — finished screens, Assurance Timeline, View Proof.
- `docs/DESIGN_SYSTEM.md` — the True911 design language.
- `docs/IMPLEMENTATION_MASTER_PLAN.md` — the two-track build sequence.

**Engineering + process:**
- `docs/OPERATING_LOOP.md` — how every development session must proceed.
- `docs/MASTER_PLAN.md` — long-term roadmap (horizons).
- `docs/PROJECT_STATE.md` — resumable current state (read this first each session).
- `docs/BACKLOG.md` — prioritized work.
- `docs/ARCHITECTURE.md` — system architecture and design decisions.
- `docs/ASSURANCE_ENGINE.md` — the product-spine engineering specification.
