# Zoho Lifecycle Ingest (staging) — Phases 0–4

**Status:** Implemented behind two flags, both default `false`. With the flags
off this is a no-op deploy. Nothing here writes to `sites` / `devices` / `lines`
/ `customers`; the working Zoho webhook and its `X-Webhook-Secret` auth are
**unchanged**.

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
Lifecycle is staged separately; promotion to an additive `lifecycle_status` is a
**deferred, separately-gated Phase 5** (not in this work).

## Flags

| Flag | Default | Effect when `true` |
|---|---|---|
| `FEATURE_ZOHO_SUBSCRIPTION_INGEST` | `false` | Worker stages Zoho `Subscription_Mgmt` webhooks into shadow tables and records a sanitized payload observation. Off ⇒ event falls through to `needs_mapping` exactly as before. |
| `FEATURE_ZOHO_STATUS_NORMALIZER` | `false` | Ingest also fills `zoho_subscription_records.lifecycle_state` from the normalizer. Off ⇒ raw status stored, `lifecycle_state` stays NULL. |

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

Every response carries `read_only: true`. No promote/write endpoint exists yet.

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
4. Review `/zoho/review/subscriptions` + `/unmapped`. Confirm mappings.
5. (Deferred Phase 5) Promote confirmed lifecycle to an additive
   `sites.lifecycle_status`, preserving the site and never touching operational
   status.

To roll back: set the flags off and restart. The tables/code stay dormant.
