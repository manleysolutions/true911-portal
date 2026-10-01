# True911+ — Customer Self-Service (Customer Operations Console)

> Moves the customer plane from **"dashboard + email support for changes"** to
> **"customer operations console + governed escalation"**. A customer
> administrator (Judy at Restoration Hardware) manages the **customer-owned**
> operational layer of her portfolio herself, and asks for anything that touches
> provisioning, identity or life-safety verification through a **governed
> request** that operations review. Support stays available — as escalation,
> not navigation.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§3 priority order, §4.3 separate axes, §4.6 no green without evidence, §4.7
> tenant isolation, §7 no jargon), `DECISIONS.md` D-006 / D-016 / **D-021**.
> Companions: `CUSTOMER_COMMAND_CENTER.md`, `LOCATION_DIGITAL_TWIN.md`,
> `E911_CUSTOMER_REVIEW_WORKFLOW.md`, `PORTFOLIO_REGISTRY.md`,
> `RH_GO_LIVE_RUNBOOK.md` §4f. Prepared: 2026-09-30.

---

## 1. The model

```
Portfolio  →  Location  →  Services / Connections  →  Action
```

Every screen answers *"what do I need to do?"* before *"what does True911 know?"*.
The dashboard carries an **Action Center**; every location carries a **Manage this
location** panel with the outstanding actions and the primary actions:

**Manage Location · Manage Connections · Verify E911 · Add Service · Request
Service Change · Report a Problem · Update Contacts**

"Contact support" remains, one line, at the bottom — secondary.

## 2. The ownership boundary (binding)

