# True911+ — CUSTOMER API CONTRACTS

> Concrete customer-safe API response contracts that implement the boundary set
> (`RH_SECURITY_READINESS.md` · `RH_ROLE_MATRIX.md` · `CUSTOMER_EXPERIENCE_BOUNDARY.md`
> · `CUSTOMER_DATA_BOUNDARY.md`). These are the **only** shapes a customer (RH / Judy)
> ever receives. Contract definition only — no code, no PRs.
>
> **Authority Level:** 3 — Execution (API contract). **Governed by:**
> `CONSTITUTION.md` (§4.5 explainable, §4.6 no green without evidence, §7 jargon veto),
> `DECISIONS.md` D-004/D-005 (label wording/vocabulary), D-006 (separate axes), D-015
> (E911 three dimensions). Prepared: 2026-06-22.

---

## 0. Architecture decision — a dedicated customer read namespace

All customer traffic is served by a **new, read-mostly `/api/customer/*` namespace**,
**not** by retrofitting customer-safe serialization onto the operator endpoints.
Rationale: the data boundary is mostly HIDE/DERIVE; a single customer serializer is the
only place the boundary is enforced, so no operator field can ever leak through a shared
path. The customer endpoints **compose the existing engines** (assurance loader, device-
health service, e911 change log, subscription data, support sessions) and emit only the
shapes below.

> **CORRECTION 2026-06-23 (PR-C1).** Permissions are now **dedicated `CUSTOMER_*`
> perms with zero operator overlap** — Locations use `CUSTOMER_VIEW_LOCATIONS` (not
> `VIEW_SITES`) and Equipment uses `CUSTOMER_VIEW_DEVICES` (not `VIEW_DEVICES`). Reusing
> operator perms would have let customer roles reach operator endpoints (the PR-B1 design
> note). The customer permission set + role grants ship in PR-C1 (`permissions.json`).

**Universal rules (every endpoint):**
- **Allow-list serialization, not deny-list.** The serializer emits *only* named
  customer fields; an unmapped/new model column is invisible by default (a new column
  can never silently leak).
- **No** raw ICCID/IMEI/IMSI/MSISDN, serial, MAC, carrier callback/correlation ids,
  provisioning traces, Zoho ids, QuickBooks ids, internal incident/session ids, raw
  telemetry, IPs, firmware, vendor (Vola) ids, or internal notes — **ever**.
- **Opaque refs.** Path ids are opaque `*_ref` tokens, server-resolved to
  `WHERE tenant_id == current_user.tenant_id` rows (never the raw `site_id`/db id).
- **No false green.** A `Protected`/green status is emitted **only** with a populated
  `evidence` object + `as_of`. Missing data → `Unknown`, never green.
- **Separate axes (D-006).** `protection` (operational), `emergency_address` (E911), and
  `billing` are **distinct** fields; one never masks another.
- **Tenant + RBAC two-layer** (`CUSTOMER_EXPERIENCE_BOUNDARY.md`): every route carries a
  `CUSTOMER_*` permission **and** filters by tenant.

### 0.1 Shared objects

**StatusObject** (the only status vocabulary customers see — D-005):
```jsonc
{
  "status": "Protected | Attention Needed | Critical | Pending Install | Inactive | Unknown",
  "reason": "plain-language why (always present for non-Protected)",
  "as_of": "ISO-8601",
  "evidence": { "...": "REQUIRED when status == Protected" }   // omitted/null otherwise
}
```
**EvidenceObject** (what makes green believable — §4.6):
```jsonc
{ "last_checked": "ISO-8601", "signals": ["device online", "test call 2026-07-10"], "source": "monitoring" }
```
**ErrorObject** (customer-safe; never leaks internals):
```jsonc
{ "error": { "code": "not_found | forbidden | unauthorized | unavailable | rate_limited",
             "message": "plain-language, no stack/SQL/internal id" } }
```
**Envelope:** every 200 returns `{ "as_of": ISO-8601, "data": <shape> }`.

