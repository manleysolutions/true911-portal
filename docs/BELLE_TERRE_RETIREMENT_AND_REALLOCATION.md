# Belle Terre retirement & reallocation — governed design (PROPOSED, NOT APPLIED)

> **Status:** design only. Nothing here has been executed. No production write is
> authorized by this document. Decision record: `DECISIONS.md` D-029.
> **Governed by:** `CONSTITUTION.md` (Safety first; additive, never destructive).
> **Evidence still pending:** production read-only trace
> `operator-tools/belle_terre_lineage_trace_v2.sh`. This plan is finalized only after
> that output is reviewed record by record.

## 1. Operator ground truth (Stuart Manley, 2026-10-01)

- IPM asked Manley Solutions to **hold** the Belle Terre at Sunrise deployment. **The
  installation never occurred.**
- The equipment, SIMs/numbers and services allocated/staged for Belle Terre were
  **repurposed** to other installations.
- **One allocation was installed for Restoration Hardware at 265 Greenwich Avenue,
  Greenwich, CT.** T-Mobile shows the subscription ending **8836** as "256 RH Greenwich
  - Elevator". The carrier label says 256 and the address is 265. Treat the label's
  digits as label noise, not as a second location; the trace records it.
- **The other two allocations** were repurposed at another customer. The recollection
  is that LM150s replaced broken MS130s. T-Mobile labels read "Yorktown Elevator 1 / 2".
  **This is a lead, not proof of placement.**

Operator provenance: Stuart Manley. Reason to record: *"IPM requested deployment hold;
allocated equipment/services were subsequently repurposed."*

## 2. What True911 holds today (from the seed; production confirmation pending)

`app/seed_integrity.py` (commit `c014fdd`, 2026-06-01, planning intake sheet) created,
under tenant `integrity-pm`:

| Record | State written by the seed |
|---|---|
| Site `IPM-BELLE-TERRE` "Belle Terre at Sunrise" | `status=active`, `onboarding_status=active`, full E911 street/city/state/zip (Sunrise FL 33351), `e911_status=provided` |
| Service units `IPM-BELLE-TERRE-EL1..3` | `elevator_phone`, `status=active`, `device_id=VOLA-<serial>` |
| Devices `VOLA-<serial>` ×3 (LM150; serials …0226 / …0227 / …0230) | `status=active`, serial/IMEI/ICCID/MSISDN populated, `telemetry_source=tmobile_callback`; no activation date or heartbeat from the seed |
| SIMs ×3 (ICCID …3645 / …3652 / …6351) | `status=active`, `data_source=manual` |
| Telephone identifiers | MSISDN on device and SIM: EL1 …7860, **EL2 …8836**, EL3 …3349. The seed creates **no** `lines` rows |

**Health contamination (important).** The 5-minute `true911-device-health-sync` cron
looks each device up in Vola **by serial** and writes the result onto these
Belle-Terre-sited rows (`last_heartbeat`, network status). It also archives each raw
Vola payload in `integration_payloads`. Repurposed hardware that is online at
Greenwich or Yorktown therefore makes Belle Terre look alive. **Device-health sync
against a seeded site never establishes installation there** (D-029).

## 3. Why a status change alone is not enough

The current read paths do not exclude sites by status:
- `services/customer/portfolio.py` loads **every** site in the tenant.
- Inactive or decommissioned service units still render, as "Inactive".

So setting `Site.status` would leave Belle Terre visible as a customer location. The
existing `plan_customer_retirement.py` is also the wrong tool. It is customer-scoped,
and it **decommissions devices and disconnects lines**, which would be false here
because the hardware is live elsewhere.

**Prerequisite (code, separate PR):** a single "current operational inventory"
predicate built on a deployment-lifecycle axis. A site/building counts as current only
when its deployment state is INSTALLED. Every customer, assurance, health, monitoring
and E911-requirement read path must use that predicate. This is the deployment
lifecycle recommended in the Phase 1 report: PLANNED / STAGED / INSTALLED /
NEVER_INSTALLED (cancelled) / DECOMMISSIONED / UNKNOWN. It is independent of asset
lifecycle, monitoring, E911, confidence and approval. Legacy `Site.status` keeps its
recorded value.

