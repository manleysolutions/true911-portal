# RH Telemetry / Heartbeat Ingestion (PR #83)

**P2** of the RH readiness plan (`docs/RH_READINESS_AUDIT.md`). PR #81 made RH
devices *monitorable* by backfilling vendor identity; **identity alone does not
create liveness.** This command asks the configured vendor adapters for **real**
status and persists fresh heartbeat/liveness onto the mapped RH devices.

> The objective is **trustworthy liveness, not making devices look online.** It
> never fabricates a heartbeat, never moves a timestamp backwards, and never
> touches E911, device status, or any Assurance label.

It **reuses** the generic probe + update logic in `app.sync_device_health` (one
place owns vendor interpretation) and adds two RH-specific things: a per-device
**telemetry-readiness report** and a **staleness guard**.

## Expected workflow after #81
1. `#80` — verify E911 (P0).
2. `#81` — backfill device identity so devices classify to a vendor (P1).
3. **`#83` (this)** — ingest real telemetry for the mapped vendors (P2).
4. Devices with no automated source → record a **manual** verification test
   (`app.record_verification_test`, PR #73).

## Commands
```bash
# Dry run — prints the readiness report + proposed updates, writes nothing:
python -m app.sync_rh_device_telemetry

# Apply (telemetry fields only):
DRY_RUN=false python -m app.sync_rh_device_telemetry

# Scope override (confirm the slug in Admin → Tenants):
RH_TELEMETRY_TENANT=restoration-hardware python -m app.sync_rh_device_telemetry
```

## Telemetry readiness classes
| Class | Meaning | Next step |
|---|---|---|
| `ready` | a configured **live** adapter (Vola/T-Mobile) applies **and** the device has the identifier it keys on | probe persists a real heartbeat |
| `telemetry_pending` | a live adapter applies but is **unconfigured** / missing identifier, **or** the vendor adapter is a not-yet-implemented stub (Telnyx/Inseego/Cisco ATA/MS130) | configure creds / finish adapter; liveness may also arrive via callbacks/CDR |
| `manual_verification_required` | no automated liveness source for this device class | record a real test via `app.record_verification_test` |
| `unmapped` | no vendor adapter — identity not backfilled | run `app.backfill_rh_device_identity` (#81) first |

## What it writes (apply only)
A **whitelist** of telemetry columns — nothing else is writable here:
`last_heartbeat`, `network_status`, `last_network_event`, `vola_last_sync`,
`firmware_version`, `wan_ip`. Each changed device gets one `audit_log` entry
(category `device_health`, action `rh_telemetry_sync`) recording the field
changes, stale-skip notes, and vendors. Raw vendor payloads are archived to
`integration_payloads` (append-only) — **never printed and never on a customer
surface**.

### Staleness guard
For `last_heartbeat` / `last_network_event` / `vola_last_sync`, an update is
applied **only if it is newer** than what's stored. A vendor reporting an old
`last_seen` cannot move a device's heartbeat backwards (it is logged as
`skipped stale …`). Non-timestamp fields (status/firmware/IP) pass through.

## Vendor credential requirements
| Vendor | Live probe needs | Identifier |
|---|---|---|
| **Vola** | `VOLA_EMAIL` + `VOLA_PASSWORD` | `serial_number` (or `imei`) |
| **T-Mobile** | TAAP consumer key/secret + RSA key (PoP) | `msisdn` (primary) — otherwise relies on callback ingest |
| Telnyx / Inseego / Cisco ATA / MS130 | live probe **not implemented** (stubs) | liveness via call records / callbacks where present |

Missing credentials are reported per device as `telemetry_pending` and logged as
`MISSING_CREDENTIALS` — the batch never fails on a single unconfigured vendor.

## Rollback
- **Dry run** writes nothing — nothing to roll back.
- **Apply** only advances telemetry timestamps/state; it never deletes and never
  touches identity/E911/status. To neutralise a bad sync, re-run after fixing the
  vendor data — the staleness guard prevents regressions, and the prior values
  remain in the `audit_log` detail. (No migration, so no schema rollback.)

## Risk assessment
- **Looking-online-without-being-online** — mitigated: only a vendor's real
  `last_seen` is written; `vola_last_sync` is only refreshed when the device is
  actually `ONLINE`; no fabricated heartbeats.
- **Stale overwrite** — mitigated by the staleness guard.
- **Scope creep into E911/Assurance/status** — mitigated by the write whitelist.
- **Partial fleet** — a missing/erroring vendor degrades to `telemetry_pending`
  and is logged; the batch continues.

## How this improves the RH portfolio score
The score's **device-health (30 pts)** component is `devices_fresh / devices`.
Once `ready` devices report, their `last_heartbeat` becomes fresh and the
component rises from 0 toward 30 — combined with E911 verification (#80, the 40-pt
component), RH climbs off the 30 floor toward Protected.

## Known gaps / what remains after #83
- **Telnyx/Inseego/Cisco ATA/MS130 live probes are stubs** — those devices stay
  `telemetry_pending` until each adapter is implemented (or liveness is taken
  from call records / callbacks).
- **T-Mobile** liveness leans on the existing callback ingest unless TAAP creds
  are present and an `msisdn` is mapped.
- **Manual-only devices** need a recorded verification test; this tool will not
  auto-create one.
- A scheduled run (cron) for continuous freshness is a follow-up, not part of
  this PR.

## Migration impact
**None.** Writes only existing Device/SIM columns.

## Tests
`tests/test_sync_rh_device_telemetry.py` — readiness classification (ready /
pending / manual / unmapped), identifier rules, the staleness guard (stale vendor
data does **not** overwrite fresh DB data; fresher data does), the write
whitelist (E911/status not writable), and that the safe report excludes raw
vendor payloads. Full backend suite passes; health surface-containment guard
green.
