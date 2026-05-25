# Health Status Audit — Why working provider integrations don't reflect in the UI

**Status:** Audit only — no code changes proposed. Awaiting plan approval before implementation.
**Branch at time of audit:** `main` (`a9df884`)
**Author:** Engineering audit (Claude Opus 4.7)
**Date:** 2026-05-25

---

## Bottom line

True911 has **four parallel "status" systems**, each maintained independently, each with its own staleness threshold, and each consulted by a different UI surface. Provider integrations (Telnyx, Verizon, Inseego, T-Mobile) write to **different fields** than the heartbeat-driven systems, so a tenant can simultaneously:

- See a site as **"Connected"** on the Sites page (reads `Site.status` — a stored string set at import time, never updated by heartbeat or provider data),
- See its devices as **"Offline"** on the Devices page (reads `Device.last_heartbeat` against a 2×-interval threshold),
- See its fleet as **"healthy"** in `compute_device_health()` (which short-circuits to healthy when `network_status` is populated — even if no heartbeat was ever received),
- See the AI Health Summary report **"5 devices with overdue heartbeat reporting"** (uses a 5-minute hard-coded `STALE_DEVICE_SECONDS=300` cutoff, the strictest in the codebase),
- Show **"Not Connected"** on the Map (reads `Site.status` directly for marker color),
- Have a perfectly healthy **Telnyx CDR stream** landing in `call_records` — which nothing in the health pipeline reads.

These surfaces are not wrong about what they read; they read **different sources of truth**. The fix is not to "wire provider X into status field Y" piecemeal — it's to introduce a single **Health Normalization Service** that fuses every signal into one canonical answer and lets the existing surfaces continue to call exactly one function.

---

## 1. The four parallel status systems

| # | System | Source field(s) | Updated by | Read by | Staleness rule |
|---|---|---|---|---|---|
| 1 | **Stored status string** | `Site.status` (`Connected` / `Attention Needed` / `Not Connected` / etc.) | Registration import (`registration_conversion.py:524`), provisioning (`provision_deploy.py:317`), manual admin action (`actions.py:149`), import decommission (`subscriber_import_engine.py:1456`). **Never updated by heartbeat or provider data.** | Sites page, Map markers, `command.py:432` (`connected_sites` count), `command.py:753-769` (system health categorization) | n/a — manual |
| 2 | **Heartbeat liveness** | `Device.last_heartbeat`, `Device.heartbeat_interval` | `heartbeat.py:37` (CSAS edge client only) | Devices page, `LLLMContext._build_fleet_snapshot()`, `compute_site_staleness()` | **Four different thresholds — see §6** |
| 3 | **Health-score "kind of healthy"** | `Device.network_status` + `Device.signal_dbm` + `Device.sip_status` + `last_network_event` | `heartbeat.py:71-75` (edge) AND `carrier_adapter.py:158-162` (Verizon polling) | `health_scoring.compute_device_health()` → consumed wherever health badges show colors | 2× interval for heartbeat, 120 min for telemetry staleness |
| 4 | **Attention engine canonical status** | Derives from `Device` row fields above | n/a (pure read-time derivation) | `attention_engine.evaluate_device()`, `evaluate_site()` — used by Command Center's IntelligenceBanner / "Attention" tiles | uses thresholds from `Device.heartbeat_interval` |

**Every one of these reads from a different ground truth, and writes (where applicable) on different triggers.** A change in the underlying field by one writer doesn't propagate to the others.

---

## 2. Data-flow diagram (current state)

