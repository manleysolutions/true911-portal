# Restoration Hardware — Portfolio Readiness Audit (PR #79)

**Read-only.** Explains exactly what must happen to make Restoration Hardware
(RH) customer-facing ready. Writes nothing — does **not** validate E911, create
service units, or touch any other tenant (Integrity untouched).

```bash
RH_AUDIT_TENANT=restoration-hardware python -m app.audit_rh_readiness
```

Reuses the **real** Assurance engine for the scorecard and the **device-health
classifier** for adapter/monitorability checks — so the audit can't disagree
with what the product shows.

## Portfolio at a glance (from the portfolio sweep)
| Metric | Value |
|---|---|
| customers | 1 |
| sites | 42 |
| devices | 51 |
| service_units | **0** |
| users | 2 |
| E911 verified | **0 / 42** (42 have an address) |
| Device health fresh | **0 / 51** (0 ever reported) |
| Health Score | **30 / 100** |

The 30 is exactly the ownership-only floor: ownership 20 + hygiene 10, with
**E911 (40) and device-health (30) both zero.** Those two gaps are the whole job.

## What the audit produces (per RH)
1. **Sites + E911 readiness** — each site's `e911_status`, the four address
   parts present/missing, and a readiness bucket.
2. **Devices + monitorability** — each device's model/probes/heartbeat and
   whether a current adapter can monitor it.
3. **Why device health is 0/51** — a reason tally across all devices.
4. **Service-unit gap** — recommended unit type per device (inferred, not created).
5. **Scorecard** — the six Assurance labels computed by the engine.

### E911 readiness buckets
| Bucket | Meaning | RH action |
|---|---|---|
| `verified` | already validated/verified/confirmed | none |
| `address_complete_needs_validation` | all 4 parts present, status not yet verified | **verify → set `validated`** (the expected RH majority) |
| `address_partial` | some parts missing | fill the missing parts, then verify |
| `address_missing` | no address | source the address first |

Because all 42 RH sites already carry addresses, the expected dominant bucket is
**`address_complete_needs_validation`** — i.e. the data is there; the sites just
need verification and a status move to `validated`. **The audit does not move
them.**

### Why device health is 0/51 — diagnosis logic
Each device is run through the device-health classifier; a device is
**monitorable** only when (a) an adapter recognises its class **and** (b) it
carries an identifier the adapter can key on. The audit tallies these reasons:
- **`never reported a heartbeat (last_heartbeat is NULL)`** — expected for all 51
  ("0 ever reported"). These are imported/manually-entered inventory rows.
- **`no vendor adapter recognises this device class`** — model/type/carrier not
  mapped to Vola/T-Mobile/Telnyx/etc.
- **`no vendor identifiers`** — no serial/imei/iccid/msisdn/vola_org_id to match
  a vendor account.

The tally tells you which lever to pull: enrich identifiers, map a vendor
adapter, or stand up telemetry — usually all three for an imported portfolio.

### Service-unit gap
RH has **0 service units for 51 devices**. Service units are the emergency
endpoints Assurance reasons about. The audit recommends **one emergency service
unit per device**, inferring the type (`elevator_phone`, `fire_alarm_line`,
`alarm_line`, `emergency_call_station`, `emergency_voice_line`) from model/type —
**recommendation only, nothing is created.**

### Expected scorecard
With E911 unverified on every active site, the Assurance engine classifies
active RH sites **Critical** (`ASSURANCE.E911_UNVERIFIED`); any site still in
onboarding shows **Pending Install**. So the expected shape is **mostly Critical,
some Pending Install** — not because RH is broken, but because it is unverified.
The real counts come from running the script.

---

## Remediation plan (priority order)

**P0 — E911 verification (unblocks the 40-point E911 component & most Critical labels).**
Life-safety first. Verify each site's existing address and move
`address_complete_needs_validation → validated`. ~42 sites; batchable by
building. No new data needed where the address is already complete.

**P1 — Device identity & vendor mapping (unblocks monitorability).**
Enrich each device with the identifier its vendor keys on (IMEI/ICCID/MSISDN for
cellular, serial for ATA, `vola_org_id` for Vola) and set the carrier/model so
the classifier yields a probe vendor. Without this, heartbeats can never arrive.

**P2 — Telemetry / heartbeat ingestion (unblocks the 30-point device-health component).**
Once devices are mapped, stand up the heartbeat/health sync so `last_heartbeat`
populates and freshness can be scored.

**P3 — Service units.**
Create one emergency service unit per device (use the audit's inferred types as
the starting proposal, corrected by the install records).

**P4 — Re-audit & confirm.**
Re-run the readiness audit + portfolio audit; expect the score to climb from 30
toward 100 and Critical→Protected as E911 and device health land.

## Risks
- **Compliance (highest):** 42 active sites with **unverified** dispatchable
  E911. Until verified, RH is not safely customer-facing — this is the gating risk.
- **False confidence:** verifying E911 in bulk **without** a real address check
  would mark sites `validated` that aren't — never auto-validate. Verification is
  a human/authoritative step; this audit deliberately won't do it.
- **Reachability blind spot:** 0/51 devices report, so today there is **no live
  liveness signal** for RH. An outage would be invisible until P1+P2 land.
- **Data integrity:** imported inventory may have placeholder models/identifiers;
  vendor mapping must be verified per device, not assumed from the model string.
- **Scope creep:** service-unit creation and E911 validation are separate,
  reviewed write-PRs — not part of this audit.

## Estimated effort to make RH customer-facing ready
| Phase | Work | Rough effort |
|---|---|---|
| P0 E911 verification | verify 42 addresses, set `validated` | ~1–2 days (batchable; address data already present) |
| P1 device mapping | enrich identifiers + carrier/model for 51 devices | ~1–2 days (depends on source-data quality) |
| P2 telemetry | wire heartbeat ingestion for the mapped vendors | ~2–3 days incl. verification |
| P3 service units | create ~51 units from corrected install data | ~1 day |
| P4 re-audit | re-run audits, confirm score/labels | ~0.5 day |
| **Total** | | **~1–1.5 weeks** of focused work |

## Proposed PR sequence
- **PR #79 (this):** RH readiness audit — read-only, no changes. *(done)*
- **PR #80:** RH E911 verification tool — dry-run-first; only sites already in
  `address_complete_needs_validation`; sets `validated` behind `DRY_RUN=false`
  with audit-log entries; refuses on missing address parts. *(P0)*
- **PR #81:** RH device identity & vendor-mapping importer — dry-run-first;
  backfills identifiers/carrier/model so the classifier yields probe vendors.
  *(P1)*
- **PR #82:** RH telemetry/heartbeat enablement for the mapped vendors. *(P2)*
- **PR #83:** RH service-unit creation from corrected install data —
  dry-run-first, audit-logged. *(P3)*
- **PR #84:** RH re-audit + portfolio-score confirmation. *(P4)*

Each write-PR keeps the standing rules: dry-run default, no migrations unless
unavoidable, audit trail preserved, no other tenant touched.

*Audit only — this script writes nothing.*
