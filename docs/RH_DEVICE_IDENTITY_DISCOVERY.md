# RH Device Identity Discovery Audit (PR #84)

**Read-only.** The RH telemetry dry-run (`app.sync_rh_device_telemetry`) showed
the real blocker is **device identity**, not telemetry:

```
Total RH devices: 51
Ready / probed:   11
Manual required:   6
Unmapped:         34   ← inventory rows with no vendor adapter / no monitorable identity
Fresh heartbeats:  0
T-Mobile:         unavailable (SubscriberInquiry requires TMOBILE_ACCOUNT_ID)
```

This audit explains, **per device**, what it is and exactly what information is
needed to make it monitorable — turning unknown inventory into an operator
checklist and a mapping template that feeds the PR #81 importer.

## Purpose
Know what the 34 unmapped RH devices are **before** trying to monitor them. The
audit never guesses a final mapping — it surfaces likely class/vendor and the
missing fields, so an operator can fill in the truth.

## Command
```bash
python -m app.audit_rh_device_identity                                   # print report
python -m app.audit_rh_device_identity --export /tmp/rh_identity.json    # + JSON export
python -m app.audit_rh_device_identity --export /tmp/rh_identity.csv     # + CSV export
RH_IDENTITY_TENANT=restoration-hardware python -m app.audit_rh_device_identity
```
Read-only — it `SELECT`s, prints, and (optionally) writes an export file. It does
**not** update the database, run the identity backfill, or run telemetry apply.

## What it outputs per device
Identity + context (device_id, display name, site_id/name, customer_id, tenant_id,
model, device_type, vendor/telemetry_source, carrier, msisdn, imei, iccid, serial,
status, last_heartbeat, network_status, import metadata), the **classifier result**
(connection/voice type, vendor cloud), the **adapter candidate**, a one-line
**category + reason**, and — for unmapped/blocked devices — an **identity hint**
(likely vendor/class, missing fields, recommended action).

## Categories (one per device)
| Category | Meaning | Operator action |
|---|---|---|
| `monitorable_now` | configured live adapter + identifier present | none — telemetry sync will work |
| `monitorable_after_tmobile_account_id` | T-Mobile + msisdn present, blocked only by `TMOBILE_ACCOUNT_ID` | set the wholesale account ID (arrives via activation callback) |
| `needs_vendor_credentials` | live adapter + identifier present but adapter unconfigured | provide vendor credentials (e.g. `VOLA_EMAIL`/`VOLA_PASSWORD`) |
| `manual_verification_required` | no automated live probe for this class yet (stub/analog) | record a real test via `app.record_verification_test` |
| `needs_identity_mapping` | blank inventory row, or a live vendor missing its identifier | capture model/vendor + the required identifier |
| `unknown_device_type` | has model/type text but no adapter recognises it | physically identify; capture a recognised model |
| `data_conflict` | contradictory identity fields | resolve the contradiction before mapping |

`data_conflict` checks are conservative and concrete: `vola_org_id` set but the
model/type doesn't classify as Vola; or a `serial_number` that looks like a phone
number but differs from `msisdn`.

## Summary counts
total devices · monitorable now · blocked by T-Mobile account ID · manual
verification required · unmapped (`needs_identity_mapping` + `unknown_device_type`)
· data conflicts · missing IMEI · missing ICCID · missing MSISDN · missing vendor ·
missing model.

## Example output
```
  RH-DEV-007  [monitorable_now]
    site=RH-TAMPA-01 (Tampa Store)  cust=7  status=active
    model='LM150' type='cellular' carrier='T-Mobile' vendor='vola'
    msisdn=None imei='354000000000007' iccid=None serial='SN7'
    classifier={'connection_type':'cellular','voice_type':'volte','vendor_cloud':'vola',...}  probes=['vola','tmobile']  adapter=vola
    → vola live probe ready

  RH-DEV-031  [needs_identity_mapping]
    site=RH-MIAMI-02 (Miami Store)  cust=7  status=active
    model=None type=None carrier=None vendor=None
    msisdn=None imei=None iccid=None serial=None
    → blank inventory row — no model / vendor / identifier
    HINT: likely unknown / unknown; missing -; action: Physically identify device; capture model + vendor + one identifier

SUMMARY
  total devices                 : 51
  monitorable_now               : 9
  monitorable_after_tmobile_account_id : 2
  manual_verification_required  : 6
  needs_identity_mapping        : 28
  unknown_device_type           : 6
  data_conflict                 : 0
  missing_imei                  : 40
  ...
```
(Counts illustrative — real numbers come from running it against prod.)

## How to use the output to prepare the PR #81 mapping file
1. Run with `--export /tmp/rh_identity.csv` (or `.json`).
2. For each row **not** `monitorable_now`, fill in the truth using the template
   schema (`docs/templates/rh_device_identity_mapping_template.json`):
   `suggested_model`, `suggested_vendor`, and the required identifier
   (`imei`/`iccid`/`msisdn`/`serial_number`). Mark `manual_verification_only: true`
   for devices with no automated source.
3. Convert the filled template into the importer's JSON shape (`device_id` +
   identity fields) and dry-run **PR #81** (`app.backfill_rh_device_identity`).
4. Then re-run the telemetry dry-run (**PR #83**) and confirm devices move to
   `ready`.

## Mapping template
`docs/templates/rh_device_identity_mapping_template.json` — the exact per-row
schema the operator fills (blanks + `manual_verification_only` + `operator_notes`).

## Risk assessment
- **Read-only** — cannot change production data (asserted by a source-scan test;
  the session also `rollback`s defensively).
- **No secrets in exports** — exports carry only whitelisted identity/diagnostic
  fields; credentials/PoP keys are never read or written (asserted by test).
- **No false mappings** — the audit only *suggests*; the operator supplies the
  final identity, so a wrong guess can't silently reach the importer.

## Next recommended action
Run the audit with `--export`, fill the mapping template for the unmapped/blocked
devices (prioritising sites with active service), and feed it to the PR #81 dry
run. Set `TMOBILE_ACCOUNT_ID` to unblock the `monitorable_after_tmobile_account_id`
devices once the wholesale account ID is known.

## Migration impact
**None.** Read-only; uses existing columns.