### 0.2 HTTP status conventions
| Case | HTTP | Body |
|---|---|---|
| OK | 200 | envelope |
| Not authenticated | 401 | ErrorObject `unauthorized` |
| Authenticated, lacks customer perm | 403 | ErrorObject `forbidden` |
| Ref not in caller's tenant (or absent) | 404 | ErrorObject `not_found` (**same body for both — no existence leak**) |
| Feature flag off | 404 | ErrorObject `not_found` |
| Engine/dep down | 503 | ErrorObject `unavailable` ("we can't confirm status right now" — **never a fake green**) |

---

## 1. Customer Dashboard / Morning Test

- **Route:** `GET /api/customer/dashboard`
- **Permission:** `CUSTOMER_VIEW_DASHBOARD` (all four customer roles)
- **Params:** none (tenant from token)
- **Field source & disposition:**

| Response field | Source | Disposition |
|---|---|---|
| `company` | `Customer.name` | SHOW |
| `as_of` | server time | DERIVE |
| `portfolio.{protected,attention_needed,critical,pending_install,inactive,unknown,total}` | Assurance labels over all tenant sites | **AGGREGATE** |
| `headline` | portfolio counts | DERIVE (D-004 wording) |
| `attention_feed[]` | sites with non-Protected status + assurance reason | DERIVE/AGGREGATE |
| `recent_manley_activity[]` | `action_audit`/`E911ChangeLog` (sanitized) | DERIVE |
| all device/site raw columns | — | **HIDE** |

- **Status mapping:** per-site Assurance label → the six-label vocabulary; counts summed.
- **Empty state:** new tenant → `portfolio.total: 0`, `headline: "No locations yet — setup in progress"`, empty feeds.
- **Error state:** assurance engine down → 503 `unavailable`; flag off → 404.
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T08:00:00Z", "data": {
  "company": "Restoration Hardware",
  "portfolio": { "total": 42, "protected": 39, "attention_needed": 2, "critical": 1,
                 "pending_install": 0, "inactive": 0, "unknown": 0 },
  "headline": "39 of 42 locations Protected (as of 8:00 AM)",
  "attention_feed": [
    { "location_ref": "loc_8f2a", "location": "RH Boston — Back Bay", "status": "Critical",
      "reason": "Emergency address not yet verified", "action": "We're verifying this address" },
    { "location_ref": "loc_3b71", "location": "RH Chicago", "status": "Attention Needed",
      "reason": "Elevator phone offline ~2h", "action": "We're investigating" } ],
  "recent_manley_activity": [
    { "when": "2026-07-14", "what": "Verified emergency address for RH Yountville" } ] } }
```

## 2. Customer Locations List

- **Route:** `GET /api/customer/locations`
- **Permission:** `CUSTOMER_VIEW_LOCATIONS`
- **Params:** `status?` (filter by customer label), `q?` (name search), `page?`, `page_size?` (default 25, max 100)
- **Field source & disposition:**

| Field | Source | Disposition |
|---|---|---|
| `items[].location_ref` | opaque token for `Site` | DERIVE (raw `site_id` HIDE) |
| `items[].location` | `Site.site_name` | SHOW |
| `items[].building_type` | `Site.building_type` | SHOW |
| `items[].city,state` | `Site.e911_city/state` | SHOW (street withheld in list view) |
| `items[].protection` | StatusObject (Assurance) | DERIVE + evidence-on-green |
| `items[].emergency_address_state` | `Site.e911_status` (separate axis) | DERIVE |
| `page,page_size,total` | query | DERIVE |
| device/network/provisioning columns | — | HIDE |

- **Status mapping:** active+healthy+E911-verified → Protected; active+E911-unverified → Critical; onboarding → Pending Install; inactive → Inactive; no signal → Unknown.
- **Empty state:** `{ "items": [], "total": 0 }` + `message: "No locations yet"`.
- **Error state:** 403 if role lacks `CUSTOMER_VIEW_LOCATIONS`; 200 empty otherwise.
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T08:00:00Z", "data": { "total": 42, "page": 1, "page_size": 25, "items": [
  { "location_ref": "loc_9c10", "location": "RH Yountville", "building_type": "Gallery",
    "city": "Yountville", "state": "CA",
    "protection": { "status": "Protected", "as_of": "2026-07-15T07:58:00Z",
                    "evidence": { "last_checked": "2026-07-15T07:58:00Z", "signals": ["device online","test call 2026-07-10"], "source": "monitoring" } },
    "emergency_address_state": "Verified" },
  { "location_ref": "loc_8f2a", "location": "RH Boston — Back Bay", "building_type": "Gallery",
    "city": "Boston", "state": "MA",
    "protection": { "status": "Critical", "reason": "Emergency address not yet verified", "as_of": "2026-07-15T07:58:00Z" },
    "emergency_address_state": "Not yet verified" } ] } }
```

