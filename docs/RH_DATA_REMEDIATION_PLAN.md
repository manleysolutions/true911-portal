# RH Data Remediation Plan — EPIC-OPS-001

> The **data-fix detail** behind the go-live taskboard. Takes RH from the documented
> baseline (0 service units, 0/42 E911 verified, 0/51 health fresh, Health Score 30/100) to
> pilot-ready, using **only existing read-only audits + the existing dry-run-gated
> remediation tools**. No new tooling, no schema changes.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md` (Data integrity;
> Safety for E911). **Owner:** Stuart Manley. Prepared: 2026-06-23.
>
> **Companion docs:** `RH_GO_LIVE_TASKBOARD.md`, `RH_CUTOVER_CHECKLIST.md`,
> `OPERATION_GREEN_RH.md`, `OPERATION_GREEN_RH_AUDIT_RUNBOOK.md`,
> `P3_SERVICE_UNIT_CREATION_SPEC.md`, `INVENTORY_RECONCILIATION_RUNBOOK.md`.

---

## Remediation principles (non-negotiable)
1. **Read before write.** Every write phase is preceded by a read-only audit that produces
   the exact worklist; nothing is changed that an audit didn't first surface.
2. **Dry-run first, all-or-nothing.** All remediation runs default `DRY_RUN=true`, plan the
   full change set, and apply atomically only after Stuart approval.
3. **Idempotent + audit-logged.** Re-running is a no-op; every write emits a `log_audit`
   entry (actor, target, before/after).
4. **RH-only scope.** Remediation tools are tenant-scoped to RH; no cross-tenant blast
   radius.
5. **No false-green.** A site/device is only marked verified/protected with evidence + an
   `as_of` timestamp. Absence of data is **Unknown**, never **Protected**.
6. **Rollback ready.** Every write phase has a captured before-state and a rollback plan
   before it runs.

---

## Data domains, current state, and target

| Domain | Source of truth | Baseline | Target | Tool(s) |
|---|---|---|---|---|
| SIM / device identity (ICCID, RadioNumber) | NAPCO export + carrier | unverified | reconciled, dedup'd, valid | `audit_rh_iccid_coverage`, `reconcile_inventory` |
| Subscriptions (active vs historical) | carrier subscription mgmt | mixed (91-vs-51 story) | classified | `audit_rh_subscription_classification` |
| Site addresses | RH facilities + carrier 911 | possibly stale | verified | address remediation (write) |
| E911 status | carrier/E911 provider | 0/42 verified | ≥ threshold | E911 verification (write) |
| Telemetry / heartbeat | device → ingest | 0/51 fresh | majority fresh | telemetry activation; health audit |
| Device health classification | computed | stale | trustworthy | `compute_device_computed_status`, health audit |
| Service units | True911 | **0** | 1 per active device | `create_rh_service_units` (P3) |
| Relationships (device↔site↔unit↔customer) | True911 | partial | clean | readiness audit re-run |

---

## Stage 1 — Identity & inventory remediation (maps to Taskboard Phase 1 + 4 inputs)

### 1A. ICCID hygiene (read-only diagnosis)
- **Run:** `audit_rh_iccid_coverage` → `rh_iccid_audit.csv`.
- **Categories handled:** `ready_for_napco_import`, `napco_candidate_no_iccid`,
  `invalid_iccid`, `duplicate_iccid`, `conflicting_identity` (ICCID in serial column),
  `non_napco_device`.
- **Remediation dispositions:**
  - *missing ICCID on NAPCO candidate* → backfill from NAPCO export (Stage 1C match) or
    carrier; if unobtainable → mark device Unknown, exclude from import.
  - *invalid ICCID* → correct from authoritative source; never guess.
  - *duplicate ICCID* → identify the true owner; the other device is re-identified or
    flagged historical.
  - *conflicting identity* → move the ICCID to the correct column; clear the wrong one.
- **Output:** identity-fix worklist (device_id → action → source).

### 1B. Subscription classification (read-only)
- **Run:** `audit_rh_subscription_classification`.
- **Resolves the "more subscriptions than devices" gap** into: `matched_service`,
  `historical_subscription`, `duplicate_subscription`, `replacement_subscription`,
  `missing_iccid`, `missing_device`, `missing_site`, `unresolved`.
- **Dispositions:** historical/replacement → exclude from active fleet (do **not** create
  service units for them); duplicate → keep the live one; missing_device → source the
  device or mark the subscription as no-device.

### 1C. Inventory reconciliation (read-only, EPIC-GEN-003)
- **Run:** `reconcile_inventory --vendor napco --vendor-export <file> --tenant
  restoration-hardware`.
- **Consumes:** the NAPCO Radiolist export + True911 inventory.
- **Produces:** per-record result (MATCHED/PARTIAL/MISSING_IN_TRUE911/MISSING_IN_VENDOR/
  DUPLICATE/REVIEW) + match rate.
- **Dispositions:**
  - `PARTIAL` (matched key, no site/unit) → feeds Stage 4 (service-unit creation).
  - `MISSING_IN_TRUE911` (vendor radio, no device) → source/import the device, or confirm
    decommissioned.
  - `MISSING_IN_VENDOR` (True911 device not in export) → confirm with carrier; possibly a
    stale True911 row → mark inactive.
  - `DUPLICATE` → dedupe (ties to 1A duplicate handling).
  - `REVIEW` → human decision (Stuart + Ops).
- **Output:** the master exception worklist that Stages 2 and 4 draw from.

> **Stage 1 writes nothing.** Its product is three reconciled worklists. Identity
> corrections that *do* require a DB write are applied through the same dry-run/audit/
> rollback discipline as later stages, under Stuart approval, and only after the worklist is
> agreed.

---

## Stage 2 — E911 & address remediation (Taskboard Phase 2) 🔒
> **Highest-safety stage.** A wrong address = wrong 911 dispatch. Treated as the most
> conservative write in the program.

### 2A. Address verification
- **Input:** RH authoritative facility list + carrier 911 service records.
- **Procedure:** for each of the 42 sites, compare True911 address vs authoritative;
  produce a delta list (site_id, current, correct, source).
- **Write (🔒 Stuart):** apply corrections — dry-run first, review the full diff, apply
  atomically, audit-log each change, retain before-state for rollback.
- **Success:** every active site address matches an authoritative source; deltas resolved
  or explicitly accepted.

### 2B. E911 status verification
- **Input:** verified addresses (2A) + E911/carrier provisioning confirmation.
- **Procedure:** record E911-verified status per site **only with evidence** (provisioning
  confirmation + `as_of`).
- **Write (🔒 Stuart):** set verified status; unverified sites stay Unknown/Pending, never
  green.
- **Success:** E911-verified count ≥ Stuart's go-live threshold; the no-false-green
  invariant holds (Protected requires verified E911 + address).

**Stage 2 rollback:** restore captured pre-change address/E911 values from the before-state
snapshot; re-run readiness audit to confirm.

---

## Stage 3 — Telemetry & device-health remediation (Taskboard Phase 3) 🔒
### 3A. Telemetry activation
- **Input:** device list + ingest path + carrier/vendor connectivity.
- **Procedure:** confirm each active device's heartbeat lands; for silent devices,
  diagnose (connectivity, config, power/field). Any device-config write is 🔒 Stuart.
- **Success:** majority of active devices emit fresh heartbeats within `heartbeat_interval`.

### 3B. Health classification verification
- **Input:** health audit re-run; `compute_device_computed_status`
  (Provisioning/Online/Offline).
- **Procedure:** confirm computed status matches physical reality on a sample; resolve
  false-offline (stale heartbeat config) and surface true-offline for field action.
- **Success:** health-fresh count ≥ Phase 3 threshold; each remaining offline device has a
  documented cause + disposition. **No device shown Online without a fresh heartbeat.**

> Devices that physically cannot be made to report stay **Offline/Unknown** — they are not
> cosmetically greened to hit a number.

---

## Stage 4 — Service-unit creation & relationship validation (Taskboard Phase 4) 🔒
### 4A. Plan (dry-run)
- **Run:** `create_rh_service_units` with default `DRY_RUN=true`.
- **Behavior:** pure planner — one `SU-<device_id>` per eligible active device; unit status
  derived from `compute_device_computed_status` (active only when device is Online);
  all-or-nothing; idempotent.
- **Gate:** only **active, identity-clean** devices (Stage 1) with reliable status (Stage 3)
  are eligible. Historical/duplicate/replacement subscriptions (Stage 1B) are excluded.
- **Output:** P3 plan + rollback plan; reviewed by Stuart.

### 4B. Apply (write) 🔒
- **Requires:** `RH_SU_APPROVED_BY=Stuart` **and** explicit approval; then `DRY_RUN=false`.
- **Behavior:** atomic create, audit-logged, idempotent (safe re-run), RH-only.
- **Success:** service-unit count == eligible active devices; re-run is a no-op.

### 4C. Relationship validation
- **Run:** readiness audit re-run.
- **Checks:** every unit links to the correct device + site + customer; zero orphans; no
  cross-tenant references; exactly one unit per active device.
- **Success:** clean relationship-integrity report.

**Stage 4 rollback:** `plan_rollback` removes the created units (idempotent); audit log
records the reversal.

---

## Remediation order & why
1. **Identity first (Stage 1)** — you cannot create correct service units or trust health
   until ICCID/RadioNumber identity is clean and subscriptions are classified.
2. **Addresses/E911 (Stage 2)** — safety-critical and independent of telemetry; do it on the
   confirmed site set.
3. **Telemetry/health (Stage 3)** — status must be real before it drives service-unit
   active/inactive.
4. **Service units (Stage 4)** — derived from clean identity + reliable status; quick once
   1–3 are done.
5. *(Validation = Taskboard Phase 5 P4; cutover = Phase 6 — covered in the taskboard and
   cutover checklist.)*

---

## Data-quality exit criteria (what "remediated" means)
- [ ] Every device categorized by ICCID coverage; duplicates + conflicts resolved.
- [ ] Every subscription classified; historical/replacement excluded from the active fleet.
- [ ] Reconciliation exception worklist fully dispositioned (no open REVIEW without an owner
      decision).
- [ ] Every active site has an authoritative, verified address.
- [ ] E911-verified count ≥ Stuart's threshold; no false-green.
- [ ] Telemetry fresh for the majority of active devices; offline devices have documented
      causes.
- [ ] Service-unit count == eligible active devices; relationships clean (no orphans, no
      cross-tenant).
- [ ] Re-running any remediation tool is a no-op (idempotency proven).

---

## Approvals required in this plan
| Stage | Write | Approval |
|---|---|---|
| 2A/2B | address + E911 | 🔒 Stuart + write window + before-state snapshot |
| 3A | device/telemetry config | 🔒 Stuart (if any config write) |
| 4B | service-unit creation | 🔒 `RH_SU_APPROVED_BY=Stuart` + explicit approval |

> Stages 1A–1C and all audit re-runs are **read-only** and require no write approval.

---

*Remediation plan only. Produces no code, no PRs, and no schema changes. Every production
write is gated behind Stuart approval and the existing dry-run / audit-log / rollback
tooling, RH-tenant-scoped.*
