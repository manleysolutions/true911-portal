# RH Go-Live Taskboard — EPIC-OPS-001

> **Operational execution board** for making Restoration Hardware (RH) the first
> production customer of True911. **No new platform features, APIs, or UI.** The software
> foundation is treated as complete enough for RH pilot use; everything below is
> **operational** (run tools, remediate data, validate, cut over).
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md` (Safety >
> Reliability > Security > Data integrity > CX). **Owner:** Stuart Manley. Prepared:
> 2026-06-23.
>
> **Companion docs:** `RH_DATA_REMEDIATION_PLAN.md` (the data-fix detail),
> `RH_CUTOVER_CHECKLIST.md` (the go/no-go gate), `OPERATION_GREEN_RH.md`,
> `OPERATION_GREEN_RH_AUDIT_RUNBOOK.md`, `P3_SERVICE_UNIT_CREATION_SPEC.md`,
> `P4_RH_CUSTOMER_API_VALIDATION_SPEC.md`, `RH_GO_LIVE_EXECUTION_PLAN.md`,
> `FEATURE_CUSTOMER_API_ROLLOUT.md`, `INVENTORY_RECONCILIATION_RUNBOOK.md`.

---

## Roles / owners

| Owner | Who | Responsibility |
|---|---|---|
| **STUART** | Stuart Manley | Sole approval authority for every write/cutover gate; final go/no-go |
| **OPS** | Operator with prod-read (and, when approved, prod-write) `DATABASE_URL` | Runs the audit + remediation tools; produces artifacts |
| **DATA** | Whoever sources external truth | Pulls NAPCO Radiolist export, carrier inventory, E911/address truth |
| **REVIEW** | Stuart + Ops | Reviews REVIEW-class reconciliation rows and exceptions |
| **CX** | Stuart | Confirms what Judy (RH) will see is correct before flag-on |

> **Standing constraints (in force this whole epic):** no `DRY_RUN=false` without
> `RH_SU_APPROVED_BY=Stuart`; do not enable `FEATURE_CUSTOMER_API` until Phase 6 gate;
> do not provision Judy until Phase 6 gate; never commit a real vendor export to the repo.

---

## Baseline (documented RH data state — to be re-confirmed by Phase 1 audits)

| Metric | Baseline | Target for go-live |
|---|---|---|
| Customers | 1 | 1 |
| Sites | 42 | 42 reconciled, addresses verified |
| Devices | 51 | 51 identity-clean, telemetry-fresh |
| Service units | **0** | 1 per active device (P3) |
| E911 verified | **0 / 42** | ≥ go-live threshold (Phase 2 gate) |
| Health fresh | **0 / 51** | majority fresh (Phase 3 gate) |
| Health Score | **30 / 100** | green-enough for pilot (Stuart judgment) |

> These numbers are the *documented* baseline. **Phase 1 re-runs the read-only audits in
> the prod-read environment to confirm them** — every later phase keys off the confirmed
> counts, not these.

---

## Phase board

Status legend: ⬜ not started · 🟡 in progress · ✅ done · ⛔ blocked · 🔒 needs Stuart approval

| Phase | Theme | Gating approval | Status |
|---|---|---|---|
| **1** | Inventory reconciliation · NAPCO matching · ICCID validation | — (read-only) | ⬜ |
| **2** | E911 verification · address remediation | 🔒 writes to address/E911 | ⬜ |
| **3** | Telemetry activation · device-health verification | 🔒 device/telemetry writes | ⬜ |
| **4** | Service-unit creation · relationship validation | 🔒 `RH_SU_APPROVED_BY` (P3 write) | ⬜ |
| **5** | Customer API validation (P4) | — (read-only) | ⬜ |
| **6** | Judy provisioning · feature-flag enablement · Day-1 walkthrough | 🔒🔒🔒 cutover gates | ⬜ |

---

## Phase 1 — Inventory reconciliation · NAPCO matching · ICCID validation
**Goal:** establish ground truth — what devices/SIMs RH actually has, matched against
True911 and the NAPCO/carrier export. **Entirely read-only.**

### T1.1 — Confirm RH baseline (readiness audit)
- **Owner:** OPS
- **Inputs:** prod-read `DATABASE_URL`; `OPERATION_GREEN_RH_AUDIT_RUNBOOK.md` command set.
- **Action:** run `audit_rh_readiness`, `audit_rh_device_identity` (read-only).
- **Outputs:** readiness CSV/JSON + device-identity CSV; confirmed counts (customers/sites/
  devices/service-units/E911/health).
- **Dependencies:** prod-read DB access.
- **Success criteria:** counts produced and reconciled against the documented baseline;
  any drift explained in writing.

### T1.2 — ICCID validation / coverage
- **Owner:** OPS
- **Inputs:** prod-read DB; `audit_rh_iccid_coverage`.
- **Action:** run the ICCID coverage audit (valid/invalid/duplicate/missing, NAPCO
  candidacy, conflicting-identity).
- **Outputs:** `rh_iccid_audit.csv`; counts: import-ready, missing-ICCID, invalid,
  duplicate, conflicting-identity.
- **Dependencies:** T1.1.
- **Success criteria:** every device categorized; duplicate + conflicting-identity sets
  enumerated for Phase 1 cleanup; estimated NAPCO match coverage % computed.

### T1.3 — Pull NAPCO Radiolist export
- **Owner:** DATA
- **Inputs:** NAPCO StarLink dealer portal access.
- **Action:** export current RH Radiolist (`.xlsx` or delimited text).
- **Outputs:** vendor export file **on the operator host only** (never committed to repo).
- **Dependencies:** none.
- **Success criteria:** export covers RH's NAPCO fleet; columns include RadioNumber, ICCID,
  SubscriberName, SIMStatus.

### T1.4 — Run inventory reconciliation (EPIC-GEN-003)
- **Owner:** OPS
- **Inputs:** prod-read DB; the NAPCO export (T1.3); `INVENTORY_RECONCILIATION_RUNBOOK.md`.
- **Action:** `python -m app.reconcile_inventory --vendor napco --vendor-export <file>
  --tenant restoration-hardware --out /tmp/INVENTORY_RECONCILIATION` (read-only).
- **Outputs:** `INVENTORY_RECONCILIATION.csv` + `.json` + summary (counts by result, match
  rate).
- **Dependencies:** T1.2, T1.3.
- **Success criteria:** every vendor record + True911 device classified
  (MATCHED/PARTIAL/MISSING_IN_TRUE911/MISSING_IN_VENDOR/DUPLICATE/REVIEW); match rate
  recorded; artifacts contain no carrier-account/dealer-email fields.

### T1.5 — Triage reconciliation exceptions
- **Owner:** REVIEW (Stuart + Ops)
- **Inputs:** `INVENTORY_RECONCILIATION.csv`; `audit_rh_subscription_classification` output
  (matched/historical/duplicate/missing-iccid/missing-device/replacement).
- **Action:** for each non-MATCHED row, assign a disposition (backfill ICCID / mark
  historical / dedupe / source missing device / accept). **No DB writes yet** — produce the
  remediation worklist.
- **Outputs:** the Phase 2/4 worklist (feeds `RH_DATA_REMEDIATION_PLAN.md`).
- **Dependencies:** T1.4.
- **Success criteria:** zero unclassified rows; each exception has a named disposition +
  owner.

**Phase 1 exit gate:** confirmed baseline + reconciliation artifacts + a fully-dispositioned
exception worklist. **No production data changed.**

---

## Phase 2 — E911 verification · address remediation
**Goal:** every active RH site has a correct, verified service address and E911 status.
**First phase that writes — 🔒 Stuart approval required before any write.**

### T2.1 — Address-truth source
- **Owner:** DATA
- **Inputs:** RH's authoritative site/address list (RH facilities, carrier 911 records).
- **Action:** assemble verified address per site; flag mismatches vs True911 site rows.
- **Outputs:** address-remediation worklist (site_id → correct address, source).
- **Dependencies:** Phase 1 site set confirmed (T1.1).
- **Success criteria:** every active site has an authoritative address + a delta vs current
  True911 value.

### T2.2 — Address remediation (write) 🔒
- **Owner:** OPS (under Stuart approval)
- **Inputs:** T2.1 worklist; approved write window.
- **Action:** apply address corrections (per the remediation plan's write procedure;
  dry-run first, all-or-nothing, audit-logged).
- **Outputs:** corrected site addresses; audit-log entries; before/after diff.
- **Dependencies:** T2.1; **🔒 Stuart approval**.
- **Success criteria:** all targeted sites updated; audit log matches the worklist; re-run
  readiness audit shows the corrected addresses.

### T2.3 — E911 verification 🔒
- **Owner:** OPS + DATA
- **Inputs:** verified addresses (T2.2); E911/carrier provisioning confirmation.
- **Action:** record E911 verification status per site against the verified address.
- **Outputs:** E911 status updated; verified count (X/42).
- **Dependencies:** T2.2; **🔒 Stuart approval**.
- **Success criteria:** E911-verified count meets the go-live threshold Stuart sets;
  remaining unverified sites explicitly accepted or excluded from pilot.

**Phase 2 exit gate:** addresses verified + E911 status at/above threshold; no-false-green
respected (a site is "verified" only with evidence).

---

## Phase 3 — Telemetry activation · device-health verification
**Goal:** devices report, and health classification reflects reality. **🔒 device/telemetry
writes require Stuart approval.**

### T3.1 — Telemetry activation
- **Owner:** OPS + DATA
- **Inputs:** device list (Phase 1); heartbeat/telemetry ingest path; carrier/vendor
  connectivity.
- **Action:** confirm/enable each active device's telemetry path so heartbeats land.
- **Outputs:** per-device telemetry-reporting status.
- **Dependencies:** Phase 1 device set; **🔒 approval if any device config write.**
- **Success criteria:** majority of active devices producing fresh heartbeats within the
  heartbeat interval.

### T3.2 — Device-health verification
- **Owner:** OPS
- **Inputs:** `audit_rh_readiness`/health audit re-run; `compute_device_computed_status`
  (Provisioning/Online/Offline) semantics.
- **Action:** re-run read-only health audit; confirm computed status matches physical
  reality for a sample; resolve stale/false-offline devices.
- **Outputs:** health-freshness count (X/51); list of devices still offline/stale with
  cause.
- **Dependencies:** T3.1.
- **Success criteria:** health-fresh count meets the Phase 3 threshold; every still-offline
  device has a documented cause + disposition (fix now / accept / exclude).

**Phase 3 exit gate:** telemetry live + health classification trustworthy; Health Score
improved from baseline 30/100 to Stuart's pilot threshold.

---

## Phase 4 — Service-unit creation · relationship validation
**Goal:** create the missing service units (0 → 1 per active device) and validate
device↔site↔service-unit↔customer relationships. **🔒 P3 write gated by
`RH_SU_APPROVED_BY=Stuart`.**

### T4.1 — P3 dry-run
- **Owner:** OPS
- **Inputs:** prod-read DB; `create_rh_service_units` (`P3_SERVICE_UNIT_CREATION_SPEC.md`);
  default `DRY_RUN=true`.
- **Action:** run P3 in dry-run; review the planned `SU-<device_id>` set + computed status
  (active only when device is Online).
- **Outputs:** P3 plan (units to be created) + rollback plan.
- **Dependencies:** Phase 1 device identity clean; Phase 3 status reliable (status feeds
  unit active/inactive).
- **Success criteria:** plan covers every eligible active device once; no duplicates; plan
  reviewed by Stuart.

### T4.2 — P3 apply (write) 🔒
- **Owner:** OPS (under Stuart approval)
- **Inputs:** approved P3 plan; `RH_SU_APPROVED_BY=Stuart`; `DRY_RUN=false`.
- **Action:** apply the approved service-unit creation (idempotent, audit-logged,
  all-or-nothing, RH-only).
- **Outputs:** service units created; audit-log entries; post-apply count.
- **Dependencies:** T4.1; **🔒 `RH_SU_APPROVED_BY=Stuart` + explicit approval.**
- **Success criteria:** service-unit count == eligible active devices; idempotent re-run is
  a no-op; rollback plan retained.

### T4.3 — Relationship validation
- **Owner:** OPS
- **Inputs:** post-apply DB; readiness audit re-run.
- **Action:** verify each service unit links to the right device, site, and customer; no
  orphans, no cross-tenant leakage.
- **Outputs:** relationship-integrity report.
- **Dependencies:** T4.2.
- **Success criteria:** zero orphaned units; every active device has exactly one unit; all
  links resolve to RH tenant.

**Phase 4 exit gate:** service units exist and relationships are clean — the customer API
now has real data to render.

---

## Phase 5 — Customer API validation (P4)
**Goal:** prove the customer plane renders correct, safe, leak-free data for RH **before**
the flag is enabled. **Read-only — flag stays OFF.**

### T5.1 — Run P4 validation
- **Owner:** OPS
- **Inputs:** prod-read DB; `validate_rh_customer_api`
  (`P4_RH_CUSTOMER_API_VALIDATION_SPEC.md`); flag **OFF**.
- **Action:** run the 10 read-only checks (5/6/8 are hard); produce verdict.
- **Outputs:** P4 CSV + JSON; verdict PASS / CONDITIONAL PASS / FAIL.
- **Dependencies:** Phase 4 complete (units + relationships); Phase 2/3 data quality.
- **Success criteria:** verdict is **PASS** (or CONDITIONAL PASS with every condition
  explicitly accepted by Stuart); all hard checks pass; no tenant leakage; six-label
  vocabulary + no-false-green honored.

### T5.2 — Remediate P4 findings (loop to Phase 2–4 as needed)
- **Owner:** OPS + REVIEW
- **Inputs:** P4 findings.
- **Action:** for any failed check, route the fix back to the owning phase, re-run, re-P4.
- **Outputs:** clean P4 verdict.
- **Dependencies:** T5.1.
- **Success criteria:** P4 re-run is clean; no open hard-check failures.

**Phase 5 exit gate:** P4 PASS with the flag still OFF — render correctness proven on real
RH data.

---

## Phase 6 — Judy provisioning · feature-flag enablement · Day-1 walkthrough
**Goal:** turn RH on. **Triple-gated cutover — see `RH_CUTOVER_CHECKLIST.md`.**

### T6.1 — Provision Judy (RH customer user) 🔒
- **Owner:** OPS (under Stuart approval)
- **Inputs:** approved customer-role assignment; `FEATURE_CUSTOMER_API_ROLLOUT.md`.
- **Action:** create Judy's account scoped to the RH tenant with the correct customer role.
- **Outputs:** Judy account (cannot see anything until flag-on + allowlist).
- **Dependencies:** Phase 5 PASS; **🔒 Stuart approval.**
- **Success criteria:** account exists, RH-tenant-scoped, correct customer role; verified
  no platform/internal permissions.

### T6.2 — Enable FEATURE_CUSTOMER_API for RH 🔒
- **Owner:** OPS (under Stuart approval)
- **Inputs:** `FEATURE_CUSTOMER_API=true` + `CUSTOMER_API_TENANT_ALLOWLIST` includes RH;
  rollout runbook two-key procedure.
- **Action:** set both keys on **all** services (api + worker) per the env-var-per-service
  lesson; confirm the gate opens only for RH.
- **Outputs:** customer API live for RH tenant only.
- **Dependencies:** T6.1; **🔒 Stuart approval; Phase 5 PASS.**
- **Success criteria:** RH-allowlisted tenant gets 200s; non-allowlisted tenant gets 404;
  internal users unaffected; rollback (unset keys) verified ready.

### T6.3 — Day-1 walkthrough (CX)
- **Owner:** CX (Stuart) + OPS
- **Inputs:** live RH customer view as Judy would see it.
- **Action:** walk every customer screen (dashboard, locations, location detail, service,
  equipment, E911 history); confirm labels, counts, headline are correct and safe.
- **Outputs:** signed-off Day-1 walkthrough; punch list (if any).
- **Dependencies:** T6.2.
- **Success criteria:** Stuart signs off that what Judy sees is correct, complete-enough,
  and contains no other customer's data and no false-green.

**Phase 6 exit gate = GO-LIVE.** Recorded in `RH_CUTOVER_CHECKLIST.md`.

---

## Cross-phase summary

### Remaining blockers
1. **Prod-read environment access** — every audit/reconciliation/validation tool needs a
   readable prod `DATABASE_URL`. Local `localhost:5432` cannot see RH data. **Hard
   blocker for Phase 1.**
2. **NAPCO Radiolist export** — Phase 1 reconciliation needs the current vendor export
   (DATA). Without it, match coverage is unknown.
3. **Address/E911 truth source** — Phase 2 needs RH's authoritative addresses + carrier
   E911 confirmation. External dependency.
4. **Telemetry/connectivity** — Phase 3 depends on devices actually being reachable; field
   issues (power, signal, wiring) are outside software control.
5. **Stuart approval windows** — Phases 2, 4, 6 cannot write without an explicit approval +
   window.

### Estimated days to RH go-live
*Assumes prod-read access on day 1, NAPCO export available, Stuart available for each gate,
and no large field-remediation surprises.*

| Phase | Work | Est. |
|---|---|---|
| 1 | Reconciliation + triage | 1–2 days |
| 2 | E911 + address (external truth + write) | 2–4 days |
| 3 | Telemetry + health (field-dependent) | 2–5 days |
| 4 | Service units + relationship validation | 0.5–1 day |
| 5 | P4 validation (+ remediation loop) | 0.5–1 day |
| 6 | Judy + flag + walkthrough | 0.5 day |
| **Total** | sequential, with overlap | **~6–10 working days** |

> Phase 3 (telemetry/field) is the widest variance — if devices need physical attention,
> it dominates. Phases 1, 4, 5, 6 are fast (tool-driven). Phase 2 hinges on how quickly RH
> supplies authoritative addresses.

### Highest-risk items
1. **E911 correctness (Phase 2)** — top of the Constitution (Safety). A wrong dispatch
   address is the worst possible failure. No-false-green must hold: never show "Protected"
   without verified E911 + address evidence.
2. **Telemetry false-green (Phase 3)** — a device shown Online that is physically dead is a
   silent life-safety gap. Verify computed status against reality on a sample, not just
   counts.
3. **Tenant isolation at flag-on (Phase 6)** — enabling `FEATURE_CUSTOMER_API` must expose
   **only** RH. P4 + the two-key allowlist are the guards; a misconfigured allowlist or a
   missed service (api vs worker) is the leak risk.
4. **Service-unit write correctness (Phase 4)** — P3 with `DRY_RUN=false` mutates prod;
   relies on clean Phase 1 identity + reliable Phase 3 status. Dry-run + audit-log +
   rollback are mandatory.
5. **Reconciliation REVIEW backlog (Phase 1)** — weak (name/site) matches need human
   judgment; if large, they slow Phase 4.

### Items that still require Stuart approval (write/cutover gates)
- **T2.2 / T2.3** — address + E911 writes.
- **T3.1** — any device/telemetry configuration write.
- **T4.2** — P3 `DRY_RUN=false` (requires `RH_SU_APPROVED_BY=Stuart`).
- **T6.1** — provisioning Judy.
- **T6.2** — enabling `FEATURE_CUSTOMER_API` + adding RH to the allowlist.
- **T6.3** — final Day-1 CX sign-off = go-live authorization.

> Everything in Phase 1 and Phase 5 is read-only and needs **no** write approval — those
> can proceed as soon as prod-read access + the NAPCO export are available.

---

*Operational plan only. No platform features, APIs, UI, code, or PRs are produced by this
document. All production writes are gated behind explicit Stuart approval and the existing
dry-run / audit-log / rollback tooling.*