## 3. Customer Site (Location) Detail

- **Route:** `GET /api/customer/locations/{location_ref}`
- **Permission:** `CUSTOMER_VIEW_LOCATIONS`
- **Params:** `location_ref` (path)
- **Field source & disposition:**

| Field | Source | Disposition |
|---|---|---|
| `location,building_type` | `Site.site_name/building_type` | SHOW |
| `service_address` | `Site.e911_street/city/state/zip` formatted | DERIVE |
| `protection` | StatusObject (Assurance) | DERIVE + evidence |
| `emergency_address` | `Site.e911_status/confirmation_required` (axis 2) | DERIVE (detail in §6) |
| `site_contact{name,phone,email,editable}` | `Site.poc_*` | SHOW (editable by ADMIN/USER) |
| `services[]` | `ServiceUnit` rollup (§4) | AGGREGATE |
| `proof` | EvidenceObject | DERIVE |
| `carrier,signal_dbm,static_ip,firmware,device_serial,heartbeat_*,psap_id,ng911_uri,notes` | — | HIDE |

- **Status mapping:** as §2; `services[]` each carry their own StatusObject; site status is the worst-of its services + E911 axis.
- **Empty state:** valid location, no services yet → `services: []`, protection `Unknown` ("setup in progress").
- **Error state:** unknown/cross-tenant ref → 404 `not_found` (identical body either way).
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T07:58:00Z", "data": {
  "location_ref": "loc_9c10", "location": "RH Yountville", "building_type": "Gallery",
  "service_address": "6725 Washington St, Yountville, CA 94599",
  "protection": { "status": "Protected", "as_of": "2026-07-15T07:58:00Z",
                  "evidence": { "last_checked": "2026-07-15T07:58:00Z", "signals": ["all services online","test call 2026-07-10"], "source": "monitoring" } },
  "emergency_address": { "state": "Verified", "verified_on": "2026-07-14", "confirmation_required": false },
  "site_contact": { "name": "Gallery Ops Lead", "phone": "707-555-0142", "email": "ops.yv@rh.example", "editable": true },
  "services": [
    { "service_ref": "svc_a1", "service": "Elevator emergency phone", "where": "Elevator #1",
      "protection": { "status": "Protected", "as_of": "2026-07-15T07:57:00Z",
                      "evidence": { "last_checked": "2026-07-15T07:57:00Z", "signals": ["device online"], "source": "monitoring" } } },
    { "service_ref": "svc_a2", "service": "Fire alarm line", "where": "Utility room",
      "protection": { "status": "Protected", "as_of": "2026-07-15T07:55:00Z",
                      "evidence": { "last_checked": "2026-07-15T07:55:00Z", "signals": ["line supervised"], "source": "monitoring" } } } ] } }