## 4. Proposed governed remediation (per entity)

Principle: **detach and reclassify; never delete; never decommission hardware that is
in service elsewhere; preserve the lineage that explains why these identifiers were
ever associated with Belle Terre.**

| Entity | Proposed change | Preserved |
|---|---|---|
| **Site** `IPM-BELLE-TERRE` | Deployment state → **NEVER_INSTALLED** (reason + operator + evidence refs). The site leaves current inventory through the predicate in §3. `onboarding_status` → `cancelled`. | Row, name, address, created_at, all history |
| **Service units** EL1-3 | `status` → `inactive`. Clear `device_id` / `line_id` / `sim_id`, with prior values written into the unit's `meta.history` and the audit row, so no health ever joins Belle Terre to live hardware again. | Rows, unit ids, types |
| **Devices** ×3 | **Stay `active`** (in service elsewhere). `site_id` → NULL with prior value in audit (allocation history). Placement is decided separately per device (§5, §6). Tenant ownership changes only by explicit operator decision per device — never automatically. | Rows, identifiers, health fields, created_at |
| **SIMs** ×3 | Same as devices: carrier status stays carrier-derived; detach `site_id`; tenant follows the device's governed decision. | Rows, identifiers |
| **Telephone identifiers** (…7860 / …8836 / …3349) | No change to the numbers. Their Belle Terre association becomes historical allocation evidence. Current placement comes only from the Greenwich / Yorktown decisions. | All |
| **E911 fields on the site** | Address kept as **historical intake data**. `e911_status` → not applicable (site never installed). The site then generates **zero** E911 requirements. Nothing is marked VERIFIED. | Address values |
| **E911 for the numbers (safety, first)** | **Before any True911 change:** an operator checks each number's **carrier-side E911 registration** in the T-Mobile portal and corrects it to the actual installed address (…8836 → 265 Greenwich Ave, Greenwich CT; the other two → their confirmed site). True911 never asserts this. It records the operator's check as evidence. | — |
| **Health history** | Untouched (append-only `integration_payloads`, `device_health` audit rows). The decision record states that observations on these rows from allocation onward reflect hardware at other locations. After detachment, health continues on the device rows with **no site contribution**. | All |
| **Monitoring history** | Untouched. Belle Terre contributes zero monitoring once out of current inventory. | All |
| **Registry / canonical** | If any `PortfolioBuilding` / `CommunicationsAsset` / snapshot record references Belle Terre or these identifiers, it is kept. Canonical assets get placement/lifecycle only through operator decisions (§5, §6). Snapshot records are immutable. | All |
| **Audit / provenance** | One `OperatorDecision` (deployment lifecycle, NEVER_INSTALLED; operator Stuart Manley; reason; evidence = trace output, carrier-portal checks). One reversible `AuditLogEntry` per field change, carrying before/after values (pattern of `remediate_rh_tenant_assignment.py`). | Everything |

**Execution shape (when authorized):** a dedicated script.
- Dry run by default; feature-flag + `--apply`.
- Gates:
  1. trace reviewed;
  2. carrier-side E911 checks recorded;
  3. per-device placement decision recorded or explicitly deferred;
  4. no device would be decommissioned;
  5. the predicate PR from §3 is deployed.
- Prints the exact planned changes and a confirmation hash; apply requires that hash.
- Post-write verification, then the Integrity customer view re-checked.

**Customer communication:** Integrity (IPM) users may currently see Belle Terre. Decide
whether IPM is told before it disappears from their portal.

## 5. Greenwich reconciliation (265 Greenwich Avenue)

Known:
- RH has a known special location "RH Greenwich (265)" (`KNOWN_RH_LOCATIONS`).
- The RH Greenwich registry currently maps **a different telephone number** (call it
  *X*).
- Operator truth: a repurposed Belle Terre allocation (**…8836**, LM150 serial …0227)
  was installed there.

**Do not overwrite X.** Decide which of these is true, from evidence:

