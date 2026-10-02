# Customer Lifecycle Plan: conversion truth, first login, portfolio reconciliation, billing

> **Status: PROPOSED. Nothing here is approved for implementation.**
> **Authority Level:** 3 (Execution, planning). **Governed by:** `CONSTITUTION.md`.
> **Written:** 2026-10-02, in an overnight architecture pass for Stuart's review.
> It was produced read-only: no code, migrations, production data or Render changes.
>
> **Sources:** the code at `main` = `a59ee3c`, plus PR #199 (`959a73e`, open), plus
> the docs listed in each section. Where documentation and code differ, the code
> wins and the difference is recorded.

The truth model every section must keep (D-006, D-015, D-022, D-023, D-030):

```
UNKNOWN ≠ HEALTHY        UNKNOWN ≠ PROTECTED         UNKNOWN ≠ VERIFIED
ADDRESS PROVIDED ≠ E911 VERIFIED     ASSESSMENT ≠ DEPLOYMENT   ALLOCATION ≠ DEPLOYMENT
CUSTOMER CREATED ≠ CONNECTED         SERVICE REQUESTED ≠ INSTALLED
PHONE NUMBER ≠ VERIFIED CONNECTION   DEVICE IDENTIFIER ≠ PHYSICAL PLACEMENT
UPLOAD ≠ CANONICAL TRUTH             INVOICE LINE ≠ SERVICE ASSOCIATION (without evidence)
```

---

## A. PR #199 final review: recommendation **HOLD**

**Merge-ready (verified by reading the diff and running the tests):**
- **Create atomicity.** The registration and its acquisition record commit together through `before_commit`. A real commit-time constraint violation rolls back both rows.
- **Submit atomicity.** The status transition and the acquisition status commit together. A failure returns 503 and keeps the draft.
- **Retry and idempotency.** The client keeps the draft it created; a 409 counts as submitted only after a token read-back confirms it.
- **Notification.** It runs after the commit, and the response is reloaded from committed state.
- **500 sanitization.** The global handler and the site-import route no longer return exception text, and full diagnostics stay in the logs.
- **Tests and CI.** CI is green (gitleaks, pytest, vite build). 4,990 backend and 106 frontend tests pass locally.
- **Migration 056.** Untouched (zero lines of diff under `api/alembic`).

**Blocker: the default rate-limit trust model rests on a single-proxy assumption that Render's own documentation contradicts.**

| Question | Evidence | Status |
|---|---|---|
| Is there more than one proxy? | Render, *How Render handles DDoS attacks*: "All inbound traffic to Render web services passes through Cloudflare's global network before reaching your application", and "traffic passes through Cloudflare and Render's load balancers". | **Documented: Cloudflare, then Render's load balancer.** That makes it two layers, not the single "Render edge" that #199's §6a assumes. |
| What does Cloudflare do with XFF? | Cloudflare *HTTP headers*: with no existing header, XFF = `CF-Connecting-IP`. With an existing header, Cloudflare "will append the IP address of the HTTP proxy connecting to Cloudflare", i.e. the real client. | **Documented: (B) appends the real client.** Values the client sent stay on the left. |
| What does Render's load balancer do with XFF? | Not in Render's docs (web-services, inbound-ip-rules, DDoS article). A community-forum answer quoted by search says the proxy "does not filter out any incoming X-Forwarded-For headers, but it just appends the proxy IP", but I couldn't open that page to verify it. | **UNVERIFIED.** |
| Is there another trusted mechanism? (D) | Cloudflare sets `CF-Connecting-IP`. Render documents forwarding `CF-Ray`, but doesn't say whether `CF-Connecting-IP` reaches the app or whether clients can inject it through a non-Cloudflare path. | **UNVERIFIED.** |

**Why it blocks:**
- If Render's load balancer appends Cloudflare's edge address, the rightmost entry (`hops=1`) is a **Cloudflare edge IP**, not the visitor.
- Every prospect routed through the same edge would then share one bucket of 5 submissions per 10 minutes. That is lost legitimate leads, the opposite of #198/#199's purpose.
- Today's `main` (first entry) is spoofable but correct for honest browsers, so #199 could be a regression in availability.
- #199's documentation also states "one proxy layer (Render's edge)", which conflicts with Render's article.

