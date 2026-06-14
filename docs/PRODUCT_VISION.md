# True911+ — PRODUCT VISION

> What we are building, why it wins, and how we measure success (the North Star).
> The umbrella over the experience documents; it states the positioning and indexes
> the detail rather than restating it.

| Metadata | |
|---|---|
| **Authority Level** | 1 — Governance |
| **Owner** | Chief Product Officer |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Low |
| **Governed By** | `CONSTITUTION.md`, `MISSION.md` |
| **Detailed In** | `ASSURANCE_PLATFORM_SPEC.md`, `CUSTOMER_EXPERIENCE.md`, `SCREEN_BY_SCREEN_SPEC.md`, `DESIGN_SYSTEM.md`, `ASSURANCE_ENGINE.md` |
| **Related Decisions** | `DECISIONS.md` → D-004 (label wording), D-005 (label vocabulary), D-010 (DocOS) |

---

## 1. The Product

True911 is the **operating system for life-safety communications assurance** — the
independent system of record that turns the telemetry it already collects into a
calm, plain-language, **provable** answer to: *"Are my people protected, and can I
prove it?"*

Customers are not buying devices, dashboards, SIMs, or reports. **They are buying
confidence, proof, and reduced operational risk.**

## 2. The North Star

> **When any Fortune 500 telecom manager logs into True911, they can determine
> within 15 seconds whether their organization is protected — and can prove it.**

This is the bar. "Protected" must be *true*, *earned*, and *provable* — never
cosmetic. The platform reflects reality (see `TRUTH_ENGINE.md`, Operation Green
Dashboard).

### Measurable success metrics

| # | Metric | Target | Source of truth |
|---|---|---|---|
| 1 | **Asset resolution** into the canonical hierarchy | **≥ 95%** | `TRUTH_ENGINE.md` Identity Audit |
| 2 | **Orphan records** (no valid hierarchy chain) | **< 2%** | Identity Audit `gaps.orphan_*` |
| 3 | **Explainable statuses** (reason codes + evidence) | **100%** | Assurance Engine + View Proof |
| 4 | **Documented decisions** | **100%** | `DECISIONS.md` |
| 5 | **Chat-only architecture** (load-bearing knowledge in chat only) | **0** | P3 enforcement |
| 6 | **Duplicate business objects** | **0** | Identity Audit `gaps.duplicate_*` |
| 7 | **Time-to-understand** on login (the "Morning Test") | **≤ 15 s** | `SCREEN_BY_SCREEN_SPEC.md` Home |

Metrics 1, 2, 6 are produced by the Truth Engine Identity Audit (read-only) and
become trackable the moment it ships. Metrics 3–5 are governance/quality gates
enforced by `CONSTITUTION.md` §4–5 and `OPERATING_LOOP.md`. Every roadmap item in
`MASTER_PLAN.md` should name which metric it moves.

## 3. The Assurance Chain

Every feature lives on this chain (full definition in `ASSURANCE_PLATFORM_SPEC.md`):

```
Asset → Communication Path → Protection Status → Business Impact
      → Recommended Action → Proof
```

## 4. Why It Wins

- **Truth discipline** — separate axes never collapse; we refuse to show green when
  E911 would misroute. Competitors routinely don't.
- **Explainability with receipts** — every status carries its evidence (View Proof)
  and a "Recent Manley Activity" timeline.
- **Read-only, deterministic, additive** — safe in front of a regulated /
  Fortune-500 buyer; AI enhances but never decides.

Competitive positioning and personas: `MISSION.md` §2 and `CUSTOMER_EXPERIENCE.md`.

## 5. The Experience (index — detail lives in the linked docs)

| Surface | Authoritative doc |
|---|---|
| Status model, labels, proof contract | `ASSURANCE_PLATFORM_SPEC.md` |
| Deterministic decision engine | `ASSURANCE_ENGINE.md` |
| Per-persona ideal experience + the Morning Test | `CUSTOMER_EXPERIENCE.md` |
| Every screen (Home, Site, View Proof, Assurance Timeline, …) | `SCREEN_BY_SCREEN_SPEC.md` |
| Visual + language design language | `DESIGN_SYSTEM.md` |

## 6. The Customer Hierarchy They See

Customers see plain-language structure, never internal nouns:

```
My Company → Locations → Services → Health → Support → Reports
```

The underlying canonical data hierarchy is defined in `DATA_MODEL.md`; customers
never default to Devices / SIMs / MSISDN / ICCID / raw vendor data
(`CONSTITUTION.md` §7).

## 7. Direction

The platform evolves from telemetry/operations portal → assurance platform →
one-stop business platform (contacts, billing, subscriptions, invoices, support),
sequenced in `MASTER_PLAN.md`. Identity and data truth (`TRUTH_ENGINE.md`) come
before any customer-facing redesign or business-platform layer.