```

## 4. Customer Service Detail

- **Route:** `GET /api/customer/services/{service_ref}`
- **Permission:** `CUSTOMER_VIEW_SERVICES`
- **Params:** `service_ref` (path)
- **Field source & disposition:**

| Field | Source | Disposition |
|---|---|---|
| `service` | `ServiceUnit.unit_type` → label map | DERIVE |
| `name,where,floor` | `unit_name/location_description/floor` | SHOW |
| `can_call_for_help[]` | `voice/video/text/..._supported` | DERIVE (chips) |
| `monitored` | `monitoring_station_type` | DERIVE (simplified) |
| `compliance{state,governing_code,last_reviewed,disclaimer}` | `compliance_status/governing_code_edition/...` | DERIVE (+ "guidance, not legal advice") |
| `protection` | StatusObject (service+equipment health) | DERIVE + evidence |
| `equipment` | Equipment summary (§5) | AGGREGATE |
| `device_id,line_id,sim_id,video_stream_url,video_transport,jurisdiction_code,meta,notes` | — | HIDE |

- **Status mapping:** active+healthy+compliant → Protected; `review_required`/`partially_compliant` → Attention; `non_compliant`/unhealthy → Critical; `pending_install` → Pending Install; else Unknown.
- **Empty state:** service exists, equipment never reported → protection `Unknown`.
- **Error state:** 404 on unknown/cross-tenant ref.
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T07:57:00Z", "data": {
  "service_ref": "svc_a1", "service": "Elevator emergency phone", "name": "Elevator #1 Phone",
  "where": "Elevator #1, Main", "floor": "1",
  "can_call_for_help": ["Voice"], "monitored": "Central station",
  "compliance": { "state": "Compliant", "governing_code": "ASME A17.1-2019",
                  "last_reviewed": "2026-06-30", "disclaimer": "Operational guidance, not legal advice." },
  "protection": { "status": "Protected", "as_of": "2026-07-15T07:57:00Z",
                  "evidence": { "last_checked": "2026-07-15T07:57:00Z", "signals": ["device online"], "source": "monitoring" } },
  "equipment": { "equipment": "Elevator phone unit", "health": "Online", "last_seen": "2026-07-15T07:57:00Z" } } }
```

## 5. Customer Equipment Health

- **Route:** `GET /api/customer/services/{service_ref}/equipment`
- **Permission:** `CUSTOMER_VIEW_DEVICES`
- **Params:** `service_ref` (path)
- **Field source & disposition:** *(the most aggressively filtered entity — see `CUSTOMER_DATA_BOUNDARY.md` §3)*

| Field | Source | Disposition |
|---|---|---|
| `equipment` | `Device.device_type/model` → label map | DERIVE (raw model HIDE) |
| `health` | `Device.status` + `last_heartbeat` | DERIVE (`Online/Offline`) |
| `last_seen` | `Device.last_heartbeat` | DERIVE |
| `in_service_since` | `Device.activated_at` | DERIVE |
| `protection` | StatusObject | DERIVE + evidence |
| `serial,mac,imei,iccid,imsi,msisdn,sim_id,starlink_id,firmware,container,provision_code,api_key_hash,carrier,network_status,data_usage_mb,wan_ip,lan_ip,vola_*,telemetry_source,reconciliation_status,import_batch_id,device_id` | — | **HIDE (all)** |

- **Status mapping:** active+fresh heartbeat → Online/Protected; active+stale → Offline/Attention→Critical; provisioning → Pending Install; inactive/decommissioned → Inactive; never reported → Unknown.
- **Empty state:** no equipment linked → `{ "equipment": null, "protection": { "status": "Unknown", "reason": "No monitored equipment yet" } }`.
- **Error state:** 404 cross-tenant/unknown ref.
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T07:57:00Z", "data": {
  "equipment": "Elevator phone unit", "health": "Online", "last_seen": "2026-07-15T07:57:00Z",
  "in_service_since": "2026-03-02",
  "protection": { "status": "Protected", "as_of": "2026-07-15T07:57:00Z",
                  "evidence": { "last_checked": "2026-07-15T07:57:00Z", "signals": ["device online"], "source": "monitoring" } } } }
