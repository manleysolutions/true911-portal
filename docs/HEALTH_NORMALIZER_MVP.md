# Health Normalizer MVP

**Status:** Implemented behind `FEATURE_HEALTH_NORMALIZER=false` (default off). PR is a no-op deploy until the flag is flipped.
**Branch:** `feat/health-normalizer-mvp`
**Date:** 2026-05-25
**Companion docs:** `docs/HEALTH_STATUS_AUDIT.md` (the architecture audit that justified this MVP), `docs/AI_OPERATIONAL_SAFETY.md` (the governance contract for AI surfaces).

---

## What this PR ships

The **smallest safe MVP** of the Health Normalization Layer described in `HEALTH_STATUS_AUDIT.md` §7. A single new pure-logic package (`api/app/services/health/`) plus a flag-gated branch in the AI Health Summary's data loader. Nothing else is touched.

### One sentence

A new `compute_device_state` / `compute_site_state` reads heartbeat + carrier event + Telnyx CDR + VOLA sync timestamps together and returns one canonical state, replacing the heartbeat-only logic in the AI Health Summary when the flag is on.

### File-level summary

| Path | Status | Purpose |
|---|---|---|
| `api/app/services/health/__init__.py` | new | Public surface of the package |
| `api/app/services/health/states.py` | new | `CanonicalDeviceState` / `CanonicalSiteState` enums |
| `api/app/services/health/signals.py` | new | `HealthSignals` dataclass + `last_observed_at()` helper |
| `api/app/services/health/thresholds.py` | new | The one place every threshold lives |
| `api/app/services/health/normalizer.py` | new | `compute_device_state` + `compute_site_state` (pure logic) |
| `api/app/services/health/signals_loader.py` | new | Read-only loader (two bulk queries per call) |
| `api/app/services/llm/context.py` | modified | Flag-gated branch into the normalizer |
| `api/app/config.py` | modified | `FEATURE_HEALTH_NORMALIZER='false'` (default) |
| `api/tests/test_health_normalizer.py` | new | 35 unit tests |
| `api/tests/test_health_signals_loader.py` | new | 12 loader tests |
| `api/tests/test_health_normalizer_integration.py` | new | 12 integration tests, incl. surface-containment guards |
| `docs/HEALTH_STATUS_AUDIT.md` | new (untracked → committed) | The Phase 0 audit |
| `docs/HEALTH_NORMALIZER_MVP.md` | new (this doc) | What was done, what was not, rollout |
| `scripts/lllm_phase1a_smoke.ps1` | new (untracked → committed) | Pre-existing LLLM smoke recipe |

**Total tests after this PR: 1443 pass (baseline 1384 + 59 new), zero regressions.**

---

## What is intentionally NOT changed

Per the user's MVP scope directive, **only the AI Health Summary's data preparation layer** consults the normalizer. Every other surface continues to use its existing logic:

- ❌ **Command Center** (`web/src/pages/Command.jsx`, `api/app/routers/command.py`) — unchanged. Still reads `Site.status` literal and `compute_site_staleness`.
- ❌ **Deployment Map** (`web/src/pages/DeploymentMap.jsx`) — unchanged. Still reads `Site.status` for marker color.
- ❌ **Sites page** (`web/src/pages/Sites.jsx`, `api/app/routers/sites.py`) — unchanged. Still reads `Site.status`.
- ❌ **Devices page** (`web/src/pages/Devices.jsx`, `api/app/routers/devices.py`) — unchanged. Still uses `compute_device_computed_status` with `2 × heartbeat_interval`.
- ❌ **Attention engine** (`api/app/services/attention_engine.py`) — unchanged. Still owns `CanonicalStatus` for Command Center.
- ❌ **Customer portal** (`web/src/pages/UserDashboard.jsx`, customer-facing surfaces) — unchanged. Customer-tenant Admins already cannot reach the AI Health Summary (internal-only gate in `app/routers/llm.py`).
- ❌ **`Site.status` writers** — unchanged. The four manual writers (`registration_conversion.py:524`, `provision_deploy.py:317`, `actions.py:149`, `subscriber_import_engine.py:1456`) keep operating as before.
- ❌ **`Device.last_heartbeat` writers** — unchanged. Only `heartbeat.py:37` writes it. **The normalizer does NOT overload this field from provider data** — provider liveness is computed at read time, never persisted.
- ❌ **Schema** — no new column, no new table, no migration.
- ❌ **E911 / provisioning / call routing / customer records** — untouched per the user's constraint list.
- ❌ **CSAS edge / local-model work** — out of scope.

