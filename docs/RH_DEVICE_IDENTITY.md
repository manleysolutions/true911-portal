# RH Device Identity / Vendor-Mapping Importer (PR #81)

**P1** of the RH readiness plan (`docs/RH_READINESS_AUDIT.md`). RH device health
is **0/51** because the devices are imported inventory rows with no vendor
identity — the classifier can't pick an adapter (no model/carrier) and there's
no identifier (imei/iccid/serial/`vola_org_id`) to key a vendor account on.

This tool **backfills those identity fields** from an operator-supplied mapping
file so the device-health classifier yields probe vendors **and** each device
has a matchable identifier — i.e. becomes monitorable. **Dry-run-first,
refusal-gated, audit-logged.** It writes **only identity fields** — never
status, heartbeat, or operational state.

```bash
# Discovery — list devices that still need mapping (read-only):
python -m app.backfill_rh_device_identity

# Dry-run a mapping file:
RH_DEVICE_MAP_FILE=rh_devices.json python -m app.backfill_rh_device_identity

# Apply:
DRY_RUN=false RH_DEVICE_MAP_FILE=rh_devices.json \
    RH_DEVICE_ACTOR="you@manleysolutions.com" python -m app.backfill_rh_device_identity
```

## Mapping file format
JSON list of objects, each keyed by `device_id` plus any allowed identity field:

```json
[
  {"device_id": "RH-DEV-001", "model": "LM150", "carrier": "T-Mobile",
   "imei": "354000000000001", "vola_org_id": "rh-org-1"},
  {"device_id": "RH-DEV-002", "model": "Cisco-ATA", "msisdn": "8135550100",
   "serial_number": "FOC1234ABCD"}
]
```

**Allowed fields** (identity / vendor-matching only): `model`, `device_type`,
`manufacturer`, `carrier`, `hardware_model_id`, `serial_number`, `imei`,
`iccid`, `msisdn`, `vola_org_id`, `sim_id`, `imsi`. Anything else refuses the
batch.

## What makes a device monitorable
The classifier yields a **probe vendor** from the model (e.g. `LM150` → `vola`)
or carrier (`T-Mobile` → `tmobile`), **and** the device must carry a matchable
identifier (`imei`/`iccid`/`serial_number`/`msisdn`/`vola_org_id`/`starlink_id`).
The planner reports `becomes_monitorable` per device so you can see which rows
still need an identifier even after mapping.

## Safety contract
| Rule | Behaviour |
|---|---|
| `DRY_RUN` | defaults **true** — nothing written unless `DRY_RUN=false`. |
| Backfill scope | only **empty** fields are filled. |
| Conflict | a mapping value that differs from an existing non-empty value **REFUSES the batch** (`RH_DEVICE_ALLOW_OVERWRITE=true` to force). |
| Bad identifiers | malformed `imei` (15 digits) / `iccid` (18–20) / `msisdn` (10–15) **REFUSE the batch**. |
| Unknown field / device / duplicate id | **REFUSE the batch**. |
| Atomicity | all-or-nothing — any refusal ⇒ nothing written. |
| Scope | identity fields only; **status/heartbeat never touched**; no other tenant. |

## What it writes (apply only)
Per changed device, in one transaction: the named identity fields, plus one
`audit_log` entry (category `device`, action `backfill_identity`) recording the
actor, each field's old→new, the resulting probe vendors, and
`becomes_monitorable`. No deletes, no migration.

## Next in sequence
**PR #82** stands up telemetry/heartbeat ingestion for the now-mapped vendors so
`last_heartbeat` populates and the device-health (30-pt) component can score.
Mapping a device's identity is necessary but not sufficient — it must still
report before it counts as fresh.
