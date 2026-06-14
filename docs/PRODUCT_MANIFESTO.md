# True911+ — PRODUCT MANIFESTO

> **Narrative companion to the Constitution.** This document tells the *story and
> philosophy* of True911 in prose. The **binding** rules, priority order, and
> vetoes live in `CONSTITUTION.md` and are referenced — never restated — here
> (per `CONSTITUTION.md` P1, Single Source of Truth). If this narrative ever
> conflicts with the Constitution, the Constitution wins.

| Metadata | |
|---|---|
| **Authority Level** | 5 — Subsystem (narrative companion) |
| **Owner** | Chief Product Officer |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Rare |
| **Governed By** | `CONSTITUTION.md`, `PRODUCT_VISION.md` |
| **Detailed In** | `PRODUCT_VISION.md`, `MISSION.md` |
| **Related Decisions** | `DECISIONS.md` → D-009 (Constitution promoted from this doc) |

---

## 1. What True911 Is

True911 is the **operating system for life-safety communications assurance**. It is
not a device dashboard and not merely a 911 verifier — it is the independent system
of record that turns messy telemetry into a calm, plain-language, **provable**
answer for every protected location.

## 2. What Customers Are Buying

Customers are not buying devices, dashboards, SIMs, telemetry, or reports. **They
are buying confidence, proof, and reduced operational risk** — the ability to
answer one question without hesitation: *"Are my people protected, and can I prove
it?"*

## 3. The Core Story

This exchange is the product. Every feature exists to make it true:

> **CEO:** "Are we protected?" · **Judy:** "Yes." · **CEO:** "How do you know?" ·
> **Judy:** "I can prove it."

## 4. The Assurance Chain

Every feature lives on this chain (model detail in `ASSURANCE_PLATFORM_SPEC.md`):

```
Asset → Communication Path → Protection Status → Business Impact
      → Recommended Action → Proof
```

A status without proof, or a problem without a recommended action, is incomplete.

## 5. Philosophy (the spirit behind the law)

The platform must be **calm, plain-language, defensible, and trustworthy**: no green
without evidence, no status without proof, deterministic before AI, AI never makes
autonomous life-safety decisions, separate axes never collapse, read-only and
additive first, smallest safe change. These are codified as binding principles and
rules in **`CONSTITUTION.md` §4–§5** — this section is the *why*, the Constitution
is the *law*.

## 6. The Promise

> True911 continuously assures that every life-safety communication path is
> operational, compliant, monitored, and provable — so the people responsible can
> answer, in seconds and with proof: **"Are my people protected?"**

## 7. What We Refuse To Build

The standing veto list (customer-facing score, autonomous AI safety decisions, a
911-will-always-connect guarantee, green without explanation, cross-tenant
benchmarking, raw vendor telemetry as the primary experience, …) is authoritative
in **`CONSTITUTION.md` §7**, with rationale in `ASSURANCE_PLATFORM_SPEC.md`.

## 8. Related

`CONSTITUTION.md` (law) · `PRODUCT_VISION.md` (positioning + North Star) ·
`MISSION.md` (audience) · `README.md` (documentation entry point).
