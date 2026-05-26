# T-Mobile Callback Ingest MVP

**Status:** Implemented behind `FEATURE_TMOBILE_CALLBACK_INGEST=false` (default off). PR is a no-op deploy until the flag is flipped.
**Branch:** `feat/tmobile-callback-ingest-mvp`
**Date:** 2026-05-25
**Companion docs:** `docs/TMOBILE_INTEGRATION_AUDIT.md` (the audit that justified this MVP), `docs/HEALTH_NORMALIZER_MVP.md` (the layer this MVP feeds), `docs/AI_OPERATIONAL_SAFETY.md` (governance contract for AI surfaces).

---

## What this PR ships

The **smallest safe MVP** of T-Mobile callback ingest from `TMOBILE_INTEGRATION_AUDIT.md` §7. A new pure-logic processor plus a flag-gated dual-write on the existing PIT callback URLs. Nothing else is touched.

### One sentence

When the flag is on, T-Mobile callbacks at the existing `/tmobile/wholesale/callback/<event>` URLs are archived to `IntegrationPayload`, then a worker matches the ICCID/MSISDN to a `Sim`, refuses ambiguous matches, and on a single safe match with a linked `Device` writes `Device.last_network_event = now` via the existing Verizon-equivalent path — which the Health Normalizer already reads as `last_carrier_event_at`.

### File-level summary

| Path | Status | Purpose |
|---|---|---|
| `api/app/config.py` | modified | `FEATURE_TMOBILE_CALLBACK_INGEST='false'` + `TMOBILE_CALLBACK_MAX_AGE_SECONDS=600` |
| `api/app/services/tmobile_callback_processor.py` | new | Extract / match / promote orchestrator (~280 lines) |
| `api/app/routers/tmobile_callback.py` | modified | Per-event POST handlers dual-write when flag on; GET handlers + legacy `/callback` untouched |
| `api/app/services/sim_service.py` | modified | `handle_webhook` delegates to processor when source==`tmobile` AND flag on |
| `api/tests/test_tmobile_callback_processor.py` | new | 30 unit tests (extraction, matching, orchestrator) |
| `api/tests/test_tmobile_callback_integration.py` | new | 13 integration tests (flag on/off, surface containment, composition) |
| `docs/TMOBILE_CALLBACK_INGEST_MVP.md` | new (this doc) | What was implemented, flag behavior, rollout, rollback, gaps |

**Test suite after this PR: 1489 pass (baseline 1446 + 43 new), zero regressions.**

---

## What is intentionally NOT changed

Per the MVP scope directive in `TMOBILE_INTEGRATION_AUDIT.md` §7:

- ❌ **Outbound TAAP API calls.** `tmobile_taap.py` remains untouched and uninstantiated. Phase 2.
- ❌ **Inbound signature verification.** Still pending T-Mobile's spec — see "Known gaps" below.
- ❌ **Telnyx, VOLA, Verizon paths.** Not touched.
- ❌ **Provisioning writes.** Processor never creates SIM rows, never creates Device rows.
- ❌ **E911, call routing, customer records, emergency behavior.** Static test guards against any import from these modules.
- ❌ **`Site.status` writers.** Unchanged.
- ❌ **`Device.last_heartbeat` writers.** Unchanged — provider data is NOT overloaded into the heartbeat field. The processor writes `Device.last_network_event` (the same column Verizon writes), never `Device.last_heartbeat`.
- ❌ **Schema.** No new column, no migration. Uses existing `IntegrationPayload`, `Sim`, `Device`, `CommandTelemetry`, `NetworkEvent`.
- ❌ **Frontend.** Zero touch.
- ❌ **Customer-facing surface.** AI Health Summary is internal-only and remains the only consumer of the normalizer this feeds.

The containment is enforced by **three static tests** in `test_tmobile_callback_integration.py` that grep the codebase and fail the PR if the allowlist is widened.

---

## Feature flag behavior