This containment is enforced by a test (`test_command_map_sites_devices_attention_do_not_import_health_package`) that grep-greps the codebase for any other file importing `app.services.health` and fails the PR if the allowlist is widened.

---

## Feature-flag behavior

```yaml
FEATURE_HEALTH_NORMALIZER: "false"   # default
```

| Flag value | AI Health Summary derivation | Other surfaces | Behavior diff vs. pre-MVP |
|---|---|---|---|
| `"false"` (default) | Legacy `_load_*_legacy()` — heartbeat-only | Unchanged | **None.** This PR is a true no-op deploy. |
| `"true"` | Normalized `_load_*_normalized()` — uses Health Normalization Layer | Unchanged | AI Health Summary counts fresh Telnyx / Verizon / Inseego liveness as CONNECTED instead of stale. `sources_used` shows the new evidence trail and the `health_normalizer:v1` tag. |
| anything else (`"yes"`, `"1"`, `""`) | Legacy (treated as off) | Unchanged | Same as `"false"`. Whitespace tolerated (`"True "` → on). |

The flag-on path produces the SAME `HealthSummaryResponse` shape as the flag-off path. The orchestrator (`app/services/llm/orchestrator.py`), the prompt template, the validator, and the audit row schema are unaffected by which path ran — only the underlying counts and `sources_used` array differ.

---

## Algorithm spec (executable)

The full algorithm is implemented in `compute_device_state` (`api/app/services/health/normalizer.py:46-83`) and tested in `api/tests/test_health_normalizer.py`. The spec, in first-match-wins order:

```
1. lifecycle ∈ {decommissioned, retired}      → DECOMMISSIONED
2. lifecycle == inactive                       → OFFLINE
3. no liveness signal on ANY channel           → PROVISIONING
4. max(heartbeat, carrier, call, vola) older than
   STALE_OBSERVATION_SECONDS (300s today)      → OFFLINE
5. fresh liveness + degradation indicator
   (network_status ∈ disconnected set,
    signal ≤ SIGNAL_CRITICAL_DBM,
    sip_status ∈ degraded set)                 → ATTENTION
6. otherwise                                    → CONNECTED
```

Site rollup (`compute_site_state`):

```
no devices                                      → UNKNOWN
all DECOMMISSIONED                              → DECOMMISSIONED
(excluding DECOMMISSIONED:)
  all CONNECTED                                 → CONNECTED
  all OFFLINE                                   → OFFLINE
  all PROVISIONING                              → PROVISIONING
  any mix                                       → ATTENTION
```

**Correctness properties asserted by tests:**

- Fails OPEN on unknown vendor strings — a `network_status` the thresholds table hasn't enumerated is NOT treated as degraded. Rolling out a new carrier won't break health reporting until `thresholds.py` gets patched.
- Stale liveness OVERRIDES degradation — a stale `"connected"` signal is still OFFLINE.
- MAX across channels — a fresh Telnyx CDR makes a device with an ancient heartbeat CONNECTED. **This is the headline regression fix.**
- Naive datetimes coerced to UTC — defense against ORM cold paths losing tzinfo.

---

## Thresholds

All in `api/app/services/health/thresholds.py`:

| Constant | Value | Rationale |
|---|---|---|
| `STALE_OBSERVATION_SECONDS` | `300` (5 min) | **Inherits the AI Health Summary's existing threshold** so flipping the flag on for the FIRST consumer keeps behavior consistent. Phase N1 (Devices page migration) may revisit. |
| `DISCONNECTED_NETWORK_STATUSES` | `{disconnected, offline, down, not_connected, not connected, unreachable}` | Conservative — anything we can't read literally is fail-open. |
| `DEGRADED_SIP_STATUSES` | `{unregistered, failed, timeout, error}` | Reserved — MVP loader doesn't populate `sip_status` yet. |
| `SIGNAL_CRITICAL_DBM` | `-110.0` | Mirrors `services/health_scoring.py`. Reserved — MVP loader doesn't populate `signal_dbm` yet. |
| `SIGNAL_WARNING_DBM` | `-100.0` | Reserved — same reason. |
| `TERMINAL_LIFECYCLE` | `{decommissioned, retired}` | Operator-action terminal. |
| `INACTIVE_LIFECYCLE` | `{inactive}` | Reported as OFFLINE. |
| `PROVISIONING_LIFECYCLE` | `{provisioning, pending, new}` | Reported as PROVISIONING when no signal. |

