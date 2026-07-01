# True911+ — CUSTOMER DATA BOUNDARY

> The field-level contract for what a customer (Restoration Hardware / Judy) sees,
> never sees, and may edit. Completes the boundary set after security
> (`RH_SECURITY_READINESS.md`), RBAC (`RH_ROLE_MATRIX.md`), and experience
> (`CUSTOMER_EXPERIENCE_BOUNDARY.md`). Definition only — no code, no PRs.
>
> **Authority Level:** 3 — Execution (data-presentation gate). **Governed by:**
> `CONSTITUTION.md` (§7 veto — no ICCID/SIP/firmware/jargon as the customer view; §4.5
> explainable; §4.6 no green without evidence), `DECISIONS.md` D-004 (label wording),
> D-005 (six-label vocabulary), D-006 (separate axes). Prepared: 2026-06-22.

---

## 0. The rule

**Judy never sees telecom, carrier, provisioning, or engineering jargon.** Every
customer-facing field must answer exactly one question:

> **① What is protected? · ② Is it healthy? · ③ What needs attention? · ④ What should I do?**

If a field answers none of these, it is **HIDE**. The platform already models this
split — `SupportDiagnostic.customer_safe_summary` vs `internal_summary` — and this doc
extends that discipline to every entity.

**Four dispositions per field:**

| Disp. | Meaning |
|---|---|
| **SHOW** | surfaced (often relabeled to plain language), value largely as-is |
| **HIDE** | never sent to a customer API/page (jargon, internal keys, secrets, raw vendor data) |
| **DERIVE** | customer value is *computed/translated* from one or more internal fields (status, "as of" time, verified ✓) — the raw field stays hidden |
| **AGGREGATE** | rolled up across many rows (device→service→site→portfolio counts); no raw row exposed |

**Customer status vocabulary (D-005, the only labels customers see):**
`Protected · Attention Needed · Critical · Pending Install · Inactive · Unknown`.
Customer wording for "all good" is **"Protected (as of <time>)"** (D-004) — never a
guarantee, never a number (§7.1).

---

## 1. Customer (account)

| Field | Disp. | Customer label / derivation |
|---|---|---|
| `name` | SHOW/DERIVE | "Company" — single-customer tenant → `Customer.name`; multi/zero → tenant org name; else `"Your Portfolio"` (generic, `portfolio.company_name`; EPIC-GEN-001) |
| `billing_email` `billing_phone` `billing_address` | SHOW (editable) | "Billing contact" (their own info) |
| `status` | DERIVE | "Account: Active" |
| `id` `tenant_id` `customer_number` `account_number` | HIDE | internal keys |
| `zoho_account_id` `zoho_contact_id` `zoho_deal_id` `zoho_sync_status` `zoho_last_synced_at` | HIDE | CRM internals |
| `onboarding_status` | DERIVE | only as "Setting up" during onboarding; else hidden |
| `created_at` `updated_at` | HIDE | — |

- **Internal fields:** all `zoho_*`, `tenant_id`, `customer_number`, `account_number`, onboarding state.
- **Customer-visible:** company name, own billing contact, account-active status.
- **Customer-editable:** `billing_email/phone/address` (CUSTOMER_ADMIN, CUSTOMER_BILLING). `name` is read-only (Manley-controlled).
- **Recommended actions:** none (account is stable); "Update billing contact" if stale.

## 2. Site → **Location**

