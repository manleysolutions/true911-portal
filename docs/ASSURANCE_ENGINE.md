# True911 Assurance Engine — Specification

**Status:** Approved direction; MVP scoped, not yet implemented.
**Owner:** Manley Solutions / True911 platform.
**Principle:** Read-only · Deterministic · Explainable · Feature-flagged · Tenant-scoped · Customer-safe · Reuse-first · **Never overwrites** operational, lifecycle, or E911 source-of-truth.

---

## 1. Executive Summary

The Assurance Engine is a **read-only, deterministic, explainable** function that turns data True911 already collects into a single customer-facing **Assurance Label** per device, rolled up per site/location and per customer portfolio. It is the shared spine for the customer dashboard, site readiness view, attention queue, compliance reporting, and (future) executive summaries.

It introduces **no new monitoring**. It **composes** existing source-of-truth axes (operational health, commercial lifecycle, deployment/install lifecycle, E911/compliance) into one calm label — **without overwriting any axis**. ~80% of inputs already exist (`services/health/`, `services/device_health/`, E911 fields, `call_records`, `verification_tasks`, Zoho `lifecycle_status`).

**MVP shape:** compute-live, read-only, feature-flagged, **labels only (no numeric score shown to customers)**, backend-first with exhaustive table-driven tests. Snapshots, alerts, PDF, and UI are explicitly deferred.

---

## 2. Product Positioning

True911 is an **Emergency Communications Assurance Platform**, not a device-monitoring portal. Customers do not think in SIMs/ICCIDs/SIP/firmware. They ask:

- Is this location protected?
- Will 911 work?
- Is the E911 address correct?
- Is the service active?
- Is the device reachable?
- Has it been tested recently?
- What needs attention?
- **What has Manley Solutions done to protect us?**

The Assurance Engine answers the first seven with one label + a calm explanation + an E911 checklist. The eighth is the **Recent Manley Activity** timeline (§9).

---

## 3. Source-of-Truth Axes (must remain separate)

| Axis | Owner / source | Field(s) today |
|---|---|---|
| **Operational health** | True911 telemetry → `services/health` normalizer | `CanonicalDeviceState` from `HealthSignals` (heartbeat / carrier event / CDR / VOLA sync); collapsed to `NormalizedStatus` (Online/Offline/Attention/Unknown) |
| **Commercial lifecycle** | Zoho CRM | `sites.lifecycle_status` (active/suspended/deactivated/pending_install/unknown)¹; `zoho_subscription_records.lifecycle_state`; `zoho_status_normalizer.presents_as_active_monitoring()` |
| **Deployment / install lifecycle** | True911 onboarding/provisioning | `sites.onboarding_status`, `sites.reconciliation_status`, `Device.status` (provisioning), registration status |
| **E911 / compliance** | True911 | `sites.e911_status`, `sites.e911_confirmation_required`, `sites.e911_street/city/state/zip`; `lines.e911_status`; `e911` change log |