```
   ┌─────────────────────────┐                                                     UI consumers
   │ CSAS edge client        │   POST /api/heartbeat                              ───────────────
   │ (the only thing that    │ ──────────────────►  heartbeat.py:28-142  ──┐      Sites page
   │  ever updates           │                       device.last_heartbeat │      Devices page
   │  Device.last_heartbeat) │                       device.network_status │      Command Center
   └─────────────────────────┘                       site.last_device_hb   │      Map markers
                                                     CommandTelemetry row  │      AI Health
                                                                           │       Summary
   ┌─────────────────────────┐                                             │
   │ Telnyx                  │   POST /api/webhooks/telnyx                 │
   │ (CDR webhooks)          │ ──────────────────►  webhooks.py:72-101 ────┤
   └─────────────────────────┘                       integration_payloads  │
                                                     call_records          │       ←━━━ NOT READ by
                                                                           │             any status
                                                                           │             surface
   ┌─────────────────────────┐                                             │
   │ Verizon ThingSpace      │   POST /api/carriers/verizon/sync           │
   │ (cellular carrier)      │ ──────────────────►  carrier_verizon.py     │
   │                         │                       sims                  │
   │                         │   POST /api/carriers/verizon/poll-telemetry │
   │                         │ ──►  carrier_adapter.py:158-179             │
   │                         │      device.network_status  ───┐            │  (compute_device_health
   │                         │      device.data_usage_mb      │            │   may return 'healthy'
   │                         │      device.last_network_event │            │   from this alone,
   │                         │      device.telemetry_source   │            │   without any heartbeat)
   │                         │      CommandTelemetry row      │            │
   └─────────────────────────┘   (writes do NOT touch last_heartbeat)      │
                                                                           │
   ┌─────────────────────────┐                                             │
   │ Inseego (VOLA TR-069)   │   POST /api/integrations/vola/devices/sync  │
   │                         │ ──────────────────►  vola_service.py:131    │       ←━━━ STATUS LIFECYCLE
   │                         │      device.firmware_version                │             ONLY — no
   │                         │      device.model                           │             telemetry, no
   │                         │      device.status:                         │             heartbeat
   │                         │        "provisioning" → "active" if online  │             update
   └─────────────────────────┘                                             │
                                                                           │
   ┌─────────────────────────┐                                             │
   │ T-Mobile (TAAP)         │   POST /tmobile/wholesale/callback/*        │
   │ (wholesale callback)    │ ──────────────────►  tmobile_callback.py    │
   │                         │      logs + 200 OK                          │       ←━━━ STUB — no
   └─────────────────────────┘   (zero state changes today)                │             writes today
                                                                           │
                                                                           ▼
                              ┌──────────────────────────────────────────────────┐
                              │  Site.status  (stored string, manual/import set) │
                              │  ───────────────────────────────────────────     │
                              │  registration_conversion.py:524: "Connected"     │
                              │  provision_deploy.py:317: "Active"/"Provisioning"│
                              │  actions.py:149: "Attention Needed"              │
                              │  subscriber_import_engine.py:1456:"Decommissioned"│
                              │                                                  │
                              │  Read by Command Center, Map, Sites, system-     │
                              │  health categorization.  NEVER recomputed from   │
                              │  device state.  Drifts indefinitely.             │
                              └──────────────────────────────────────────────────┘
```

The picture in one sentence: **The only field that actually reflects "we heard from this site recently" is `Device.last_heartbeat`, and only the CSAS edge client writes it. Every provider integration writes somewhere else.**

---

## 3. Provider ingestion — what each one actually updates

Verified against `api/app/routers/webhooks.py`, `services/telnyx_service.py`, `services/carrier_adapter.py`, `services/vola_service.py`, `routers/tmobile_callback.py`, `routers/heartbeat.py`.

| Source | `Device.last_heartbeat` | `Device.network_status` | `Device.last_network_event` | `Site.last_device_heartbeat` | `Site.status` | `CommandTelemetry` row | Raw payload table |
|---|---|---|---|---|---|---|---|
| **CSAS heartbeat** (`heartbeat.py:37,71-75,110,79-98`) | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | `telemetry_events`, `events` |
| **Telnyx webhook** (`webhooks.py:72-101`, `telnyx_service.py:205-231`) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | `integration_payloads`, `call_records` |
| **Verizon sync** (`carrier_verizon.py:279-643`) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | `sims`, `devices` (inventory), `events` |
| **Verizon poll-telemetry** (`carrier_adapter.py:158-179`) | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | — |
| **Inseego VOLA sync** (`vola_service.py:131-159`) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | `devices` (lifecycle only) |
| **T-Mobile callback** (`tmobile_callback.py:95-211`) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | — (stub, only logs) |

**Three immediate takeaways:**

1. **`Site.status` is a black hole.** No automated writer keeps it accurate. It is the import-time value forever, until a human clicks something.
2. **`Device.last_heartbeat` only knows about the CSAS edge client.** A 100% functional Verizon SIM, a steady Telnyx CDR stream, a TR-069-reachable Inseego — none of them count as "we heard from the device" for staleness purposes.
3. **`Device.network_status` IS multi-source** (heartbeat + Verizon poll), but `compute_device_health()` treats `network_status` as a sufficient signal to return `"healthy"` even when no heartbeat ever happened. That's why a never-reported Verizon device can show **"healthy" in health scoring AND "Provisioning" in continuity AND "stale" in LLM context** — the same row, three answers.

