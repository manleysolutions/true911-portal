# True911+ — IMPLEMENTATION MASTER PLAN

> **Constitution-level execution document.** Translates the product vision
> (`PRODUCT_MANIFESTO.md`, `ASSURANCE_PLATFORM_SPEC.md`, `CUSTOMER_EXPERIENCE.md`,
> `SCREEN_BY_SCREEN_SPEC.md`, `DESIGN_SYSTEM.md`) into a sequenced, two-track build
> plan. Complements `docs/MASTER_PLAN.md` (the horizon roadmap) and
> `docs/BACKLOG.md` (the prioritized item list); this doc owns the **track
> structure, dependencies, and first implementation slices.**
>
> Sequencing rule (from `MASTER_PLAN.md`): **no Track-B customer surface ships
> while a Track-A Critical foundation item is open.** Safety/reliability debt is
> paid first. Every item: smallest-safe-change, flag-gated, additive, read-only
> where it touches source-of-truth.

---

## Two Parallel Tracks

True911 advances on two tracks at once. Track A makes the platform's truth **safe
and provable**; Track B makes that truth **visible and valuable**. Track B reads
the spine Track A protects.

```
Track A — Foundation Hardening   (Safety · Reliability · Security)
Track B — Product Experience     (Assurance Platform surfaces · Customer value)
                 │
                 └── Track B customer surfaces gated behind Track A's
                     E911 data normalization + reliability + auth gates.
```

---

## Track A — Foundation Hardening

*Priority: Safety > Reliability > Security. Must precede customer exposure.*
*(Maps to `BACKLOG.md` C1/C2/C3/H1–H6, M1/M2/M4/M5.)*

| Item | What | Backlog | Effort |
|---|---|---|---|
| **A1 — CI hardening** | Lint, coverage floor on safety modules, `npm ci` | H1 | S–M |
| **A2 — Secret scanning** | Secret scanner in CI (would have caught C1) | H1 | S |
| **A3 — Dependency scanning** | `pip-audit` / SCA in CI | H1 | S |
| **A4 — Startup guards** | Refuse default `JWT_SECRET` + CORS wildcard in prod | H4/H5 | S |
| **A5 — Key rotation before prod** | Rotate leaked T-Mobile PIT key (C3 gate) | C1/C3 | S (operator) |
| **A6 — Enable callback auth** | Turn on built C2 auth with provisioned token | C2 | S |
| **A7 — Backup/restore validation** | DR drill; document RPO/RTO | H2 | M |
| **A8 — E911 regression testing** | Comprehensive E911 correctness + change-log suite | H6 | M |
| **A9 — Feature-flag governance** | Per-flag owner/soak-exit/removal + api/worker parity guard | M2/M4 | S–M |
| **A10 — Canonical status normalization** | One mapping per axis (precedes Assurance surfacing) | M1/TD3 | M |
| **A11 — E911 data normalization sweep** | Validate active-site addresses before customer exposure | (new) | M |

**Track A exit gate (before any Track B customer surface):** A1–A6 done; A8 +
A11 done; A5/C3 closed if any external/customer/gov exposure is in scope.

## Track B — Product Experience

*Priority: Customer value, built safety-first. Reads the Assurance spine.*
*(Maps to `BACKLOG.md` M6 + the new product epics added this cycle.)*

| Item | What | Depends on |
|---|---|---|
| **B0 — Assurance Engine (PR1)** | Backend, read-only, flag-gated — **already implemented** (`ASSURANCE_ENGINE.md §19`) | — |
| **B1 — Assurance Engine graduation** | Exit internal-only; portfolio + attention endpoints | A10, B0 |
| **B2 — View Proof** | Evidence bundle per status (the trust mechanism) | B0, A8 |
| **B3 — Morning Test dashboard (Home)** | <15s portfolio snapshot | B1, A11 |
| **B4 — Site experience** | Four-axis breakdown + E911 checklist + status | B0, B2 |
| **B5 — Assurance Timeline** | Customer / support / audit versions; proof export | B0 (read-only aggregation) |
| **B6 — Judy experience** | Portfolio + attention queue + compliance export | B1, B3 |
| **B7 — Cindy experience** | Community cards + plain language + timeline | B3, B5 |
| **B8 — Installer workflow** | Mobile onboarding: live-online + test + E911 + Accept | A8, B4 |
| **B9 — Support workflow** | Console: reason codes → action, gated remediation | B0, A9 |
| **B10 — Executive dashboard** | Trend, Protected %, Lives Protected, monthly PDF | B1, B3 |
| **B11 — Revenue & business-impact layer** | Revenue at risk, upsell, churn-risk (read-only Zoho) | B1 |