```
*(Pre-remediation RH today: `health: "Unknown"`, `protection.status: "Unknown"`, `reason: "Setting up monitoring"` — never green.)*

## 6. Customer E911 Summary  *(read-only; request-only writes; separate from device health)*

- **Routes:**
  - `GET /api/customer/locations/{location_ref}/e911`
  - `POST /api/customer/locations/{location_ref}/e911/correction-request` *(request-only — never a direct write)*
- **Permission:** `CUSTOMER_VIEW_E911` (GET); `CUSTOMER_MANAGE_SUPPORT` (correction request, ADMIN/USER)
- **Params:** `location_ref` (path); POST body `{ proposed_address, reason }`
- **Field source & disposition:**

| Field | Source | Disposition |
|---|---|---|
| `emergency_dispatch_address` | `Site.e911_street/city/state/zip` | SHOW (formatted) |
| `verification.state` | `Site.e911_status ∈ {validated,verified}` (axis only) | DERIVE |
| `verification.verified_on` | `E911ChangeLog.applied_at` | DERIVE |
| `verification.is_critical` | active site AND not verified | DERIVE (D-015) |
| `confirmation_required` | `Site.e911_confirmation_required` | DERIVE |
| `address_history[]` | `E911ChangeLog` (new addr, status, applied_at, requester_name) | DERIVE/AGGREGATE |
| `customer_actions[]` | static | DERIVE (`["Request an address correction"]`) |
| `psap_id,ng911_uri,emergency_class,correlation_id,requested_by(email),address_source` | — | HIDE |

- **Rule:** **E911 is its own axis** — this endpoint never returns operational/device
  health, and §3/§5 never assert E911 verification. `is_critical=true` whenever an
  **active** location's address is unverified (shown red with reason, never green).
- **Status mapping:** present+verified → "Verified ✓ (as_of)"; present+unverified →
  "Not yet verified" (Critical if active); missing → "Setup needed".
- **POST result:** `202 Accepted` → `{ "request_ref": "...", "state": "submitted",
  "message": "We'll verify and update this address" }`. Creates a **Manley-gated**
  change; **no `Site` field is written by the customer.**
- **Empty state:** no address yet → `emergency_dispatch_address: null`, state `"Setup needed"`.
- **Error state:** 404 unknown ref; 403 if role lacks perm; POST 422 on invalid address (customer-safe message).
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T08:00:00Z", "data": {
  "location": "RH Boston — Back Bay",
  "emergency_dispatch_address": "234 Berkeley St, Boston, MA 02116",
  "verification": { "state": "Not yet verified", "is_critical": true,
                    "message": "Active location with an unverified emergency address — we're verifying it" },
  "confirmation_required": false,
  "address_history": [ { "when": "2026-07-12", "change": "Address set", "by": "Manley", "state": "Pending verification" } ],
  "customer_actions": ["Request an address correction"] } }
```

## 7. Customer Support Requests  *(customer_safe_summary only)*

- **Routes:**
  - `GET /api/customer/support` (list own-tenant cases)
  - `GET /api/customer/support/{case_ref}` (detail + sanitized conversation)
  - `POST /api/customer/support` (open a case)
  - `POST /api/customer/support/{case_ref}/messages` (add a comment)
  - `POST /api/customer/support/{case_ref}/resolve`
- **Permission:** `CUSTOMER_VIEW_SUPPORT` (GET); `CUSTOMER_MANAGE_SUPPORT` (POST). READONLY/BILLING: GET only / none.
- **Field source & disposition:**