| Field | Disp. | Customer label / derivation |
|---|---|---|
| `site_name` | SHOW | "Location" |
| `building_type` | SHOW | "Building type" |
| `e911_street/city/state/zip` | DERIVE | one formatted "Service address" (and feeds E911 §6) |
| `poc_name/phone/email` | SHOW (editable) | "Site contact" |
| `lat` `lng` | AGGREGATE | map pin only (never raw coords in a field) |
| `status` + `last_device_heartbeat` + `uptime_percent` | DERIVE | **"Protection status"** (Protected/Attention/Critical) + "Last checked X ago" |
| `e911_status` `e911_confirmation_required` | DERIVE | "Emergency address: Verified ✓ / Needs verification" (→ §6) |
| `onboarding_status` | DERIVE | "Pending Install" when onboarding |
| `device_model` `device_serial` `device_firmware` `csa_model` `kit_type` `container_version` `firmware_version` | HIDE | equipment jargon |
| `carrier` `static_ip` `signal_dbm` `network_tech` `endpoint_type` `service_class` | HIDE | telecom jargon |
| `heartbeat_frequency/interval/next_due` `update_channel` `template_id` `last_portal_sync` | HIDE | provisioning jargon |
| `address_source` `address_notes` `reconciliation_status` `import_batch_id` | HIDE | data-ops internals |
| `psap_id` `emergency_class` `ng911_uri` | HIDE | NG911 engineering |
| `notes` | HIDE | internal notes |
| `site_id` `tenant_id` `customer_id` `customer_name` | HIDE | keys |
| `created_at` `updated_at` `last_checkin` | HIDE/DERIVE | only "Last checked" surfaces |

- **Internal:** every device/network/provisioning/NG911 column above.
- **Customer-visible:** location name, building type, service address, site contact, protection status, emergency-address state.
- **Customer-editable:** `poc_name/phone/email` (site contact). **Address is read-only** — corrections go through a Manley-gated E911 request (§6).
- **Status mapping:** active + fresh health + E911 verified → **Protected**; active + E911 unverified → **Critical** (rule); onboarding → **Pending Install**; no health signal → **Unknown** (never "healthy").
- **Recommended actions:** "Verify emergency address" (Manley), "Update site contact" (customer).

## 3. Device → **Equipment health** (the most jargon-heavy entity — almost all HIDE)

| Field | Disp. | Customer label / derivation |
|---|---|---|
| `status` + `last_heartbeat` | DERIVE | **"Online / Offline · Last seen X ago"** |
| `device_type` / `model` | DERIVE | friendly equipment name via label map ("Elevator phone unit") — never the raw model string |
| `activated_at` | DERIVE | "In service since <date>" |
| `serial_number` `mac_address` `imei` `iccid` `msisdn` `imsi` `sim_id` `starlink_id` | HIDE | identifiers (§7 veto) |
| `firmware_version` `container_version` `provision_code` `hardware_model_id` `identifier_type` `manufacturer` | HIDE | engineering |
| `carrier` `network_status` `data_usage_mb` `last_network_event` `telemetry_source` `wan_ip` `lan_ip` | HIDE | telecom/network |
| `vola_org_id` `vola_last_sync` `vola_last_task_id` | HIDE | vendor internals |
| `api_key_hash` | HIDE | **secret — never** |
| `reconciliation_status` `import_batch_id` `source_row_id` `claimed_by` `claimed_at` | HIDE | data-ops |
| `term_end_date` | HIDE | surfaces under Billing only (§5) |
| `device_id` `tenant_id` `site_id` `heartbeat_interval` | HIDE | keys/config |

- **Internal:** essentially the entire row.
- **Customer-visible:** a derived "this equipment is Online/Offline, last seen X ago, in service since Y," attached to the **Service** it powers — never a standalone "device with an ICCID."
- **Customer-editable:** **none** (devices are Manley-managed).
- **Status mapping:** `status=active` + heartbeat fresh → **Online (Protected)**; active + stale/no heartbeat → **Offline (Attention/Critical)**; `provisioning` → **Pending Install**; `inactive/decommissioned` → **Inactive**; never reported → **Unknown** (not healthy).
- **AGGREGATE:** device health rolls up into its Service unit, then the Location, then the portfolio.
- **Recommended actions:** "We're investigating" (offline → Manley), surfaced as a Support prompt — never a customer device action.

## 4. ServiceUnit → **Service** (the "what is protected" unit — most customer-relevant)

