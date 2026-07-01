# True911+ — MASTER PLAN

> Long-term roadmap. Living document; sequencing is guided by the **priority order
> in `CONSTITUTION.md` §3**, not by feature excitement. Last reviewed: 2026-06-22.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`,
> `PRODUCT_VISION.md`. Each roadmap item should name which **North Star** metric it
> moves (`PRODUCT_VISION.md` §2). Entry point: `README.md`.
>
> Phasing principle: **stabilize the foundation (safety/reliability/security)
> before expanding surface.** Every roadmap item ships flag-gated, additive, and
> read-only-first where it touches source-of-truth data.

## Guiding Arc

True911 evolves from a telemetry/operations portal into the **operating system for
life-safety communications assurance** (`docs/PRODUCT_MANIFESTO.md`). The Assurance
Engine (`docs/ASSURANCE_ENGINE.md`) is the spine that every customer-facing surface
reads. The technical strategy is: *collect once, normalize per axis, compose into
calm labels, never overwrite.*

> **Two parallel tracks.** Execution now runs on two tracks — **Track A
> (Foundation Hardening)** and **Track B (Product Experience)** — sequenced in
> `docs/IMPLEMENTATION_MASTER_PLAN.md`. The horizons below remain the strategic
> framing; the two-track plan is their execution view. No Track-B customer surface
> ships while a Track-A Critical foundation item is open.

---

## Current Primary Objective — RH Customer Go-Live (`EPIC-RH-GO-LIVE`)

> **The roadmap now has a concrete commercial anchor:** make **Restoration Hardware
> (Judy)** the first production customer **actively using True911 every week**
> (assurance + support scope; billing/QuickBooks/invoicing deferred). This is the
> current top execution objective — full four-phase epic in `BACKLOG.md`, design
> complete across the customer-go-live doc set.

RH go-live is not a detour from the horizons below — it is their **first real
instantiation**, sequenced safety-first:
- **Phase 1 (Foundation)** = Horizon-0 work made specific: tenant-isolation fixes,
  the `INTERNAL_OPS` guard, and the scoped `CUSTOMER_*` roles
  (`RH_SECURITY_READINESS.md`, `RH_ROLE_MATRIX.md`, `CUSTOMER_EXPERIENCE_BOUNDARY.md`).
- **Phase 2 (Data)** = the Horizon-0 **E911 assurance/data sweep** applied to RH's 42
  sites / 51 devices (E911 verify, device mapping, telemetry, service units).
- **Phase 3 (Surface)** = Horizon-1/2 **Assurance spine + customer health surfaces**
  graduated for the RH tenant via the read-only `/api/customer/*` contract layer
  (`CUSTOMER_DATA_BOUNDARY.md`, `CUSTOMER_API_CONTRACTS.md`).
- **Phase 4 (Launch)** = enable `FEATURE_CUSTOMER_API` for RH only, default-OFF
  elsewhere, with instant flag rollback (`FEATURE_CUSTOMER_API_ROLLOUT.md`).

**The surface has graduated into the Customer Command Center** (2026-07-01) — the
enterprise, service-first Life-Safety Operating System (Enterprise→Portfolio→
Location→Service→Equipment→Carrier): executive metrics, evidence-graded portfolio
health, interactive map, enterprise search, and a Location Command Center. This is
the concrete Horizon-2 "customer surface" + Horizon-4 "enterprise" instantiation,
built additively on `/api/customer/*`. Spec: `docs/customer/CUSTOMER_COMMAND_CENTER.md`.

**Design status recorded:** customer boundary architecture complete · tenant isolation
audited (no CRITICAL) · customer RBAC design complete · customer API contract design
complete · `FEATURE_CUSTOMER_API` rollout design complete. The horizons below remain the
strategic frame; **the PE (Track-B) epics resume after RH launch** or where they are
shared dependencies of the epic. **North Star moved:** RH go-live is the first proof that
a customer can determine protection in ≤15s with evidence (`PRODUCT_VISION.md` §2).

---

## Horizon 0 — Foundation Hardening (now → next)

*Priority: Safety, Reliability, Security, Data integrity. Must precede major
feature expansion.*

- **Security baseline:** remediate the committed private key; add app-layer auth to
  the T-Mobile callback; refuse-to-start on default JWT secret in prod; guard CORS
  wildcard in prod; plan JWT-off-`localStorage`. (BACKLOG C1, C2, H3, H4, H5)
- **CI/CD hardening:** lint, frontend smoke tests, coverage floor on safety modules,
  dependency/secret scanning, `npm ci`. (BACKLOG H1)
- **Disaster recovery:** verify + rehearse DB backup/restore; document RPO/RTO.
  (BACKLOG H2)
- **E911 assurance regression suite** — prove the life-safety path. (BACKLOG H6)

## Horizon 1 — The Assurance Spine

*Priority: Safety, then Customer experience built safety-first.*

- **Assurance Engine backend MVP** — read-only, deterministic, flag-gated, labels
  only, exhaustive table-driven tests; composes operational / commercial-lifecycle /
  deployment-lifecycle / E911 axes. (BACKLOG M6; spec in `docs/ASSURANCE_ENGINE.md`)
- **Health layer graduation** — exit the Health Normalizer soak; extend canonical
  device state to additional consumers beyond AI Health Summary once proven.
- **Device Health adapters** — mature the hardware-agnostic adapter set (VOLA,
  T-Mobile, Telnyx, Inseego, Cisco ATA, MS130) behind `FEATURE_DEVICE_HEALTH`;
  Belle Terre/Integrity is the pilot dataset, not a special case.

## Horizon 2 — Customer & Device Health Surfaces

- **Customer Health** — per-customer portfolio assurance rollup; reconciliation
  surfaced to internal ops (already partly built: portfolio reconciliation dashboard).
- **Device Health UI** — Property Health / per-site drill-down reading the read-only
  device-health APIs.
- **Customer portal UX** — calm, plain-language assurance for Cindy/Judy; the
  "Recent Manley Activity" timeline; no telecom jargon.

## Horizon 3 — Workflows & Operations

- **E911 workflows** — surface E911 out of Admin into a first-class, guided,
  auditable workflow (address verify, confirmation-required handling, change log).
- **Support workflows** — mature the support console: deterministic diagnostics,
  gated self-healing/remediation, Zoho Desk escalation; reduce time-to-safe-fix.
- **Onboarding/installer experience** — Day-0 guided flow that confirms a site is
  live and E911 is correct before the installer leaves; managed-POTS playbook
  (Red Tag Line / US Courts Tampa as first deployment).
- **Mapping** — geographic health overlay beyond the current `DeploymentMap`.

## Horizon 4 — Enterprise, Mobile, API

- **Enterprise reporting** — defensible compliance reports and exports for Judy's
  hundreds of locations; scheduled report/PDF generation (deferred in Assurance MVP).
- **Mobile experience** — installer-first mobile flow; responsive assurance views.
- **API strategy** — read-only customer-facing API so enterprises can pull their
  own assurance state; versioned, tenant-scoped, rate-limited.

## Horizon 5 — AI Capabilities (deterministic-first, gated)

- **LLLM graduation** — Phase 1b external egress only after governance approval
  (`docs/AI_OPERATIONAL_SAFETY.md`); always with deterministic fallback and
  per-tenant token caps.
- **AI Health Summary** expansion to more scopes once the deterministic baseline is
  trusted.
- **AI-assisted support** — remediation suggestions surfaced to techs, never
  auto-applied to life-safety state without human confirmation.

## Cross-Cutting Tracks (continuous across all horizons)

- **Scalability** — keep hot paths (Command Center, health sync cron, assurance
  rollups) query-bounded; plan for Postgres/Redis growth beyond starter plans;
  watch the `*/5` health-sync cost as device count grows.
- **Disaster recovery** — backups, restore drills, runbooks; multi-region is a
  later consideration.
- **Security** — periodic dependency + secret scans, webhook-auth coverage for
  every inbound integration, tenant-isolation tests, secret rotation cadence.
- **Testing strategy** — backend pytest stays the gate; add frontend tests; add
  table-driven tests for every new normalization/label mapping; soak new behavior
  behind flags with runbooks before graduation.
- **Monitoring** — build on `X-Request-ID` request logging; add health/SLO
  dashboards, alerting on webhook failures, job-queue depth, and false-state
  detection; daily soak runbooks (already practiced for T-Mobile callback).
- **Documentation** — keep this docs set and `PROJECT_STATE.md` current every
  session; add a `docs/README.md` index; per-flag graduation notes.

## Sequencing Rule

Do not start a Horizon-2+ feature while a Horizon-0 Critical item is open. Safety
and reliability debt is paid down first. Each horizon item enters work only through
the Operating Loop, smallest-safe-change first, flag-gated.
