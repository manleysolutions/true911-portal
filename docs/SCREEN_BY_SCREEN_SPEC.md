# True911+ — SCREEN-BY-SCREEN SPEC

> **Constitution-level document.** Defines the finished product screens. Each
> screen is specified by: purpose, primary user, primary question answered,
> required data, main actions, customer-facing language, internal-only fields,
> trust/proof elements, empty states, error states, and what must never appear.
> Governed by `docs/PRODUCT_MANIFESTO.md`; statuses in
> `docs/ASSURANCE_PLATFORM_SPEC.md`; visual/language rules in
> `docs/DESIGN_SYSTEM.md`; personas in `docs/CUSTOMER_EXPERIENCE.md`.
>
> Screens reuse existing components where possible (`PropertyHealth.jsx`,
> `CustomerStatusBadge`, `AssuranceBadge`, `DeploymentMap`) — see
> `docs/ASSURANCE_ENGINE.md §6, §13`.

---

## Global rules for every screen

- Must answer **"Why should I believe this?"** (View Proof reachable in one tap).
- Every status shows its **"as of" timestamp** and disclaimer where it's a claim.
- **No green without explanation. No status without evidence.**
- Customer surfaces never show: ICCID, IMSI, SIP detail, firmware, raw vendor
  events, `RECON_*`, raw AI uncertainty.
- Empty states **guide**, never blank. Error states **degrade conservatively**
  (toward Attention/Unknown) and say what's missing — never a false "all good."

---

## 1. Home (the Morning Test)

- **Purpose:** Whole-portfolio understanding in <15 seconds.
- **Primary user:** Judy / Cindy / Executive (role-scoped).
- **Primary question:** "Are my people protected right now?"
- **Required data:** Portfolio counts by label; % E911 verified; revenue at risk;
  open support items; Recent Manley Actions count; Lives Protected; 30-day trend.
- **Main actions:** Drill into Critical/Attention; open Portfolio; export snapshot.
- **Customer language:** "482 Protected · 4 Need Attention · 1 Critical."
- **Internal-only fields:** raw reason-code rollups, ops-only mismatch counts.
- **Trust/proof:** "as of" timestamp on the snapshot; View Proof per item; trend.
- **Empty state:** "No sites yet — start onboarding" with a CTA.
- **Error state:** If a data source is stale, show "Some data is being refreshed
  (as of <time>)" — never silently show stale-as-current.
- **Never appears:** device telemetry; a single composite numeric score; jargon.

> **The Morning Test snapshot (canonical layout):**
> ```
> 487 Sites · 482 Protected · 4 Need Attention · 1 Critical
> Revenue at Risk: $0 · Open Support Items: 2 · E911 Verified: 99.8%
> Recent Manley Actions: 17 · Lives Protected Today: 4,872
> ```

## 2. Portfolio

- **Purpose:** Manage many sites; find what needs attention.
- **Primary user:** Judy.
- **Primary question:** "Which locations need me, and which are proven fine?"
- **Required data:** All sites with label, E911 state, last verified, customer,
  region, trend.
- **Main actions:** Filter/sort (default **worst-first**); bulk export; map toggle.
- **Customer language:** plain labels + last-verified dates.
- **Internal-only fields:** reconciliation status, raw signals.
- **Trust/proof:** per-row View Proof; portfolio % E911 verified anchor metric.
- **Empty state:** "No sites match these filters."
- **Error state:** Partial load → show what loaded + a refresh notice.
- **Never appears:** alphabetical-by-default sort that buries Critical; jargon.

## 3. Site (the heart of the product)

- **Purpose:** One location's full, provable truth.
- **Primary user:** Judy / Cindy / Support.
- **Primary question:** "Is this location protected, and why?"
- **Required data:** Assurance label + as-of + disclaimer; four-axis breakdown
  (Service active · Device reachable · E911 verified · Recently tested); E911
  checklist; Assurance Timeline; reason codes (internal).
- **Main actions:** View Proof; Run test call; open E911 workspace; escalate.
- **Customer language:** per-status sentences from `ASSURANCE_ENGINE.md §8`.
- **Internal-only fields:** reason codes + recommended action panel; raw signals.
- **Trust/proof:** the four-axis evidence rows; Recent Manley Activity; View Proof.
- **Empty state:** Pending Install → onboarding checklist; no devices → "Unknown."
- **Error state:** missing axis → conservative label + "we're confirming X."
- **Never appears:** ICCID/SIP/firmware in the customer view; unexplained green.