```yaml
FEATURE_TMOBILE_CALLBACK_INGEST: "false"   # default
TMOBILE_CALLBACK_MAX_AGE_SECONDS: 600
```

| Flag value | POST `/tmobile/wholesale/callback/<event>` | Worker `webhook.tmobile` job | Health Normalizer impact |
|---|---|---|---|
| `"false"` (default) | Log + 200 ack, no DB write, no job enqueue | Legacy stub: mark IntegrationPayload processed | None |
| `"true"` | Log + archive IntegrationPayload (source=`tmobile`, synthetic event-type header) + enqueue `webhook.tmobile` + 200 ack | Delegate to `tmobile_callback_processor.process_payload`: extract → tenant-scoped SIM match → promote `Device.last_network_event` when safe | Promoted devices appear `CONNECTED` in AI Health Summary via existing `last_carrier_event_at` channel |
| any other value | Treated as off | Treated as off | None |

**Hard contract:** HTTP response from the callback endpoints is **always 200**, regardless of flag value or downstream archive success — the PIT validator and T-Mobile retry logic must never see a 5xx. Archive failures log + are swallowed; the validator's contract is preserved.

---

## Algorithm spec

### Router (per POST event handler)

```
if FEATURE_TMOBILE_CALLBACK_INGEST.strip().lower() != "true":
    _log_callback(...)                              # existing structured log
    return _ack(event)                              # 200 + JSON ack
else:
    _log_callback(...)
    try:
        _archive_tmobile_callback(request, event_type, db)
        # → IntegrationPayload(source='tmobile', body=..., headers=...+synthetic event-type)
        # → job_service.create_and_enqueue('webhook.tmobile', {payload_id, source, event_type})
    except Exception:
        logger.exception(...)                       # archive failure does NOT 5xx
    return _ack(event)                              # always 200
```

### Worker (sim_service.handle_webhook)

```
if source == "tmobile" and FEATURE_TMOBILE_CALLBACK_INGEST.strip().lower() == "true":
    result = await tmobile_callback_processor.process_payload(db, payload_id)
    return {"payload_id": ..., "tmobile_status": result.status, ...}
else:
    # legacy stub — mark IntegrationPayload.processed = True
```

### Processor (`process_payload`)

```
1. Load IntegrationPayload by payload_id. Missing → error:not_found.
2. Mark payload.processed = True (defensive — every callback auditable).
3. Extract ICCID, MSISDN, network_status, event_timestamp, event_type
   from body + synthetic header. Tolerant of malformed/missing.
4. No ICCID and no MSISDN → skipped:no_identifier.
5. event_timestamp > now - TMOBILE_CALLBACK_MAX_AGE_SECONDS → skipped:replay.
6. match_sim(signal):
     - ICCID is globally unique (Sim.iccid UNIQUE) → 0 or 1 result.
       Tenant context = matched sim.tenant_id.
     - Fallback to MSISDN only if ICCID absent. Count first; refuse on >1.
7. No match → skipped:no_match.
8. Ambiguous (MSISDN>1) → skipped:ambiguous_match.
9. Match has no linked Device (sim.device_id IS NULL or device row missing)
   → skipped:no_device.
10. Single safe match with linked Device → call
    carrier_adapter.ingest_carrier_telemetry(db, sim.tenant_id, CarrierTelemetry(
        device_id=device.device_id,
        carrier="t-mobile",
        network_status=signal.network_status,
        ...
    ))
    # ingest_carrier_telemetry sets device.last_network_event = now,
    # which signals_loader.py reads as last_carrier_event_at.
    return promoted.
```

**Hard correctness properties (each pinned by a test):**

