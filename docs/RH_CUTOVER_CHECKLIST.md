# RH Cutover Checklist — EPIC-OPS-001

> The **go/no-go gate** for turning RH live. This is the final control before
> `FEATURE_CUSTOMER_API` is enabled and Judy can log in. Every box must be checked, every
> approval initialed by Stuart. **If any hard gate is unchecked → NO-GO.**
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md` (Safety >
> Reliability > Security > Data integrity > CX). **Owner / sole go-live authority:** Stuart
> Manley. Prepared: 2026-06-23.
>
> **Companion docs:** `RH_GO_LIVE_TASKBOARD.md`, `RH_DATA_REMEDIATION_PLAN.md`,
> `P4_RH_CUSTOMER_API_VALIDATION_SPEC.md`, `FEATURE_CUSTOMER_API_ROLLOUT.md`.

---

## How to use this checklist
- Work top to bottom. **Hard gates (🔒) cannot be waived.** Soft gates (▫) may be accepted
  with a written Stuart note.
- Every approval line needs Stuart's initials + date.
- A single failed hard gate = **NO-GO**; fix, re-validate, return here.
- Keep this checklist with the run artifacts as the go-live record.

---

## Section A — Pre-cutover data readiness (must be true before cutover day)

| # | Gate | Type | Evidence | ✔ |
|---|---|---|---|---|
| A1 | Phase 1 reconciliation complete; exception worklist fully dispositioned | 🔒 | `INVENTORY_RECONCILIATION.csv` + signed worklist | ☐ |
| A2 | ICCID/identity clean (no unresolved duplicates or conflicts in active fleet) | 🔒 | `rh_iccid_audit.csv` | ☐ |
| A3 | Subscriptions classified; historical/replacement excluded from active fleet | 🔒 | subscription-classification report | ☐ |
| A4 | Every active site has an authoritative, verified address | 🔒 | address remediation diff + audit log | ☐ |
| A5 | E911-verified count ≥ Stuart's go-live threshold; no false-green | 🔒 | readiness audit; E911 evidence | ☐ |
| A6 | Telemetry fresh for the majority of active devices | ▫ | health audit | ☐ |
| A7 | Device-health classification verified against reality (sample); offline devices documented | 🔒 | health audit + cause list | ☐ |
| A8 | Service units created (== eligible active devices); idempotent re-run is a no-op | 🔒 | P3 apply audit log | ☐ |
| A9 | Relationships clean — no orphans, no cross-tenant refs, 1 unit/active device | 🔒 | readiness relationship report | ☐ |

**Section A approval (data ready):** Stuart ____________  Date ________

---

## Section B — Customer API validation (P4 — flag still OFF)

| # | Gate | Type | Evidence | ✔ |
|---|---|---|---|---|
| B1 | P4 validation run on real RH data with flag OFF | 🔒 | `validate_rh_customer_api` CSV/JSON | ☐ |
| B2 | Verdict = PASS (or CONDITIONAL PASS with every condition accepted by Stuart) | 🔒 | P4 verdict | ☐ |
| B3 | All hard checks (P4 checks 5/6/8) pass | 🔒 | P4 report | ☐ |
| B4 | No tenant leakage — customer view shows **only** RH data | 🔒 | P4 isolation checks | ☐ |
| B5 | Six-label vocabulary + no-false-green honored in rendered output | 🔒 | P4 render checks | ☐ |
| B6 | No sensitive internal fields exposed (allow-list serializer verified) | 🔒 | P4 field checks | ☐ |

**Section B approval (render proven safe):** Stuart ____________  Date ________

---

## Section C — Cutover readiness (rollback + access)

| # | Gate | Type | Evidence | ✔ |
|---|---|---|---|---|
| C1 | Rollback plan ready: unsetting `FEATURE_CUSTOMER_API` / allowlist immediately closes the gate | 🔒 | rollback runbook step | ☐ |
| C2 | Two-key procedure understood: flag + `CUSTOMER_API_TENANT_ALLOWLIST` set on **all** services (api **and** worker) | 🔒 | `FEATURE_CUSTOMER_API_ROLLOUT.md` | ☐ |
| C3 | Confirmed non-allowlisted tenant returns 404 when flag is on (negative test plan ready) | 🔒 | rollout runbook | ☐ |
| C4 | Stuart available for the cutover window and Day-1 walkthrough | ▫ | scheduled | ☐ |
| C5 | Before-state snapshots retained for all Phase 2–4 writes | 🔒 | snapshot artifacts | ☐ |

**Section C approval (safe to flip):** Stuart ____________  Date ________

---

## Section D — Cutover execution (live, in order) 🔒🔒🔒

> Do **not** start Section D until A, B, and C are fully approved.

| # | Step | Type | Approval | ✔ |
|---|---|---|---|---|
| D1 | Provision Judy (RH customer user) — RH-tenant-scoped, customer role only | 🔒 | Stuart ______ | ☐ |
| D2 | Verify Judy has **no** platform/internal permissions (cannot see other tenants) | 🔒 | — | ☐ |
| D3 | Enable `FEATURE_CUSTOMER_API=true` + add RH to `CUSTOMER_API_TENANT_ALLOWLIST` on **all** services | 🔒 | Stuart ______ | ☐ |
| D4 | Positive test: RH-allowlisted requests return 200 with correct data | 🔒 | — | ☐ |
| D5 | Negative test: a non-allowlisted tenant returns 404; internal users unaffected | 🔒 | — | ☐ |
| D6 | Day-1 walkthrough as Judy: dashboard, locations, location detail, service, equipment, E911 history | 🔒 | — | ☐ |
| D7 | Stuart confirms what Judy sees is correct, complete-enough, leak-free, no false-green | 🔒 | Stuart ______ | ☐ |

---

## GO / NO-GO decision

> **GO requires:** every 🔒 gate in A, B, C, D checked **and** every approval line initialed.

- ☐ **GO** — RH is live. Record timestamp: ____________
- ☐ **NO-GO** — reason: ________________________________  → route fix to owning phase, re-run
  Section B (P4) at minimum, return here.

**Final go-live authorization (sole authority):** Stuart Manley ____________  Date ________

---

## Immediate rollback triggers (post-cutover)
Flip back (unset `FEATURE_CUSTOMER_API` / remove RH from allowlist) immediately if any of:
- Any cross-tenant data appears in the customer view (**security — instant rollback**).
- A site shows **Protected/green** without verified E911 + address (**safety — false-green**).
- A device shows **Online** that is known physically dead (**safety — false-green**).
- Customer-facing errors or wrong counts that undermine trust (**reliability**).

Rollback is a single action (unset the keys); it requires no data changes and is always
available. Document any rollback with cause + remediation before re-attempting cutover.

---

## Open items still requiring Stuart approval (summary)
- **A4/A5** — address + E911 writes (Phase 2).
- **A8** — service-unit creation `DRY_RUN=false` (`RH_SU_APPROVED_BY=Stuart`).
- **D1** — provisioning Judy.
- **D3** — enabling `FEATURE_CUSTOMER_API` + allowlist.
- **D7** — final Day-1 CX sign-off = go-live authorization.

---

*Cutover checklist only. No code, no PRs, no platform changes are produced by this document.
The cutover itself is two reversible env-key changes plus one user provisioning, all gated
behind Stuart's explicit approval, with single-action rollback always available.*