¹ *The `sites.lifecycle_status` column and Zoho staging tables are delivered by the Zoho Lifecycle work (PR #70). Until that merges to `main`, the engine treats these inputs as absent and degrades conservatively — see §16.*

**Hard rules the engine enforces:**
- Computes a **label only**; never mutates operational status, Zoho lifecycle, E911 status, or device status.
- **Commercial-active never implies operationally healthy.** A Zoho-active line that is offline is **Critical**, not best-status.
- **A live heartbeat never hides a compliance gap.** Fresh heartbeat + missing/unverified E911 on active service = **Critical**.
- **Missing data ≠ healthy.** Absent signals push toward Attention/Unknown, never the best status.
- **Deactivated/suspended → no false emergency alarms** (resolve to Inactive/Deactivated).
- **Pending installs are not failures** (resolve to Pending Install).

---

## 4. Approved MVP Labels

| Label | Plain meaning | Alarm? |
|---|---|---|
| **Protected** | Service active and verified working | No |
| **Attention Needed** | Likely working, but a human should check something | Soft |
| **Critical** | Emergency calling may not work right now | Yes |
| **Inactive / Deactivated** | Service intentionally not active (suspended/cancelled) | No (suppressed) |
| **Pending Install** | Not yet in service (being deployed/tested) | No |
| **Unknown** | Not enough data to assert status | No, but flagged for ops |

### Label-wording decision: "Protected" vs "911 Ready"

- **Prior spec** used **"911 Ready."** Reconsidered for **liability** — it can read as a guarantee that a 911 call will succeed.
- **Approved MVP label is "Protected."** It is calmer and less of an absolute guarantee, but still a positive assurance claim.
- **Recommendation (safer wording):** display **"Protected"** *always paired with an "as of <timestamp>" qualifier* and a short disclaimer ("Status reflects the most recent data; not a guarantee of call completion"). If legal prefers a more clinical term, the documented fallback is **"Active & Verified"** (most conservative) — this requires **no engine change**, only a label string + customer copy swap.
- **Open for sign-off (Q-A):** confirm "Protected (as of <time>) + disclaimer" wording with Stuart/legal before any customer surface ships.

> Internally the best state may be referenced as `PROTECTED` regardless of the customer string chosen, so the decision logic is independent of marketing copy.

---

## 5. Decision Matrix

Computed **per device/line first**, then **rolled up to site**. Evaluation is **ordered — first matching branch wins** (the ordering is what enforces the §3 rules).

### Per device / line (ordered)

| # | Branch | Condition (first match wins) | Result |
|---|---|---|---|
| 1 | **Inactive / Deactivated** | commercial lifecycle ∈ {deactivated, suspended} **OR** device lifecycle = decommissioned | **Inactive / Deactivated** (alarms suppressed). If also transmitting, set ops-only `RECON_DEACTIVATED_BUT_TRANSMITTING` for the ops queue — never a customer Critical. |
| 2 | **Pending Install** | commercial lifecycle = pending_install **OR** deployment status pre-active (onboarding/provisioning not yet active) **OR** device never observed any liveness AND not yet expected live | **Pending Install** |
| 3 | **Critical** | service active/expected-live AND any hard-fail: operational **Offline** (no liveness within global stale threshold) · **E911 address missing** · **dispatchable location not verified** · SIM/line **inactive/suspended** while active · **failed test** on record · open **Critical** incident | **Critical** |
| 4 | **Attention Needed** | service active AND any warning: operational **Attention** (low signal / SIP unreg / network disconnected but fresh) · `e911_confirmation_required` · **test overdue / no test on record** · open non-critical incident or open support ticket · failed sync / recent failed job for this site · `RECON_ACTIVE_BUT_OFFLINE` soft-mismatch | **Attention Needed** |
| 5 | **Protected** | service active AND all green: operational **Online** · E911 address present + dispatchable **verified** + not confirmation_required · SIM/line active · no open Critical incident. **Test recency is a warning only (see §16 Q1) — not a gate.** | **Protected** |
| 6 | **Unknown** | none of the above can be asserted (active/expected-live but no liveness signal at all and not clearly pending, or key inputs missing) | **Unknown** (+ ops flag `INSUFFICIENT_DATA`) |

### Approved decisions baked into the matrix
- **Missing/unverified E911 on an active service → Critical** (branch 3). We cannot claim a location is Protected if 911 may misroute.
- **Recent test → warning, not gate.** Overdue/missing test → Attention (branch 4); a *failed* test → Critical (branch 3).
- **Stale threshold = existing global platform threshold** (`services/health/thresholds`). No per-device-class thresholds in MVP.
- **Pending Install mapped conservatively from existing fields** (Zoho `lifecycle_status=pending_install`, `onboarding_status`, device `provisioning`). No new lifecycle system.

### Site rollup (after device labels)
- Site commercial lifecycle deactivated/suspended → **Inactive / Deactivated** (whole site).
- All devices Pending (or pre-active site) → **Pending Install**; no devices at all → **Unknown**.
- Else **worst-wins**: any device **Critical** → Critical; any **Attention** → Attention; all **Protected** → Protected; otherwise **Unknown**.
- **Site-level E911 gate** still applies: an active site whose dispatchable address is missing/unverified is at least **Critical** even if devices report Online (a live device behind a wrong 911 address is the exact failure we must catch).

---

## 6. Signal Inventory & Current Code Mapping

| Signal | Source in repo | Reuse? |
|---|---|---|
| Operational device state | `services/health/compute_device_state(HealthSignals)` → `device_health` `NormalizedStatus` | **Reuse** |
| Last heartbeat | `Device.last_heartbeat` (`HealthSignals.last_heartbeat_at`) | Reuse |
| Last carrier event | `Device.last_network_event` | Reuse |
| Last successful call | `MAX(call_records.started_at)`; `call_record.status` distinguishes failed | Reuse |
| Last test call | `verification_tasks` (task_type/result/completed_at) and/or `command_testing` | Reuse (confirm convention — Q4) |
| SIP / signal / VOLTE | `CommandTelemetry` metadata; `VendorStatus.sip_status` | Partial — absent treated as not-degraded |
| SIM / carrier status | `Sim`; `Device.network_status`; `VendorStatus.sim_status` | Reuse |
| Commercial lifecycle | `sites.lifecycle_status`, `zoho_subscription_records.lifecycle_state` | Reuse (PR #70 dependency) |
| E911 address present | `sites.e911_street/city/state/zip`, `lines.e911_*` | Reuse |
| Dispatchable location verified | `sites.e911_status`, `lines.e911_status` | Reuse |
| E911 confirmation required | `sites.e911_confirmation_required` | Reuse |
| Deployment lifecycle | `sites.onboarding_status` / `reconciliation_status`; `Device.status`; `Line.status` | Reuse (conservative mapping) |
| Open incidents | `Incident` (status, severity) | Reuse |
| Open support tickets | `services/support/*`, Zoho Desk; `SupportEscalation` | Reuse (read-through) |
| Failed jobs / syncs | `Job` (status=failed), `integration_events` (failed/needs_mapping) | Reuse |
| Verification task status | `verification_tasks` | Reuse |
| Reconciliation status | `reconciliation_snapshot`; Zoho `external_record_map` cross-checks | Reuse |

**Reusable routers/components:** `routers/device_health.py` (sanitized `/property/{site_id}` pattern), `PropertyHealth.jsx`, `CustomerStatusBadge`, `friendlyStatus()`, `DeviceHealth.to_customer_view()`.
**Feature-flag precedent:** `FEATURE_HEALTH_NORMALIZER`, `FEATURE_DEVICE_HEALTH`, `FEATURE_LLLM` (all default `"false"`, read as `settings.X.strip().lower()=="true"`).
**Test precedent:** `tests/test_health_*`, `tests/test_device_health*`, `tests/test_zoho_*` (table-driven, pure, mocked DB).

---

## 7. Reason Codes (internal, namespaced `ASSURANCE.*`)

Customer sees a calm label + sentence; support sees the codes that produced it.

- **Lifecycle:** `LIFECYCLE_DEACTIVATED`, `LIFECYCLE_SUSPENDED`, `LIFECYCLE_PENDING_INSTALL`, `DEVICE_DECOMMISSIONED`
- **Operational:** `DEVICE_OFFLINE`, `NO_HEARTBEAT_EVER`, `HEARTBEAT_STALE`, `SIGNAL_LOW`, `SIP_UNREGISTERED`, `NETWORK_DISCONNECTED`
- **E911:** `E911_ADDRESS_MISSING`, `E911_NOT_VERIFIED`, `E911_CONFIRMATION_REQUIRED`, `E911_VALIDATION_FAILED`
- **Service:** `SIM_INACTIVE`, `LINE_INACTIVE`, `CARRIER_SUSPENDED`
- **Testing:** `TEST_FAILED`, `TEST_OVERDUE`, `NO_TEST_ON_RECORD`
- **Issues:** `INCIDENT_OPEN_CRITICAL`, `INCIDENT_OPEN`, `TICKET_OPEN`, `SYNC_FAILED`, `JOB_FAILED`
- **Reconciliation (ops-only):** `RECON_ACTIVE_BUT_OFFLINE`, `RECON_DEACTIVATED_BUT_TRANSMITTING`
- **Data:** `INSUFFICIENT_DATA`

Each code carries `value`, `severity` (gate/critical/warning/info), `axis`, and `recommended_action`. Implement as `services/assurance/reason_codes.py`, mirroring `device_health/reason_codes.py`.

---

## 8. Customer-Facing Language (calm, non-technical)

| Label | Example sentence |
|---|---|
| **Protected** | "This location's emergency calling is active and verified (as of <time>)." |
| **Attention Needed** | "This location is working, but we're reviewing an item to keep it fully protected." |
| **Critical** | "This location needs immediate attention — emergency calling may not work. Manley Solutions has been alerted." |
| **Inactive / Deactivated** | "Service at this location is not currently active." |
| **Pending Install** | "This location is being set up. Protection will be confirmed once installation and testing are complete." |
| **Unknown** | "We're confirming the status of this location." |

Per-item plain phrases map from reason codes (e.g. `E911_NOT_VERIFIED` → "We're verifying the 911 address."; `DEVICE_OFFLINE` → "The device isn't currently reachable."). **Never** show ICCID/SIP/firmware in customer text.

---

## 9. Recent Manley Activity (first-class requirement)

Every site readiness/detail view should (in a later PR) show a simple, plain-language timeline of **what Manley Solutions has done to protect this location**. This is a core retention/value feature — it makes the service tangible.

**Example entries:** E911 address updated · SIM replaced · Test call completed · Ticket opened/resolved · Device restored · Carrier sync completed · Technician dispatched.

**Data already exists** to source this without new capture: `action_audit`, `command_activity`, `e911` change log, `verification_tasks`, `support`/`SupportEscalation`, `Job` history, `Incident` transitions, reconciliation events. The work is a **read-only aggregation + plain-language mapping**, tenant-scoped and customer-sanitized (no internal IDs/secrets).

**Scope:** not in the first PR. Reserved as the immediate fast-follow once the engine + site detail endpoint exist (it shares the same sanitized read pattern).

---

## 10. Monthly Executive Summary (first-class future deliverable)

A future customer-facing **monthly assurance report** built on the engine + persisted snapshots:
- Customer/portfolio status summary (Protected / Attention / Critical counts)
- E911 readiness summary (% verified)
- Open issues
- Recent Manley Activity highlights
- Downloadable **PDF** (frontend already bundles `jspdf`/`html2canvas`)
- Possible scheduled/emailed monthly report later

**Depends on:** persisted assurance snapshots (§11) for trend + point-in-time reporting. **Not in MVP.**

---

## 11. Data Model / Snapshot Recommendation

**Recommendation: compute-live for MVP; persist snapshots in the next PR.**
- **PR1 — compute live only.** Source of truth = live composition over existing tables. No writes, no migration. Fully testable; powers the first site/portfolio reads.
- **Next PR — snapshots.** Additive table `site_assurance_snapshot` (and optionally device-level): `tenant_id, site_id, label, reason_codes(jsonb), computed_at`, indexed `(tenant_id, computed_at)`. Required for trends, the monthly report, and change-detection alerts ("site went Critical at 2:14pm"). Additive-only, no mutation of existing tables.

No new operational columns are added; everything is derived. (Confirm "last successful test/call" is derivable from `call_records` + `verification_tasks` before adding any field — expected yes.)

---

## 12. API Recommendation

Read-only, tenant-scoped, sanitized, behind `FEATURE_ASSURANCE_ENGINE` (default off):
- **PR1:** `GET /api/assurance/site/{site_id}` — site label + per-device/line breakdown + reason codes + E911 checklist + last heartbeat/call/test + recommended actions. (Endpoint included only if low-risk; otherwise the pure engine + tests ship first and the endpoint follows.)
- **Next:** `GET /api/assurance/portfolio` (counts by label + E911 %), `GET /api/assurance/attention` (ranked queue), `GET /api/assurance/report` (structured monthly summary).

Design: one bounded query per site (reuse the health loader; avoid the existing "load all tenant devices into memory" pattern). Serialize via a `to_customer_view()`-style shape (no raw vendor payloads). When the flag is off, the route returns **404** (matches `FEATURE_LLLM`/`FEATURE_DEVICE_HEALTH` precedent) — zero behavior change.

---

## 13. Frontend Recommendation

**Not in the first PR** beyond, at most, a tiny safe **`AssuranceBadge`** component (six labels; extend `CustomerStatusBadge`) that renders only where explicitly wired and only when `VITE_FEATURE_ASSURANCE_ENGINE` is on. Larger surfaces (Site Readiness panel via `PropertyHealth`, portfolio counts on dashboards) are deferred to dedicated UI PRs after the engine is proven. No numeric score shown.

---

## 14. RBAC / Security Recommendation

- New read permission **`VIEW_ASSURANCE`** (customer roles User/Manager + internal). Reuse tenant scoping; sanitized output (no ICCID/SIP/firmware to customers).
- Reason codes + ops-only mismatches (`RECON_*`, `INSUFFICIENT_DATA` detail) gated to internal roles (reuse `VIEW_ADMIN` or add `VIEW_ASSURANCE_INTERNAL`).
- Do not loosen any existing permission. Close pre-existing unguarded GET endpoints (incidents list, some sites/devices reads) before exposing more customer data — tracked separately, not required for PR1.

---

## 15. Test Plan

- **Pure decision tests (core):** table-driven, one case per label × per gate × per missing-data path. Assert the §3 rules explicitly: deactivated suppresses alarms; pending ≠ failed; fresh heartbeat + missing E911 = Critical; commercial-active + offline = Critical; missing data → Attention/Unknown (never best status); failed test = Critical, overdue/no test = Attention.
- **Signal-loader tests:** DB rows / health output → `AssuranceSignals` (mocked DB, house pattern); defensive handling when lifecycle columns are absent (pre-PR#70).
- **Rollup tests:** worst-wins; site E911 gate; all-pending → Pending Install; no devices → Unknown; deactivated site → Inactive.
- **Endpoint + RBAC tests (if endpoint in PR1):** 200 shape, `read_only`, tenant scoping, customer sanitization, 403 unauthorized, **flag-off → 404 and zero behavior change**.
- **Guardrail regression:** `RECON_DEACTIVATED_BUT_TRANSMITTING` never yields a customer Critical; engine performs no writes (assert no session mutations in unit tests).

---

## 16. MVP First-PR Scope

Backend-first, feature-flagged, no UI, no writes:
1. `FEATURE_ASSURANCE_ENGINE` in `config.py`, default `"false"`.
2. `services/assurance/` — `AssuranceSignals` dataclass, `reason_codes.py`, `engine.py` (`compute_device_assurance` + `compute_site_assurance`) — **pure, deterministic, no I/O**.
3. A **signals loader** reusing `services/health` + bounded DB reads (E911, lifecycle [defensive], incidents, last call/test). Read-only.
4. **Exhaustive table-driven unit tests** for the decision matrix (+ loader tests).
5. **Read-only `GET /api/assurance/site/{id}` only if low-risk** (flag-gated, 404 when off). If there's any doubt, ship the pure engine + tests first and add the endpoint in PR1b.
6. **Compute-live only.** No snapshots, no migration, no alerts, no PDF, no automation, **no customer numeric score**, no broad refactors, no deletions.

---

## 17. Risks & Guardrails

- **Unreliable inputs → wrong label** (worst failure for a 911 product). Mitigation: reuse the validated health normalizer; conservative gates; `missing ≠ healthy`; recommend the platform reliability fixes (worker flag parity, indexes, stale-heartbeat correctness) land alongside/soon.
- **False confidence / liability:** hard gates (E911 verified, lifecycle active) cannot be overridden by a fresh heartbeat; "Protected" shown with timestamp + disclaimer; legal review of wording.
- **False alarms on deactivated/suspended/pending:** ordering branches 1–2 evaluate before any Critical logic.
- **Axis bleed:** engine is read-only; never writes operational/Zoho/E911/device fields. Unit tests assert no mutations.
- **PR #70 dependency:** `sites.lifecycle_status` lands with the Zoho work. The engine reads lifecycle inputs defensively so it is correct whether or not PR #70 is merged (absent lifecycle → conservative: not treated as active-healthy).
- **Performance:** one bounded query per site; reuse normalizer; flag-gated; snapshots later.
- **Scope creep:** UI, snapshots, alerts, PDF, score all explicitly deferred.

---

## 18. Open Questions / Future Decisions

- **Q-A (wording):** Confirm "Protected (as of <time>) + disclaimer," or switch to the more clinical "Active & Verified." (Engine-independent; copy only.)
- **Q1 (test recency):** Confirmed — overdue/missing test = Attention, failed test = Critical. ✔ (recorded)
- **Q2 (E911 unknown on active):** Confirmed — Critical. ✔ (recorded)
- **Q3 (thresholds):** Confirmed — global thresholds for MVP. ✔ (recorded)
- **Q4 (test source):** Which is authoritative for "last test" — `verification_tasks` (which task_type/result convention?) or `command_testing`, or both?
- **Q5 (deployment lifecycle mapping):** Confirm the conservative mapping of existing fields (`lifecycle_status=pending_install`, `onboarding_status`, device `provisioning`) → Pending Install. Do not build a new lifecycle system.
- **Q6 (snapshots timing):** Confirmed — snapshots in the PR after MVP, not PR1. ✔ (recorded)
- **Q7 (reason-code visibility):** Confirm customers see calm sentences only; raw `ASSURANCE.*` + `RECON_*` stay internal.

### Future area (preserved, not MVP) — Installer / Activation Lifecycle
A canonical install lifecycle to be designed later, aligned with (not overwriting) commercial and operational status:

`Ordered → Shipped → Received → Staged → Installed → Tested → Accepted → Operational`

This would power the installer/staging experience and feed Pending Install precision. Out of MVP; captured here so it is not lost.

---

---

## 19. PR1 — Implemented (backend-first, flag-gated, read-only)

**Status:** Implemented on branch `feat/assurance-engine-pr1`. `FEATURE_ASSURANCE_ENGINE` defaults `false` → no behavior change until enabled.

### Scope delivered
- `FEATURE_ASSURANCE_ENGINE: str = "false"` in `api/app/config.py`.
- `api/app/services/assurance/`:
  - `signals.py` — `AssuranceSignals` + `DeviceSignal` / `ServiceUnitSignal` / `LineSignal` / `TestRecord`, and `AssuranceLabel` (the 6 labels).
  - `reason_codes.py` — `ASSURANCE.*` codes with severity + customer message + internal action.
  - `engine.py` — **pure** `compute_device_assurance()` + `compute_site_assurance()`. No I/O, injectable clock, no input mutation.
  - `loader.py` — **read-only** assembly from existing tables; reuses `services.health.compute_device_state` / `load_signals_for_site` for operational state; **defensive `getattr`** for `lifecycle_status` (absent on a pre-PR#70 deployment → conservative, never "healthy").
- `api/app/routers/assurance.py` — `GET /api/assurance/site/{site_id}`, returns **404 when the flag is off**, RBAC `VIEW_ASSURANCE`, tenant-scoped to the caller's effective tenant, customer-sanitized (no ICCID/IMEI/SIP/vendor payloads).
- `permissions.json` — new `VIEW_ASSURANCE` (Admin, Manager, User, DataEntry, DataSteward — mirrors `VIEW_SITES`).
- Wired into `main.py` under `/api/assurance`.
- Health-package surface-containment guard updated to register the Assurance Engine loader as the **approved second consumer** of the health normalizer.

### Endpoint response fields
`site_id`, `site_name`, `customer_name`, `assurance_label`, `internal_label` ("Active & Verified" for Protected), `as_of`, `statement` ("Protected as of <ts>" when Protected), `summary`, `recommended_action`, `reasons[]` (code/severity/message; `internal_action` only for platform users), `devices[]`, `service_units[]`, `e911_status{}`, `last_test`, `disclaimer`, `read_only`.

### Labels & wording
`Protected` · `Attention Needed` · `Critical` · `Inactive / Deactivated` · `Pending Install` · `Unknown`. "Protected" is shown with an `as_of` timestamp and the disclaimer: *"Status reflects the latest available platform data and does not replace required manual life-safety testing or regulatory inspections."* Internal/support equivalent of Protected is **"Active & Verified."**

### Last-test source priority
`verification_tasks` (result `pass`/`fail`) first, then `command_testing` (`infra_test_results` status `pass`/`fail`); most recent wins, verification_tasks breaks ties. None on record → `ASSURANCE.TEST_MISSING` → Attention.

### Belle Terre validation
- Tenant `Integrity Property Management`, site `IPM-BELLE-TERRE`.
- Enable: set `FEATURE_ASSURANCE_ENGINE=true` (api service), authenticate, then:
  `GET /api/assurance/site/IPM-BELLE-TERRE`.
- **Expected:** if the site has E911 verified + a healthy device but **no recorded verification test**, the label is **Attention Needed** with reason `ASSURANCE.TEST_MISSING` (we do not fabricate test history). It becomes **Protected** only once a recent passing test exists. If the seed (`app/seed_integrity.py`) has not been applied to the environment, the site won't exist and the endpoint returns 404 — apply the seed first.

### Known limitations (intentional for MVP)
- `lifecycle_status` is absent until PR#70 merges → commercial-lifecycle gating is conservative (driven by `onboarding_status` / device status until then).
- SIP/signal-strength signals are not yet populated by the health loader (live on `CommandTelemetry`) — absent ≠ degraded.
- `TEST_STALE_SECONDS` is a single global (90 days); not per-device-class.
- Compute-live only; no persistence, so no trend/history yet.

### Future work (not in PR1)
- Persisted **assurance snapshots** (trends, change-detection).
- **Recent Manley Activity** timeline on the site view.
- **Monthly Executive Summary** + PDF export.
- Alerts / scheduled recomputation.
- `/api/assurance/portfolio` + attention queue + customer UI.

---

*End of specification. Reviewers: Stuart Manley (+ ChatGPT).*
