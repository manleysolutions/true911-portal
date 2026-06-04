# Asset Liveness Audit (by MSISDN)

**Read-only.** For each MSISDN, reports the True911 device / line / site / customer
plus liveness signals and recommends a disposition: **active / inactive / orphaned
/ unknown** — to decide whether an asset is genuinely in use or a historical record
to retire.

## Command
```bash
python -m app.audit_asset_liveness \
  --msisdn 7869600498 --msisdn 7869600490 --msisdn 7869600588 --msisdn 7869600567
python -m app.audit_asset_liveness --export-json webber_assets.json
```
With no `--msisdn`, defaults to the four Webber MSISDNs.

## Fields per MSISDN
Device ID, Line ID, Site ID, Customer ID (+ name/status), device/line/site status,
network status, last heartbeat, last network event, last status update, last call
activity, last telemetry, open alert count, telemetry source, data usage, E911
status + location. Duplicate maps (MSISDN → >1 device/line) are flagged.

## Disposition rules
| Disposition | Rule |
|---|---|
| `unknown` | No device **and** no line carries the MSISDN |
| `orphaned` | A device/line exists but has **no customer owner** (dangling) |
| `active` | Owned **and** a liveness signal within 30 days **and** an active/provisioning status |
| `inactive` | Owned but stale / no recent liveness — a **historical** record (retire candidate) |

Liveness = the most recent of `last_heartbeat`, `last_network_event`, last call
activity, last telemetry.

## Safety / data sources
Read-only — only SELECTs; no writes, no status/customer changes, no migrations.
Core fields use `devices` / `lines` / `sites` / `customers`. Activity sources
(`call_records`, `command_telemetry`, `incidents`) are queried **best-effort** — a
missing/renamed table degrades that field to `n/a` rather than failing the report.
`--export-json` writes only the operator-requested file.

## Migration impact
**None.**
