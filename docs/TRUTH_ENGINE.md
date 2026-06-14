# True911+ — TRUTH ENGINE

> The identity & normalization subsystem that ensures every record resolves to one
> authoritative place in the canonical hierarchy (`DATA_MODEL.md`) before any write.
> This document captures designs previously held only in conversation, per
> `CONSTITUTION.md` P3 (No Conversation Dependency).
>
> **Status: DESIGNED — not yet implemented.** First slice (read-only Identity
> Resolution Audit) is planned; nothing here changes runtime behavior until built
> behind `FEATURE_TRUTH_ENGINE` (default off).

| Metadata | |
|---|---|
| **Authority Level** | 2 — Architecture (canonical, subsystem) |
| **Owner** | Principal Architect |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Medium–High (during build) |
| **Governed By** | `CONSTITUTION.md` (§4.8 one identity, §5 P5), `DATA_MODEL.md` |
| **Detailed In** | `api/app/services/identity/*` (when built), `SCREEN_BY_SCREEN_SPEC.md` (Data Health Console) |
| **Related Decisions** | `DECISIONS.md` → D-007 (read-only-first), D-011 (PR-1 scope) |

---

## 1. Purpose

There is no single identity authority today: each integration matches and writes on
its own (T-Mobile by ICCID/MSISDN, NAPCO by serial, Verizon via adapter, Zoho via
account map). Dirty or ambiguous keys cause data to land on the wrong object — or
nowhere. The Truth Engine resolves identity **once, authoritatively, before any
write**, so the Assurance/health engine can label genuinely-healthy devices green
and the portal reflects reality (`PRODUCT_VISION.md` North Star).

~40% already exists, scattered: crosswalk models (`external_record_map`,
`external_customer_map`, `external_subscription_map`, `reconciliation_snapshot`),
per-vendor matching (`carrier_adapter`, device-health adapters), an append-only
event log + RQ queue. The Truth Engine **consolidates** these.

## 2. Goals

- Resolve every record into the canonical hierarchy `Tenant → Customer → Site →
  Service Unit → Device → SIM → MSISDN → E911` with one authoritative identity.
- Make the resolution **deterministic and explainable** (reason codes + confidence).
- **Measure** the resolution gap (read-only audit) before changing any behavior.
- Give the Data Steward a single, low-input workstation (Data Health Console).
- Be the single normalization point every integration writes through.

## 3. Non-Goals

- **Not** a UI, an AI feature, or an autonomous writer of life-safety state.
- **Not** a heuristic guesser — ambiguous input is queued, never auto-resolved.
- **Not** an event bus (deferred — `DECISIONS.md` D-007); the tail stays RQ +
  read-time composition until write-time resolution is proven.
- **Not** in scope for the first slice: writes, migrations, frontend, automation.

## 4. Invariants

- **One authoritative identity per object** (`CONSTITUTION.md` §4.8).
- **Never guess** — only confident, deterministic matches resolve.
- **Read-only first** — resolve-and-report before resolve-and-write (D-007).
- **Separate axes never collapse** (`DATA_MODEL.md`, D-006); resolution composes,
  it never overwrites another axis.
- **Pure core** — the resolver does no I/O, takes an injected clock, never mutates
  its inputs.
- **Flag-gated** — all behavior behind `FEATURE_TRUTH_ENGINE` (default off); 404
  when off.

## 5. Inputs

- A subject record — primary subject is the **Device** (the object that turns
  green); secondary tallies cover unassigned/orphan SIMs.
- Pre-loaded read-only lookups (built by the audit loader, one bounded query each):
  `sims_by_iccid`, `sims_by_msisdn`, `sites_by_id`, `customers_by_id`,
  `service_units_by_device`, `external_map_by_device`.
- An injected clock (`now`).
- *(Future)* a normalized integration record (`NormalizedRecord`) from any of:
  T-Mobile, NAPCO, Zoho, Verizon, Telnyx, Vola/PR12.

## 6. Outputs

`HierarchyResolution` (pure, frozen):

```
status            "resolved" | "ambiguous" | "orphan"
tenant_id, customer_id, site_id, service_unit_id,
device_id, sim_iccid, msisdn, e911_present
confidence        0.0 – 1.0
match_basis       e.g. ("ICCID","SITE_FK","CUSTOMER_FK")
reason_codes      IDENTITY.* (machine-stable)
```

**Status rules:** *resolved* — tenant + site + customer present and unambiguous,
cellular ⇒ SIM matched (E911 / Service Unit absence are *gaps*, not orphan-makers);
*ambiguous* — a key matches >1 candidate or contradictory links; *orphan* — missing
a required link (no site / no customer / cellular-no-SIM).