When the rollout reaches Phase N1 / N2, the threshold-drift table from `HEALTH_STATUS_AUDIT.md §6` converges to this one file.

---

## MVP gaps (documented, not bugs)

These are known limitations that the MVP deliberately accepts to keep the surface small. Each is reversible by a follow-up commit and doesn't require a schema change.

1. **`signal_dbm` and `sip_status` are not populated by the MVP loader.** Those values live in `CommandTelemetry.metadata_json`, not on `Device` rows. A follow-up commit can read the most recent `CommandTelemetry` row per device and populate them. Until then, the signal/SIP branches of the algorithm are dormant (tested but unreached in production). Tested explicitly by `test_signal_dbm_and_sip_status_are_none_in_mvp`.

2. **Site site-id mapping requires an extra small projection query** in `_load_fleet_normalized` (`SELECT device_id, site_id FROM devices WHERE tenant_id=?`) on top of the loader's own device query. Total queries per fleet load are comparable to the legacy path (7 vs 7). Can be folded into one query if it shows up in profiling.

3. **CDRs with `device_id IS NULL` are ignored.** Telnyx ingestion sometimes can't match a CDR to a device (no matching DID, etc.). Those rows are correctly excluded from the Telnyx liveness signal — the audit row's `sources_used` references `MAX(call_records.started_at) per device_id`, so missing-device CDRs were never intended to count.

4. **Per-tenant override is platform-wide for now.** The flag is global. A future per-tenant `ai_enabled` field on `Tenant` (Phase 3 of the LLLM roadmap) would also gate the normalizer per tenant.

---

## Tests (59 new, 1443 total)

### Unit (`api/tests/test_health_normalizer.py` — 35)

- `TestDeviceLifecycleTerminals` (3) — terminal/inactive beats freshness
- `TestDeviceProvisioning` (3) — no-signal cases
- `TestSingleChannelLiveness` (4) — each of heartbeat / carrier / telnyx / vola alone is sufficient — covers the audit doc's Scenario A and B regressions
- `TestStaleness` (4) — threshold boundary, MAX rule, all-channels-stale
- `TestDegradation` (9) — network / signal / SIP each; fail-open on unknown strings; stale beats degraded
- `TestNaiveTimestamps` (1) — defensive: naive datetimes coerced to UTC
- `TestSiteRollup` (11) — full truth table + parametric "mixed" set

### Loader (`api/tests/test_health_signals_loader.py` — 12)

- Empty tenant → empty dict, single round-trip (Q2 skipped)
- One `HealthSignals` per device
- Each liveness channel propagates correctly (heartbeat, last_network_event, call_records MAX, vola_last_sync)
- Defensive `getattr` survives missing optional columns
- Lifecycle null falls back to `"active"`
- `signal_dbm` / `sip_status` explicitly None (MVP gap as test)
- 50-device fleet still issues only TWO round-trips (the O(1) guarantee)
- `load_signals_for_site` scopes by site_id + tenant_id

### Integration (`api/tests/test_health_normalizer_integration.py` — 12)

- `TestFlagRouting` (5) — flag on routes normalized, flag off routes legacy; whitespace/case variations
- `TestSourcesUsedCanary` (2) — `health_normalizer:v1` tag present only in normalized path
- `TestTelnyxOnlyLivenessIsConnected` (3) — the headline regression fix
- `TestSurfaceContainment` (2) — static guards: no surface other than AI Health Summary references the flag or imports the health package. Catches scope-widening at PR time.

### Full suite

```
python -m pytest -q --tb=line
→ 1443 passed, 14 warnings in 10.20s
```

Warnings are all pre-existing (FastAPI `on_event` deprecation, Pydantic v2 config deprecation, `vola_service` AsyncMock — none from this PR).

---

## Rollout plan

The future rollout — once the AI Health Summary has soaked successfully — is documented for transparency. **NONE of these phases ship in this PR.**