| Field | Source | Disposition |
|---|---|---|
| `case_ref,opened,status` | `SupportSession.id(opaque)/created_at/status` | DERIVE |
| `subject` | `issue_category` → plain label | DERIVE |
| `messages[]` | `SupportMessage` (role user/assistant only; `system` dropped) | SHOW (sanitized) |
| `checks[]` | `SupportDiagnostic.customer_safe_summary` + `status` | **SHOW (customer_safe only)** |
| `escalation` | `SupportEscalation.status` + `zoho_ticket_number` (number only) | DERIVE |
| `resolution` | `resolution_summary` | SHOW |
| `internal_summary,raw_payload,probable_cause,handoff_summary,diagnostics_checked,dedupe_key,zoho_ticket_id/url/status,confidence,check_type,remediation.*,ai_summary.*` | — | **HIDE (all)** |

- **Status mapping:** `active`→"Open", `escalated`→"In progress (with our team)", `resolved`→"Resolved".
- **Empty state:** `{ "items": [], "total": 0, "message": "No support requests" }`.
- **Error state:** 404 cross-tenant `case_ref`; 403 if READONLY tries to POST.
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T08:05:00Z", "data": {
  "case_ref": "case_5d2", "subject": "Elevator phone not working", "status": "In progress (with our team)",
  "opened": "2026-07-15T07:40:00Z",
  "messages": [ { "from": "you", "text": "Elevator #2 phone has no dial tone", "at": "2026-07-15T07:40:00Z" },
                { "from": "True911", "text": "Thanks — we're checking the line now.", "at": "2026-07-15T07:42:00Z" } ],
  "checks": [ { "what": "Phone line", "result": "Needs attention", "detail": "Line not responding to our test" } ],
  "escalation": { "state": "Escalated to our team", "ticket": "T-10482" },
  "resolution": null } }
```

## 8. Customer Billing Summary  *(read-only visibility — not accounting)*

- **Route:** `GET /api/customer/billing`
- **Permission:** `CUSTOMER_VIEW_BILLING` (ADMIN, BILLING only)
- **Params:** `page?`, `page_size?`
- **Field source & disposition:**

| Field | Source | Disposition |
|---|---|---|
| `as_of,source` | sync metadata | DERIVE ("synced from billing system") |
| `portfolio_monthly_total` | sum `Subscription.mrr`/`zoho_subscription_record.mrc` | **AGGREGATE** |
| `active_services_count` | count active subscriptions/lines | AGGREGATE |
| `plans[].location` | `facility_name` → Location name | DERIVE (service-to-billing) |
| `plans[].plan` | `plan_name/subscription_type` | SHOW |
| `plans[].monthly_cost` | `mrr/mrc` | SHOW |
| `plans[].services_covered` | `qty_lines` | DERIVE |
| `plans[].status,renews_on` | `status/renewal_date/service_term_ends` | DERIVE |
| `external_subscription_id,external_source,msisdn,device_activation_status,connection_type,account_number,org_id,raw_json,zoho/qb ids` | — | **HIDE (all)** |

- **Rule:** **read-only** — no customer write to any commercial field (D-006). Invoices,
  invoice PDF, payment status, QuickBooks data are **deferred** (not in this contract).
- **Status mapping:** `active`→"Active", `paused`→"Paused", `cancelled/expired`→"Ended".
- **Empty state:** no subscriptions/unreconciled → `portfolio_monthly_total: null`,
  `message: "Billing details are being finalized"` (**never a fabricated number**).
- **Error state:** 403 for USER/READONLY; 200 with `null` total if data not yet reconciled.
- **RH example:**
```jsonc
{ "as_of": "2026-07-01", "data": {
  "source": "synced from billing system", "portfolio_monthly_total": "$4,830.00", "active_services_count": 51,
  "plans": [ { "location": "RH Yountville", "plan": "Emergency Line Monitoring", "services_covered": 2,
               "monthly_cost": "$120.00", "status": "Active", "renews_on": "2026-12-01" } ] } }