The **Identity Audit** aggregates resolutions into:
`totals` (resolved/ambiguous/orphan + resolution_rate) · `by_reason` ·
`by_match_basis` · `gaps` (missing_customer/site/e911, missing_sim_cellular,
missing_msisdn, unmatched_iccid, unknown_carrier, orphan_devices, unassigned_sims,
duplicate_iccid, duplicate_msisdn) · bounded `samples` (SuperAdmin-only, id-level).
Surface: `GET /api/data-health/identity-audit`, flag-gated 404, SuperAdmin
(`GLOBAL_ADMIN`), read-only. PR plan: `DECISIONS.md` D-011.

## 7. Resolution Order (first confident match wins; NEVER guess)

1. **ICCID** (globally unique on `sims`) — confidence 1.0, basis `ICCID`.
2. **IMEI / serial** — 0.9, basis `IMEI`/`SERIAL`.
3. **MSISDN** — 0.8, basis `MSISDN`; **>1 match → `ambiguous`**
   (`IDENTITY.AMBIGUOUS_MSISDN`).
4. **`external_record_map`** confirmed link — 0.7, basis `EXTERNAL_MAP`.
5. **customer + site heuristic** — **never auto-applied**; emits
   `IDENTITY.HEURISTIC_SUGGESTED` for steward approval only.

## 8. Confidence Rules

- Confidence is set by the match basis (1.0 ICCID → 0.7 external map); it is not
  additive and not shown to customers.
- A contradiction (e.g. ICCID-matched SIM on a different site) **caps status at
  `ambiguous`** regardless of basis confidence → `AMBIGUOUS_ICCID_SITE_MISMATCH`.
- Heuristic matches carry confidence below the auto-resolve threshold by definition
  → they never set `resolved`.
- Confidence is for ranking the steward queue, not for asserting green.

## 9. Reason Codes (`IDENTITY.*` namespace)

`RESOLVED_ICCID | RESOLVED_IMEI | RESOLVED_MSISDN | RESOLVED_EXTERNAL_MAP` ·
`MISSING_SITE | MISSING_CUSTOMER | MISSING_SIM | MISSING_MSISDN | MISSING_E911 |
MISSING_SERVICE_UNIT` ·
`AMBIGUOUS_MSISDN | AMBIGUOUS_ICCID_SITE_MISMATCH` ·
`ORPHAN_NO_SITE | ORPHAN_NO_CUSTOMER | ORPHAN_CELLULAR_NO_SIM` ·
`UNKNOWN_CARRIER | UNMATCHED_ICCID` · `HEURISTIC_SUGGESTED`.
Each code carries `severity`, `description`, and `steward_action`. Customer-facing
text is never the raw code (`GLOSSARY.md` → Reason Code).

## 10. Steward Workflow

```
Import → Validate → Reconcile → Approve → Publish
```

The Data Steward (Sivmey) operates the engine via the Data Health Console (panels:
Data Health Score, duplicate devices/SIMs, missing customer/site/E911, unknown
carrier, unmatched ICCID, orphan/unassigned devices & SIMs, import failures, last
sync by provider, items needing approval) and the existing `audit_*` / `plan_*`
(dry-run-first) tools — owning data trustworthiness, leaving the portal greener
daily. She does not approve life-safety state changes outside the gated planners,
and does not do cosmetic work before data is green. Process discipline lives in
`OPERATING_LOOP.md`; console UI in `SCREEN_BY_SCREEN_SPEC.md`.

## 11. Operation Green Dashboard — success criteria

≥99% of live devices resolve to a complete chain; **orphans = 0** steady-state;
≥95% of genuinely-healthy devices auto-green; **0%** green while a hard gate
(E911/offline/suspended) fails; Data Health Score trends up; per-provider sync
freshness visible; whole pipeline flag-gated/reversible. Metrics:
`PRODUCT_VISION.md` (North Star).

## 12. Safety, Flags, Rollback

- All behavior gated by `FEATURE_TRUTH_ENGINE` (default off); endpoints 404 when off
  (matches `FEATURE_ASSURANCE_ENGINE` / `FEATURE_LLLM`).
- Read-only first (D-007): resolve-and-report before resolve-and-write.
- Per `CONSTITUTION.md` P5, build in smallest safe slices (PR-1 = pure resolver +
  read-only audit; no writes, no migration, no frontend).

## 13. Future Enhancements

- **Write-time resolution** — wire the resolver into integration write paths
  (shadow → enabled), one integration at a time, old path retained until verified.
- **Normalize all six integrations** through the resolver: T-Mobile, NAPCO, Zoho,
  Verizon, Telnyx, Vola/PR12.
- **Event fan-out / bus** — push updates to Device → Site → Customer → Dashboard →
  AI → Alerts → Reports once write-time resolution is proven (D-007).
- **Per-device-class thresholds**, confidence-tuning from steward feedback, and an
  approvals audit trail for heuristic resolutions.
- Sequencing for all of the above lives in `MASTER_PLAN.md`.