| Field | Disp. | Customer label / derivation |
|---|---|---|
| `unit_name` | SHOW | "Service" |
| `unit_type` | DERIVE | plain label: `elevator_phone`→"Elevator emergency phone", `fire_alarm`→"Fire alarm line", `emergency_call_station`→"Emergency call station", `voice_line`→"Emergency voice line" |
| `location_description` `floor` | SHOW | "Where" ("Elevator #3, South Tower") |
| `voice/video/text/visual_messaging/onsite_takeover/backup_power _supported` | DERIVE | "Can call for help: Voice ✓ · Video ✓" (capability chips) |
| `compliance_status` | DERIVE | "Compliance: Compliant / Needs review" (+ "guidance, not legal advice" disclaimer) |
| `governing_code_edition` | SHOW (opt) | "Governing code" (compliance proof — customer-relevant) |
| `compliance_last_reviewed_at` | DERIVE | "Last reviewed <date>" |
| `status` + linked device health | DERIVE | **"Protection status"** for this service |
| `camera_present` | DERIVE | "Camera: Yes/No" |
| `monitoring_station_type` | DERIVE | "Monitored: Central station / Not monitored" (simplified) |
| `compliance_notes` | HIDE | internal review notes |
| `install_type` `jurisdiction_code` | HIDE | ops/jurisdiction internals |
| `video_stream_url` `video_transport_type` `video_encryption` `video_retained` `video_operator_visible` | HIDE | streaming engineering |
| `device_id` `line_id` `sim_id` `meta` `notes` `unit_id` `tenant_id` `site_id` | HIDE | keys/linkage |

- **Internal:** linkage keys, video transport, jurisdiction code, raw compliance notes.
- **Customer-visible:** service name, type, where it is, what it can do, compliance state, protection status.
- **Customer-editable:** **none** at go-live (could later allow editing `location_description` label). 
- **Status mapping:** `status=active` + healthy device + compliant → **Protected**; `review_required`/`partially_compliant` → **Attention Needed**; `non_compliant` or unhealthy → **Critical**; `pending_install` → **Pending Install**; `unknown` → **Unknown**.
- **Recommended actions:** "Schedule a compliance review" (review_required), "Contact support" (Critical).

## 5. Subscription / Billing Record → **Billing** (visibility, not accounting)

Sources: `Subscription` (`mrr`) + `zoho_subscription_record` (`mrc`).

| Field | Disp. | Customer label / derivation |
|---|---|---|
| `plan_name` / `subscription_type` | SHOW | "Service plan" |
| `mrr` / `mrc` | SHOW | "Monthly cost" (with "as of" + source) |
| `qty_lines` | DERIVE | "Services covered" (count) |
| `start_date` | DERIVE | "Active since" |
| `renewal_date` / `service_term_ends` | DERIVE | "Renews on" |
| `status` / `lifecycle_state` | DERIVE | "Active / Paused / Ended" |
| `facility_name` | DERIVE | mapped to the customer's Location name (service-to-billing) |
| `external_subscription_id` `external_source` (`zoho`/`qb`) | HIDE | system-of-record internals |
| `msisdn` `device_activation_status` `connection_type` | HIDE | telecom jargon |
| `account_name` `org_id` `raw_json` `external_record_map_id` `last_event_id` | HIDE | internals |

- **Internal:** all external ids/source system, raw telecom subscription detail, raw_json.
- **Customer-visible:** plan, monthly cost, services covered, active-since, renews-on, status, mapped to Location.
- **Customer-editable:** **none** (read-only visibility; commercial state is never customer-written — D-006).
- **AGGREGATE:** **portfolio MRR total** + count of active services across all Locations.
- **Status mapping:** `active`→"Active", `paused`→"Paused", `cancelled/expired`→"Ended".
- **Deferred (not shown at go-live):** invoices, invoice PDF, payment status, QuickBooks data (per `RH_GO_LIVE_EXECUTION_PLAN.md` Track D).
- **Recommended actions:** "Renews soon — contact us" (near `renewal_date`).

## 6. E911 Record → **Emergency address** (read-only; the life-safety surface)

Sources: `Site.e911_*` + `E911ChangeLog`.

