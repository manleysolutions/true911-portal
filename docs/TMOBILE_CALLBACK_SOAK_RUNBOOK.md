# T-Mobile Callback Ingest — Phase 1a Soak Runbook

**Audience:** operators of the True911 production deployment during the T-Mobile callback ingest soak.
**Status:** Phase 1a LIVE end-to-end as of 2026-05-26 evening. `FEATURE_TMOBILE_CALLBACK_INGEST=true` on both `true911-api` and `true911-worker`. First production promotion verified for `msisdn=+18563081391` (matched `device_id=8563081391`, `Device.last_network_event` updated, `command_telemetry` row written).
**Companion docs:** `docs/TMOBILE_CALLBACK_INGEST_MVP.md` (algorithm + operator note), `docs/HEALTH_NORMALIZER_MVP.md`, `docs/AI_OPERATIONAL_SAFETY.md`.

---

## What this soak is for

We've enabled three production-affecting flags in sequence (LLLM, Health Normalizer, T-Mobile callback ingest). All three are internal-only / observability surfaces today. The soak window confirms:

- Callbacks continue to arrive from T-Mobile PIT (no silent disconnection)
- Each callback gets archived (`IntegrationPayload(source='tmobile').processed=true`)
- Each worker job completes with a visible `tmobile_status` in `jobs.result`
- Cellular devices receive `last_network_event` updates → AI Health Summary picks them up as CONNECTED via the existing `last_carrier_event_at` channel
- No retry storms, no ambiguous matches, no cross-tenant writes

Once those properties hold for the agreed soak window with zero red flags, we can either (a) extend the soak to additional surfaces (e.g. customer-facing CONNECTED indicators) or (b) move on to Phase 2 design (outbound TAAP). Neither is in scope for this runbook.

---

## When to run the check

- **Once per business day** during the soak window — minutes of work.
- **Immediately after** any change to: `FEATURE_TMOBILE_CALLBACK_INGEST`, Render env vars on `true911-api` or `true911-worker`, Cloudflare WAF rules, or T-Mobile-side credentials.
- **Before** any PR that touches `tmobile_callback*`, `sim_service`, `carrier_adapter`, `signals_loader`, or `worker.py` is merged.

---

## How to run

### Prerequisites

- `psql` on PATH (Windows: install PostgreSQL client or `winget install --id PostgreSQL.PostgreSQL`)
- Network access to the Render Postgres external URL
- Render dashboard → `true911-prod-db` → "Connect" → "External Database URL"

### Steps

```powershell
# 1. Copy the External Database URL from Render dashboard into a session-scoped env var.
#    (Use $env:DATABASE_URL — the script reads this name explicitly.)
$env:DATABASE_URL = "postgres://USER:PASS@HOST.render.com/DBNAME"

# 2. Run the check from the repo root.
./scripts/tmobile_soak_check.ps1

# 3. (Recommended) clear the env var afterwards so the credential
#    doesn't linger in the shell session.
Remove-Item Env:DATABASE_URL
```

The script:

- Connects only if `$env:DATABASE_URL` is set
- Wraps every query in `BEGIN TRANSACTION READ ONLY ... ROLLBACK` so a typo cannot mutate data
- Runs a fixed list of `SELECT` statements
- Prints PASS / WARN per check + a one-line summary
- Exits `0` on all PASS, `1` if any WARN

If the script reports WARN, drill into that specific check using the SQL from §"Daily monitoring SQL" below — every WARN check has a corresponding SQL block you can run by hand to see the offending rows.

### Optional flags

```powershell
./scripts/tmobile_soak_check.ps1 -HoursWindow 4   # narrow to the last 4 hours
./scripts/tmobile_soak_check.ps1 -DatabaseUrl "postgres://..."  # pass URL directly
```

---

## Daily monitoring SQL

Every block below is **read-only** and bounded to a recent time window so a single execution stays cheap. Run from `psql` directly when you need to see rows the script aggregated only as counts.

### Q1 — Recent `webhook.tmobile` jobs (last 24h)

```sql
SELECT status,
       count(*) AS jobs
FROM jobs
WHERE job_type = 'webhook.tmobile'
  AND created_at > now() - interval '24 hours'
GROUP BY status
ORDER BY status;
```

**Expected:** mostly `completed`. Any `failed` deserves investigation (see Q3). `queued` rows older than a couple of minutes deserve immediate investigation (see Q4).

### Q2 — Recent T-Mobile callback status distribution (last 24h)

```sql
SELECT result->>'tmobile_status' AS tmobile_status,
       count(*) AS jobs
FROM jobs
WHERE job_type = 'webhook.tmobile'
  AND created_at > now() - interval '24 hours'
GROUP BY 1
ORDER BY 2 DESC;
```