- **Tenant isolation is implicit.** `Sim.iccid` is globally unique, so a successful ICCID lookup identifies the tenant. No cross-tenant guess.
- **Fail closed on ambiguity.** MSISDN match returning >1 row is refused (`skipped:ambiguous_match`). The load query is asserted to NOT issue.
- **Always archive.** Every callback writes an IntegrationPayload row, regardless of whether it eventually promotes. The audit trail is complete.
- **Always 200.** Archive failures don't surface to T-Mobile.
- **No PII in logs.** ICCID and MSISDN are passed through `_redact_identifier()` (first 6 chars + last 2 chars + dots) before logging.
- **Reuse Verizon's pipeline.** The actual `Device.last_network_event` write goes through the unchanged `carrier_adapter.ingest_carrier_telemetry` — same code path Verizon has used for months, including its `NetworkEvent` creation for disconnection / roaming / signal degradation when applicable.

---

## Operator note: env var must be set on the WORKER service, not just the API

`FEATURE_TMOBILE_CALLBACK_INGEST` is **not** listed in `render.yaml`. When the operator flips it on, they must set it on **both** Render services:

- `true911-api` — controls whether the callback router archives + enqueues
- `true911-worker` — controls whether `sim_service.handle_webhook` invokes the processor (and therefore whether `Device.last_network_event` ever updates)

If the var is set on the API only (e.g. via Render dashboard on that service alone, or via Blueprint sync without listing it for the worker), the symptom is:

- Callback returns 200 ✅
- `IntegrationPayload(source='tmobile')` row created with `processed=true` ✅
- `Job(job_type='webhook.tmobile')` reaches `status='completed'` ✅
- **`Device.last_network_event` stays NULL** ❌
- **`command_telemetry` has no new rows** ❌
- **`jobs.result` contains `tmobile_status: "skipped:flag_off"`** (this is the immediate diagnostic)

The result-shape diagnostic was added in the worker-observability PR (see §"Worker observability" below). For older jobs that pre-date that PR, the legacy result shape was just `{"processed": True, "payload_id": "..."}` with no marker — those rows can't be retroactively distinguished from a successful legacy webhook handling.

### Fix

Two equivalent paths:

**(a) Dashboard:** add `FEATURE_TMOBILE_CALLBACK_INGEST=true` directly on the `true911-worker` service env. Restart the worker. New callbacks will promote correctly.

**(b) render.yaml + Blueprint sync:** add to both service blocks:

```yaml
  - type: web
    name: true911-api
    envVars:
      ...
      - key: FEATURE_TMOBILE_CALLBACK_INGEST
        value: "true"

  - type: worker
    name: true911-worker
    envVars:
      ...
      - key: FEATURE_TMOBILE_CALLBACK_INGEST
        value: "true"
```