**Ways to unblock (Stuart decides, §M):**
1. **Split #199 (recommended).** Merge the atomicity and sanitization work, which is independent and high value. Move the client-identity change into its own PR that lands after verification.
2. **Amend #199 to be evidence-proof.** Walk XFF from the right, skipping entries inside Cloudflare's published ranges (cloudflare.com/ips) and private ranges; the first remaining entry is the client. This is correct whether or not Render appends the edge IP, and spoof-resistant either way. Cost: a small maintained CIDR list.
3. **Verify, then set the hop count.** Ask Render support the exact question, or deploy a short-lived, flag-gated diagnostic that logs only hop count and `CF-Connecting-IP` presence with addresses masked. Then pick `hops` = 1 or 2.

---

## B. Conversion truth

### B.1 What conversion does today (code, not docs)

The chain: public wizard → `registrations` + `registration_locations` + `registration_service_units` → review state machine → `POST /api/registrations/{id}/convert` → `registration_conversion.convert_registration` → tenant → customer → `_materialize_sites` → `_materialize_service_units` → optional `_maybe_create_subscription` → (router) acquisition `converted` → later, activation hooks (`issue_invite` at `ready_for_activation`; `mark_customer_complete` at `active`).

One converted, never-installed location shows up three different ways:

```
                      ┌─ Legacy portal (invited "User" role) ─► green "Connected"    ✗ false good
Converted location ───┼─ Assurance engine / customer API ─────► CRITICAL             ✗ false alarm
(no equipment)        │     (E911_UNVERIFIED + NO_ACTIVE_DEVICE)
                      └─ Reality ──────────────────────────────► being set up
```

### B.2 Field-by-field (abridged; the full trace with file:line is in the review notes)