```

## 9. Customer Reports

- **Routes:**
  - `GET /api/customer/reports/portfolio` (JSON snapshot)
  - `GET /api/customer/reports/portfolio.pdf` (one-page export)
- **Permission:** `CUSTOMER_VIEW_REPORTS` (view); `CUSTOMER_EXPORT_REPORTS` (PDF — ADMIN, BILLING)
- **Params:** `as_of?` (defaults now)
- **Field source & disposition:**

| Field | Source | Disposition |
|---|---|---|
| `company,generated_at` | `Customer.name`, server | SHOW/DERIVE |
| `summary.{protected,attention,critical,...,total}` | Assurance labels | AGGREGATE |
| `protected_percent` | derived ratio | DERIVE (percentage of locations Protected — **not** a customer "readiness score", §7.1) |
| `e911_verified_count` | E911 axis (separate) | AGGREGATE |
| `attention[]` | non-Protected locations + reason | AGGREGATE |
| `proof_note` | static | DERIVE ("Each status is backed by evidence and a timestamp.") |
| raw rows / ids / telemetry | — | HIDE |

- **Status mapping:** as §1.
- **Empty state:** `total: 0` → "No locations to report yet."
- **Error state:** PDF for USER/READONLY → 403; engine down → 503.
- **RH example:**
```jsonc
{ "as_of": "2026-07-15T08:00:00Z", "data": {
  "company": "Restoration Hardware", "generated_at": "2026-07-15T08:00:00Z",
  "summary": { "total": 42, "protected": 39, "attention": 2, "critical": 1, "pending_install": 0, "inactive": 0, "unknown": 0 },
  "protected_percent": 92.9, "e911_verified_count": 41,
  "attention": [ { "location": "RH Boston — Back Bay", "status": "Critical", "reason": "Emergency address not yet verified" } ],
  "proof_note": "Each status is backed by evidence and a timestamp." } }
