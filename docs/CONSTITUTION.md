# True911+ — CONSTITUTION

> **Supreme governing document.** The highest authority in the True911
> documentation operating system. When any document, feature, screen, roadmap, or
> decision conflicts with this Constitution, the Constitution wins. It contains
> only timeless principles and governance rules — nothing that changes when code
> changes. *(History note: this document was promoted from the former
> `PRODUCT_MANIFESTO.md`.)*

| Metadata | |
|---|---|
| **Authority Level** | 0 — Supreme (overrides all) |
| **Owner** | Product Owner (Stuart Manley) |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Rare (deliberate amendment only) |
| **Governed By** | — (this is the supreme document) |
| **Detailed In** | `MISSION.md`, `PRODUCT_VISION.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `TRUTH_ENGINE.md`, `OPERATING_LOOP.md` |
| **Related Decisions** | `DECISIONS.md` → D-001 (constitutional rules), D-006 (separate-axes invariant) |

---

## 1. What True911 Is (one line)

True911 is the **operating system for life-safety communications assurance** — it
continuously assures that every life-safety communication path is operational,
compliant, monitored, and **provable**. *(Full statement of purpose and audience:
`MISSION.md`. Product positioning: `PRODUCT_VISION.md`.)*

## 2. The Core Promise

The person responsible can answer, in seconds and with proof:

> **"Are my people protected, and can I prove it?"**

Embodied in the founding story — every feature must keep it true:

> **CEO:** "Are we protected?" · **Judy:** "Yes." · **CEO:** "How do you know?" ·
> **Judy:** "I can prove it."

## 3. Priority Order (the universal tiebreaker)

Every decision, trade-off, and review is resolved in this order. When two goals
conflict, the higher one wins — always. *(This order is constitutional; other
documents reference it rather than restate it.)*

1. **Safety** — a 911 call must work; never present a false "all good."
2. **Reliability** — the platform and its truth must be available and correct.
3. **Security** — protect credentials, tenant isolation, and customer data.
4. **Data integrity** — one source of truth per axis; additive, never destructive.
5. **Customer experience** — calm, honest, plain-language answers.
6. **Support efficiency** — fewer escalations, faster safe remediation.
7. **Scalability** — grow to thousands of locations without re-architecture.
8. **Revenue generation** — dashboards and reporting that support the business.
9. **Internal convenience** — never at the expense of anything above it.

## 4. Founding Principles (timeless invariants)

1. **Production-safe by default.** New capability ships behind a `FEATURE_*` flag
   defaulting off. Turning a flag on is a deliberate, reviewed act.
2. **Read-only first, additive always.** New intelligence computes and stages; it
   never overwrites a source-of-truth axis.
3. **Separate axes never collapse.** Commercial-active ≠ operationally healthy ≠
   E911-verified. A live heartbeat never hides a compliance gap. Missing data is
   never "healthy." *(See `DECISIONS.md` D-006.)*
4. **Deterministic before AI.** Every status comes from deterministic, explainable
   rules with a deterministic fallback. The platform behaves identically with AI
   disabled. **No AI makes autonomous life-safety decisions.**
5. **Explainable.** Any asserted status carries the reason codes/evidence that
   produced it. No black-box life-safety claims. Every screen answers *"Why should
   I believe this?"*
6. **No green without evidence.** No customer-facing status shows green without its
   timestamp and proof. No status exists without evidence.
7. **Tenant isolation is sacred.** A customer never sees another tenant's data.
8. **One authoritative identity per object.** Every entity resolves to exactly one
   place in the canonical hierarchy. *(Mechanics: `TRUTH_ENGINE.md`.)*

## 5. Constitutional Rules (governance)

These rules govern *how* all development and documentation proceed. They are
binding and enforced through `OPERATING_LOOP.md`.

- **P1 — Single Source of Truth.** Every fact has exactly one authoritative
  location; all other documents reference that source. Duplication is permitted
  only by reference, never by parallel maintenance.
- **P2 — Documentation Freshness.** Implementation is not complete until:
  documentation updated · `PROJECT_STATE.md` updated · decision recorded in
  `DECISIONS.md`.
- **P3 — No Conversation Dependency.** If information exists only in conversation,
  it does not exist. Architectural knowledge, business rules, workflows, and
  implementation philosophy must be documented — in the correct level — before any
  future work depends on them. *(Governs load-bearing knowledge; passing ideas may
  live in `BACKLOG.md` → IDEAS until promoted.)*
- **P4 — AI Session Rule.** Every AI session must, in order: (1) read
  `CONSTITUTION.md` → (2) `DECISIONS.md` → (3) `PROJECT_STATE.md` → (4)
  `MASTER_PLAN.md` → (5) `BACKLOG.md` → (6) build a dependency graph → (7) plan →
  (8) wait for approval → (9) implement. Entry point: `README.md`.
- **P5 — Smallest Safe Slice.** All implementation shall proceed in the smallest
  independently reviewable, independently testable, and independently reversible
  slice. Large changes shall be decomposed until each slice can be understood
  without understanding the entire project.

*(Adoption recorded in `DECISIONS.md` D-001.)*

## 6. Definition of "Done"

A change is done when it is: correct, verified by tests, flag-gated (if it alters
behavior), documented (including rollback), reviewed against the priority order,
recorded as a decision where one was made, and leaves `PROJECT_STATE.md` accurate
for the next session. *(Per P2 + P5.)*

## 7. Features That Must Never Be Built (standing veto)

Adding any of these requires a constitutional amendment. *(Detailed rationale:
`ASSURANCE_PLATFORM_SPEC.md` → Features That Should Never Be Built.)*

1. Customer-facing numeric "readiness score."
2. AI making autonomous life-safety decisions / auto-remediation without human
   approval.
3. A guarantee that 911 will always connect.
4. Green/red indicators without explanation.
5. Raw vendor telemetry as the primary customer experience.
6. Cross-tenant benchmarking.
7. Multiple competing / customer-configurable health scores.
8. Generic network monitoring (we assure life-safety paths, not general IT).
9. Technical jargon (ICCID/IMSI/SIP/firmware) as the default customer view.

## 8. Amendment

This document changes only by deliberate decision of the Product Owner, recorded
in `DECISIONS.md`. Lower documents may not weaken it; where a lower document must
deviate, that deviation is a recorded decision, not a silent override.

## 9. The Documentation Operating System

The full hierarchy and reading order are defined in `README.md`. Success is defined
in `PRODUCT_VISION.md` (North Star). Authority flows: **Constitution → Mission/Vision →
Architecture (Data Model, Truth Engine, Decisions, Glossary) → Execution (Master
Plan, Backlog, Project State) → Process (Operating Loop)**.