## 4. Device

- **Purpose:** Technical drill-down for diagnosis.
- **Primary user:** Support / internal (advanced admin opt-in).
- **Primary question:** "What exactly is wrong with this asset?"
- **Required data:** operational state, last heartbeat/carrier event/call/test,
  vendor adapter detail, SIM/line status, firmware.
- **Main actions:** Run diagnostics; gated remediation (with confirmation); view
  vendor data.
- **Customer language:** sanitized summary only if ever shown to a customer.
- **Internal-only fields:** all telemetry, vendor payloads, reason codes.
- **Trust/proof:** raw evidence timestamps feeding the site label.
- **Empty state:** "No telemetry yet for this device."
- **Error state:** vendor fetch fail → show last-known + failure note.
- **Never appears:** as a customer's *primary* experience (customers think in
  locations); auto-applied life-safety changes.

## 5. E911

- **Purpose:** The compliance workspace — the most legally important surface.
- **Primary user:** Judy / internal compliance.
- **Primary question:** "Will 911 route correctly, and can I prove it?"
- **Required data:** per-site dispatchable address, verification state,
  confirmation-required, immutable change log; portfolio % verified.
- **Main actions:** Guided verify-address (gated, auditable); bulk remediation
  queue for unverified-but-active sites.
- **Customer language:** "The 911 address is verified / being verified."
- **Internal-only fields:** validation source, PSAP/carrier detail, change author.
- **Trust/proof:** immutable change log; verification timestamps; % verified.
- **Empty state:** "No E911 records yet."
- **Error state:** validation service down → mark "pending verification," never
  "verified."
- **Never appears:** a "verified" claim without an actual verification record.

## 6. Revenue

- **Purpose:** Map assurance posture to commercial reality.
- **Primary user:** Executive / internal.
- **Primary question:** "What is our revenue exposure and growth opportunity?"
- **Required data:** revenue at risk (at-risk/renewing accounts), assurance-tier
  distribution, upsell candidates, churn-risk signals.
- **Main actions:** Filter by account; export; flag for sales follow-up.
- **Customer language:** N/A (internal/executive).
- **Internal-only fields:** all commercial data; account mapping.
- **Trust/proof:** read-only from Zoho lifecycle; never writes commercial state.
- **Empty state:** "No commercial data linked yet."
- **Error state:** Zoho fetch fail → last-synced note.
- **Never appears:** cross-tenant commercial data; writes back to Zoho.

## 7. Support

- **Purpose:** Resolve unhealthy sites safely and fast.
- **Primary user:** Support T1/T2.
- **Primary question:** "What's wrong, why, and what's the safest fix?"
- **Required data:** ranked work queue (severity + business impact); reason codes;
  recommended action; deterministic diagnostics; last events.
- **Main actions:** Diagnose; gated remediation (confirm first); escalate to Zoho
  Desk; auto-log to Assurance Timeline.
- **Customer language:** mapped to plain language when communicating outward.
- **Internal-only fields:** RECON_*, raw signals, recommended-action confidence.
- **Trust/proof:** auto-logged audit trail; diagnostics evidence.
- **Empty state:** "Queue clear — nothing needs attention."
- **Error state:** action failure → clear failure + safe retry, never silent.
- **Never appears:** auto-remediation of life-safety status without approval.

## 8. Mobile Installer

- **Purpose:** Confirm a site is truly live + E911 correct before the tech leaves.
- **Primary user:** Installer.
- **Primary question:** "Is this site accepted and protected?"
- **Required data:** today's jobs; live onboarding state; test-call result; E911
  verify.
- **Main actions:** Scan/onboard → watch online → run test call → verify E911 →
  **Site Accepted**.
- **Customer language:** checklist imperatives with instant green ticks.
- **Internal-only fields:** device identifiers during onboarding (tech context).
- **Trust/proof:** the live "Device Online ✓ / Test Passed ✓ / E911 ✓" sequence →
  feeds the Assurance Timeline.
- **Empty state:** "No jobs scheduled today."
- **Error state:** a step fails → block "Site Accepted," show the fix.
- **Never appears:** portfolio/exec/revenue data; other customers' sites.

## 9. Executive Dashboard

