# Public Acquisition — durable lead capture and the assessment path

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Decisions: **D-030** (public claims inherit the truth rules), **D-031** (durable
> before success), **D-032** (assessment direction), **D-033** (brand colour roles).
> Introduced by PR "Fix: Establish Durable Public Acquisition Foundation" (2026-10-01).

## 1. The invariant

**True911 never tells a prospect "received" until the submission exists durably
in True911.**

- The server returns a receipt `{"received": true, "record_ref": "ACQ-…", "status": …}`
  only after the `acquisition_records` row is **committed**.
- The client (`web/src/lib/acquisition.js` → `submitAcquisition`) shows success
  only for that exact receipt. 404, timeout, network error, 4xx, 5xx, a missing
  body or a body without `received === true` and a `record_ref` all fail. The form
  keeps every value and retries with the **same idempotency key**.
- Before this PR, `/quote` and `/get-started` showed success on 404 and on network
  errors, and the server only tried to email (nothing was persisted).

## 2. System of record

The True911 database is the system of record: table `acquisition_records`
(migration **056**, additive, one new table). Success never depends on SMTP,
email, Zoho or analytics. Those are downstream side effects. **No Zoho lead is
created** (not authorised).

| Kind | Entry point | Created with status |
|---|---|---|
| `quote_request` | `POST /api/public/quote-request` (`/quote`) | `inquiry` |
| `assessment_request` | `POST /api/public/request-access` (`/get-started`) | `inquiry` |
| `assessment` | `POST /api/public/registrations` (`/register` wizard) | `assessment_draft` |

The `/register` wizard is still **the** assessment pipeline. There is no second
lead architecture. Its full payload stays in the `registrations*` staging tables,
and the acquisition row links to it by `registration_ref`. Submit moves the row to
`assessment_submitted`, and a real (non-dry-run) internal conversion moves it to
`converted`.

### 2a. Wizard failure boundaries (hardened after #198)

A response must describe durable state.

- **Create is atomic.** The registration and its acquisition record are one
  logical operation: the record is staged through
  `create_registration(..., before_commit=…)` and the two commit together. If
  the record write or the commit fails, both roll back and the client gets
  **503 "We couldn't save your registration, and nothing was stored."** A retry
  creates exactly one registration and one record.
- **Submit is atomic.** The `draft → submitted` transition and the record's move
  to `assessment_submitted` commit together through
  `transition_status(..., before_commit=…)`. On failure the client gets **503 "It
  is still saved as a draft"**, and the draft is still there: the resume token
  keeps working and a retry submits it once. A further submit still returns 409.
- **Notifications come after the commit.** A failed internal notification never
  changes the response. The handler reloads the registration from committed
  state before replying, and the quote/assessment receipt is built before
  `notify()` runs.
- **The client never duplicates on retry.** Once create succeeds, the wizard
  keeps that draft's id and resume token (`web/src/lib/registrationSubmit.js`). A
  retry with the same answers only resubmits it. A 409 counts as "submitted" only
  after the client reads the registration back with its token and sees it is no
  longer a draft. Changing answers after a failure starts a new registration; the
  earlier draft stays visible in the internal queue.
- **Residual limitation.** If the connection drops after the server commits but
  before the client receives the response, the client has no id or token, and a
  retry creates a second draft. Closing that gap needs idempotent create with
  resume-token re-issue (BACKLOG A12).

## 3. Acquisition lifecycle (separate from deployment)

`inquiry → assessment_draft → assessment_submitted → under_review → qualified → converted → closed`

These are **acquisition** states only. None of them means anything is deployed,
connected, monitored or E911-verified. Prospect-provided information is intent,
not operational truth. `under_review` / `qualified` / `closed` are reserved for the
internal review UI (deferred). Today they are set by nobody.

## 4. Notification rule

1. Persist and commit.
2. Only then attempt the internal notification (`acquisition_service.notify`).
3. Record the outcome on the row: `notification_status` ∈ `pending | sent | failed | not_configured`,
   plus `notification_attempts`, `notification_error` and `notified_at`.

- `sent` means only that the configured SMTP transport accepted the message.
- Empty `SMTP_HOST` gives `not_configured`. It is never reported as sent. `send_email`
  returns True in that mode, which is why the service checks the host itself.
- A failed notification never deletes or duplicates the lead. A retry with the same
  key returns the same record and does **not** notify again.
- Every value in the email is HTML-escaped, and the subject is header-safe (CR/LF stripped).
- **Observability:** `GET /api/acquisition/records?notification=failed|not_configured`
  (platform role with `VIEW_REGISTRATIONS`). An internal UI is deferred.
- **Production note:** the SMTP keys are commented out in `render.yaml`, so production
  rows will read `not_configured` until SMTP is configured. That is the honest state.
  Read leads via the endpoint above.
- **Acknowledgement email to the prospect:** deferred (design only). It must never
  claim to have been sent unless the transport accepted it.

## 5. Attribution

Captured first-touch per browser session (`captureAttribution`) and sent with
each submission: `landing_path`, `referrer`, `utm_source/medium/campaign/term/content`
and `initial_cta` (the first tracked CTA). The server's
`acquisition_service.normalize_attribution`:

