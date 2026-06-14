# True911+ — PRODUCT MANIFESTO

> **Constitution-level document.** This is the highest-altitude statement of what
> True911 is and why it exists. It governs every other document and every product
> decision. When a feature, screen, or roadmap item conflicts with this manifesto,
> the manifesto wins. Living document; change only with deliberate intent.
>
> Read alongside `docs/MISSION.md` (priority order + principles),
> `docs/ASSURANCE_PLATFORM_SPEC.md` (the model), and
> `docs/ASSURANCE_ENGINE.md` (the deterministic decision logic).

---

## 1. What True911 Is

**True911 is the operating system for life-safety communications assurance.**

It continuously assures that every life-safety communication path is
**operational, compliant, monitored, and provable** — and it expresses that
assurance in calm, plain language that a non-technical owner can act on in
seconds.

True911 is **not** a device dashboard. It is **not** merely a 911 verifier. It is
an **Assurance Platform**: the independent system of record that answers, for
every protected location, on demand and truthfully:

> **"If someone calls 911 from this location right now, will it work — and can we
> prove it?"**

## 2. What Customers Are Actually Buying

Customers are not buying devices, dashboards, SIMs, telemetry, or reports.

**Customers are buying confidence, proof, and reduced operational risk.**

They are buying the ability to answer one question without hesitation:

> **"Are my people protected, and can I prove it?"**

Everything we build is justified only insofar as it strengthens the customer's
ability to answer that question quickly, honestly, and defensibly.

## 3. The Core Story

This exchange is the product. Every screen, label, and feature exists to make it
true:

> **CEO:** "Are we protected?"
> **Judy:** "Yes."
> **CEO:** "How do you know?"
> **Judy:** "I can prove it."

If a feature does not help Judy say "Yes" with confidence and then **prove it**,
it does not belong in True911.

## 4. The Assurance Chain

Every feature must support — and can be located on — this chain. Nothing in the
product exists outside it:

```
Asset
  → Communication Path
    → Protection Status
      → Business Impact
        → Recommended Action
          → Proof
```

- **Asset** — the physical thing at the location (device, line, SIM, radio).
- **Communication Path** — the end-to-end route a 911 call would take.
- **Protection Status** — the calm label (Protected / Attention Needed / Critical
  / Pending Install / Inactive / Unknown).
- **Business Impact** — what this means commercially (revenue at risk, accounts
  affected, compliance exposure).
- **Recommended Action** — the single safest next step.
- **Proof** — the evidence that the status is true (timestamps, device/carrier/
  E911/test/monitoring evidence, Recent Manley activity).

A feature that produces a status without proof, or a proof without a recommended
action, is incomplete.

## 5. Guiding Principles (non-negotiable)

These extend the `MISSION.md` priority order (Safety > Reliability > Security >
Data integrity > CX > Support > Scalability > Revenue > Internal) with the product
philosophy that makes True911 trustworthy:

1. **The platform must be calm, plain-language, defensible, and trustworthy.**
   Calm beats comprehensive. A customer should feel *reassured*, never alarmed
   without cause.
2. **No customer-facing screen shows green without explaining why.** Every
   positive assurance is paired with the evidence and timestamp behind it.
3. **No status exists without evidence.** A label is a claim; a claim without
   proof is not allowed to render.
4. **Every screen must answer: "Why should I believe this?"** If a screen cannot
   answer that, it is not finished.
5. **No AI may make autonomous life-safety decisions.** AI never changes,
   suppresses, or asserts a life-safety status on its own.
6. **Deterministic logic comes first.** Every status is produced by deterministic,
   explainable rules with a deterministic fallback. The platform must behave
   identically with AI disabled.
7. **AI may explain, summarize, and assist — only after deterministic truth is
   established.** AI is an enhancement layered on top of proven truth, never a
   source of truth.
8. **Separate axes never collapse.** Commercial-active ≠ operationally healthy ≠
   E911-verified. A live heartbeat never hides a compliance gap. Missing data is
   never "healthy."
9. **Read-only first, additive always.** New intelligence computes and stages; it
   never overwrites a source-of-truth axis.
10. **Smallest safe change, flag-gated, with a rollback path.** This is a
    life-safety system; it changes incrementally.

## 6. The Promise We Make

> True911 continuously assures that every life-safety communication path is
> operational, compliant, monitored, and provable — so that the people
> responsible can answer, in seconds and with proof: **"Are my people protected?"**

## 7. What This Manifesto Forbids

The manifesto is also a list of things we refuse to do. The authoritative list
lives in `docs/ASSURANCE_PLATFORM_SPEC.md` → *Features That Should Never Be Built*
and is summarized here as a standing veto:

- No customer-facing numeric "readiness score."
- No autonomous AI life-safety decisions or auto-remediation without human
  approval.
- No guarantee that 911 will always connect.
- No green/red without explanation.
- No raw vendor telemetry as the primary customer experience.
- No cross-tenant benchmarking.
- No competing/configurable health scores.

## 8. Related Constitution Documents

- `docs/MISSION.md` — who we serve, the priority order, non-negotiable principles.
- `docs/ASSURANCE_PLATFORM_SPEC.md` — the Assurance model, statuses, and proof.
- `docs/ASSURANCE_ENGINE.md` — the deterministic decision matrix (engineering spec).
- `docs/CUSTOMER_EXPERIENCE.md` — the ideal experience per persona.
- `docs/SCREEN_BY_SCREEN_SPEC.md` — the finished screens.
- `docs/DESIGN_SYSTEM.md` — the visual + language design language.
- `docs/IMPLEMENTATION_MASTER_PLAN.md` — the two-track build sequence.