| Class | What | How it changes |
|---|---|---|
| **Customer-managed** | Location display name · location notes · access notes · customer reference · notification preferences · facility / emergency / property-manager contacts · per-connection friendly name, purpose (elevator / fire alarm / emergency phone / security / fax / gate / other), notes, point of contact | **Directly**, by the customer. Stored in the customer **overlay** (`customer_managed_fields`) beside — never inside — the system record. Every write is an audit event with old/new. |
| **Request-based** | Canonical name · address · city/state/zip · store number · site type (→ `location_correction`) · telephone number or E911 callback number (→ `change_number`) · service type (→ `change_service_type`) · add / remove / move service · replace equipment · problem report · **E911 verification** | Creates a `CustomerServiceRequest`. **Nothing changes** until operations act, through the existing controlled tools. |
| **System-managed** | SIM / ICCID / IMEI / IMSI / MSISDN · SIM activation state · carrier provisioning & account ids · SIP credentials · network configuration · device hardware identity (serial, MAC, firmware, model, radio #) · monitoring / health / telemetry evidence · audit & certification evidence · **verified-E911 status** · source-system and Portfolio Registry mappings | **Refused** (HTTP 403, `system_managed_field`). A payload that mixes an allowed field with a system field is refused **whole** — nothing in it is applied. |

The authoritative lists are the constants at the top of
`api/app/services/customer/self_service.py` (`LOCATION_FIELDS`,
`CONNECTION_FIELDS`, `REQUEST_BASED_*`, `SYSTEM_MANAGED_FIELDS`). A request's free-
form `requested_changes` may not carry system identifiers either — customers
describe the need in words; operations hold the identifiers.

**Why an overlay, not an edit of the record.** The canonical identity stays the
Portfolio Registry building (`canonical_name` is never customer-written); the
customer's "Our Chicago Store" is a display preference layered on top. A
customer edit therefore can never overwrite a Site, Device, Line, registry, carrier
or E911 value — structurally, not by convention.

## 3. E911 self-service

The customer does **their portion** of verification; the official record is never
customer-asserted.

1. Review the service telephone numbers.
2. Review the registered dispatch address (the official E911 record on the linked
   site; else the canonical service address).
3. Confirm the building.
4. Confirm / add suite, floor, additional location detail.
5. Confirm or request a callback-number change.
6. **Attest** that the information is correct (required).
7. Submit.

Submission creates an `e911_verification` request whose `requested_changes` holds
the **server-side snapshot** (not client content), the attestation (who, when,
method `customer_attestation`, which items were confirmed), and any corrections;
for a site-backed location it also feeds the **existing** internal E911 review
queue (`e911_review.record_confirmation` / `record_correction`) — one verification
authority, not two.

| State | Label (customer) | Reached when |
|---|---|---|
| `not_verified` | E911 record being prepared | no dispatch address on file, nothing submitted — **not a customer action** (§12) |
| `customer_confirmation_required` | Confirmation needed | address on file, nothing submitted — or operations asked the customer to re-confirm |
| `customer_submitted` | Submitted — awaiting verification | attestation submitted, no corrections |
| `requires_review` | Correction under review | attestation carried corrections (address, suite, floor, callback …) |
| `verification_pending` | Verification in progress | operations are working it (also after they complete the request, until the official record changes) |
| `failed` | Needs correction | operations rejected the submission |
| `verified` | Verified | **only** when the official record is verified (`Site.e911_status`) |

Provenance travels with the state: `verified_by` / `verification_method` /
`verification_timestamp` / `source` for the official record (timestamp `null`
when the record does not carry one — never fabricated), `attested_by` /
`attested_at` / `customer_attestation` for a submission. Completing an E911
request does **not** mark E911 verified; the official record changes only through
the existing `UPDATE_E911` flow (`/api/e911-changes`).

## 4. RBAC

| Permission | Roles | Allows |
|---|---|---|
| `CUSTOMER_MANAGE_LOCATION` | CUSTOMER_ADMIN | location profile, connection name / purpose / notes / contact, location corrections |
| `CUSTOMER_MANAGE_CONTACTS` | CUSTOMER_ADMIN, CUSTOMER_MANAGER | facility / emergency / property-manager contacts |
| `CUSTOMER_SUBMIT_REQUESTS` | CUSTOMER_ADMIN, CUSTOMER_MANAGER, CUSTOMER_SUPPORT | service requests, problem reports, cancel / respond |
| `CUSTOMER_ATTEST_E911` | CUSTOMER_ADMIN | E911 attestation |
| `CUSTOMER_VIEW_REQUESTS` | all seven `CUSTOMER_*` roles | read requests + activity |
| `MANAGE_CUSTOMER_REQUESTS` | Admin, Manager, DataSteward, UX_QA_ANALYST (internal) | the operations queue |

**Manager semantics.** The existing `CUSTOMER_MANAGER` grants mirror the account
owner's *operational* rights (contribute, E911 confirm, support) but not the
administrative ones; here it keeps contacts + requests, and does **not** get
location/connection administration or the E911 **attestation** (a legal
statement reserved for the account owner). `CUSTOMER_USER` keeps its existing
contribution + E911-confirm rights and gains nothing new; VIEWER / READONLY /
BILLING are read-only. No `CUSTOMER_*` role holds `MANAGE_CUSTOMER_REQUESTS`
(pinned by `test_customer_rbac_posture.py`).

Every route re-checks permission and tenant **server-side**; the UI only decides
what to show (`GET /customer/self-service/capabilities`).

## 5. Requests

Types: `add_service · remove_service · move_service · change_number ·
change_service_type · replace_device · e911_verification · location_correction ·
support_request` (shown as "Report a Problem").

Statuses and who moves them:

```
submitted ──► under_review ──► approved ──► in_progress ──► completed
    │              │               │              │
    └──────────────┴───────► waiting_customer ◄───┘      (operations)
    └──► rejected                  │
customer: cancel (submitted / under_review / waiting_customer) · respond (waiting_customer → submitted)
```

Every transition writes a `customer_activity_events` row (`request_status_changed`,
old → new) and an `ActionAudit` mirror. The customer sees the actor of an operations
transition as **"Operations team"** — never a staff identity.

## 6. Audit

`customer_activity_events` is append-only: tenant, location key, building / site,
connection key, request ref, event type, field, **old value, new value**, summary,
**origin** (`customer_portal` | `operations`), actor email / name / role, time.
Each event is mirrored into the platform `ActionAudit` log (`action_type =
customer_self_service`, acting-as tenant recorded) so internal audit tooling sees
it too. The location **Activity** feed renders the same events in plain language
("Judy · Updated emergency contact", "Operations team · Move service: completed").

## 7. API

All under `/api/customer` — customer API two-key gate + the self-service gate
(§8) + the permission above; 404 when off.

| Method | Path | Permission |
|---|---|---|
| GET | `/self-service/capabilities` | CUSTOMER_VIEW_LOCATIONS |
| GET | `/action-center` | CUSTOMER_VIEW_DASHBOARD |
| GET | `/locations/{ref}/workspace` | CUSTOMER_VIEW_LOCATIONS |
| PATCH | `/locations/{ref}/profile` | CUSTOMER_MANAGE_LOCATION |
| PUT | `/locations/{ref}/contacts` | CUSTOMER_MANAGE_CONTACTS |
| PATCH | `/locations/{ref}/connections/{connection_ref}` | CUSTOMER_MANAGE_LOCATION |
| POST / GET | `/locations/{ref}/requests` | CUSTOMER_SUBMIT_REQUESTS / CUSTOMER_VIEW_REQUESTS |
| GET | `/requests` (`?open=true`), `/requests/{request_ref}` | CUSTOMER_VIEW_REQUESTS |
| POST | `/requests/{request_ref}/cancel`, `/respond` | CUSTOMER_SUBMIT_REQUESTS |
| GET / POST | `/locations/{ref}/e911/verification` | CUSTOMER_VIEW_E911 / CUSTOMER_ATTEST_E911 |
| GET | `/locations/{ref}/activity` | CUSTOMER_VIEW_LOCATIONS |

Internal: `GET /api/customer-requests` (`?status=open|all|<status>`),
`GET /api/customer-requests/{ref}` (with history), `POST
/api/customer-requests/{ref}/transition` `{to_status, notes}` —
`MANAGE_CUSTOMER_REQUESTS`, acting tenant, 404 when the global flag is off.

`{ref}` is a registry `bldg_…` ref (registry mode) or a legacy `loc_…` ref (Site
mode) — the same layer serves both (`location_key` = `bldg:<id>` / `site:<site_id>`).
A `connection_ref` is HMAC-signed **together with its location key**, so a ref
issued for one location is rejected on another.

## 8. Flags & rollout

| Flag | Default | Meaning |
|---|---|---|
| `FEATURE_CUSTOMER_SELF_SERVICE` | `false` | global kill-switch (also gates the internal queue) |
| `CUSTOMER_SELF_SERVICE_TENANT_ALLOWLIST` | `""` | tenants that get the console |
| `CUSTOMER_SELF_SERVICE_USER_ALLOWLIST` | `""` | optional emails; when set, **only** these users get it (RH Test first) |

Set on **both** `true911-api` and `true911-worker` (per-service env vars). With the
flag off every route 404s, the UI components render nothing, and the customer view
is byte-for-byte the pre-existing one. Rollback: flip the flag — instant, no
deploy, no data change (overlay / requests / events are retained).

Rollout: enable for RH with the user allowlist = the RH Test user → exercise the
console → clear the user allowlist → run the go-live audit → send Judy's invite
(`RH_GO_LIVE_RUNBOOK.md` §4f).

## 9. Devices KPI (fixed with this work)

The RH dashboard showed **Devices = 0** in registry mode for two reasons: the UI
read `summary.devices` while the registry summary returned only `total_devices`
(and also omitted `critical_sites` / `sites_requiring_attention`, which made the
"All listed locations are currently protected" banner render at 29/45 — a false
green, now fixed in both the API keys and the banner rule); and the registry count
summed only equipment on *linked True911 sites*. Devices are now counted as
**physical devices** from all evidence — approved registry mappings, the fused
device groups of the approved review payloads, and True911 Device rows — merged by
shared identifier (`services/customer/physical_devices.py`). A Napco radio seen in
three sources with its SIM and number is **one** device; an ICCID, IMEI-less SIM or
phone number on its own is **zero**.

## 10. Files

- Models / migration: `api/app/models/customer_self_service.py`,
  `api/alembic/versions/053_customer_self_service.py` (off `052`).
- Service: `api/app/services/customer/self_service.py`; device counting
  `physical_devices.py`; gate `gate.require_customer_self_service`.
- Routers: `api/app/routers/customer.py` (self-service section),
  `api/app/routers/customer_requests.py` (internal queue).
- Audit: `api/scripts/rh_customer_go_live_audit.py`.
- UI: `web/src/components/customer/{ActionCenter,LocationOperations}.jsx`,
  `selfService.js` (+ `selfService.test.js`, `npm test`).
- Tests: `test_customer_self_service.py` (real SQLite DB via
  `tests/_customer_db.py`), `test_customer_physical_devices.py`,
  `test_rh_customer_go_live_audit.py`, `test_customer_rbac_posture.py`.

## 12. Customer semantics (go-live pass, 2026-09-30)

**E911 — action vs state.** Only `customer_confirmation_required` and `failed`
are customer actions (`customer_action = "verify_e911"`); Verify E911 is offered
only there. `not_verified` means *no dispatch address on file*: there is nothing
to confirm, so it is labelled **"E911 record being prepared"**, carries no action,
and is reported to operations as a system warning by the go-live audit. The
Action Center therefore shows two buckets — **E911 confirmations needed** (each
row opens the location straight into Verify E911) and **E911 records being
prepared** (informational) — and the headline counts them separately
("35 E911 confirmations needed · … · 10 E911 records being prepared"). The
combined figure stays available as `counts.e911_attention`. (Before this pass the
two were one list headlined "45 E911 confirmations", and Verify E911 was offered
on records with no address.)

**One dispatch address.** The registry read model computes a single
`dispatch_address` per building (official E911 record on a linked site first, else
the canonical service address). The dashboard, the location page, the E911 wizard
and the go-live audit all read it, so a location is never "being prepared" on one
screen and "confirmation needed" on another.

**Building → Life-Safety Service → Connection → Device → Carrier.** A service
(Elevator, Fire Alarm …) may have several connections (lines / numbers); a
connection may be known — e.g. a registry telephone number — before it is linked
to a monitored service. Such a connection is named **"Additional line"**, its
service reads **"Not yet linked to a life-safety service"**, and its status stays
Unknown. The workspace reports `service_count`, `connection_count` and
`unlinked_connection_count` ("2 connections across 1 service · 1 not yet linked to
a service"). Devices are counted separately (§9) and never per connection.

**Data Completeness vs Operational Readiness.** See `LOCATION_DIGITAL_TWIN.md`
§12. Contacts the customer supplies through the console count toward the
readiness item *Site contacts*.

**Workspace controls.** Upload Photo / Upload Document render disabled with a
*Soon* badge (no file storage yet; they cannot open a form). Add Procedure,
Record Inspection and Add Note are real text records. With self-service on, the
older append-only *Add Contact* and *Create Request* controls are replaced by
Update Contacts and the governed requests, so there is one path for each. Billing
remains a *Soon* section with no control.

## 13. Presentation: calm, owned, evidence-based (D-022)

The console presents its data under the customer trust rule — **UNKNOWN ≠ FAILED,
UNKNOWN ≠ PROTECTED** — and by owner:

- **For you (customer actions):** E911 confirmations ready · requests waiting on
  you · site contacts (low priority, "Portfolio setup").
- **True911 is working on:** E911 records being prepared (no dispatch address
  yet) · monitoring records being confirmed · requests in progress.
- **Urgent** is reserved for evidence-backed service problems.

The Action Center returns `tiers` (urgent / action_needed / in_progress /
informational, each with its lists and owner) and a `being_reconciled` list;
the location workspace returns `operational_state` and
`monitored_service_count`. Presentation rules live in the pure, unit-tested
`web/src/components/customer/selfService.js` (`portfolioHero`,
`actionCenterTiers`, `locationActions`, `LOCATION_TABS`, `statusWord`,
`operationalView`). The location page and dashboard are described in
`LOCATION_DIGITAL_TWIN.md` §14 and `CUSTOMER_COMMAND_CENTER.md` §8g.

## 14. Customer UX conventions (D-028)

**Universal nouns.** Generic UI says **Location**, and **Facility** where a
physical place reads better. It never says Store / School / Campus / Installation /
Gallery: those are customer data (a building named "Edmonton Gallery #505" keeps
its name) or a future per-tenant vocabulary layer. Defaults live in
`CUSTOMER_NOUNS` in `web/src/components/customer/selfService.js`:

| Concept | Customer label | Notes |
|---|---|---|
| a place the customer has service | Location | universal default |
| the customer's own identifier on True911's record (`store_number`) | Location ID | hint: "site, building, school, store or facility number" |
| the customer-owned overlay reference | Your reference / cost-center # | unchanged |
| True911's governed record of the location | True911 record | not "official": it is not a legal or government record |

A future vocabulary layer could override these per tenant (RH: Location / Gallery,
school district: School / Campus, municipality: Facility / Site, military:
Installation / Building, healthcare: Facility / Campus). No such engine exists yet.

**Ownership on every screen.** Every item answers *who acts?*:

| Owner | Dashboard (Action Center) | Location page |
|---|---|---|
| Customer action | Action needed ("Things you can do now") | "Your to-do here" |
| True911 action | In progress ("True911 is handling these — nothing for you to do") | "True911 is working on: …. No action is needed from you." |
| Optional setup | Portfolio setup ("Optional — complete over time; nothing is wrong") | Portfolio setup readiness |
| History | Recent activity ("History — already done; nothing is waiting") | Activity ("Already done, for your records") |

A request waiting on the customer appears only under Action needed. Activity rows
are past tense; a request's current status is shown only on the request.

**No internal language.** Never shown to a customer: reconcile / reconciliation,
canonical, registry, mapping, source systems, research / review flags, and SIM or
device identifiers as the default view (Constitution §7.9). The UNKNOWN
`being_reconciled` state reads "Monitoring record being confirmed — True911 is
confirming this location's monitoring information. No action is needed from you."
Internal flags inside a record name ("RESEARCH REQUIRED …") are stripped from the
customer name, and nothing is invented in their place.

## 11. Not in this slice (roadmap)

Notification delivery for the stored preferences · document / photo storage ·
an internal UI for the request queue (API only today) · auto-drafting an
`E911ChangeLog` from an approved E911 correction · SLA timers on requests.