---

## 4. UI consumers — what each surface actually reads

| Surface | Endpoint | Handler | What drives status |
|---|---|---|---|
| **Command Center** (`web/src/pages/Command.jsx:888`) | `GET /api/command/summary` | `command.py:373-644` | `connected_sites = sum(1 for s in sites if s.status == "Connected")` (`command.py:432`) — **literal string match on the stored Site.status field**. Also `compute_site_staleness()` for `stale_devices` (heartbeat-based). |
| **Deployment Map** (`web/src/pages/DeploymentMap.jsx:270-272`) | `GET /api/sites?...` | `sites.py:85-148` | Marker color is `STATUS_COLORS[site.status]` (`DeploymentMap.jsx:13-18`). `compute_site_computed_status` IS computed on the response but **is not what the marker reads** — the marker reads the stored `site.status` field. |
| **Sites page** (`web/src/pages/Sites.jsx`) | `GET /api/sites?...` | `sites.py:85-148` | Same — `StatusBadge` renders `site.status` directly. |
| **Devices page** (`web/src/pages/Devices.jsx`) | `GET /api/devices` | `routers/devices.py` | Uses `compute_device_computed_status(last_heartbeat, heartbeat_interval)` (`continuity.py:15-31`) — `Provisioning` / `Online` / `Offline`. **Pure heartbeat read; ignores `network_status`, ignores any provider signal.** |
| **AI Health Summary** (`web/src/components/AIHealthSummary.jsx`) | `GET /api/llm/health-summary?scope=...` | `routers/llm.py` → `LLLMContext` (`services/llm/context.py:119-148`) | `connected_sites` = sites with any device having `last_heartbeat >= now - 300s`. `stale_devices` = active devices with `last_heartbeat is null OR < now-300s`. **The strictest threshold in the codebase.** |
| **Command Center IntelligenceBanner highlights** | (same endpoint) | `attention_engine.evaluate_device/site` | Derives canonical status (`CONNECTED | ATTENTION | OFFLINE | UNKNOWN`) from `Device` fields. Doesn't read provider tables. |

---

## 5. The "Not Connected but Healthy" contradiction — three concrete scenarios

### Scenario A — Provider says yes, edge client says nothing

A Verizon-attached cellular gateway. Verizon polling runs nightly and reports `network_status="connected"` on `Device`. The CSAS edge client hasn't been installed or has been mis-keyed, so `Device.last_heartbeat` is `NULL`.

- `Devices page`: shows **"Provisioning"** (`continuity.py:18-19`: `if last_heartbeat is None: return "Provisioning"`)
- `LLM Health Summary`: counts this device as **stale** (`context.py:140-148`: `last_heartbeat is null OR < cutoff`)
- `compute_device_health()`: returns **"healthy"** (`health_scoring.py:60-65`: `has_heartbeat=False, has_network=True` skips the `unknown` short-circuit; then `has_heartbeat=False` skips the offline check; then `network_status` is not in `DISCONNECTED_STATUSES`; signal/SIP/telemetry-staleness all skipped because their inputs are `None`; falls through to `healthy` at line 106)
- `Site.status`: still **"Connected"** from registration import — never recomputed.

Four answers, four surfaces.

### Scenario B — Telnyx CDRs flowing, edge client silent

A managed-POTS Red Tag Line site. Telnyx delivers call CDRs every few minutes; they land cleanly in `call_records`. The CSAS edge client is offline.

- `call_records`: shows healthy traffic — **but no UI reads this for status**.
- `Device.last_heartbeat`: stale → device shows **"Offline"** on Devices page.
- `LLM Summary`: counts as stale.
- `Site.status`: still "Connected" (import-time).
- Operator looks at the call log, sees Telnyx working, looks at the dashboard, sees "Offline" — and either (a) loses trust in the dashboard, or (b) opens a ghost ticket about a working line.

### Scenario C — Site.status drifts forever