| Phase | Surface | Approach | Soak |
|---|---|---|---|
| **MVP (this PR)** | AI Health Summary only | Flag-gated branch in `LLLMContext` | 2 weeks of internal-only use, observe `llm_audit_log` `sources_used` for `health_normalizer:v1` rows and operator-reported anomalies |
| **N1** | Devices page | Add `?compute=v2` query param to `GET /api/devices`; UI opt-in toggle | 1 week side-by-side with the legacy computed status |
| **N2** | Command Center | Replace `compute_site_staleness` and `connected_sites` derivation inside `command.py:373-644` | 2 weeks — high-visibility surface, requires explicit governance approval |
| **N3** | Map + Sites page | Route `Site.status` reads through normalizer when flag is on | 1 week after N2 lands cleanly |
| **N4** | Attention engine | Make `attention_engine.evaluate_device/site` accept `HealthSignals` instead of raw fields | 1 week |
| **N5** | Threshold unification | Migrate `template_engine.py` per-tenant thresholds + `automation_engine.py` rules to read from `thresholds.py` | as needed |
| **N6** | `Site.status` decision | Governance call: deprecate (always computed) or auto-recompute via background job | requires sign-off |

Each phase is independently revertable and ships behind the same flag.

---

## Rollback plan

### Tier 1 — flag flip (preferred, instant)

```
# On true911-api in Render:
FEATURE_HEALTH_NORMALIZER=false   # set, or remove the var
# Restart the service.
```

After restart:
- `LLLMContext.load_fleet/load_site` revert to `_load_*_legacy()`.
- AI Health Summary `sources_used` no longer contains `health_normalizer:v1`.
- No other surface was reading the flag → nothing else changes.
- No data loss; no schema rollback; no migration to reverse.

### Tier 2 — revert the PR

```
git revert <merge-commit>
git push
```

Safe because every change is additive (new files + one flag-gated branch). Render auto-deploys; the new package is removed; the legacy path is the only one left.

### Verification after rollback

```bash
curl https://true911-api.onrender.com/api/config/features
# Expected: { ..., "lllm": ..., (no 'health_normalizer' key) }

# Hit the AI Health Summary with a SuperAdmin token:
curl -H "Authorization: Bearer ..." \
     https://true911-api.onrender.com/api/llm/health-summary?scope=fleet
# Expected: sources_used does NOT contain 'health_normalizer:v1'
```

---

## Pre-merge verification (already passed on this branch)

```bash
# 1. Full backend suite — 1443 pass, 0 fail, no new warnings.
cd api && python -m pytest -q --tb=line

# 2. Import + flag default smoke.
cd api && python -c "from app.services.health import compute_device_state; \
                     from app import main; \
                     print(main.settings.FEATURE_HEALTH_NORMALIZER)"
# Expected: false

# 3. Frontend NOT touched in this PR — no build needed.
git diff --stat main -- web
# Expected: empty
```

---

## Post-merge expectations

With `FEATURE_HEALTH_NORMALIZER` unset (the default), nothing observable changes in production:

- `GET /api/config/features` returns the same JSON it did before this PR.
- `GET /api/llm/health-summary` returns responses identical to the pre-MVP behavior (legacy path).
- The new `app.services.health` package is loaded into memory but no function in it is called for any request.
- Test suite continues to run green in CI.

**The PR is safe to merge before deciding whether/when to enable the flag.**

---

## What to do after merge (your call)

1. **Merge this PR with the flag off.** Confirms the no-op deploy holds in production.
2. **(Optional) Enable the flag in Render for `true911-api`** via a small ops PR similar to `ops/lllm-phase-1a-soak`. Set `FEATURE_HEALTH_NORMALIZER=true`. Trigger Blueprint sync.
3. **Run the AI Health Summary** as SuperAdmin. Expected: `sources_used` includes `health_normalizer:v1` and the four new evidence references (carrier liveness / vola liveness / telnyx liveness / lifecycle).
4. **Spot-check `llm_audit_log`** for rows generated during the soak — the `summary_text` should reflect normalizer-derived counts (a site with only Telnyx evidence now appears as CONNECTED instead of in the stale list).
5. **2-week soak before any Phase N1+ rollout.** Per the audit doc.

---

*End of MVP documentation. Implementation lives on branch `feat/health-normalizer-mvp`; PR awaits review.*