| Field | Disp. | Customer label / derivation |
|---|---|---|
| `e911_street/city/state/zip` | SHOW | "Emergency dispatch address" (formatted, one block) |
| `e911_status` | DERIVE | "Verified ✓ (as of <applied_at>)" if `∈{validated,verified}`; else "Not yet verified" |
| `e911_confirmation_required` | DERIVE | "Confirmation needed" badge |
| `E911ChangeLog.new_*` + `status` + `applied_at` | DERIVE/AGGREGATE | "Address history" timeline (date · what changed · Verified/Applied) |
| `E911ChangeLog.requester_name` | DERIVE | "Updated by Manley" (name shown, internal email hidden) |
| `E911ChangeLog.requested_by` `correlation_id` | HIDE | internal actor email / trace id |
| `E911ChangeLog.old_*` `reason` | DERIVE (opt) | "Previous address" / "Reason" in history detail |
| `psap_id` `emergency_class` `ng911_uri` `address_source` | HIDE | NG911/engineering |

- **Internal:** PSAP/NG911 ids, address source, correlation ids, requester email.
- **Customer-visible:** the dispatch address, its verified state + timestamp, and a plain-language change history (proof).
- **Customer-editable:** **none directly.** A customer may **request a correction**, which creates a Manley-gated E911 change (never a customer write to a life-safety field). Verification is always an authoritative Manley step.
- **Status mapping (D-015, three dimensions never collapsed):** address present + `e911_status` verified → **Verified ✓**; present + unverified → **Attention / "Not yet verified"**; missing → **Setup needed**; **active + unverified = Critical** (shown red with reason, never green).
- **Recommended actions:** "Request an address correction" (customer); "We're verifying this address" (Manley) when unverified.

## 7. Support Case → **Support** (reuses the existing customer-safe/internal split)

Sources: `SupportSession`, `SupportMessage`, `SupportDiagnostic`, `SupportEscalation`.

| Field | Disp. | Customer label / derivation |
|---|---|---|
| `SupportSession.status` | DERIVE | "Open / In progress / Resolved" (`active/escalated/resolved`) |
| `issue_category` | DERIVE | plain category ("Phone not working") — raw enum hidden |
| `resolution_summary` | SHOW | "Resolution" |
| `created_at` | SHOW | "Opened" |
| `SupportMessage.content` (role user/assistant) | SHOW | conversation (sanitized; `system` role hidden) |
| `SupportDiagnostic.customer_safe_summary` + `status` | SHOW/DERIVE | "We checked X: OK / Needs attention" |
| `SupportDiagnostic.internal_summary` `raw_payload` `confidence` `check_type` | HIDE | internal diagnostics |
| `SupportEscalation.status` `zoho_ticket_number` | DERIVE | "Escalated to our team · Ticket #" (number only) |
| `SupportEscalation.probable_cause` `internal_summary` `handoff_summary` `diagnostics_checked` `dedupe_key` `zoho_ticket_id/url/zoho_status` | HIDE | internal/vendor |
| `SupportRemediationAction.*` | HIDE | internal remediation engine (action_level, raw_result, etc.) |
| `SupportAISummary.*` (probable_cause, transcript_summary, confidence) | HIDE | internal AI working notes |

- **Internal:** all `internal_summary`, `raw_payload`, probable cause, remediation engine, Zoho desk internals, AI working notes.
- **Customer-visible:** their own case status, sanitized conversation, customer-safe diagnostic outcomes, "escalated · ticket #", resolution.
- **Customer-editable:** create a case, add a message/comment, mark resolved (CUSTOMER_ADMIN/USER via `CUSTOMER_MANAGE_SUPPORT`). CUSTOMER_READONLY/BILLING: view-only / none.
- **Status mapping:** `active`→Open, `escalated`→In progress (with our team), `resolved`→Resolved.
- **Recommended actions:** "Add details", "Mark resolved", "Reopen".

## 8. Field-disposition summary (counts the boundary)