A site was imported as `status="Connected"`. Six months later it's been decommissioned in the field. No one ran the decommission action. CSAS heartbeats stopped. But:

- `Sites page`: still shows **"Connected"** (the stored field never changed).
- `Map marker`: green.
- `Devices page`: every device shows **"Offline"**.
- `Command Center`: `connected_sites` count is inflated by this site (`command.py:432`); `stale_devices` count is also inflated. The "fleet is X% connected" metric is wrong on both sides.

---

## 6. Threshold drift — same field, four different rules

Every staleness check ultimately reads `Device.last_heartbeat`, but each consumer applies a different threshold:

| Service | File | Threshold | Effective default |
|---|---|---|---|
| Device "online" badge | `services/continuity.py:11-12,28-29` | `2 × heartbeat_interval` | 10 min |
| Fleet/site health score | `services/health_scoring.py:35-36,76-77` | `2 × heartbeat_interval` | 10 min |
| Automation rule "stale" gate | `services/automation_engine.py:41` | `3 × heartbeat_interval` | 15 min |
| Automation rule `heartbeat_missing` template | `services/automation_engine.py:147` | configurable, default `30 min` | 30 min |
| Telemetry-staleness warning | `services/health_scoring.py:26` | `120 min` since `last_network_event` | 120 min |
| Tenant template defaults | `services/template_engine.py:103,119,137,153,167,180` | per-tenant: 5 / 10 / 15 / 30 min | varies |
| LLM Health Summary | `services/llm/context.py:47,138-148` | `300 seconds` hard-coded | **5 min** (strictest) |

The LLM and the Devices page disagree about whether the **same device** is stale, because the LLM cuts off at 5 min and continuity gives 10 min. Different operators looking at different surfaces draw different conclusions.

---

## 7. Recommended Health Normalization Layer

### Goal

One service, one contract, one answer per device, per site. Every UI surface and every audit consumer calls the same function.

### Shape

```
api/app/services/health/
├── __init__.py              # exports compute_device_state / compute_site_state
├── normalizer.py            # the canonical function
├── signals.py               # HealthSignals dataclass — every input from every source
├── thresholds.py            # ONE place for every staleness threshold
└── states.py                # CanonicalDeviceState / CanonicalSiteState enums
```

### Inputs (`HealthSignals` — everything a single device knows)

```
HealthSignals:
    # Liveness signals — any one of these proves "we heard from this device"
    last_heartbeat_at:      datetime | None    # from heartbeat.py
    last_carrier_event_at:  datetime | None    # from carrier_adapter.py (Verizon poll)
    last_call_event_at:     datetime | None    # from call_records (Telnyx CDR)
    last_vola_sync_at:      datetime | None    # from vola_service (Inseego TR-069 reachability)

    # Provider-reported state
    network_status:         str | None         # "connected" | "disconnected" | "degraded"
    sim_status:             str | None         # carrier-reported SIM lifecycle state
    sip_status:             str | None         # registered | failed | unknown

    # Quality
    signal_dbm:             float | None
    heartbeat_interval:     int | None         # device-specific cadence

    # Lifecycle
    device_lifecycle:       str                # provisioning | active | inactive | decommissioned
```

### Output (one of these, period)

```
CanonicalDeviceState:
    CONNECTED        # any liveness signal within fresh threshold AND no critical degradation
    ATTENTION        # liveness ok but signal/sip/network degraded, OR stale on one path but fresh on another
    OFFLINE          # no liveness signal within stale threshold across ANY source
    PROVISIONING     # device known but never reported on any channel
    UNKNOWN          # no device row / inconsistent state
    DECOMMISSIONED   # explicit lifecycle terminal
```

`CanonicalSiteState` is the aggregation rule from `evaluate_site` (already in `attention_engine.py:453-558`), just rooted on the new device state.

### Derivation rule (the entire algorithm)

```
last_observed_at = max(
    last_heartbeat_at,
    last_carrier_event_at,
    last_call_event_at,
    last_vola_sync_at,
)

if lifecycle == "decommissioned": return DECOMMISSIONED
if last_observed_at is None:      return PROVISIONING
if now - last_observed_at > STALE_THRESHOLD:
    if network_status in DISCONNECTED_VALUES: return OFFLINE
    return OFFLINE   # truly nothing recent

# fresh on at least one source
if network_status in DISCONNECTED_VALUES:  return ATTENTION
if signal_dbm and signal_dbm <= SIGNAL_CRITICAL: return ATTENTION
if sip_status in SIP_DEGRADED_VALUES:      return ATTENTION
return CONNECTED
```