---

## Recommended Sequencing (next ~12 months)

**Quarter 1 — Track A foundation + B0/B2 substrate (no customer UI yet)**
- A1, A2, A3, A4 (CI + guards) → A5/A6 (key rotation + enable C2) → A7 (DR) →
  A8 (E911 regression) → A11 (E911 data sweep, measured internally via B0).
- B0 already done; add **B2 (View Proof)** backend evidence shape on top of B0.
- *Outcome: truth is safe, provable, and measurable before anyone sees a label.*

**Quarter 2 — Track B spine surfaced**
- A10 (canonical normalization) → **B1** (engine graduation) → **B3** (Morning
  Test) → **B4** (Site) → **B5** (Assurance Timeline).
- *Outcome: Judy and Cindy get the calm, defensible view; the product becomes the
  product.*

**Quarter 3 — Workflows**
- **B8** (installer — ships the Tampa/managed-POTS playbook, unblocks PR #51) →
  **B9** (support) → **B6/B7** (persona polish) → alerting on label transitions.
- *Outcome: first-time-right installs; faster safe resolution; proactive ops.*

**Quarter 4 — Enterprise, revenue, scale**
- **B10** (executive dashboard + monthly PDF) → **B11** (revenue layer) →
  read-only customer API → A9 completion → scalability hardening → AI graduation
  (LLLM Phase 1b *only* after governance approval).
- *Outcome: defensible enterprise/gov readiness + the monetization surface.*

---

## Key Dependencies (explicit)

- **B-anything-customer-facing → A11 (E911 sweep).** By approved rule, active +
  unverified E911 = Critical. Enabling labels before the sweep would surface a wall
  of false Criticals. Measure internally (B0 + flag on) first, clean data, then
  expose. (`ASSURANCE_ENGINE.md §19` E911 data-readiness consideration.)
- **B2/B4 → A8 (E911 regression).** Proof and the Site view assert E911
  correctness; the regression suite must back it.
- **B1 → A10 (canonical normalization).** Don't surface labels built on
  duplicated/divergent status logic; consolidate first.
- **Any external/customer/gov exposure → A5/C3 (key rotation).** Hard gate.
- **B9 → A9 (flag governance + worker parity).** Remediation actions must not
  fall victim to the api/worker flag-drift pitfall (PR #63).

---

## First Implementation Slice (recommended)

**A1 + A2 + A3 — Harden CI (lint + secret scan + dependency scan) and switch to
`npm ci`.** Rationale (highest ROI, lowest risk):
- Small effort (1–3 days), entirely in `.github/workflows/` + config.
- Retires the *class* of failure that caused the Critical C1 key leak.
- Force-multiplier: every subsequent Track A and Track B PR ships under a stronger
  gate.
- Pairs with the operator-led **A5 (key rotation)** as the cheap, unblocking duo
  for external/customer/gov readiness.

**Second slice:** A4 (startup guards) — hours of work, removes catastrophic
misconfig foot-guns.

**First Track-B slice (after Track-A gate):** B2 (View Proof) — it is the trust
mechanism the entire customer experience depends on, and it builds directly on the
already-implemented Assurance Engine PR1.

---

## Related Documents

- `docs/MASTER_PLAN.md` — horizon roadmap (this doc is its execution view).
- `docs/BACKLOG.md` — prioritized items (C/H/M/L) referenced above.
- `docs/PROJECT_STATE.md` — current resumable state.
- `docs/ASSURANCE_ENGINE.md` — engineering spec + PR1 status.
- `docs/PRODUCT_MANIFESTO.md` / `ASSURANCE_PLATFORM_SPEC.md` — what we're building.