| Entity | SHOW | DERIVE | AGGREGATE | HIDE | Editable |
|---|--:|--:|--:|--:|---|
| Customer | 2 | 2 | 0 | ~9 | billing contact |
| Site → Location | 3 | 5 | 1 | ~25 | site contact |
| Device → Equipment | 0 | 3 | 1(rollup) | ~30 | none |
| ServiceUnit → Service | 4 | 6 | 0 | ~9 | none |
| Subscription → Billing | 2 | 5 | 1 | ~9 | none |
| E911 | 1 | 4 | 1 | ~6 | request-only |
| Support | 3 | 5 | 0 | ~15 | create/comment/resolve |

**The Device entity is ~100% HIDE/DERIVE** — proof the §7 jargon veto holds: a customer
never sees a raw device, only "equipment that is Online, protecting this Service."

---

## Customer-facing Data Models (the JSON shapes a customer API returns)

> Examples use **Restoration Hardware** (1 customer, 42 galleries, elevator emergency
> phones + fire/alarm lines). Values show the **target post-remediation** state; the
> pre-remediation reality today (0/42 verified, 0/51 reporting) renders as
> "Verifying…" / "Setting up" / **Unknown**, never green — per the go-live gate.

### A. Customer Dashboard Data Model (the Morning Test)
```jsonc
{
  "company": "Restoration Hardware",
  "as_of": "2026-07-15T08:00:00Z",
  "portfolio": {                       // AGGREGATE across 42 locations
    "locations_total": 42,
    "protected": 39,
    "attention_needed": 2,
    "critical": 1,
    "pending_install": 0,
    "unknown": 0
  },
  "headline": "39 of 42 locations Protected (as of 8:00 AM)",   // D-004 wording
  "attention_feed": [                  // what needs attention — ranked
    { "location": "RH Boston — Back Bay", "status": "Critical",
      "why": "Emergency address not yet verified", "action": "We're verifying this address" },
    { "location": "RH Chicago", "status": "Attention Needed",
      "why": "Elevator phone offline 2h", "action": "We're investigating" }
  ],
  "recent_manley_activity": [          // trust trail (sanitized audit)
    { "when": "2026-07-14", "what": "Verified emergency address for RH Yountville" }
  ]
}
```

### B. Customer Site (Location) Detail Data Model
```jsonc
{
  "location": "RH Yountville",
  "building_type": "Gallery",
  "status": "Protected",
  "as_of": "2026-07-15T07:58:00Z",
  "service_address": "6725 Washington St, Yountville, CA 94599",
  "emergency_address": { "state": "Verified", "verified_on": "2026-07-14" },
  "site_contact": { "name": "Gallery Ops Lead", "phone": "707-555-0142", "editable": true },
  "services": [                        // AGGREGATE: service units + their equipment health
    { "service": "Elevator emergency phone", "where": "Elevator #1", "status": "Protected", "can_call_for_help": ["Voice"] },
    { "service": "Fire alarm line", "where": "Utility room", "status": "Protected", "can_call_for_help": ["Voice"] }
  ],
  "proof": { "last_checked": "2026-07-15T07:58:00Z", "evidence": "device online + test call 2026-07-10" }
}
```

### C. Customer Device (Equipment) Detail Data Model
```jsonc
{
  "equipment": "Elevator phone unit",   // DERIVE from device_type/model — no raw model
  "powers_service": "Elevator emergency phone — Elevator #1",
  "health": "Online",                   // DERIVE: status + last_heartbeat
  "last_seen": "2026-07-15T07:57:00Z",
  "in_service_since": "2026-03-02",
  "status_label": "Protected"
  // NO serial, ICCID, IMEI, MSISDN, firmware, carrier, IP — all HIDE
}
```

### D. Customer Billing Data Model (visibility only)
```jsonc
{
  "as_of": "2026-07-01",
  "source": "synced from billing system",
  "portfolio_monthly_total": "$4,830.00",   // AGGREGATE of mrr/mrc
  "active_services_count": 51,
  "plans": [                                 // service-to-billing mapping
    { "location": "RH Yountville", "plan": "Emergency Line Monitoring",
      "services_covered": 2, "monthly_cost": "$120.00", "status": "Active", "renews_on": "2026-12-01" }
  ]
  // NO external_subscription_id, source system, MSISDN, raw_json; NO invoices/PDF at go-live
}
```