### Wins

- **One threshold** in `thresholds.py`. The five-way drift in §6 collapses to one value (per category).
- **Provider data finally counts toward liveness.** A Telnyx CDR or a fresh Verizon poll is treated as "we heard from this site" exactly like a heartbeat.
- **`Site.status` becomes a deprecated mirror, computed on read.** New writers stop touching it; old writers continue working unchanged; readers transparently switch to the computed value.
- **The audit story improves.** When a surface disagrees with what an operator sees in Verizon's console, we can show the exact `HealthSignals` that fed the decision.

---

## 8. Smallest safe MVP fix (no schema change, no behavior change for any tenant who doesn't opt in)

The full normalization layer is the destination; the **smallest production-safe step** is much smaller. Three commits, no migration, fully reversible.

### MVP commit 1 — new pure-logic module, no callsite touched

Add `api/app/services/health/` with:
- `signals.py` (the `HealthSignals` dataclass)
- `normalizer.py` (`compute_device_state(signals: HealthSignals) -> CanonicalDeviceState`)
- `thresholds.py` (one place; initial values copied from the existing `2 × interval`)
- `states.py` (the enum)
- `tests/` covering every branch in the algorithm with no mocks

At this point **nothing reads it**. Risk: zero. Reviewable as a self-contained module.

### MVP commit 2 — `signals_loader.py` reads existing tables, no writes

Add `api/app/services/health/signals_loader.py` exposing `load_signals_for_device(db, device, tenant_id) -> HealthSignals`. It:
- Reads `Device.last_heartbeat`, `Device.network_status`, `Device.signal_dbm`, etc. (already populated)
- Reads `Device.last_network_event` (already populated by Verizon poll)
- Looks up `MAX(call_records.started_at)` for the device's `line_id` set (new read, no write — this is the Telnyx liveness signal we currently throw away)
- Looks up `Device.vola_last_sync` if present (already populated by VOLA sync)
- Returns `HealthSignals`

Add an opt-in feature flag `FEATURE_HEALTH_NORMALIZER=false` (default off). Zero callsites yet. Tests verify the loader returns the same signals an operator can verify by hand against the DB.

### MVP commit 3 — one read-only surface adopts it behind the flag

The **AI Health Summary** is the right first consumer because:
- Internal-only (Phase 1 LLLM)
- Already governed by its own feature flag
- Its current 5-min hard-coded threshold is the most surprising surface
- Operators will immediately notice when it disagrees with continuity less often

Change `LLLMContext._build_fleet_snapshot` to, when `FEATURE_HEALTH_NORMALIZER=true`, call `compute_device_state(load_signals_for_device(...))` and roll up from canonical states instead of counting `last_heartbeat < cutoff`.

When `FEATURE_HEALTH_NORMALIZER=false`, behavior is exactly as today.

### What we explicitly do NOT do in the MVP

- ❌ No schema change. No `last_observed_at` column. We compute it.
- ❌ No `Site.status` migration. We do not stop writing it, we do not auto-recompute it.
- ❌ No change to `compute_device_computed_status()` (Devices page) — its 2× threshold stays the default. Phase 2 will route it through the normalizer behind the same flag.
- ❌ No change to Command Center `connected_sites` count — Phase 2.
- ❌ No change to Map marker source — Phase 2.
- ❌ No new writes to `Device.last_heartbeat` from provider paths. The normalizer reads provider tables directly; no field gets overloaded.
- ❌ No edge runtime / CSAS change.
- ❌ No touch to E911, provisioning, call routing, or customer records — per the constraint.

### Rollback

`FEATURE_HEALTH_NORMALIZER=false` and restart. The new code stays in the repo but is dormant.

---

## 9. Phased roadmap for the full layer (post-MVP)

