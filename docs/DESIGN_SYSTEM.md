# True911+ — DESIGN SYSTEM

> **Constitution-level document.** Defines the True911 design language — the tone,
> color intent, status language, iconography, layout, empty/alert behavior, and
> the strict separation between customer and internal views. Governed by
> `docs/PRODUCT_MANIFESTO.md`. Applies to every customer-facing surface in
> `docs/SCREEN_BY_SCREEN_SPEC.md`. Implementation reuses the existing React +
> Tailwind + Radix/shadcn stack (`docs/ARCHITECTURE.md §8`).

---

## 1. Design Values

The product must feel: **Calm · Trustworthy · Minimal · Plain-language ·
Enterprise-grade.**

And it must avoid: **unnecessary alarm · noisy red · vanity metrics · unexplained
green checks · technical jargon on customer dashboards.**

The emotional target: a customer should leave any screen feeling *reassured and in
control*, with the evidence to back the feeling.

## 2. Tone

- **Honest before reassuring.** We never soften a real Critical, and we never
  inflate a Protected. Calm is earned by truth, not by hiding problems.
- **Plain, short, human.** Sentences a property manager understands instantly.
- **Action-oriented when action is needed; quiet when it isn't.**
- **Defensible.** Every assertion is phrased so it could stand in front of a
  regulator or an attorney ("verified as of <time>," never "guaranteed").

## 3. Color Intent

Color encodes **required action**, not decoration. (Exact palette tokens live in
the Tailwind theme; intent is fixed here.)

| Intent | Meaning | Where |
|---|---|---|
| **Protected (calm green)** | Active & verified | only with evidence + timestamp |
| **Attention (amber)** | A human should check one item | soft, non-urgent |
| **Critical (red)** | Act now — calling may not work | reserved; never decorative |
| **Inactive (neutral grey)** | Intentionally not active | suppressed, calm |
| **Pending (blue/info)** | Being set up | informational |
| **Unknown (muted)** | Confirming | honest, low-key |

**Rules:**
- **Red is rationed.** It appears only when immediate action is required. Never use
  red for "FYI" or for intentionally-inactive sites.
- **Green never appears alone.** A green status always carries its "why" + "as of."
- **No color-only meaning.** Always pair color with a label + icon (accessibility).

## 4. Status Language

The six labels are fixed (`docs/ASSURANCE_PLATFORM_SPEC.md §3`):
**Protected · Attention Needed · Critical · Pending Install · Inactive /
Deactivated · Unknown.**

- Customer copy uses the per-status sentences in `docs/ASSURANCE_ENGINE.md §8`.
- "Protected" always renders with an "as of <time>" qualifier + disclaimer.
- The internal/clinical equivalent of Protected is "Active & Verified."
- Never invent new customer-facing status words per screen — the vocabulary is
  global and singular.

## 5. Icon Usage

- One consistent icon per status, paired with the label (never icon-only).
- Icons are calm and geometric, not alarmist (no flashing, no exclamation-heavy
  motifs except on true Critical).
- Evidence types (device/carrier/E911/test/monitoring) each have a stable icon used
  consistently in View Proof and the four-axis Site breakdown.
- No vendor logos or device imagery on customer surfaces (we sell assurance, not
  hardware).

## 6. Layout Principles

- **One primary question per screen**, answered above the fold (see each screen's
  "primary question" in the screen spec).
- **Worst-first ordering** in any list of sites/issues — never alphabetical by
  default.
- **Progressive disclosure:** calm summary first; evidence and technical depth one
  interaction away (View Proof / internal panels).
- **Whitespace as calm.** Dense telemetry tables are an internal pattern, not a
  customer one.
- **The number that matters is the anchor.** (Home → protection counts; E911 → %
  verified; Revenue → revenue at risk.)

## 7. Empty States

Empty states **guide**, never blank or dead-end:
- Home (no sites): "No sites yet — start onboarding."
- Portfolio (filtered to nothing): "No sites match these filters."
- Timeline (new site): "Activity will appear here as we protect this location."
- Always offer the next safe action where one exists.

## 8. Alert Behavior

- **Alarm only on action-required.** Critical alerts; Attention nudges; everything
  else is quiet.
- **No false "all good."** If data is missing or stale, the UI says so and the
  status degrades conservatively — it never shows confident green over a gap.
- **Stale data is labeled, not hidden** ("as of <time>" / "refreshing").
- **Alerts carry the why + the action**, never a bare red dot.
- **Intentionally-inactive sites never alarm** (Inactive/Pending are calm).

## 9. Internal vs Customer View Separation

This separation is a design *and* security requirement.

| | Customer view | Internal/support view |
|---|---|---|
| Status label | ✅ plain language | ✅ + reason codes |
| Evidence | ✅ plain, via View Proof | ✅ raw values |
| ICCID/IMSI/SIP/firmware | ❌ never default | ✅ |
| Raw vendor events | ❌ | ✅ |
| `RECON_*` / `INSUFFICIENT_DATA` detail | ❌ | ✅ |
| Raw AI uncertainty | ❌ | ✅ (as confidence, labeled) |
| Commercial/revenue data | ❌ (only own tenant, exec-gated) | ✅ internal |

Enforced via RBAC + sanitized serializers (`to_customer_view()` pattern). A
customer surface that leaks an internal field is a defect, not a styling issue.

## 10. Accessibility & Trust Cues

- Color + label + icon together (never color alone).
- Timestamps are human-readable ("Tuesday 2:14pm") with exact time on hover.
- "View Proof" is a consistent, always-available affordance on every status.
- Disclaimers are present but calm — informative, not fear-inducing.

## 11. Anti-patterns (forbidden in the design)

- Walls of green tiles (Judy's nightmare).
- A single composite numeric "readiness score."
- Red used decoratively or for non-actionable info.
- Unexplained green checks.
- Telecom jargon on customer dashboards.
- Vanity metrics with no decision value.
- Raw vendor telemetry as the customer's primary experience.

(See `docs/ASSURANCE_PLATFORM_SPEC.md §7` for the full "never build" list.)