- **Purpose:** Strategic assurance + business posture in one view.
- **Primary user:** Executive.
- **Primary question:** "Are we safe, and are we growing — provably?"
- **Required data:** assurance trend, Protected %, E911 readiness %, open Critical,
  revenue at risk, assurance-activity volume, Lives Protected.
- **Main actions:** Review; export monthly PDF.
- **Customer language:** strategic, one number per idea.
- **Internal-only fields:** none beyond aggregates (tenant-scoped).
- **Trust/proof:** trend over time; Recent Manley Actions volume; downloadable
  report as the proof artifact.
- **Empty state:** "Not enough history yet — trend appears after first month."
- **Error state:** partial aggregates → show coverage caveat.
- **Never appears:** operational noise; vanity metrics; device detail.

## 10. Assurance Timeline *(product concept)*

> The Assurance Timeline is **not a raw log.** It is the plain-language story of
> **what Manley did to keep this site protected.** It is a core retention and
> trust feature — it makes the service tangible.

- **Purpose:** Tell the protection story for a site/portfolio.
- **Primary user:** Cindy/Judy (customer version); Support (internal version);
  Compliance (audit version).
- **Primary question:** "What has Manley done to protect us?"
- **Example (customer version):**
  ```
  08:14 — SIM Activated
  08:17 — E911 Verified
  08:20 — Test Call Passed
  08:21 — Device Online
  08:22 — Protected
  ```
- **Three versions:**
  - **Customer-facing** — plain language, sanitized, reassurance-oriented.
  - **Internal support** — adds reason codes, technical detail, actor.
  - **Compliance/audit** — full, immutable, timestamped, with sources.
- **Required data (read-only aggregation, no new capture):** `action_audit`,
  `command_activity`, `e911` change log, `verification_tasks`,
  `support`/`SupportEscalation`, `Job` history, `Incident` transitions,
  reconciliation events.
- **Main actions:** Filter by date/type; **export proof package** (audit version).
- **Internal-only fields:** actor identity, raw codes, internal IDs.
- **Trust/proof:** *it is itself the proof of work.*
- **Empty state:** "Activity will appear here as we protect this location."
- **Error state:** source gap → show available entries + a gap note.
- **Never appears:** internal IDs/secrets in the customer version; raw vendor
  events as customer entries.

## 11. View Proof *(product concept)*

> Every Protected / Attention / Critical label must let the user **inspect the
> evidence behind it.** This is how the platform answers "Why should I believe
> this?" — see `docs/ASSURANCE_PLATFORM_SPEC.md §4`.

- **Purpose:** Make every status independently believable and defensible.
- **Primary user:** All (depth scales with role).
- **Primary question:** "What is the evidence for this status?"
- **Required data / shows:**
  - Last verified timestamp
  - Data sources used
  - Device evidence
  - Carrier evidence
  - E911 evidence
  - Test-call evidence
  - Monitoring evidence
  - Recent Manley actions
  - Limitations / disclaimer
  - **Export option** (proof package)
- **Main actions:** Inspect each evidence type; export.
- **Customer language:** each evidence row in plain language with a timestamp.
- **Internal-only fields:** raw signal values, reason-code internals.
- **Trust/proof:** *this screen is the trust mechanism of the entire product.*
- **Empty state:** if evidence is partial, **say which evidence is missing** and
  show how that affected the (conservatively degraded) label.
- **Error state:** never fabricate evidence; show "could not retrieve X."
- **Never appears:** a confident proof for a status we cannot evidence; raw vendor
  payloads as customer-facing proof.

---

## Screen ↔ Persona ↔ Existing-component map

| Screen | Primary persona | Reuse candidate |
|---|---|---|
| Home (Morning Test) | Judy/Cindy/Exec | dashboard widgets + `AssuranceBadge` |
| Portfolio | Judy | site list + `CustomerStatusBadge` + `DeploymentMap` |
| Site | Judy/Cindy/Support | `PropertyHealth.jsx` pattern |
| Device | Support/internal | `DeviceHealth.to_customer_view()` |
| E911 | Judy/compliance | E911 admin surfaces + change log |
| Revenue | Exec/internal | new, read-only over Zoho lifecycle |
| Support | Support | support console + diagnostics |
| Mobile Installer | Installer | onboarding flow + test-call |
| Executive Dashboard | Exec | aggregates + `jspdf`/`html2canvas` export |
| Assurance Timeline | all (3 versions) | read-only aggregation (no new capture) |
| View Proof | all | `/api/assurance/site/{id}` evidence shape |