Then trigger Blueprint sync (same gotcha as PR #55/#57). The `value: "true"` here is the production-state intent — Blueprint sync sets it explicitly on both services.

---

## Worker observability (added 2026-05-26)

The `webhook.tmobile` worker handler (`sim_service.handle_webhook`) now always returns a structured `jobs.result` so the legacy-stub-vs-processor-vs-skip distinction is visible from `SELECT result FROM jobs WHERE job_type='webhook.tmobile' ORDER BY id DESC LIMIT 5;` without re-running anything.

| Worker code path | `jobs.result` shape |
|---|---|
| Flag ON, processor promoted via Sim | `{processed, payload_id, source="tmobile", tmobile_status="promoted", tmobile_reason=null, tmobile_matched_sim_iccid="<iccid>", tmobile_matched_device_id="<id>"}` |
| Flag ON, processor promoted via Device fallback | `{processed, payload_id, source="tmobile", tmobile_status="promoted:device_fallback", tmobile_reason=null, tmobile_matched_sim_iccid=null, tmobile_matched_device_id="<id>"}` |
| Flag ON, processor skipped (any reason) | `{processed, payload_id, source="tmobile", tmobile_status="skipped:<reason>", tmobile_reason="<details>", ...}` |
| Flag OFF (worker missing env var) | `{processed, payload_id, source="tmobile", tmobile_status="skipped:flag_off"}` — **diagnostic for the missing-worker-env-var case** |
| Non-T-Mobile job | `{processed, payload_id, source="<other>"}` — no `tmobile_*` fields |

The flag-off branch also emits a WARNING log line in the worker process:

```
T-Mobile webhook wh-XXXXXXXXXX arrived but the worker's
FEATURE_TMOBILE_CALLBACK_INGEST is not 'true' — using legacy stub
(no promotion).  Set the env var on the WORKER service (not just
the API) to enable promotion. See docs/TMOBILE_CALLBACK_INGEST_MVP.md
operator note.
```

### How to diagnose a callback that's not promoting

```sql
SELECT id, job_type, status, result, completed_at
FROM jobs
WHERE job_type = 'webhook.tmobile'
ORDER BY id DESC LIMIT 10;
```

- `result->>'tmobile_status'` is `'skipped:flag_off'` → worker env var missing (see Operator note above)
- `result->>'tmobile_status'` is `'skipped:no_match'` → neither Sim nor Device matched the callback identifiers (cross-check `signal.iccid` / `signal.msisdn` against `sims` and `devices`)
- `result->>'tmobile_status'` is `'skipped:ambiguous_device_match'` → multiple devices share that MSISDN/ICCID; `result->>'tmobile_reason'` lists `matched_on=` and `candidates=`
- `result->>'tmobile_status'` is `'promoted'` or `'promoted:device_fallback'` → worker did its job; if `last_network_event` still looks wrong, check `device_id` in the result vs the device you expected

---

## Production finding 2026-05-26: device-fallback match

After flipping `FEATURE_TMOBILE_CALLBACK_INGEST=true` in production, end-to-end testing confirmed:

- The callback returned 200.
- `IntegrationPayload(source='tmobile')` was created correctly.
- The `webhook.tmobile` job was created, picked up by the worker (after PR #61), and completed.
- **But `Device.last_network_event` did not update** for any production callback.

Root cause: the processor matched ICCID/MSISDN only against the `sims` table. In production, the `sims` table contained no rows for the affected lines. Many cellular devices were imported with the cellular identifiers stored **directly on the `Device` row** (`devices.iccid`, `devices.msisdn`), leaving the `sims` table empty for those devices. Every callback was correctly archived but archived-only — `skipped:no_match`.

### Fix

After `match_sim` returns `kind='none'`, the processor now invokes `match_device_fallback(db, signal)`:

- Tries `Device.iccid` first (more specific). Count-first; refuse if >1.
- Then tries `Device.msisdn` with a small set of equivalent forms via `_msisdn_variants(value)` so a callback's `8563081391` matches a stored `+18563081391` and vice-versa.
- Tenant is read from the matched `Device.tenant_id` — never guessed from the callback body.
- On exactly one match: promotes via the same `carrier_adapter.ingest_carrier_telemetry` path the SIM-side uses. Status returned is `promoted:device_fallback` (distinct from the SIM-path `promoted` so logs can distinguish).
- Ambiguous (>1 device matches): `skipped:ambiguous_device_match` — refuses to guess.
- Zero matches anywhere: `skipped:no_match` (existing behavior preserved).

The SIM-match path is unchanged and still wins first when populated. Existing tenant isolation contracts hold:

- ICCID match: `Device.iccid` is not globally UNIQUE on the schema, but ambiguous matches are refused, so a single match is unambiguous.
- MSISDN match: same — ambiguity is refused.
- No cross-tenant write is possible without a duplicate identifier across tenants (which is itself a data-integrity issue and would be caught as ambiguous).

### MSISDN normalisation

`_msisdn_variants("8563081391")` returns the set `{"8563081391", "18563081391", "+18563081391"}`. The same set is returned for `"18563081391"` and `"+18563081391"`. Non-US numbers degrade safely to `(raw, digits-only)` with no false US-prefix injection. The raw input is always preserved so a literal stored form (e.g. `"(856) 308-1391"` or an extension) still matches.

### Status names introduced

| Status | Meaning |
|---|---|
| `promoted:device_fallback` | Device matched directly (no Sim row), `last_network_event` updated. |
| `skipped:ambiguous_device_match` | ICCID/MSISDN matched >1 Device row. Reason carries `matched_on=` + `candidates=`. |

`skipped:no_match` now means "no Sim AND no Device match" (was: no Sim match).

### Container statics still hold

The two surface-containment tests at the bottom of `test_tmobile_callback_integration.py` continue to pass — no new imports of E911 / provisioning / customer / call-routing / line_service modules in the processor; no new consumer of `FEATURE_TMOBILE_CALLBACK_INGEST` outside the allowlist. New tests live in `test_tmobile_callback_device_fallback.py` (22 tests) plus one modified existing test in `test_tmobile_callback_processor.py`.

---

## Known gaps (deliberate, documented in code + tests)

1. **Inbound signature verification not implemented.** T-Mobile has not published their callback signing spec. Current callback endpoints accept any payload. **Mitigations to apply at the operator/network layer:**
   - IP allowlist via Render / Cloudflare to T-Mobile's source CIDRs.
   - Keep the flag OFF in any environment exposed to the public internet until either signing is implemented OR the IP allowlist is verified.
   - Document the gap in operator runbook so anyone enabling the flag knows.
   See `docs/TMOBILE_INTEGRATION_AUDIT.md` §6 risk #1 for the threat model.

2. **No idempotency check.** Same callback arriving twice (T-Mobile retries on transient failure) writes `last_network_event = now` twice. Both writes are effectively the same value within a second, so this is harmless operationally — but it means our archive contains duplicates. Phase 1c can add a SELECT-before-promote check using `(source, hash(body))`. Skipped here to avoid a schema change.

3. **`signal_dbm` and `sip_status` not extracted from callbacks.** T-Mobile callback payloads can carry signal quality fields in some events (notably `usage` and `subscriber_status`), but the schemas vary by event type and we don't have a documented mapping. Phase 1c can extend `extract_signal()` once we have real PIT traffic to model from.

4. **Static-IP and CIM events have no carrier-liveness semantic.** They will still be archived (audit trail) but will reach `skipped:no_identifier` or similar in the processor — no promotion. This is the right behavior; documented here so an operator reviewing audit logs understands why these event types show as "skipped" routinely.

5. **No per-tenant override.** Flag is global. If a tenant should NOT receive T-Mobile evidence even when the flag is on, today there's no per-tenant kill switch. Add `tenants.settings_json['tmobile_callback_enabled']` in a Phase 1c if needed.

6. **No outbound TAAP.** This MVP is inbound-only. The outbound TAAP client (`tmobile_taap.py`) exists and is fully signing-correct but uninstantiated. Phase 2 will pick a use case and wire it behind `FEATURE_TMOBILE_OUTBOUND=false` + `TMOBILE_ALLOW_EXTERNAL=false`, mirroring the LLLM cost-control pattern.

---

## Security model

| Surface | Defense |
|---|---|
| Inbound callback authenticity | **Not implemented** (known gap). Operator must use IP allowlist + flag-off-by-default until T-Mobile spec lands. |
| Inbound callback PII exposure in logs | ICCID/MSISDN passed through `_redact_identifier()` before any log line. Raw body never logged in normal operation (debug-only). |
| Inbound callback PII exposure in archive | `IntegrationPayload` retains raw body + headers — accepted; this is the existing pattern for Telnyx / VOLA. Access to `integration_payloads` is RBAC-gated. |
| Cross-tenant write | Sim.iccid UNIQUE constraint + MSISDN ambiguity refusal — structurally impossible to write to the wrong tenant. Static test guards. |
| Replay | `TMOBILE_CALLBACK_MAX_AGE_SECONDS` (default 600) — events older than 10 min are archived but not promoted. |
| Spoofing | **Not defended** (no sig verification). Same mitigations as authenticity above. |
| HTTP 5xx leaking to T-Mobile | Archive exceptions swallowed; handler always returns 200. Tested. |
| Worker hijack (non-tmobile job dispatched to processor) | Worker checks `source == "tmobile"` before delegation. Tested (`test_flag_on_but_non_tmobile_source_uses_legacy_stub`). |

---

## Tests (43 new, 1489 total)

### Unit (`test_tmobile_callback_processor.py` — 30)

- `TestExtractSignal` (9) — canonical + camelCase + alternate keys; ISO 8601 + epoch + malformed timestamp fallback; whitespace strip; empty body; non-dict body; event_type default.
- `TestMatchSim` (6) — ICCID single match, ICCID miss + MSISDN fallback, MSISDN-only ambiguous refusal (the **critical** test: load query asserted NOT issued — no guessing), MSISDN miss, no identifiers.
- `TestFindLinkedDevice` (3) — happy path, no `device_id` (no query), device not found.
- `TestProcessPayload` (7) — every decision branch end-to-end, including happy path asserting `ingest_carrier_telemetry` called with `tenant_id=sim.tenant_id`, `carrier='t-mobile'`, `network_status` propagated.
- `TestRedactIdentifier` (5) — None / empty / short / 20-char ICCID / 11-char MSISDN.

### Integration (`test_tmobile_callback_integration.py` — 13)

- `TestFlagOffPreservesCurrentBehavior` (2) — POST returns 200, NO IntegrationPayload, NO job enqueued.
- `TestFlagOnArchivesPayload` (4) — IntegrationPayload row written with synthetic event-type header; malformed body archives as `raw_body`; **archive failure still returns 200**; webhook.tmobile job enqueued with correct event_type.
- `TestWorkerHandlerDelegation` (3) — flag-off→legacy stub; flag-on+source=tmobile→processor; flag-on+source=telnyx→legacy (no cross-source hijack).
- `TestSurfaceContainment` (3) — static guards: flag references allowlist; processor import allowlist; **no E911/provisioning/customer/call-routing imports in processor**.
- `TestHealthNormalizerComposition` (1) — proves `Device.last_network_event` is both written by `carrier_adapter` AND read by `signals_loader` — the wire is intact.

### Full suite

```
python -m pytest -q --tb=line
→ 1489 passed, 14 warnings in 11.95s
```

Warnings all pre-existing.

---

## Rollout plan

### Phase 1 (this PR)

Merge with flag off. Confirm no-op deploy in production. Zero env-var changes.

### Phase 1a — enable soak (separate ops PR)

A small `ops/tmobile-callback-ingest-soak` PR (mirror of `ops/health-normalizer-phase-1` / PR #57) that adds:

```yaml
# render.yaml under true911-api envVars:
- key: FEATURE_TMOBILE_CALLBACK_INGEST
  value: "true"
```

After merging the ops PR, **trigger Blueprint sync** in Render (the same gotcha that bit PR #55 and PR #57: a per-service "Deploy latest commit" does NOT re-read render.yaml; Blueprint sync does).

Before flipping the flag, **verify the IP allowlist** for T-Mobile's source CIDRs is configured at the Render edge or Cloudflare — that's the substitute defense until inbound signature verification lands.

### Phase 1b — soak observation

For 1 week after Phase 1a:

```sql
-- New IntegrationPayloads of source='tmobile'
SELECT date_trunc('hour', created_at) AS hour,
       count(*) AS callbacks
FROM integration_payloads
WHERE source = 'tmobile'
  AND created_at > now() - interval '24 hours'
GROUP BY 1 ORDER BY 1 DESC;

-- Promoted devices in the last day (by reading last_network_event with
-- a recency window similar to STALE_OBSERVATION_SECONDS).  Spot-check
-- that AI Health Summary reflects this.
SELECT device_id, last_network_event, telemetry_source
FROM devices
WHERE telemetry_source = 't-mobile_carrier'
  AND last_network_event > now() - interval '24 hours'
ORDER BY last_network_event DESC LIMIT 20;

-- Worker handler result distribution (audit log if we want it):
-- handle_webhook returns {tmobile_status: ...}; today there's no
-- persistence of this — Phase 1c can add a stats table if useful.
```

**Stop signals during soak:**

- Any `skipped:ambiguous_match` row in the worker logs → investigate `Sim.msisdn` collisions for that tenant.
- Any device shows `last_network_event` updated when its tenant should not have T-Mobile SIMs → likely a cross-tenant ICCID collision; flip the flag off immediately and audit.
- T-Mobile's PIT validator starts retrying (visible in their dashboard) → confirms an HTTP 5xx leaked; check Render logs and the `_maybe_archive` exception path.

### Phase 1c (separate PR, post-soak)

- Add idempotency check (SELECT before promote).
- Extract `signal_dbm` / `sip_status` from real PIT traffic once we've modeled the payload shape per event type.
- Add per-tenant `tmobile_callback_enabled` flag on `tenants.settings_json` if needed.

### Phase 2 (separate audit + PR)

Outbound TAAP — pick a use case (subscriber verification probe?), gate behind `FEATURE_TMOBILE_OUTBOUND=false` + `TMOBILE_ALLOW_EXTERNAL=false`.

### Phase 3

Inbound signature verification once T-Mobile publishes spec.

---

## Rollback plan

### Tier 1 — flag flip (instant, preferred)

```
# On true911-api in Render dashboard:
FEATURE_TMOBILE_CALLBACK_INGEST=false   # set, or remove the var
# Restart the service.
```

After restart:

- Callback endpoints revert to log-only + 200.
- `IntegrationPayload` rows already written remain (audit value).
- `Device.last_network_event` values already promoted remain (those promotions are correct historical records — `last_network_event` is meant to reflect the most recent observation regardless of when the flag was on).
- No data loss. No schema rollback.

### Tier 2 — revert the merge

```
git revert <merge-commit>
git push
```

Safe because every change is additive. Tables and historical writes remain.

### Tier 3 — purge T-Mobile archive (only if explicitly needed)

```sql
DELETE FROM integration_payloads
WHERE source = 'tmobile'
  AND created_at > <flag_enable_ts>;
```

Permanent. Loses audit trail for the soak period. Should not normally be needed.

---

## How to test in PIT

1. **Pre-merge** (flag off in dev or staging):
   ```bash
   # Health-check style smoke — POST returns 200 ack, no DB writes:
   curl -X POST https://pit-api.manleysolutions.com/tmobile/wholesale/callback/provisioning \
        -H "content-type: application/json" \
        -d '{"iccid":"89014103211118510720","msisdn":"13105551234","status":"active"}'
   # Expected: {"status":"ok","provider":"t-mobile","event":"provisioning",...}
   # In Render Postgres:
   #   SELECT count(*) FROM integration_payloads WHERE source='tmobile';
   # Should be unchanged.
   ```

2. **Post-merge with flag ON** (production or PIT environment):
   ```bash
   # 1. Confirm flag is live (no public endpoint for FEATURE_TMOBILE_CALLBACK_INGEST,
   #    so this is checked via the worker result):
   #
   # 2. POST a synthetic payload that matches an existing Sim in your tenant:
   curl -X POST https://true911-api.onrender.com/tmobile/wholesale/callback/subscriber-status \
        -H "content-type: application/json" \
        -d '{"iccid":"<a-real-iccid-from-your-sims-table>","status":"registered"}'
   # Expected: 200 + ack.
   
   # 3. Verify archive:
   #   SELECT payload_id, source, headers->>'x-true911-tmobile-event-type' AS event_type, created_at
   #   FROM integration_payloads
   #   WHERE source='tmobile' ORDER BY created_at DESC LIMIT 5;
   
   # 4. Wait ~5s for the worker, then verify promotion:
   #   SELECT device_id, last_network_event, network_status, telemetry_source
   #   FROM devices
   #   WHERE device_id = (SELECT device_id FROM sims WHERE iccid='<the-iccid>');
   # Expected: telemetry_source='t-mobile_carrier', last_network_event ≈ now.
   ```

3. **Test the safe-skip paths** (each should archive but not promote):
   ```bash
   # No identifier — archived as skipped:no_identifier
   curl -X POST .../callback/usage -d '{"event":"ping","unrelated":"data"}'
   
   # Unknown ICCID — archived as skipped:no_match
   curl -X POST .../callback/subscriber-status -d '{"iccid":"NOT_IN_OUR_DB","status":"x"}'
   
   # Old event (replay) — archived as skipped:replay
   curl -X POST .../callback/subscriber-status \
        -d '{"iccid":"<real>","event_time":"2020-01-01T00:00:00Z","status":"x"}'
   ```
   Verify each row's `webhook.tmobile` job result in the worker log carries the expected `tmobile_status`.

---

## How to verify Health Normalizer evidence

When `FEATURE_HEALTH_NORMALIZER=true` (currently the case in production per PR #57) AND `FEATURE_TMOBILE_CALLBACK_INGEST=true`:

1. **A device that was previously "stale" because its CSAS heartbeat is stale, but whose linked SIM just received a T-Mobile callback, will now show `CONNECTED` in the AI Health Summary.** This is the headline behavioral change.

2. To verify end-to-end:
   ```
   # Pick a tenant + device where:
   #   - Device.last_heartbeat is old (e.g., > 5 min ago)
   #   - The Device has a SIM (Device.sim_id IS NOT NULL)
   #   - That SIM is a T-Mobile SIM (Sim.carrier = 'tmobile')
   
   # Before posting the synthetic callback:
   #   GET /api/llm/health-summary?scope=site&scope_id=<the-site>
   #   → may show stale_devices > 0
   
   # POST the callback (see PIT test recipe above).
   
   # Wait ~5s, then re-request:
   #   GET /api/llm/health-summary?scope=site&scope_id=<the-site>
   #   → stale_devices count for that site DECREASES by 1.
   #   → sources_used will continue to include
   #     "devices:tenant=X.last_network_event (carrier liveness)"
   #     because the same field is being read (now reflecting the
   #     T-Mobile callback time).
   ```

3. The `sources_used` array on the AI Health Summary response does NOT specifically tag T-Mobile vs Verizon vs heartbeat — that's intentional (the Health Normalizer treats them as one channel). If per-vendor attribution becomes useful operationally, Phase N1+ of the Normalizer rollout (`docs/HEALTH_NORMALIZER_MVP.md` §Rollout plan) is the right place to add it.

---

## Pre-merge verification (already passed on this branch)

```
cd api && python -m pytest -q --tb=line
→ 1489 passed, 14 warnings in 11.95s

cd api && python -c "from app import main; \
                     from app.routers.tmobile_callback import _ingest_enabled; \
                     print(main.settings.FEATURE_TMOBILE_CALLBACK_INGEST, _ingest_enabled())"
→ false False

# Frontend untouched
git diff --stat main -- web
→ empty
```

---

## Post-merge expectations

With `FEATURE_TMOBILE_CALLBACK_INGEST` unset (the default), nothing observable changes in production:

- `POST /tmobile/wholesale/callback/<event>` returns identical 200 + JSON ack as today.
- `IntegrationPayload` rows of `source='tmobile'` do not appear.
- `webhook.tmobile` jobs are NOT enqueued from the callback URLs.
- `Device.last_network_event` continues to be written ONLY by Verizon polling and CSAS heartbeats.
- AI Health Summary `sources_used` is unchanged.

**The PR is safe to merge before deciding whether/when to enable the flag.**

---

*End of MVP documentation. Implementation lives on branch `feat/tmobile-callback-ingest-mvp`; PR awaits review.*