**Expected mix (after PR #62 + #63):**
- `promoted` and/or `promoted:device_fallback` dominant
- Some `skipped:no_identifier` if T-Mobile emits CIM / static-IP events (no liveness semantic)
- Zero `skipped:flag_off`
- Zero `skipped:ambiguous_match` and zero `skipped:ambiguous_device_match`

### Q3 — Failed `webhook.tmobile` jobs (last 7d)

```sql
SELECT id, status, attempt, error, created_at, completed_at
FROM jobs
WHERE job_type = 'webhook.tmobile'
  AND status = 'failed'
  AND created_at > now() - interval '7 days'
ORDER BY id DESC
LIMIT 50;
```

**Expected:** zero rows. A non-empty result is a RED FLAG — see §Red flags.

### Q4 — Stuck queued jobs

```sql
SELECT id, job_type, attempt, created_at, started_at
FROM jobs
WHERE status = 'queued'
  AND created_at < now() - interval '5 minutes'
ORDER BY id
LIMIT 50;
```

**Expected:** zero rows. After PR #61, no job should sit in `queued` for more than a few seconds. A row stuck more than 5 minutes is a RED FLAG (worker process down, RQ disconnect, or the dispatch path regressed — see [[worker-rq-dispatch-pitfall]] in memory).

### Q5 — Recent IntegrationPayload tmobile rows (last 24h)

```sql
SELECT date_trunc('hour', created_at) AS hour,
       count(*) AS payloads,
       sum(case when processed then 1 else 0 end) AS processed
FROM integration_payloads
WHERE source = 'tmobile'
  AND created_at > now() - interval '24 hours'
GROUP BY 1
ORDER BY 1 DESC;
```

**Expected:** `payloads == processed` per hour. A delta means archives are landing but the worker isn't reaching them (or is failing inside `process_payload` such that the IP row never gets marked processed — this is unusual because the processor marks defensively at start).

### Q6 — Recent `devices.last_network_event` updates via T-Mobile (last 24h)

```sql
SELECT device_id, tenant_id, msisdn, last_network_event, network_status,
       telemetry_source
FROM devices
WHERE telemetry_source = 't-mobile_carrier'
  AND last_network_event > now() - interval '24 hours'
ORDER BY last_network_event DESC
LIMIT 50;
```

**Expected:** at least one row per device that received a callback. Each row shows the carrier-promoted state.

### Q7 — Recent `command_telemetry` rows from T-Mobile (last 24h)

```sql
SELECT id, tenant_id, device_id, signal_strength, created_at,
       substring(metadata_json from 1 for 120) AS metadata_preview
FROM command_telemetry
WHERE metadata_json LIKE '%"source": "t-mobile_carrier"%'
  AND created_at > now() - interval '24 hours'
ORDER BY id DESC
LIMIT 50;
```

**Expected:** one row per `promoted` / `promoted:device_fallback` job. The `metadata_preview` should show `carrier=t-mobile`, `source=t-mobile_carrier`, and the network status passed through from the callback.

### Q8 — Ambiguous / skipped breakdown with reasons (last 7d)

```sql
SELECT result->>'tmobile_status' AS tmobile_status,
       result->>'tmobile_reason' AS tmobile_reason,
       count(*) AS jobs
FROM jobs
WHERE job_type = 'webhook.tmobile'
  AND result->>'tmobile_status' LIKE 'skipped:%'
  AND created_at > now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

**Expected:** mostly `skipped:no_identifier` (CIM/static-IP events) and possibly some `skipped:replay`. Any `skipped:ambiguous_match` or `skipped:ambiguous_device_match` deserves investigation against the `sims` / `devices` tables for the affected identifier.

### Q9 — Cross-tenant sanity (last 7d)

```sql
SELECT d.tenant_id,
       count(*) AS devices_promoted_via_tmobile
FROM devices d
WHERE d.telemetry_source = 't-mobile_carrier'
  AND d.last_network_event > now() - interval '7 days'
GROUP BY d.tenant_id
ORDER BY 2 DESC;
```

**Expected:** counts only against tenants you EXPECT to have T-Mobile inventory. An unexpected tenant appearing here is a RED FLAG — the device fallback may have matched the wrong row (ICCID/MSISDN collision across tenants would have been refused as ambiguous, so a single match into the wrong tenant means the source data has an issue).

---

## Red flags (script will surface these as WARN)

| # | Symptom | Likely cause | First action |
|---|---|---|---|
| 1 | Any `webhook.tmobile` job in `status='failed'` | Processor exception, DB error, or upstream API problem | Read `job.error` for the message; check Render worker logs around `completed_at` |
| 2 | Stuck `status='queued'` rows older than 5 min | Worker service down, Redis disconnect, OR dispatch path regressed | Check Render worker service is running; check Redis health; cross-reference [[worker-rq-dispatch-pitfall]] |
| 3 | Any `skipped:ambiguous_match` (Sim-side) | Duplicate `Sim.msisdn` rows | `SELECT * FROM sims WHERE msisdn = ?` to find the duplicates; fix data, do not adjust the refusal logic |
| 4 | Any `skipped:ambiguous_device_match` | Duplicate `Device.msisdn` or `Device.iccid` rows | Same approach — fix the data on the devices side |
| 5 | `last_network_event` update appears on a tenant that should have no T-Mobile inventory | Cross-tenant identifier collision in the data, OR processor matched a record that shouldn't have it | Pause: flip `FEATURE_TMOBILE_CALLBACK_INGEST=false` on the worker, investigate, do not resume until reconciled |
| 6 | No `command_telemetry` row for a `promoted` job | `carrier_adapter.ingest_carrier_telemetry` failed silently OR session was rolled back | Read Render worker logs at the job's `started_at` for any exception; cross-check `Device.last_network_event` was actually set |
| 7 | T-Mobile retries the same payload many times (`IntegrationPayload` duplicates with similar bodies) | We returned non-200 on a previous attempt | Search Render API logs for any 5xx near the callback path; verify the `_maybe_archive` swallow is still in effect |
| 8 | `result->>'tmobile_status' = 'skipped:flag_off'` appears | `FEATURE_TMOBILE_CALLBACK_INGEST` slipped off on the worker (env var lost, Blueprint sync without the var, dashboard edit) | Re-set the env var on `true911-worker`; see [[render-env-vars-per-service-pitfall]] |
| 9 | Cloudflare blocks from a real T-Mobile source IP | WAF allowlist drift or IP rotation announced by T-Mobile | Compare the blocked IP against `206.29.176.74-79` and `208.54.104.32-37`; update the Cloudflare IP List if T-Mobile rotated; check `/security/events` filtered by the rule |
| 10 | `IntegrationPayload(source='tmobile')` count drops to zero for >2h during business hours | T-Mobile stopped sending, OR our endpoint is unreachable, OR Cloudflare WAF blocked everything | `curl https://pit-api.manleysolutions.com/tmobile/wholesale/callback/usage` from outside — expect 405 for GET method (route exists). If unreachable, escalate to T-Mobile + Cloudflare |

### Cloudflare-side red flags (script can't query these directly)

The soak script can't reach Cloudflare's API without additional credentials. For the duration of the soak, **once per day** also open Cloudflare dashboard → Security → Events for `pit-api.manleysolutions.com` and confirm:

- Rule `tmobile_pit_callback_sources` (if/when R2 is enforcing) shows blocks only from IPs **outside** the allowlist
- No T-Mobile-allowlisted IP appears in the "blocked" or "challenge" buckets
- If R1 only (Log-mode) is active, check that real T-Mobile traffic is consistently inside the allowlist

If you see any T-Mobile-allowlisted IP in the blocked bucket, flip the Cloudflare rule to Log-mode immediately (instant rollback per PR #60 rollout plan) and investigate.

---

## Success criteria for ending soak

Soak can be considered complete when **all** of the following hold for a continuous **14-day window**:

1. ≥1 `webhook.tmobile` job per business day reaches `status='completed'` with `tmobile_status='promoted'` or `'promoted:device_fallback'`
2. Zero rows from Q3 (failed jobs)
3. Zero rows from Q4 (stuck queued)
4. Zero rows from Q8 with `skipped:ambiguous*` status
5. Zero `skipped:flag_off` results
6. Q5 shows `payloads == processed` consistently
7. Q6 / Q7 are in 1:1 correspondence — every promotion has a `command_telemetry` row
8. Q9 shows promotions only against expected tenants
9. Cloudflare Security Events shows no blocks against real T-Mobile IPs
10. No T-Mobile-side retry storms in their PIT dashboard (operator confirms with T-Mobile engineering on a regular cadence)

After 14 days clean, write a short close-out memo with the daily check artifacts attached and link it from `docs/TMOBILE_CALLBACK_INGEST_MVP.md`. Then either:
- Begin Phase 2 design (outbound TAAP, separate flag, separate PR), OR
- Extend the soak by promoting `Device.last_network_event` evidence to additional internal surfaces — explicitly NOT to customer-facing dashboards until a separate governance review.

---

## Escalation

If a red flag is triggered and the first-action step doesn't resolve it within one operator-hour:

1. **Set `FEATURE_TMOBILE_CALLBACK_INGEST=false` on the worker service.** This reverts the worker to legacy-stub behavior; callbacks continue to arrive and archive (`IntegrationPayload` still gets written), but no promotion occurs. The API service flag can stay `true` — that keeps archives happening, which is useful for post-incident replay.
2. Capture the offending payload IDs from `IntegrationPayload`, the job IDs from `jobs`, and the worker log range.
3. Open an issue with the captured artifacts before touching any data.
4. Do **not** delete `IntegrationPayload` rows or modify `jobs` rows during investigation — the audit trail is the primary forensic artifact.
5. Coordinate with T-Mobile engineering before any change that affects callback-URL accessibility (Cloudflare rule, custom domain DNS, Render edge config).

Re-enabling the worker flag after a fix requires a fresh single-callback test (operator-known device) before resuming the daily soak check cadence.
