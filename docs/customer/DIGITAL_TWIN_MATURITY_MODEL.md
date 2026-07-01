# True911+ — Digital Twin Maturity Model

> A building's Digital Twin is only as valuable as it is **complete**. The
> Maturity Model gives a customer a clear, motivating way to see how complete
> their building record is, and exactly what to add next — turning the Location
> Workspace into a **collaborative Building Workspace**.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.5 explainable, §4.6 no green without evidence, §7 no jargon).
> Companions: `LOCATION_DIGITAL_TWIN.md`, `CUSTOMER_COMMAND_CENTER.md`,
> `WORKFLOW_ENGINE.md`. Prepared: 2026-07-01.

---

## 1. Why a maturity model

The Digital Twin is built additively over time. Some data comes from operations
(services, equipment, E911); most *context* (contacts, procedures, photos,
inspection records, documents) is best supplied by the people who run the
building. The maturity tier makes that contribution loop visible and rewarding
**without ever fabricating data** — an empty building is honestly Bronze, and it
climbs only as real information is added.

## 2. The seven dimensions

A building earns one point per **dimension present** (real signal only):

| Dimension | Met when… | Source |
|---|---|---|
| Documentation | ≥1 document contributed | contribution log (`document`) |
| Site contacts | a site contact on file **or** ≥1 contact contributed | `Site.poc_*` / contribution (`contact`) |
| Emergency procedures | ≥1 procedure contributed | contribution log (`procedure`) |
| Testing records | ≥1 inspection contributed | contribution log (`inspection`) |
| Compliance | reserved — reliable per-site compliance signal (future) | — |
| Photos | ≥1 photo contributed | contribution log (`photo`) |
| E911 verified | emergency address is Verified | `Site.e911_status` |

Signals are **booleans derived from real data**. A missing signal is *not met* —
never guessed. (`compliance` is reserved: it stays *not met* until a trustworthy
per-site compliance source exists, so the score is never inflated.)

## 3. Tiers

| Tier | Dimensions met |
|---|---|
| **Bronze** | 0–2 |
| **Silver** | 3–4 |
| **Gold** | 5–6 |
| **Platinum** | 7 |

`score = round(100 × met / 7, 1)`. The workspace shows the tier badge, the
progress bar, and the **next steps** (the unmet dimensions, capped at four) so the
customer always knows how to advance.

Serializer: `app/services/customer/serialize.py::building_maturity(signals)` —
pure, additive, returns `{tier, met, total, score, dimensions[], next_steps[]}`.
Wired in `command_center.load_location_health(...)` alongside separated health.

## 4. Separated Building Health (companion concept)

Maturity answers *"how complete is this twin?"*. **Separated health** answers
*"how healthy is this building?"* by splitting the single score into four factors
and showing the composite **only after** explaining them (Constitution §4.5):

| Factor | Weight | Derived from |
|---|---|---|
| Operational Health | 40% | protected share of the location's life-safety services |
| Digital Twin Completeness | 25% | services + equipment + address + contacts present |
| Compliance | 20% | reserved (unknown → lowers confidence, never fabricated) |
| Documentation | 15% | share of document/photo/procedure artefact types present |

`serialize.separated_health(...)` computes a weighted average **over known factors
only**; unknown factors lower `confidence` rather than the score. An all-unknown
building yields `composite = None` (Unknown, not zero) — the no-false-green rule.

## 5. Guarantees

- **Additive** — new API fields (`building_health`, `maturity`) sit beside the
  existing `health`; legacy callers are unchanged.
- **Real-only** — every dimension and factor is derived from stored data or a
  logged customer contribution; nothing is invented.
- **Explainable** — factors precede the composite; maturity lists concrete next
  steps.
- **Neutral** — no operating-company references anywhere in the customer plane.
