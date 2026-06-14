# True911+ — CUSTOMER EXPERIENCE

> **Constitution-level document.** Defines the ideal experience for each persona:
> what they care about, what they see first, what they must never see, their daily
> workflow, the trust signals they rely on, their actions, success metrics, the
> screens they use, and the language style we use with them. Governed by
> `docs/PRODUCT_MANIFESTO.md`; statuses defined in
> `docs/ASSURANCE_PLATFORM_SPEC.md`; screens in `docs/SCREEN_BY_SCREEN_SPEC.md`.
>
> Personas are the canonical set from `docs/MISSION.md §2`.

---

## 0. Universal Experience Rules

- **The Morning Test** (see §1): any portfolio owner can understand their whole
  portfolio in **under 15 seconds** on login.
- **Calm by default, alarm only on action-required.** Red means "do something
  now," never "FYI."
- **Plain language always.** No telecom jargon on customer surfaces unless
  intentionally expanded with a plain explanation.
- **Every status answers "Why should I believe this?"** via View Proof.
- **Never exposed to customers by default:** ICCID, IMSI, SIP registration detail,
  firmware version, raw vendor events, internal reconciliation codes, raw AI
  uncertainty.

---

## 1. The Morning Test (the executive-grade snapshot)

The Home page is designed so **Judy logs in and understands the entire portfolio
in under 15 seconds.** This is the single most important customer moment.

```
487 Sites
482 Protected
4 Need Attention
1 Critical
Revenue at Risk: $0
Open Support Items: 2
E911 Verified: 99.8%
Recent Manley Actions: 17
Lives Protected Today: 4,872
```

Design intent: the eye lands on the three protection counts, then the one number
that quantifies risk (Revenue at Risk), then the proof-of-work (Recent Manley
Actions). Critical is the only thing that draws urgency. Everything reconciles to
a single feeling: *calm, in control, provable.* (Full screen spec: Home in
`docs/SCREEN_BY_SCREEN_SPEC.md`.)

---

## 2. Judy — Enterprise Telecom Manager

- **What she cares about:** Portfolio-wide truth at a glance; defensible
  compliance; zero silent failures; audit-readiness.