| Destination | Source | Read as | Truth problem | Customer sees |
|---|---|---|---|---|
| `sites.status` | constant **"Connected"** (`registration_conversion.py:524`) | KPI connected count (`command.py`), digest "not attention" (`digest_engine.py:55`), simulated ping success (`actions.py:124`), `attention.js` LEGACY_MAP → green | **Connectivity nobody verified** | Legacy UI: green "Connected" |
| `sites.onboarding_status` | constant **"active"** (`:530`) | Assurance engine `_LIVE_ONBOARDING` → "expected live" | **Assessment ≠ deployment** (it also blocks the engine's Pending Install path) | Customer API: **Critical** |
| `sites.e911_street/city/state/zip` | prospect `loc.*` (`:525-528`) | `e911_address_present=true`, "Emergency dispatch address" (`customer/serialize.py`) | **Address provided ≠ E911 verified** | Address the prospect typed, shown as the dispatch address |
| `sites.e911_status` | **not set (NULL)** | Only validated/verified count as verified. Review lists key on "unverified"/"needs_review", so NULL rows can be missed. | No explicit unverified marker | "Not yet verified" |
| `sites.e911_confirmation_required` | default False | engine | Should be True for prospect data | — |
| `sites.address_source` | NULL | address enrichment | Provenance lost | — |
| `sites.lat/lng`, country | dropped | map, geocoder | Lost | no map pin |
| location POC, dispatchable description | dropped | — | Lost (only on staging rows) | — |
| `service_units.status` | "pending_install" | `customer/portfolio.py` → "Pending Install" | **Truthful. Keep it.** | "Being set up" |
| requested phone number, hardware model, carrier, quantity | **dropped** (`quantity` 3 → 1 unit) | — | Lost, though correctly never asserted | — |
| `subscriptions` | status "pending"; `qty_lines` = estimate; no MRR or dates | reconciliation counts only active | `qty_lines` labelled "billed lines" holds an estimate | not shown |
| `customers.status` | "active" | admin lists | Customer created ≠ active service | indirect |
| acquisition `converted` | separate, best-effort commit (`registrations.py:453`) | acquisition reports | Can disagree with the conversion | — |
| **invited user** | `INVITE_ROLE = "User"` (`registration_activation.py:66`) | **The legacy internal-plane role, holding `INTERNAL_OPS`** | **A self-service customer is not put on a `CUSTOMER_*` role.** They land in the legacy shell (green "Connected"), not the customer Command Center, and hold internal-ops permission within their tenant. | Legacy portal |

**Other conversion findings:**
- The convert gate allows `pending_customer_info`.
- A pre-set `target_tenant_id` silently overrides `tenant_choice`.
- The failure path commits a failure event even on a dry run.
- After a dry-run rollback, the response reads attributes of expired objects (`registration_conversion.py:1012-1016`). That is a suspected async `MissingGreenlet`. It is unverified, because the unit tests use fake sessions.
- Conversion writes **nothing** to the canonical model (D-023). In registry mode a converted site appears only if it happens to link to an approved building.

### B.3 Recommended architecture: "Conversion creates a planned portfolio, never an operational one"

```
Registration (assessment)        Conversion (planned)              Deployment (evidence)
──────────────────────────       ───────────────────────────       ────────────────────────────
location ───────────────────►    Site: status "Pending Install"     operator "Mark location live"
                                       onboarding_status "pending"  ── requires device/line evidence
address ────────────────────►    e911_* = address on file           E911 workflow → verified
                                       e911_status "unverified"     (official record only, D-021/D-025)
                                       e911_confirmation_required ✓
                                       address_source "registration"
service request ────────────►    ServiceUnit "pending_install"      install + test → "active"
phone / device / carrier ───►    ServiceUnit.meta.requested{…}      Line / Device created ONLY by
                                 (never a Line or Device)           provisioning with evidence
```

**Rules:**
- Conversion may only write *planned* states.
- Promotion to live is a deliberate operator action backed by evidence. The existing `provision_deploy` path already sets Provisioning/Active.
- The canonical model is fed later as **candidates**: `new_building` review items, services at PROBABLE/UNRESOLVED, phone numbers as UNRESOLVED assets, and a new `REGISTRATION` evidence source. Never as approved rows.

**Migration impact: none for the core fix.**
- `Site.status`, `onboarding_status`, `e911_status` and `address_source` are free strings, and `e911_confirmation_required` is a boolean.
- `ServiceUnit.meta` (JSONB) already exists.
- An optional later step would add a CHECK constraint or enum for `Site.status`, which has no validator today. Not in this PR.

**Readers to update in the same PR:**
- `StatusBadge.jsx` and the `attention.js` LEGACY_MAP: "Pending Install" as neutral "Being set up". Today an unmapped status reads "Registered".
- `customer/serialize.py:325`, which keys `is_critical` on lowercase `"active"`.
- Align the verified-status sets: engine `{validated, verified, confirmed}` vs serializer and `e911_gaps` `{validated, verified}`.
- `actions.py:124`, the simulated ping.
- Move the acquisition `converted` write into the conversion commit, using #199's `before_commit` pattern.

**Production risk.** Converted sites may already exist, and some may since have been deployed for real. Before any change, run a **read-only audit**:
- sites linked through `registration_locations.materialized_site_id`;
- their status and onboarding values, and `updated_at` vs `created_at`;
- device and line counts and last heartbeat;
- service-unit statuses;
- E911 review or change-log rows;
- whether an invite was issued.

A later backfill would be a separate dry-run-first script that touches only rows with zero devices and lines and an unchanged `updated_at`.

**Proposed PR (CT-1, after Stuart approves):** "Conversion creates planned locations, not connected ones." It covers `_materialize_sites` values, `meta.requested`, the readers listed above, the acquisition commit, and rewriting `test_conversion_truth_characterization.py` into regression tests (never Connected, never a live onboarding value, never verified).

**Separate decisions (not bundled into CT-1):**
- **CT-2:** the invite role (`CUSTOMER_ADMIN`?).
- **CT-3:** the convert gate and the `target_tenant_id` override.
- **CT-4:** verify the dry-run expired-object bug.
- **CT-5:** canonical candidate feed.

---

## C. Customer first-login guided experience

### C.1 What exists

- **Shell** (`CustomerShell.jsx`): routed purely by a `CUSTOMER_` role prefix. Top bar from `md` up; bottom bar below `md` with 56px items.
- **Views:** Overview · Action Center (only if self-service loads) · Locations, via `?view=`. A location opens a dialog with four tabs (Overview, Services & Lines, Compliance, Records). The E911 wizard is reserved to `CUSTOMER_ATTEST_E911` (ADMIN).
- **Account menu:** name, Change password, Help (a mailto), Sign out.
- **Gaps:** no tour library and no first-login code. The only first-login mechanism is the forced password change. No per-user UI-state storage. No portfolio-wide Requests view (the API exists). No Help page. The location `Modal` in `LocationOperations.jsx` has no focus trap.
- **Building blocks available:** Radix Popover, Dialog and Tooltip; vaul (drawer); framer-motion; `useReducedMotion` and the `.t911-customer` reduced-motion rule.
- **Recommendation: build a small in-house coach-mark** from Radix Popover plus Dialog. No tour dependency is justified.

### C.2 Journey (about 75 s, six steps, anchored to the real UI)

| # | Anchor (real UI) | Says | Varies by |
|---|---|---|---|
| 1 | Welcome card over the status statement | "This is your Command Center: one place to see your locations' life-safety lines. Here is what True911 knows today." Shows the **live** status statement and tiles. Explains that grey "being confirmed" items are True911's work, never "healthy". | — |
| 2 | Action Center (rail on Overview) | The ownership tags. "**Your action** items need you; **True911** items we are handling." Urgent comes first. | Self-service off: anchor to the Exceptions rail instead |
| 3 | Locations view (and map on desktop) | Search, exceptions first, open a location. | Mobile skips the map |
| 4 | Location → Compliance (E911) | "E911 has three parts: an address on file, your confirmation, and official verification. Only the official record makes it Verified." | ADMIN: how to confirm or correct. MANAGER: your administrator confirms; you can submit a review. VIEWER: read-only explanation. |
| 5 | Location → Overview → Requests, plus Account menu → Help | How to request a change, report a problem or get help. | VIEWER: help only |
| 6 | Finish | "Replay this tour any time from the account menu." | — |

**Requirement 7 (where billing and inventory will live) conflicts with an existing rule.** The shell must not show "Billing", "Coming soon" or "Soon", and nav may point only at destinations that exist (`commandCenter.test.js:231-243`). **Recommendation:** the tour says nothing about billing until Billing is real (§M question).

### C.3 Storyboard (desktop / mobile)

```
Desktop ─ Step 2                                   Mobile ─ Step 2 (bottom sheet)
┌──────────────────────────────────────────────┐   ┌───────────────────────┐
│ True911  Overview  Action Center  Locations ▾│   │ Status statement       │
│ ┌──────────────── Status statement ────────┐ │   │ ┌ Action Center rail ┐ │
│ │ 2 locations need attention               │ │   │ │▓ highlighted      ▓│ │
│ └──────────────────────────────────────────┘ │   │ └───────────────────┘ │
│ [tiles] [tiles] [tiles] [tiles]               │   │╭─────────────────────╮│
│ ┌ map ──────────────┐ ┌ What needs you ────┐ │   ││ 2 of 6               ││
│ │                   │ │▓ highlighted rail ▓│◄┼─┐ ││ "Your action" items  ││
│ └───────────────────┘ └────────────────────┘ │ │ ││ need you…            ││
└──────────────────────────────────────────────┘ │ ││ [Back] [Next] Skip   ││
     ┌───────────────────────────────┐            │ │╰─────────────────────╯│
     │ 2 of 6 · Action Center        │────────────┘ │ ▢Overview ▢Actions ▢… │
     │ "Your action" items need you; │              └───────────────────────┘
     │ "True911" items we handle.    │
     │ [Back]  [Next]   Skip tour    │
     └───────────────────────────────┘
```

### C.4 Rules

- **Who gets it.** Only `CUSTOMER_*` roles, never while impersonating, and only after the forced password change.
- **Urgent items come first.** The tour never auto-starts while the Urgent tier has items. It offers a quiet "Take the 1-minute tour" chip instead, so urgent items are never covered.
- **Persistence.** Server-side per user (preferred): a small additive table `user_ui_state(user_id, key, value JSON, updated_at)` storing `tour.command_center = {version, status: completed|skipped, at}`. Interim: `localStorage` keyed by user id, wrapped in try/catch. A tour **version** lets a substantial revision re-offer the tour once. Persistence needs a migration, so it is a separate slice.
- **Replay.** An Account menu item "Take the tour".
- **Accessibility.**
  - The coach card is a labelled, non-modal dialog with focus moved into it.
  - Tab stays inside the card; Esc means "Skip tour". Each step is announced as "2 of 6".
  - The highlight is not colour-only.
  - Targets are at least 44px.
  - Reduced motion: no animated travel or pulsing.
  - On mobile, the card is a bottom sheet above the bottom bar.
- **Truth.** Copy is static explanation plus the live values the existing `statusStatement()` already produces. It never claims protected, verified or monitored. Tour files join `customerTerminology.test.js`'s file list, so the banned terms are enforced.
- **Events.** `tour_started`, `tour_step`, `tour_completed` and `tour_skipped`. Extending the D-032 event vocabulary is itself a decision.

**Implementation plan.**
- **FL-1:** a `TourProvider`, `CoachMark` and `steps.js` (pure step resolution by role and capability, tested in node) behind `VITE_FEATURE_CUSTOMER_TOUR`, persisted in localStorage.
- **FL-2:** server-side persistence (migration).
- **FL-3:** content review with RH Test before Judy's invite.

---

## D. Billing Center architecture (no implementation)

### D.1 What exists vs. what is planned

| Capability | State |
|---|---|
| Stripe | **Unused dependencies only** (`web/package.json` `@stripe/*`); backend tests **forbid** Stripe imports. No keys. |
| QuickBooks | **Placeholder**: an HMAC inbound webhook `/qb/webhook` that writes subscriptions through the generic processor. No OAuth, API client, invoices or sync. |
| Zoho | CRM `Subscription_Mgmt` staging with `mrc` (flags off). No Zoho Books or Billing. |
| Model | `subscriptions` (plan_name, status, **mrr**, qty_lines, start/renewal dates, external refs); `customers.billing_email/phone/address`; registration billing intake (plan, method, billing address; text only). |
| Customer API | `billing_from_subscription()` serializer exists but **no route**. `GET /api/customer/billing` is specified (`CUSTOMER_API_CONTRACTS.md` §8, PR-C3). |
| RBAC | `CUSTOMER_VIEW_BILLING` (ADMIN, MANAGER, BILLING) is unused. **Mismatch:** the contracts doc says ADMIN and BILLING only. A `CUSTOMER_BILLING` role exists. No permission for pay, methods or contacts. |
| Invoices, payments, statements, autopay, PCI | **Nothing in code or docs.** RH go-live Track D scopes a read-only MRR surface; QuickBooks and invoices are deferred. |

### D.2 Boundaries

```
┌──────────────────────── TRUE911 (experience + representation) ──────────────────────┐
│ Billing views · invoice/statement MIRROR · plan & recurring charges · billing status │
│ invoice-line ⇢ subscription ⇢ location/service ASSOCIATION (with basis) · audit      │
│ NEVER: card numbers, CVV, bank account numbers, amounts computed client-side         │
└───────────────▲───────────────────────────────────────────────▲──────────────────────┘
                │ webhooks (signed, idempotent) / read sync      │ read sync
┌───────────────┴────────────── PAYMENT PROCESSOR ─┐  ┌─────────┴──────── ACCOUNTING SYSTEM ───┐
│ hosted payment page / embedded fields (iframe)   │  │ invoice of record, AR, GL, tax,        │
│ payment methods (tokens) · charges · autopay     │  │ reconciliation, credit memos           │
│ → True911 sees brand + last4 + status only       │  │ (system of record for money)           │
└──────────────────────────────────────────────────┘  └────────────────────────────────────────┘
```

**The first decision (B0) is which system issues invoices today and should keep issuing them.** Options:
- QuickBooks Online plus QBO Payments;
- Stripe Billing plus accounting sync;
- Zoho Books or Billing, next to the Zoho CRM lifecycle system of record.

Choose on today's invoicing practice, the accountant's system, ACH vs card mix, autopay needs, and fees. Don't choose on which SDK happens to be in `package.json`.

**PCI target: SAQ-A.** Card entry happens only on the processor's hosted page or iframe fields. True911 never receives payment-card data.

### D.3 Data model (future, additive)

- **`billing_accounts`**: customer_id, external system + id (hidden), status, autopay_state mirror, default contact.
- **`invoices`**: external_id (hidden), number, issue/due dates, currency, subtotal, tax, total, amount_due, status (`draft|open|paid|partially_paid|past_due|void|uncollectible`), statement/PDF reference, `synced_at`, source.
- **`invoice_lines`**: description, quantity, unit amount, amount, service period, external subscription ref.
- **`invoice_line_associations`**: invoice_line_id → subscription_id / building / service, with **`basis` ∈ {EXTERNAL_ID_EXACT, OPERATOR_MAPPED, UNASSOCIATED}** and who/when. *An invoice line is never linked to a service without a basis; otherwise it reads "Not yet linked to a location".*
- **`payments`** (mirror): amount, date, method brand/last4, status, failure reason (customer-safe).
- **`billing_contacts`**: reuse `customers.billing_*` first, then a table if multiple contacts are needed.
- **`billing_sync_runs`** plus **`billing_events`**: an append-only audit trail of payment, autopay and contact changes, mirrored to ActionAudit.

**APIs (customer, allow-list serialized):**
- `GET /api/customer/billing` (summary)
- `/billing/invoices`, `/billing/invoices/{ref}`, `/billing/invoices/{ref}/statement`, which returns a short-lived signed URL
- `/billing/payments`
- `POST /billing/invoices/{ref}/pay-session`, which returns a hosted page URL
- `POST /billing/payment-methods/session`, `PATCH /billing/autopay`, which proxy to the processor
- `/billing/contacts`

Payment status changes only through **signed processor webhooks**.

### D.4 RBAC (recommendation, not policy)

| Permission | ADMIN | BILLING | MANAGER | VIEWER/USER |
|---|---|---|---|---|
| `CUSTOMER_VIEW_BILLING` (exists) | ✓ | ✓ | ? (§M) | ✗ |
| `CUSTOMER_PAY_INVOICES` (new) | ✓ | ✓ | ✗ | ✗ |
| `CUSTOMER_MANAGE_PAYMENT_METHODS` / autopay (new) | ✓ | ✓ | ✗ | ✗ |
| `CUSTOMER_MANAGE_BILLING_CONTACTS` (new) | ✓ | ✓ | ✗ | ✗ |

### D.5 Phases

1. **B0:** decide the issuing system and the processor.
2. **B1:** read-only "Plan & charges" from existing subscriptions/MRR (already specified as PR-C3; matches RH Track D), flag-gated. Its empty state is "Billing details are being finalized", never an invented number.
3. **B2:** read-only invoice and statement mirror sync; Invoices and Statements views.
4. **B3:** billing contacts (customer-owned).
5. **B4:** pay an invoice through a hosted page.
6. **B5:** payment methods and autopay through the processor.
7. **B6:** past-due and failed-payment states plus notifications.
8. **B7:** invoice-line ↔ service association (operator-mapped).

The Billing nav item appears only once B1 is real, per the existing rule.

---

## E. Portfolio export

**Format:**
- CSV (UTF-8 with BOM, so it opens in Excel).
- Row 1 holds the manifest: `schema=t911.portfolio.v1`, `export_id`, `tenant`, `generated_at`.
- Each row is one location, service or connection (`row_type`), with stable opaque refs.
- Each row carries a `row_etag` (a hash of the server values at export time) for optimistic concurrency.
- The export is **registered** (`export_id` stored), so an upload diffs three ways: the export base, current True911 state, and the uploaded file.
- An XLSX variant with a README sheet can come later.

| Column | Class | Notes |
|---|---|---|
| `row_type`, `location_ref`, `service_ref`, `connection_ref` | key (read-only) | Opaque refs (`bldg_…`, HMAC-signed connection refs) |
| `location_id` (customer's store number) | request-based | D-028 label "Location ID" |
| `location_name` (canonical) / `display_name` (customer) | request / **customer-owned** | Overlay field |
| `street`, `city`, `state`, `postal_code`, `country` | request-based (`location_correction`) | Read-only in effect; changes become governed requests |
| `access_notes`, `location_notes`, `customer_reference` | **customer-owned** | Overlay |
| `service_type`, `service_status` (customer label) | request / read-only | Customer vocabulary only |
| `connection_friendly_name`, `purpose`, `customer_notes`, `customer_contact` | **customer-owned** | Overlay |
| `telephone_number` | request-based (`change_number`) | Only where the customer API already shows it; never MSISDN |
| `equipment` (generic: "Elevator phone gateway") | read-only | No identifiers |
| `e911_readiness`, `address_on_file`, `confirmation_state` | read-only | Three dimensions, never collapsed (D-015) |

**Never exported** (`SYSTEM_MANAGED_FIELDS`, `CUSTOMER_API_CONTRACTS.md` §1, Constitution veto 9): ICCID, IMEI, IMSI, MSISDN, SIM ids, SIP credentials, serials, MAC addresses, firmware, IPs, carrier and provider account ids, Napco/Genesis/Zoho/QuickBooks ids, reconciliation or import internals. No change is proposed to this boundary.

---

## F. Bulk import and reconciliation

**Name:** internally, the **Portfolio Reconciliation Engine**, with two modes, *Maintenance* and *Onboarding*. Customer copy must avoid "reconcile", which is a banned customer term (`selfService.js` `INTERNAL_TERMS`). Customer-facing labels: "Upload portfolio changes" and "Review changes".

**Reuse, not a new inventory:**
- Upload handling follows the source-snapshot discipline (D-024): immutable, SHA-256, dry-run first.
- Matching uses the registry normalizers and the D-023 placement priority.
- Governed changes become `CustomerServiceRequest`s.
- Customer-owned changes write the `CustomerManagedField` overlay.
- Canonical changes go through `OperatorDecision`.
- Evidence is recorded as `CanonicalEvidence` with a new source, **CUSTOMER**.
- Audit is `CustomerActivityEvent` mirrored to ActionAudit.
- **Avoid** the existing direct-write importers: `subscriber_import.commit_import`, `site_import_engine` commit, and `csv_importer` (no preview at all).

**New tables (migration, later):**
- `portfolio_uploads`: immutable header (tenant, uploaded_by, sha256, base_export_id, schema, mode, status).
- `portfolio_upload_rows`: row number, raw hash, parsed values, match result, classification.
- `portfolio_change_proposals`: field, base, current, proposed, ownership class, route, decision, applied_ref.

```
RECEIVED → PARSED → VALIDATED → MATCHED → DIFF_READY ─┬─► READY_FOR_APPROVAL → APPROVED → APPLYING ─┬─► APPLIED
                                                      └─► NEEDS_REVIEW ──────────┘                  ├─► PARTIALLY_APPLIED
   (any state before APPLYING) ─► SUPERSEDED (newer upload) │ CANCELLED │ EXPIRED (base too old)   └─► FAILED
```

**Row/field classification:**
- **UNCHANGED**
- **PROPOSED ADD** · **PROPOSED CHANGE** · **PROPOSED RETIREMENT**: governed, never direct.
- **AMBIGUOUS:** more than one candidate match.
- **CONFLICT:** current ≠ base and ≠ upload, i.e. a stale edit. The diff shows all three values.
- **INVALID:** parse or format failure.
- **NOT PERMITTED:** a system-managed field, or the role lacks permission.
- **REQUIRES TRUE911 REVIEW:** moves, identity, E911, lifecycle.

**Hard rules:**
1. Blank means **no change**. Removal needs an explicit `REMOVE` token, and even then it only proposes a retirement.
2. A missing row means **no information**, never decommission.
3. No path can set E911 verified, deployed or monitored.
4. Moving a service between locations is always a governed `move_service` request.
5. Nothing is deleted. Supersession preserves lineage.
6. Free-text cells are screened for identifier patterns (closing the self-service gap where only keys are checked, not values).

**Matching order:**
1. The exported `*_ref` (exact).
2. Location ID unique in the tenant.
3. Normalized address.
4. Alias or name. Names only ever **suggest**; they never auto-match.
5. No cross-tenant matching, ever (tenant isolation). A duplicate number seen in another tenant is an internal-only operations signal.

**Approval and apply:**
- `CUSTOMER_ADMIN` approves customer-owned proposals, which are applied to the overlay in small idempotent transactions per proposal.
- Governed proposals become requests that True911 works through the existing queue.
- Partial apply is recorded per proposal.

**Rollback:**
- Overlay changes are reverted by a compensating batch built from the stored base values.
- Governed changes are reversed through supersession of the request or decision.

**Audit questions answered per applied change:**

| Question | Recorded as |
|---|---|
| Who | actor |
| When | `occurred_at` |
| Which file | `upload_id` + sha256 + row number |
| Before | base and current values |
| After | new value |
| Owned or governed | ownership class |
| Approved by | approver |
| Evidence | evidence ref |

---

## G. Initial enterprise portfolio onboarding (the same engine, Onboarding mode)

A 500-location customer receives a **template**: the export schema with no refs, allowed values including "unknown / not sure", and an example row marked as an example. Each row becomes **customer-provided evidence**:
- locations become `new_building` review items;
- services become LifeSafetyService **PROBABLE/UNRESOLVED** candidates;
- telephone numbers become **UNRESOLVED** CommunicationsAsset candidates;
- carrier and notes are kept as evidence attributes.

The engine reports:
- duplicate locations and numbers within the file;
- incomplete addresses;
- conflicting IDs;
- possible existing True911 records in the same tenant;
- ambiguous building matches;
- missing services, as a *suggestion only*.

**From acquisition:** a file attached during the assessment is stored as evidence on the acquisition or registration record (sha256). After conversion it is **carried into the tenant's onboarding run by reference**, not re-entered, and its provenance stays "prospect-provided".

---

## H. Command Center information architecture

**Top level (at most four items, which fits the mobile bottom bar):**
- **Overview**
- **Action Center**: it already contains "In progress (True911)" request tracking. Add a Requests tab inside it rather than a top-level item.
- **Locations**: services and lines per location, a portfolio "Services" lens as a view toggle, and "Export / Upload changes" in the toolbar (ADMIN).
- **Billing**: only once B1 is real.

**Not top-level:** Inventory (a lens of Locations), Requests (inside Action Center), E911 (per location plus an Action Center tier), Help and the tour (account menu), Documents and Reports (actions within views), Users and settings (account menu, once customer user management exists).

The customer's questions map onto it like this:

| Question | Answered by |
|---|---|
| Anything wrong? | Overview status statement |
| What needs me? | Action Center |
| Where? | Locations / map |
| What services? | Location → Services, or the Locations Services lens |
| What is True911 doing? | Action Center "In progress" |
| What am I paying for? | Billing |
| How do I change something? | Location actions / Upload changes |

---

## I. End-to-end lifecycle

```
PUBLIC SITE ─► LIFE-SAFETY ASSESSMENT ─► acquisition_records (inquiry→assessment_submitted)   [#198/#199]
                   │ (+ optional portfolio file = evidence, sha256)
                   ▼
            INTERNAL QUALIFICATION (registrations review states)                   acquisition: under_review/qualified
                   ▼
            CONVERSION ─► tenant / customer / PLANNED sites + pending_install units  [CT-1]  acquisition: converted
                   ▼
            PORTFOLIO ONBOARDING (Reconciliation Engine, Onboarding mode)  ◄── file carried by reference
                   ▼   candidates → review → approval → canonical (D-023) + overlay (D-021)
            DEPLOYMENT (provisioning; evidence promotes Pending Install → live)
                   ▼
            E911 (address on file / customer confirmation / official verification) · MONITORING (evidence)
                   ▼
            COMMAND CENTER (first-login tour → Overview / Action Center / Locations)
                   ▼
            BILLING (subscriptions → invoices mirror → payments via processor)  ·  RENEWAL (Zoho lifecycle SoR)
                   ▼
            ONGOING (Reconciliation Engine, Maintenance mode: export → scrub → upload → review)
```

---

## J. Proposed decisions (to record only once approved)

- **D-034:** Conversion creates planned locations, never operational state (B.3).
- **D-035:** Customer uploads are evidence. Changes route by ownership class (overlay / governed request / refused). Blank means no change; absence means no information.
- **D-036:** Billing boundary. True911 represents, the processor executes, accounting records. No card data in True911 (SAQ-A). An invoice line is linked to a service only with a basis.
- **D-037:** First-login guidance is customer-plane only, skippable, persisted per user, and asserts nothing beyond the existing truth rules.
- **D-038:** Client-IP trust model for public rate limiting (after the Render verification in §A).
- **D-039:** Self-service invites use a `CUSTOMER_*` role, not the legacy internal `User` (pending decision).

(D-029 is reserved by the unmerged #193.)

---

## K. Recommended order (an improvement on the proposed one)

1. **Resolve #199**: split, or amend per §A. Merge the atomicity and sanitization; land client identity after verification.
2. **The RH Completion Program stays primary (D-025, Master Plan).** New workstreams fit around it, not ahead of it. **Doc drift:** `RH_COMPLETION_PROGRAM.md` reserves migration 056 for slot #188, but #198 used 056, so the program's migrations become 057+. Its "#188–#193" are program slots, not GitHub PR numbers.
3. **Conversion truth CT-1**: small and no migration, preceded by the read-only production audit and the CT-2 invite-role decision. It is a correctness fix and unblocks everything downstream.
4. **Portfolio Export (read-only)**: earlier than import. It is safe, immediately useful to RH, and fixes the schema the import needs.
5. **First-login tour FL-1**: ideally ready before RH acceptance (#193 slot), since Judy is its first audience.
6. **Billing B0 decision and B1 read-only "Plan & charges"**: B1 is already specified and in RH Track D.
7. **Reconciliation Engine**:
   - R1: staging and dry-run diff, internal-only;
   - R2: customer review UI;
   - R3: apply customer-owned changes;
   - R4: governed routing;
   - R5: Onboarding mode and the link to acquisition.
8. **Billing B2–B7.**
9. **Assessment and public acquisition redesign.**
10. **Homepage and subscriber funnel.**
11. **Analytics vendor.**

Why this order differs:
- Export before import (read-only first, Constitution §4.2).
- The tour is pulled ahead of bulk work because it serves the RH launch.
- Billing B1 is pulled ahead because it is read-only, already specified, and in RH scope.
- The assessment redesign waits for conversion truth and the Onboarding mode, so the new funnel feeds a truthful pipeline.

---

## L. Open questions for Stuart

See the morning report; the authoritative list is in BACKLOG "Customer lifecycle workstreams".