### E. Customer E911 Data Model (read-only, life-safety)
```jsonc
{
  "location": "RH Boston — Back Bay",
  "emergency_dispatch_address": "234 Berkeley St, Boston, MA 02116",
  "verification": { "state": "Not yet verified", "is_critical": true,
                    "message": "Active location with an unverified emergency address — we're verifying it" },
  "confirmation_required": false,
  "address_history": [                       // DERIVE/AGGREGATE from E911ChangeLog
    { "when": "2026-07-12", "change": "Address set", "by": "Manley", "state": "Pending verification" }
  ],
  "customer_actions": ["Request an address correction"]   // request-only; never a direct write
  // NO psap_id, ng911_uri, emergency_class, correlation_id, requester email
}
```

---

## 6a. RH Login Preview — the one scoped exception (IMPLEMENTED)

For the urgent RH go-live, a tenant-scoped **preview mode** (`FEATURE_CUSTOMER_PREVIEW`
+ `CUSTOMER_PREVIEW_TENANT_ALLOWLIST`, default OFF) presents the **operational
axis** (Site/Service/Device protection + equipment health) as **Protected/Online**
before live telemetry is connected. It is **presentation-only** (writes nothing;
raw device/API state and internal views are untouched) and its green carries an
honest **operator-attestation** evidence signal, not fabricated telemetry — so the
"no green without evidence" rule below still holds.

**The E911 axis is explicitly excluded from preview** (§6). Preview never forces
"Verified"; `verified` is true **only** when the stored `e911_status` is actually
verified, and active+unverified stays **Critical**. Additionally the customer E911
record now enumerates, from **real stored data** ("where applicable", never faked):

| E911 endpoint field | Source (real) |
|---|---|
| service type | `ServiceUnit.unit_type` → plain label |
| where (unit/suite) · floor | `ServiceUnit.location_description` · `ServiceUnit.floor` |
| callback number / BTN / line id | linked `Line.did`, else `Device.msisdn` |
| verified flag | `Site.e911_status ∈ {validated, verified}` only |

Missing/unverified E911 data is surfaced on the **internal** correction worklist
`GET /api/e911-changes/gaps` (`UPDATE_E911`) — see `CUSTOMER_EXPERIENCE_BOUNDARY.md` §F.

The conceptual model (evidence sources, E911 exclusion, per-location retirement)
is `docs/customer/ASSURANCE_ENGINE.md`; the operator steps are
`docs/customer/RH_GO_LIVE_RUNBOOK.md` (D-016). The enterprise, service-first
presentation of this data (Enterprise→Portfolio→Location→Service→Equipment→Carrier;
executive metrics, health score, map, search, Location Command Center) is
`docs/customer/CUSTOMER_COMMAND_CENTER.md` — all additive and customer-safe.

## Cross-cutting rules
1. **No green without evidence** (§4.6): every `status: Protected` carries `as_of` +
   `proof`. Missing data → **Unknown**, never Protected. *(Preview satisfies this via
   an operator-attestation evidence signal — honest, not fabricated telemetry.)*
2. **Separate axes never collapse** (D-006): operational health, E911 verification, and
   billing status are **distinct** customer fields — a paused subscription never shows a
   location "Offline," and a live heartbeat never hides an unverified E911 (Critical).
3. **Derive, don't dump:** any time a raw field is jargon, the customer sees a derived
   plain-language value; the raw field is HIDE.
4. **Sanitize at the boundary:** reuse the existing `customer_safe_summary` /
   `internal_summary` pattern for every new customer payload; internal text is stripped
   server-side, not just hidden in the UI.
5. **Request, don't write, life-safety:** customers never write E911/dispatch fields;
   they request a Manley-gated change.

---

*Definition only — writes nothing, changes no behavior, creates no PRs.*
</content>