- **What she sees first:** The Morning Test snapshot, then the Attention Queue
  (only what changed / what's at risk), worst-first.
- **What she must never see:** Walls of green tiles; raw telemetry; SIP/ICCID/
  firmware; reconciliation codes; an unexplained status.
- **Daily workflow:** Glance at the snapshot → triage Critical/Attention →
  assign/escalate → end-of-month export a board-ready compliance PDF.
- **Trust signals:** "as of" timestamps, % E911 verified, View Proof, trend line,
  Recent Manley Actions count.
- **Required actions:** Acknowledge/assign Critical; export compliance report;
  drill into any site's proof.
- **Success metrics:** % portfolio Protected; MTTR for Critical; % E911 verified;
  audit-prep time (hours→minutes); zero silent failures reaching a real call.
- **Screens:** Home, Portfolio, Site, E911, Executive Dashboard, View Proof.
- **Language style:** Executive, precise, defensible. Numbers with context; no
  jargon.

## 3. Cindy — Property Manager (non-technical)

- **What she cares about:** Are my communities protected; who do I call; no
  jargon.
- **What she sees first:** Community cards in plain English — *"Belle Terre:
  Protected, last verified Tuesday."*
- **What she must never see:** Any telecom term; device-level detail; technical
  failure descriptions; anything that implies *she* must fix it.
- **Daily workflow:** Weekly glance; acts only on amber/red; forwards plain-
  language status upward; reads the Assurance Timeline for reassurance.
- **Trust signals:** "Manley has been alerted and is working on it"; the Recent
  Manley Activity timeline; last-verified dates.
- **Required actions:** Almost none — acknowledge, contact support if prompted.
  The product does the work; she gets the proof.
- **Success metrics:** Time-to-understand (seconds); jargon-driven support calls
  → zero; confidence/renewal.
- **Screens:** Home (her scope), Site, Assurance Timeline, View Proof.
- **Language style:** Warm, reassuring, zero jargon, short sentences.

## 4. Installer — Field Technician

- **What they care about:** Get in, deploy, **confirm the site is truly live and
  E911 correct before leaving.** No callbacks.
- **What they see first (mobile):** Today's jobs, then a Day-0 checklist that turns
  green step by step.
- **What they must never see:** Portfolio/exec dashboards; revenue data; other
  customers' sites; deep analytics.
- **Daily workflow:** Scan/onboard device → watch it come online live → run guided
  test call → verify E911 address → get **"Site Accepted"** → leave.
- **Trust signals:** Real-time "Device Online ✓"; test-call passed; E911 verified;
  the green "Site Accepted" confirmation.
- **Required actions:** Complete each onboarding step; resolve any red step before
  leaving; capture the test result.
- **Success metrics:** First-time-right install rate; truck-roll reduction; time-
  on-site; % sites Protected within 24h.
- **Screens:** Mobile Installer (onboarding flow), Site (mobile), View Proof
  (install evidence).
- **Language style:** Imperative, checklist-driven, instant feedback.

## 5. Support — Tier 1/2 Technician

- **What they care about:** Why a site is unhealthy and the **safest remediation**,
  fast, in one screen.
- **What they see first:** The work queue (Critical/Attention ranked by severity +
  business impact), then reason codes → recommended action.
- **What they must never see hidden:** Internal signals (RECON_*,
  INSUFFICIENT_DATA detail, raw vendor data) — these are *available* to support,
  unlike customers.
- **Daily workflow:** Pull item → read reason codes + recommended action → run
  deterministic diagnostics → apply gated safe remediation or escalate to Zoho
  Desk → action auto-logs to the site's Assurance Timeline.
- **Trust signals:** Deterministic diagnostics; recommended-action confidence;
  auto-logged audit trail.
- **Required actions:** Resolve or escalate; never apply an unsafe action to a
  life-safety line; confirm before any state change (no auto-remediation).
- **Success metrics:** MTTR-to-safe-resolution; escalation rate; first-contact
  resolution; reopened-ticket rate.
- **Screens:** Support console, Site (internal view), Device, View Proof
  (internal), Assurance Timeline (support version).
- **Language style:** Technical-precise internally; still maps to customer plain
  language when communicating outward.

## 6. Executive — Manley & Customer Leadership

- **What they care about:** Portfolio health, revenue posture, and the defensible
  "what have we done to protect them" story.
- **What they see first:** The Executive Dashboard — overall assurance trend,
  Protected %, E911 readiness %, open Critical, revenue-at-risk, assurance-activity
  volume.
- **What they must never see:** Operational noise; device-level detail; anything
  requiring telecom knowledge.
- **Daily workflow:** Monthly (and on-demand) review; uses the assurance report in
  QBRs/board decks; watches trend and revenue-at-risk.
- **Trust signals:** Trend over time; Lives Protected; Recent Manley Actions
  volume; downloadable monthly PDF.
- **Required actions:** Review, export, direct strategy. No operational actions.
- **Success metrics:** Protected % trend; revenue retained/at-risk; assurance-
  driven upsell; NPS/renewal.
- **Screens:** Executive Dashboard, Revenue, Home (rollup), monthly report.
- **Language style:** Strategic, outcome-oriented, one number per idea.

---

## 7. Internal Operations Staff (supporting persona)

Reconciliation, onboarding review, data stewardship, carrier provisioning. They
see the full internal truth: reason codes, RECON_* mismatches, raw signals, the
compliance/audit timeline, and the gated dry-run-first write planners. They are
the only persona who acts on `INSUFFICIENT_DATA` / `RECON_*`. Language style:
operational and exact. (See `docs/ARCHITECTURE.md §6–7` for RBAC.)

---

## 8. Language Style Reference

| Audience | Tone | Jargon | Example |
|---|---|---|---|
| Cindy | Warm, reassuring | None | "Belle Terre is protected — last verified Tuesday." |
| Judy | Executive, precise | None (numbers w/ context) | "482 of 487 protected · 99.8% E911 verified." |
| Installer | Imperative, instant | Minimal, expanded | "Device Online ✓ — run the test call." |
| Support | Technical-precise | Full (internal) | "DEVICE_OFFLINE 14m; recommend remote reboot." |
| Executive | Strategic | None | "Protected trend +1.2% MoM; $0 revenue at risk." |

Customer-facing copy is owned per-status in `docs/ASSURANCE_ENGINE.md §8` and
must always pair a positive status with its evidence + timestamp.
