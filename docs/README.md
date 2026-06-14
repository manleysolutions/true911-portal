# True911+ — DOCUMENTATION INDEX (README)

> **Required entry point for every session — human or AI.** Start here. This file
> maps the Documentation Operating System and defines the mandatory reading order.
> Authority flows top-down; conflicts are resolved by level, then by the
> `CONSTITUTION.md` priority order.

| Metadata | |
|---|---|
| **Authority Level** | 1 — Governance (navigational) |
| **Owner** | Product Owner |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Low |
| **Governed By** | `CONSTITUTION.md` |
| **Detailed In** | every document listed below |
| **Related Decisions** | `DECISIONS.md` → D-010 (DocOS) |

---

## AI Session Rule (mandatory — `CONSTITUTION.md` P4)

Every AI session must, in order:

1. Read `CONSTITUTION.md`
2. Read `DECISIONS.md`
3. Read `PROJECT_STATE.md`
4. Read `MASTER_PLAN.md`
5. Read `BACKLOG.md`
6. Build a dependency graph
7. Plan
8. **Wait for approval**
9. Implement (in the smallest safe slice — P5)

Then consult the level-specific docs relevant to the task.

## The Four-Level Hierarchy

### Level 1 — Governance (timeless: WHY)
- `CONSTITUTION.md` — supreme principles, priority order, P1–P5, vetoes.
- `MISSION.md` — who we serve, what True911 is, personas.
- `PRODUCT_VISION.md` — what we're building, why it wins, and the **North Star** +
  success metrics (umbrella over the experience docs).
- `PRODUCT_MANIFESTO.md` — narrative companion to the Constitution (the "why" prose).

### Level 2 — Architecture (canonical: WHAT / HOW)
- `DATA_MODEL.md` — the canonical entity hierarchy and identity anchors.
- `ARCHITECTURE.md` — system structure, runtime tiers, event flow, integrations.
- `TRUTH_ENGINE.md` — identity resolution, data health, steward tooling.
- `DECISIONS.md` — append-only decision log (D-001…).
- `GLOSSARY.md` — canonical terminology.

### Level 3 — Execution (rolling: NOW / NEXT)
- `MASTER_PLAN.md` — strategic horizons + execution sequencing.
- `BACKLOG.md` — prioritized work + tech debt.
- `PROJECT_STATE.md` — resumable current state (read first each session).

### Level 4 — Process (HOW WE WORK)
- `OPERATING_LOOP.md` — the development loop, SWAT discipline, steward workflow,
  governance-rule enforcement.

### Level 5 — Subsystem detail (~46 docs)
Per-vendor specs, runbooks, audits, and the product-experience docs
(`ASSURANCE_PLATFORM_SPEC.md`, `ASSURANCE_ENGINE.md`, `CUSTOMER_EXPERIENCE.md`,
`SCREEN_BY_SCREEN_SPEC.md`, `DESIGN_SYSTEM.md`, `PRODUCT_MANIFESTO.md`, …).
Subordinate to Levels 0–2; may not contradict them without a `DECISIONS.md` entry.

## Authority & Conflict Resolution

```
CONSTITUTION  →  MISSION / PRODUCT_VISION / PRODUCT_MANIFESTO
              →  ARCHITECTURE (DATA_MODEL · TRUTH_ENGINE · DECISIONS · GLOSSARY)
              →  EXECUTION (MASTER_PLAN · BACKLOG · PROJECT_STATE)
              →  PROCESS (OPERATING_LOOP)
              →  SUBSYSTEM docs
```

Higher level wins. A lower-level deviation from a higher level is valid only as a
recorded decision (`DECISIONS.md`); otherwise it is a defect.

## Governing Rules (quick reference — `CONSTITUTION.md` §5)

- **P1** Single Source of Truth — one fact, one home; reference, never copy.
- **P2** Documentation Freshness — not done until docs + Project State + decision.
- **P3** No Conversation Dependency — chat-only knowledge does not exist.
- **P4** AI Session Rule — the read order above.
- **P5** Smallest Safe Slice — independently reviewable, testable, reversible.