| Phase | Goal | Surface migrated | Risk |
|---|---|---|---|
| **MVP** | Module + loader + AI Health Summary adopts behind flag | AI Health Summary | low — internal-only |
| **N1** | Devices page reads `CanonicalDeviceState` via the normalizer | Devices page | low — read-only, additive endpoint param `?compute=v2` |
| **N2** | Command Center `compute_site_staleness` and `connected_sites` route through normalizer | Command Center | medium — high-visibility surface, soak required |
| **N3** | Map markers + Sites status badge route through normalizer | Map, Sites | medium |
| **N4** | `attention_engine.evaluate_device/site` consumes `HealthSignals` instead of raw fields | Attention engine | medium |
| **N5** | One threshold table in `thresholds.py` becomes per-tenant overrideable; templates in `template_engine.py` migrate | Automation engine | medium |
| **N6** | Decide on `Site.status` — either deprecate (always computed) or auto-recompute via a background job | Sites schema | requires governance call |

Each phase ships behind the same flag and can be rolled back independently. Existing per-tenant behavior is preserved by default.

---

## 10. Constraints honored

- ✅ No code changes proposed yet — this is an audit only.
- ✅ Recommended changes are additive: new package, new flag, new computed values; no schema change, no field overloading.
- ✅ No touch to E911 (`e911.py`, `e911_change_log`).
- ✅ No touch to provisioning (`provisioning.py`, `provision_deploy.py`, `vola.py` deploy paths).
- ✅ No touch to call routing (Telnyx webhook handler, `call_records` writes).
- ✅ No touch to customer records (`customers.py`, `Customer` model).
- ✅ Fully reversible via feature flag.
- ✅ Reuses the existing `attention_engine.py` algorithm — the new layer is a refinement, not a replacement.

---

## Appendix A — Exact file:line references cited

Backend ingestion:
- `api/app/routers/heartbeat.py:28-142,37,71-75,79-98,110` — only writer of `Device.last_heartbeat`, `Site.last_device_heartbeat`
- `api/app/routers/webhooks.py:72-101`, `api/app/services/telnyx_service.py:58-99,205-231` — Telnyx ingestion, CDR-only
- `api/app/routers/carrier_verizon.py:279-643,680-699`, `api/app/services/carrier_adapter.py:158-179` — Verizon writes `network_status`, `last_network_event`, `CommandTelemetry`
- `api/app/routers/vola.py:250-272`, `api/app/services/vola_service.py:131-159,245,410` — Inseego TR-069 (lifecycle only, no telemetry)
- `api/app/routers/tmobile_callback.py:95-211` — stub endpoints, no writes

UI consumers:
- `web/src/pages/Command.jsx:888` → `api/app/routers/command.py:373-644` (esp. `:432,490-502,524,528-533,576,753-769`)
- `web/src/pages/DeploymentMap.jsx:13-18,76,270-272` → `api/app/routers/sites.py:85-148`
- `web/src/pages/Sites.jsx`, `web/src/pages/SiteDetail.jsx` → same as Map
- `web/src/pages/Devices.jsx` → `api/app/routers/devices.py` → `api/app/services/continuity.py:15-52`
- `web/src/components/AIHealthSummary.jsx` → `api/app/routers/llm.py` → `api/app/services/llm/context.py:47,119-148`

Status derivation services:
- `api/app/services/continuity.py:11-52` — `compute_device_computed_status`, `compute_site_computed_status` (2× threshold)
- `api/app/services/health_scoring.py:26,35-36,39-106` — `compute_device_health` (the "healthy without heartbeat" bug)
- `api/app/services/attention_engine.py:30-116,312-446,453-558,666-681` — canonical status enum + per-device/per-site evaluation
- `api/app/services/command_intelligence.py:204-272` — `compute_readiness_breakdown`
- `api/app/services/automation_engine.py:28-53,145-157,247` — 3×/30-min/120-min thresholds

`Site.status` writers (all of them):
- `api/app/services/registration_conversion.py:524` — `"Connected"` on import
- `api/app/services/provision_deploy.py:317` — `"Active"`/`"Provisioning"` post-provisioning
- `api/app/routers/actions.py:149` — `"Attention Needed"` on manual admin action
- `api/app/services/subscriber_import_engine.py:1456` — `"Decommissioned"` on import merge
- *(no other writer in the codebase)*

`Device.network_status` writers:
- `api/app/routers/heartbeat.py:71-75` — from CSAS
- `api/app/services/carrier_adapter.py:158-162` — from Verizon polling

`Device.last_heartbeat` writers:
- `api/app/routers/heartbeat.py:37` — **only one**

---

*End of audit. Awaiting approval before any implementation work.*