```

---

## A. Backend implementation PR sequence
1. **PR-C1 — Customer serializer + shared objects.** `services/customer/serialize.py`:
   allow-list serializers for StatusObject/Evidence/Error + the entity mappers; pure,
   exhaustively unit-tested (every model column proven HIDE unless explicitly mapped).
   *No routes yet.*
2. **PR-C2 — Read endpoints (compose existing engines).** `routers/customer.py` under
   `/api/customer/*`, behind `FEATURE_CUSTOMER_API` (404 off) + `CUSTOMER_*` perms:
   dashboard, locations, location detail, service detail, equipment, e911 (GET), reports.
   Each calls the existing assurance/device-health/e911 loaders and serializes via PR-C1.
3. **PR-C3 — Billing summary.** `GET /api/customer/billing` over existing
   `Subscription`/`zoho_subscription_record` (read-only), gated `CUSTOMER_VIEW_BILLING`.
4. **PR-C4 — Support (read).** `GET /api/customer/support[/{ref}]` over `SupportSession`
   using `customer_safe_summary` only.
5. **PR-C5 — Customer writes (request-only).** E911 correction-request (202, Manley-gated),
   support create/comment/resolve (`CUSTOMER_MANAGE_SUPPORT`), site-contact edit.
6. **PR-C6 — Report PDF export.** `/reports/portfolio.pdf` (`CUSTOMER_EXPORT_REPORTS`).

*Depends on `CUSTOMER_EXPERIENCE_BOUNDARY.md` PR-2/PR-3 (perms + INTERNAL_OPS) landing first.*

## B. Frontend implementation PR sequence
1. **PR-F1 — Customer API client + types** for `/api/customer/*`; StatusBadge that renders
   only the six labels + "as of" + a "View proof" affordance (no green without evidence).
2. **PR-F2 — Dashboard (Morning Test)** consuming §1; attention feed + Manley activity.
3. **PR-F3 — Locations list + Location detail** (§2/§3) with `CustomerSiteDetailDrawer` pattern.
4. **PR-F4 — Service detail + Equipment health** (§4/§5), plain-language chips, zero jargon.
5. **PR-F5 — E911 view + correction-request modal** (§6), read-only with request action.
6. **PR-F6 — Support list/detail/create** (§7); **PR-F7 — Billing** (§8, ADMIN/BILLING nav);
   **PR-F8 — Reports + PDF** (§9). Each nav item gated by `can(perm)` per the role matrix.

## C. Test plan — customer-safe serialization
- **Allow-list proof (the core test):** for every entity, build a model row with **every**
  column populated with a sentinel (e.g. `iccid="LEAK_ICCID"`), serialize, assert the
  output JSON contains **none** of the HIDE sentinels (ICCID/IMEI/MSISDN/serial/MAC/
  firmware/carrier/IP/Zoho/QB/incident/session ids/raw telemetry). Golden-file the exact
  customer shape.
- **New-column safety:** add a fake column → assert it does **not** appear (allow-list).
- **No false green:** assert `status:"Protected"` is rejected/recoded to `Unknown` when
  `evidence` is empty or `as_of` missing; assert active+unverified-E911 → `Critical`.
- **Axis separation:** a row with healthy device + unverified E911 → `protection:Protected`
  **and** `emergency_address:Not yet verified` simultaneously (neither masks the other).
- **Support:** assert only `customer_safe_summary` is emitted; `internal_summary`/
  `raw_payload`/probable_cause/Zoho ids absent.
- **Billing read-only:** assert no write route exists on commercial fields; total is
  `null` (not fabricated) when unreconciled.
- **E911 request-only:** assert POST correction-request writes **no** `Site.e911_*` field
  (creates a gated change row only).
- **Empty/error states:** each endpoint's empty + 401/403/404/503 bodies match §0.2 and
  carry no internals.

## D. 403 / 404 tenant-scope tests
- **Per role × endpoint matrix:** the four customer roles → 200 on their allow-list, 403
  on endpoints they lack (USER→billing 403; READONLY→all POST 403; BILLING→equipment/E911
  detail 403). The six internal roles unaffected (regression gate).
- **Tenant scoping:** customer in tenant A requesting a tenant-B `*_ref` → **404
  `not_found`** with the **identical body** to a truly-missing ref (no existence leak);
  list endpoints never return another tenant's rows.
- **Impersonation:** SuperAdmin `X-Act-As-Tenant=RH` sees RH customer shapes; customer
  roles cannot impersonate.
- **Flag off:** `FEATURE_CUSTOMER_API=false` → every `/api/customer/*` → 404.
- **Opaque-ref integrity:** a guessed/sequential id is not a valid `*_ref`; refs resolve
  only within the caller's tenant.

## E. RH Day-1 API checklist
- [ ] `/api/customer/dashboard` returns RH portfolio counts with **evidence on every Protected**.
- [ ] `/api/customer/locations` lists 42 RH galleries, tenant-scoped, no jargon fields.
- [ ] Location/Service/Equipment details render plain-language only (sentinel-leak test green).
- [ ] `/api/customer/locations/{ref}/e911` shows verified state **separately** from device health; active+unverified = Critical (no false green).
- [ ] E911 correction-request returns 202 and writes **no** life-safety field.
- [ ] `/api/customer/support` returns `customer_safe_summary` only.
- [ ] `/api/customer/billing` shows RH MRR total + per-plan mapping, read-only, "as of" dated (or honest `null` if unreconciled).
- [ ] `/api/customer/reports/portfolio[.pdf]` exports a board-ready, evidence-backed snapshot.
- [ ] Full 403/404 tenant-scope matrix green; six internal roles unaffected.
- [ ] `FEATURE_CUSTOMER_API` on for RH only; Judy provisioned `CUSTOMER_ADMIN`; no internal route reachable.

---

*Contract definition only — writes nothing, changes no behavior, creates no PRs.*
</content>
