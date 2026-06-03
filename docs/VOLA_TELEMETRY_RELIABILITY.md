# Vola Telemetry Reliability (PR #72)

Fixes the Belle Terre LM150 false-OFFLINE: devices online in Vola Cloud showed
`ASSURANCE.DEVICE_OFFLINE` because True911 had no fresh liveness signal.

## Root cause (from the prior audit)
- The Vola adapter's `lastUpdateTime` parser accepted only three string formats →
  `last_seen=None` → `Device.last_heartbeat` never written.
- The only liveness persisted for an online device was `vola_last_sync` (a
  *sync-time proxy*), refreshed only when the sync runs.
- `sync_device_health` was a **manual CLI** — no scheduler. `vola_last_sync`
  aged past the normalizer's 300 s staleness window → OFFLINE.

## What this PR changes (Vola telemetry reliability + cadence only)
1. **Hardened parser** (`adapters/vola.py` `_parse_vola_timestamp`): now handles
   ISO-8601, several human string layouts, and **epoch seconds/milliseconds**
   (int / float / numeric string). Returns `None` when untrusted — never
   fabricates a timestamp.
2. **Alternate heartbeat keys**: the adapter picks the first populated of
   `lastUpdateTime, last_update, lastActiveTime, lastOnlineTime, lastSeen,
   updateTime, heartbeatTime`.
3. **Safe debug dump**: run the sync with `DEVICE_HEALTH_DEBUG=true` to print the
   named Vola fields (`deviceSN`, `status`, `lastUpdateTime` + alternates,
   firmware, ip, signal) and the parsed `last_seen`. Console-only (the sync is a
   CLI); never a customer surface; never the whole payload.
4. **Online status mapping unchanged & confirmed**: online → `network_status="online"`,
   `vola_last_sync=now`, and `last_heartbeat=last_seen` when parseable.
   `last_heartbeat` is the primary liveness signal; `vola_last_sync` is the proxy.
5. **Scheduled sync**: a Render **Cron Job** runs `python -m app.sync_device_health`
   every 5 minutes (see below).

**Not changed:** Assurance label rules, the 300 s threshold, E911 status, T-Mobile
OAuth/PoP, Vola TR-069 control. No migration.

> Confirm the real format first: this parser is robust but the exact production
> `lastUpdateTime` shape must be **observed**, not assumed. Run the dry-run with
> `DEVICE_HEALTH_DEBUG=true` (below) and confirm `_parsed_last_seen` is non-null.
> If a never-before-seen format appears, add it to `_VOLA_TS_FORMATS` — don't guess.

## Render Cron setup

### Option A — Blueprint (render.yaml, included in this PR)
This PR adds a `type: cron` service `true911-device-health-sync` (schedule
`*/5 * * * *`, `DRY_RUN=false`). On the next Blueprint sync Render creates it.
**You must then set the Vola secrets on that cron service** (they are
`sync: false`, dashboard-managed):

1. Render Dashboard → `true911-device-health-sync` → **Environment**.
2. Add: `VOLA_EMAIL`, `VOLA_PASSWORD`, `VOLA_ORG_ID` (and `VOLA_BASE_URL` if not
   the default `https://cloudapi.volanetworks.net`). Use the same values already
   on the API/worker for Vola.
3. Save → the next scheduled run picks them up.

### Option B — Dashboard only (if you don't auto-apply blueprints)
1. Render Dashboard → **New** → **Cron Job**.
2. Repo = this repo; **Root Directory** = `api`; Runtime = Python.
3. **Schedule**: `*/5 * * * *`.
4. **Build Command**: `pip install -r requirements.txt`.
5. **Command**: `python -m app.sync_device_health`.
6. **Environment**: `DRY_RUN=false`, `APP_MODE=production`, `DATABASE_URL` (link
   the `true911-db` connection string), `VOLA_EMAIL`, `VOLA_PASSWORD`,
   `VOLA_ORG_ID`, `VOLA_BASE_URL` (if non-default).
7. Create. Verify the first run's logs show `status=online` and
   `last_seen=<timestamp>` for the LM150s.

> Cadence note: the cron runs every 5 min and the staleness window is 5 min, so
> `vola_last_sync` alone is borderline. With the parser fix, `last_heartbeat`
> carries the device's real Vola contact time (LM150s inform Vola frequently),
> which is the durable signal that keeps the device fresh between cron runs. If
> you ever see edge flapping, tighten the schedule to `*/3 * * * *`.

## Verification commands

Run from the API service shell (Render → `true911-api` → **Shell**), `rootDir=api`.
Replace the tenant if Belle Terre's tenant_id differs from `integrity-pm`.

**1. Dry-run sync for Belle Terre only — captures the real Vola format, writes nothing:**
```bash
DRY_RUN=true DEVICE_HEALTH_DEBUG=true \
DEVICE_HEALTH_TENANT=integrity-pm DEVICE_HEALTH_SITE=IPM-BELLE-TERRE \
python -m app.sync_device_health
# Look for: status=online, last_seen=<ts>, and [DEBUG vola fields] {... _parsed_last_seen: <ts>}
```

**2. Apply sync for Belle Terre only — writes Device.last_heartbeat etc.:**
```bash
DRY_RUN=false \
DEVICE_HEALTH_TENANT=integrity-pm DEVICE_HEALTH_SITE=IPM-BELLE-TERRE \
python -m app.sync_device_health
```

**3. Confirm last_heartbeat is populated for the three devices (psql):**
```bash
psql "$DATABASE_URL" -c "SELECT device_id, status, last_heartbeat, vola_last_sync, network_status \
FROM devices WHERE serial_number IN \
('VOLA00325600226','VOLA00325600227','VOLA00325600230');"
```

**4. Call the Assurance endpoint (needs FEATURE_ASSURANCE_ENGINE=true + a token):**
```bash
curl -s https://true911-api.onrender.com/api/assurance/site/IPM-BELLE-TERRE \
  -H "Authorization: Bearer $TOKEN" | jq '.assurance_label, [.reasons[].code]'
```

**5. Confirm DEVICE_OFFLINE is gone (heartbeat fresh):** the `reasons` array
should no longer contain `ASSURANCE.DEVICE_OFFLINE`.

## Before / after (Belle Terre)

**Before:** `Critical` — `ASSURANCE.E911_UNVERIFIED`, `ASSURANCE.DEVICE_OFFLINE`,
`ASSURANCE.TEST_MISSING`.

**After (heartbeat fresh):** `Critical` (still) — `ASSURANCE.E911_UNVERIFIED`,
`ASSURANCE.TEST_MISSING`. **`DEVICE_OFFLINE` is gone.** The label stays Critical
because E911 is still `provided` (not `validated`) — by design; E911 is a
separate task. Belle Terre is **not** marked Protected.

## Risks
- Cron writes to prod every 5 min (additive Device-health fields only; the sync
  never creates/deletes and self-guards on missing creds → safe no-op without
  Vola secrets). Verify the first run via the dry-run above.
- The cron fetches the full Vola device list once per device — fine for the
  current fleet; revisit for scale.
- If Vola uses a `lastUpdateTime` format outside the supported set, `last_heartbeat`
  stays NULL and the device relies on the `vola_last_sync` proxy — the dry-run
  debug surfaces this so the format can be added.

## Rollback
- **Disable cron:** Render Dashboard → `true911-device-health-sync` → Suspend (or
  remove the `type: cron` block from render.yaml and re-sync). Liveness reverts to
  manual syncs — no data harm.
- **Revert code:** `git revert` this PR. The parser/adapter changes are additive
  and read-only at request time; reverting restores the prior parser. No migration
  to undo.
