# Zoho Lifecycle Ingest — Phases 0–5

**Status:** Implemented behind three flags, all default `false`. With the flags
off this is a no-op deploy. Staging/ingest never writes to
`sites`/`devices`/`lines`/`customers`. The only path that writes a production row
is the gated Phase 5 promotion, which touches **only** the additive
`sites.lifecycle_status` columns (never `sites.status`) and only for
operator-confirmed mappings. The working Zoho webhook and its `X-Webhook-Secret`
auth are **unchanged**.

## Why

Zoho CRM is the commercial **source of truth for lifecycle status** (e.g. Webber
Infra shows `Device Activation Status = De-activated`), but True911 didn't know
it. Lifecycle is a **separate axis** from operational status:

| Axis | Source of truth | Values |
|---|---|---|
| **Operational** | True911 telemetry / Health Normalizer | Online / Offline / Attention Needed |
| **Lifecycle** | **Zoho CRM** | Active / Suspended / Deactivated / Pending Install / Unknown |

A device can be operationally Online but lifecycle Deactivated, and vice versa.
Zoho **never** overrides `sites.status` / `devices.status` / `lines.status`.
Lifecycle is staged separately and, in Phase 5, promoted to the additive
`sites.lifecycle_status` (NULL = not governed by Zoho), preserving the site and
leaving operational status untouched.

## Flags

| Flag | Default | Effect when `true` |
|---|---|---|
| `FEATURE_ZOHO_SUBSCRIPTION_INGEST` | `false` | Worker stages Zoho `Subscription_Mgmt` webhooks into shadow tables and records a sanitized payload observation. Off ⇒ event falls through to `needs_mapping` exactly as before. |
| `FEATURE_ZOHO_STATUS_NORMALIZER` | `false` | Ingest also fills `zoho_subscription_records.lifecycle_state` from the normalizer. Off ⇒ raw status stored, `lifecycle_state` stays NULL. |
| `FEATURE_ZOHO_LIFECYCLE_PROMOTION` | `false` | Allows the promote endpoint to **apply** (write `sites.lifecycle_status`). Off ⇒ dry run still works; applying returns 409. |

Set **both `api` and `worker`** services (see the Render env-vars-per-service
pitfall — flag-gated worker behavior is inert if only `api` has the flag).

### Configurable routing (Zoho contract not finalized)

A payload is treated as a subscription event when **either** matches
(case-insensitive, comma-separated, tunable via env without a deploy):

- `ZOHO_SUBSCRIPTION_MODULES` (default `Subscription_Mgmt`) vs `payload.module`
- `ZOHO_SUBSCRIPTION_EVENT_TYPES` (default empty) vs `payload.event_type`

## Data flow

```
Zoho webhook ─(unchanged auth)─▶ _ingest_event ─▶ IntegrationEvent + job
   worker ─▶ integration_processor
      └─ source==zoho AND FEATURE_ZOHO_SUBSCRIPTION_INGEST:
           record_observation (sanitized, matched or not)
           if routing matched: stage ZohoSubscriptionRecord + ExternalRecordMap(unmapped)
              if FEATURE_ZOHO_STATUS_NORMALIZER: lifecycle_state = normalize(status)
```

### Tables (migration 047, additive)

- `external_record_map` — `(source, module, external_record_id)` → optional
  True911 links + `map_status` (`unmapped`/`suggested`/`confirmed`, never
  auto-confirmed).
- `zoho_subscription_records` — Subscription Mgmt ID, Account Name, FacilityName,
  MSISDN, Device Activation Status (raw), Connection Type, Subscription Type,
  MRC, Service Term Ends, normalized `lifecycle_state`, sanitized `raw_json`.
- `zoho_payload_observations` — secret-free structural ledger of inbound payloads
  (matched + unmatched) for learning the real contract from production.

## Review (read-only, RBAC `VIEW_INTEGRATIONS`)

- `GET /api/integrations/zoho/review/subscriptions` — staged records, raw +
  normalized status, `presents_as_active_monitoring`, map status/links.
- `GET /api/integrations/zoho/review/unmapped` — records needing a confirmed map.
- `GET /api/integrations/zoho/review/observations` — sanitized inbound payloads.

Every response carries `read_only: true`.

## Promotion (write, Admin-only `MANAGE_INTEGRATIONS`) — Phase 5

Two explicit operator actions, the only Zoho writes:

- `POST /api/integrations/zoho/mappings/{record_map_id}/confirm` — confirm an
  operator-reviewed mapping: validates the site belongs to the tenant, sets the
  links, and flips `map_status` to `confirmed`. Writes only the staging
  `external_record_map` row.
- `POST /api/integrations/zoho/promote?dry_run=true` — default **dry run**
  returns the plan (current vs proposed `lifecycle_status` per confirmed-mapped
  site) and writes nothing. `dry_run=false` requires
  `FEATURE_ZOHO_LIFECYCLE_PROMOTION=true` (else 409) and writes **only**
  `sites.lifecycle_status` / `lifecycle_source` / `lifecycle_synced_at` — never
  `sites.status`, never a delete. Idempotent (writes only on change).

`sites.lifecycle_status` is added by migration 048 (additive, NULL default).
Alerting/UI may **read** it to suppress/relabel a deactivated site, but operational
status remains the separate, telemetry-owned axis.

## Dry run (writes nothing)

```powershell
cd api
python ../scripts/zoho_webber_infra_dryrun.py
python ../scripts/zoho_webber_infra_dryrun.py --status Active
python ../scripts/zoho_webber_infra_dryrun.py --json real_payload.json
```

Prints the staged record + normalized lifecycle the operator would see, with
secrets redacted. Webber Infra `De-activated` → `lifecycle_state = deactivated`,
`presents_as_active_monitoring = false`.

## Rollout

1. Deploy (flags off — no-op). `alembic upgrade head` creates the three tables.
2. Flip `FEATURE_ZOHO_SUBSCRIPTION_INGEST=true` on **api + worker** to start
   staging + observing. Inspect `/zoho/review/observations` to confirm the real
   Zoho contract; adjust `ZOHO_SUBSCRIPTION_MODULES` / `_EVENT_TYPES` if needed.
3. Flip `FEATURE_ZOHO_STATUS_NORMALIZER=true` to populate `lifecycle_state`.
4. Review `/zoho/review/subscriptions` + `/unmapped`; confirm mappings via
   `POST /zoho/mappings/{id}/confirm`.
5. `POST /zoho/promote` (dry run) to preview. Then flip
   `FEATURE_ZOHO_LIFECYCLE_PROMOTION=true` and `POST /zoho/promote?dry_run=false`
   to write `sites.lifecycle_status` for confirmed-mapped sites — preserving each
   site and never touching operational `sites.status`.

To roll back: set the flags off and restart. The columns/tables/code stay
dormant; previously-written `lifecycle_status` values remain (harmless, NULL
elsewhere) and can be cleared manually if desired.