- strips control characters and enforces length caps;
- reduces `landing_path` to a same-origin path with no query;
- accepts `referrer` only as http(s) and drops its query;
- reduces `initial_cta` to slug characters;
- ignores unknown keys.

Attribution is **never** used for security decisions. The server also records
`entry_point` and `created_at`.

## 6. Abuse controls and the CAPTCHA decision

Abuse controls:

- server-side Pydantic validation (EmailStr, max lengths, allow-listed service/need values);
- Content-Length cap (16 KB for leads, 256 KB for the wizard), giving 413;
- a honeypot field `website`: a non-empty value gives 422, never a receipt;
- per-client rate limits: 5 per 10 min and 30 per day on creates/submits, 60 per 10 min
  on resume-token lookups, giving 429;
- safe error messages (see §6b).

**CAPTCHA is deliberately not added.** A third-party CAPTCHA adds a vendor, a
privacy surface and accessibility friction. Honeypot + rate limit + size caps are
proportionate at current volume. Revisit if `acquisition_records` shows abuse.

**The limiter is process-local, not fleet-wide.** Counts live in the memory of one
Python process. They reset on every deploy or restart, aren't shared between
uvicorn workers or API instances, and would multiply if the service scaled out.
Production runs one instance with one process. A shared store can replace
`RateLimiter` without changing callers (BACKLOG A6). This is not a global
rate limit and must not be described as one.

### 6a. Client identity for rate limiting: KNOWN LIMITATION, deferred

**Unchanged since #198.** The limiter keys on the **first** `X-Forwarded-For` entry,
falling back to the socket peer.

- Honest browsers get a correct per-visitor key.
- A determined sender can put arbitrary values first and rotate them to get fresh
  buckets.
- The honeypot, size caps and validation still apply.
- **This is not solved.** It must not be described as trustworthy client identity.

**Known topology.** Cloudflare → Render load balancer → application. Render's
documentation says all web-service traffic passes through Cloudflare and Render's
load balancers, and that the app should read `X-Forwarded-For` for the client IP.
Cloudflare documents that it appends the connecting client to an existing header.

**Not established.** What Render's load balancer adds, if anything, and therefore
which entry is trustworthy for our deployment.

Until that is established:
- no hop count is guessed;
- no Cloudflare-CIDR parser is added;
- uvicorn's `--forwarded-allow-ips` is not changed.

A wrong hop count would key visitors on Cloudflare edge addresses and throttle
legitimate prospects together, which is worse than today's behaviour. Follow-up:
BACKLOG A14 ("Public rate-limit client identity").

### 6b. Server errors

- Unhandled exceptions return a stable body:
  `{"detail": "Internal server error.", "error": "internal_error", "request_id": …}`.
  It never includes exception text, SQL, stack traces, file paths or secrets.
- The full traceback, exception type, method, path and `request_id` are logged
  server-side. Quote the `X-Request-ID` to find the log line.
- 4xx responses are unchanged: 422 keeps field-level validation detail, and
  401/403/404/409/410/429 keep their messages.
- The internal site-CSV import's 500 no longer echoes the exception.
- **Audited, not changed:** the authenticated operator consoles return 502s that
  pass through upstream vendor error text (`vola`, `zoho_crm`, `carrier_verizon`,
  `sims`). They don't include SQL, but they are listed for review (BACKLOG A13).

## 7. Assessment vs deployment (D-032)

- **Assessment is self-service**: request it or complete the wizard.
- **Qualification is sales-assisted**.
- **Deployment is True911-operated**.

There is no billing, pricing or checkout in the assessment. "Free Audit" wording
is retired. The page says **Request a Life-Safety Assessment** and does not
pretend an automated assessment exists.

## 8. `/register` architecture

`/register` (wizard) → `registrations` staging (tenant `ops`) → internal review queue
`/api/registrations` (`VIEW_REGISTRATIONS`) → `POST /api/registrations/{id}/convert`
(`CONVERT_REGISTRATIONS`, Admin/SuperAdmin, dry-run first). Conversion creates the
tenant, customer, sites, service units and an optional pending subscription. The
route is not linked from public navigation and is `Disallow`ed in `robots.txt`.

`ALLOW_PUBLIC_REGISTRATION` does **not** gate this wizard. It gates only user-account
self-registration at `POST /api/auth/register`.

## 9. Conversion truth: conversion creates a PLANNED portfolio (CT-1, D-034)

`registration_conversion` creates sites and services that are **planned**, never
operational. The values come from `app/services/site_lifecycle.py`:

| Field | Before (#198) | Now (future conversions) |
|---|---|---|
| `Site.status` | `"Connected"` | `"Pending Install"` |
| `Site.onboarding_status` | `"active"` | `"pending"`. The assurance engine treats this as **Pending Install**, never Critical. |
| `e911_street/city/state/zip` | prospect address | same, kept as an **address on file** |
| `e911_status` | NULL | `"unverified"` |
| `e911_confirmation_required` | false | **true** |
| `address_source` | NULL | `"registration"` |
| `address_notes` | dropped | `"Customer-provided location detail (not verified): …"` |
| `poc_name/phone/email` | dropped | copied from the location |
| `ServiceUnit.status` | `pending_install` | unchanged (already truthful) |
| requested phone / hardware / carrier / quantity | dropped | `ServiceUnit.meta.requested` (never serialized to customers) |
| acquisition `converted` | separate best-effort commit | **same commit** as the conversion |

**Never created by conversion:** a Line (from a typed phone number), a Device (from
requested hardware), a placement, a verified E911 status, or a live onboarding value.

**Promotion is a later, evidence-backed act:**
- **Operations:** an internal site edit (`EDIT_SITES`; DataEntry excluded) may set
  `onboarding_status` to a live value from the known vocabulary.
- **E911:** the existing provider-evidence verification path (`verify_rh_e911` /
  `record_verification_test`) sets a verified status and clears confirmation.

**Readers updated:**
- `command.py`: a planned site category is `pending`, not `critical`.
- `digest_engine.py`: a planned site is not an attention item.
- `actions.py`: ping and reboot never simulate equipment, telemetry or check-ins
  on a planned site.
- `StatusBadge` / `CommandSite`: neutral slate.
- `attention.js`: customer label "Being set up", unless device evidence says reporting.
- The customer API already reads Pending Install as "This location is being set up."

**Existing converted rows are NOT changed.** The read-only audit
(`python -m app.audit_registration_conversions`, PR #200) classifies converted sites
as A planned / B deployed with evidence / C ambiguous, using evidence only.

The read-only audit (PR #200, merged `56bbc8c`) was **run in production on
2026-10-02**: **2 converted sites from 1 registration; A = 0, B = 0, C = 2.**
- Both sites belong to registration `REG-EE9B668655CC` (tenant
  `integrity-property-management`): `TIFFANY-GARDENS-EAST` (site_pk 691) and
  `TIFFANY-GARDENS-NORTH` (site_pk 692).
- Both are now `status=archived`, `onboarding_status=retired`, `e911_status` NULL,
  confirmation not required, `address_source` NULL.
- Neither has **recorded** deployment evidence: 0 lines, 0 devices, 0 heartbeats,
  0 telemetry (0 simulated), 0 provisioning rows, 0 E911 change logs or reviews, and
  no invite issued.
- They are class **C**, not A, only because each was edited after conversion and
  has one operator audit row (the conservative rule). This does not prove they were
  never deployed. It records that no deployment evidence exists in True911.

**Stuart's decision: NO remediation.** They are historical records. No backfill
script is created, and CT-1 changes only future conversions.

## 10. Public truth rules (D-030)

Public copy inherits the platform truth rules. **Removed claims:**

- guaranteed emergency connectivity, "never go dark", "stay online. Period.";
- instant or seconds-level alerts;
- automatic E911/Kari's Law enforcement, "verified and enforced", dispatchable
  location "with every call";
- inspection-proof, automatic compliance reports;
- universal four-path/satellite failover;
- blanket "no vendor lock-in";
- blanket "Made in USA" and "NDAA-TAA Compliant";
- "Free Audit" and "True911+".

Kari's Law and RAY BAUM'S Act appear as **neutral context** only, with the line that
True911 does not certify compliance. Regression guard:
`web/src/pages/public/publicPages.test.js`.

NDAA/TAA statements may return only on a specific offering with evidence. Product
screenshots, when added (hero direction O1), must come from sanitized fixture data
and be labelled "Product UI · Sample data". The controlled product-imagery strategy
(disclosure levels, sharp-vs-abstracted specification, sanitization pipeline,
competitive review) is in `PUBLIC_PRODUCT_PROOF.md` (proposed).

## 11. Analytics event boundary (no vendor)

`EVENTS`:

- `page_view`, `cta_click`;
- `assessment_started`, `assessment_step`, `assessment_submitted`;
- `lead_created`, `lead_qualified`;
- `customer_created`, `subscriber_activated`.

`track()` is a no-op until `setSink()` installs a sink. No GA, Meta or LinkedIn
tracking is installed. Server-confirmed events (`lead_created` and later ones) are
emitted only from durable state: the client emits `lead_created` only from a real
receipt.

## 12. Migration 056 is permanent history

`056_acquisition_records.py` is applied in production (presumed from deployment
evidence). Never remove, rewrite or renumber it, and never roll back by deleting
it: a build without 056 can't start against a database at 056 (`Can't locate
revision '056'`). That rules out Render "Rollback" to a pre-#198 deploy and a
wholesale `git revert` of #198. Roll back with a forward commit that keeps the
migration history.

## 13. Future direction

- Internal acquisition review UI (statuses `under_review` / `qualified` / `closed`).
- Prospect acknowledgement email.
- Zoho lead sync as a recorded side effect.
- Shared rate limiter.
- Homepage redesign on sanitized product proof (O1); see `PUBLIC_PRODUCT_PROOF.md`.
- An analytics vendor, if approved.
- The conversion-truth remediation in §9.