| Hypothesis | Evidence that supports it | Canonical outcome |
|---|---|---|
| **A. Two elevator services** (X and …8836 both current) | X still active at T-Mobile with recent CDRs; Zoho has two elevator rows for Greenwich; operator confirms two elevators | 2 ELEVATOR services → 2 required connections; both assets CURRENT at Greenwich |
| **B. Replacement** (…8836 replaced X) | X deactivated/idle at carrier; old device at the Greenwich site stale or broken; operator confirms a swap | X → **REPLACED**, `superseded_by` …8836 (lifecycle event + operator decision); one service |
| **C. Stale / incorrect mapping** (X never belonged to Greenwich) | X attributed elsewhere by carrier/Zoho, or never active | Registry mapping `active=false` with reason (never deleted); X re-reviewed on its own |

Evidence to collect:
- The trace's Greenwich section: every Greenwich-labelled T-Mobile, Zoho, site, line,
  service-unit and snapshot record.
- The Vola org/online history for serial …0227.
- The carrier status / last CDR for X and …8836.
- **One operator answer: how many elevator phones are at 265 Greenwich Ave today?**

Outcome:
- **…8836** becomes a CURRENT asset placed at RH Greenwich, confirmed by an operator
  decision plus corroboration.
- Its tenant moves to `restoration-hardware` only through that recorded decision.
- Its **carrier E911 must read 265 Greenwich Ave** (operator-verified).

## 6. Yorktown evidence plan (the other two allocations)

Goal: establish physical placement of LM150 serials …0226 (EL1, …7860) and …0230
(EL3, …3349) without relying on the carrier label.

| # | Source | Question |
|---|---|---|
| 1 | T-Mobile (staged export, SHA-gated) | Are the two "Yorktown Elevator 1/2" subscriptions exactly …7860 and …3349? Status, last CDR |
| 2 | Zoho Subscription_Mgmnt | Which account/facility holds these numbers / ICCIDs / IMEIs / serials? |
| 3 | True911 sites / customers named Yorktown | Which tenant? Which elevators? |
| 4 | MS130 devices at those sites | Stale or broken heartbeat consistent with replacement? Serials? |
| 5 | Vola archived payloads for …0226 / …0230 | Which Vola org do they report under, since when? Online now? |
| 6 | Vola portal (operator, read-only) | Current org / site naming for the two serials |
| 7 | Call records / CDRs | Calls on …7860 / …3349 and when |
| 8 | Field records (operator) | Install date / tech / ticket for the MS130 → LM150 swap |

**Acceptance for placement:** at least **two independent sources** (e.g. Zoho + Vola org,
or Vola + field record) **plus operator confirmation**. Until then the assets stay
**placement UNRESOLVED**: detached from Belle Terre, not assigned to Yorktown. Only
after acceptance: placement decision, the MS130 being replaced gets lifecycle REPLACED,
and carrier E911 is checked for the Yorktown address.

## 7. How this feeds attribution v2

- The Belle Terre holders of …7860 / …8836 / …3349 (`integrity-pm` devices/SIMs) are
  **cancelled-allocation provenance** once D-029's NEVER_INSTALLED decision is
  recorded, not competing customer claims. Until then they remain a recorded conflict.
- The T-Mobile record for …8836 can be preserved as **RH-attributed source evidence**
  (RH brand + known Greenwich location + operator truth). Placement is decided by the
  Greenwich decision, never by the snapshot.
- The Yorktown records are preserved with whatever tenant the source credibly indicates.
  Placement stays UNRESOLVED.

## 8. Sequence (each step: dry run → review → explicit apply → verify)

1. Run the read-only production trace v2 and review it.
2. **Carrier-side E911 checks** for the three numbers. Correct them at the carrier
   where wrong (operator). This is the safety item.
3. Greenwich operator answer (number of elevator phones) → Greenwich decision.
4. Yorktown evidence → decision or explicit UNRESOLVED.
5. PR: deployment-lifecycle axis + "current inventory" predicate (read paths). Includes
   the rule that health contributes to a site only through current, confirmed placement.
6. PR: governed Belle Terre retirement script (dry run default).
7. Apply Belle Terre retirement (explicit), then verify the Integrity and RH views.
8. Attribution v2 / T-Mobile snapshot dry run again. Apply only after review.
