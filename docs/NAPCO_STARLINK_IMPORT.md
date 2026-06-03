# NAPCO StarLink Classification + Portal Status Import

Most of Restoration Hardware's "unknown" devices are **NAPCO StarLink fire
communicators** — supplied and billed by Manley Solutions (Manley pays the NAPCO
MRC and rebills the subscriber) and managed in the **NAPCO portal**. There is no
public API, but the portal exports an XLS/XLSX with device status, last
communication, name/address, trouble condition, etc.

This PR does two things:
1. **Classifier recognition** — StarLink models are now classified as
   Manley-managed vendor devices, not "unknown".
2. **Portal status import** — a dry-run-first command that ingests the portal's
   XLS export as telemetry.

## 1. Classification
`classify()` now recognises the NAPCO StarLink family and returns:

| Field | Value |
|---|---|
| `vendor_cloud` | `napco_portal` |
| `vendor_managed` | `true` |
| `device_family` | `napco_starlink` |
| `monitoring_source` | `napco_xls_import` |
| `connection_type` | `cellular` |
| `probe_vendors` | `()` — **no live probe**; monitored via XLS import |

Recognised by the unambiguous model codes (`SLELTE`, `SLE-LTEVI`, `SLEMAXVI`,
`SLE5G`), "StarLink Communicator", or a **NAPCO** manufacturer/carrier — e.g. a
"Fire Alarm Control Panel" with carrier `Napco`. Bare "Starlink" (SpaceX
satellite internet) is **deliberately not** matched.

## 2. Import command
```bash
# Dry run (default) — prints matches + proposed updates, writes nothing:
NAPCO_IMPORT_FILE=/path/to/export.xlsx python -m app.import_napco_portal_status

# Apply:
DRY_RUN=false NAPCO_IMPORT_FILE=/path/to/export.xlsx python -m app.import_napco_portal_status
```
`.xlsx`/`.xls`/`.csv` are accepted (save-as-CSV works if you prefer). Scoped to
one tenant (`NAPCO_IMPORT_TENANT`, default `restoration-hardware`).

### How to export from the NAPCO portal
1. Sign in to the NAPCO StarLink dealer portal (Manley account).
2. Open the account/device list for the subscriber.
3. **Export to Excel (XLS/XLSX)** — the default device report.
4. Save the file locally and pass its path as `NAPCO_IMPORT_FILE`.

> This PR does **not** scrape or call the NAPCO portal. You export the file
> manually; the command reads that file.

### Real export format (validated against `Radiolist-…​.xlsx`, 2026-06-03)
The NAPCO StarLink dealer portal export is a single `RadioList` worksheet whose
headers are **NAPCO-native camelCase with no spaces**. The 28 columns include:

`RadioNumber · ICCID · DealerId · SubscriberName · DealerCompany · DealerEmail ·
LastSignalReceived · OnlineDate · SIMStatus · FirmwareVer · … · Plan · GenTech`

Key mapping (the importer's column detection handles both this real export and
generic exports; headers are matched case-insensitively by substring, most
specific first):

| Canonical field | Real NAPCO header | Also accepts |
|---|---|---|
| serial | **RadioNumber** | Serial Number, ESN, Device Serial |
| iccid | **ICCID** | SIM ICCID |
| portal_status | **SIMStatus** | Comm Status, Communication Status, Status |
| last_comm | **LastSignalReceived** | Last Communication, Last Check-In, Last Signal |
| name | **SubscriberName** | Account Name, Site Name, Name |
| config | **Plan** | Configuration, Profile |
| gen_tech | **GenTech** (`4G:LTE`/`FirstNet`/`LTE-M`/`UNK`) | Network Tech |
| device_id | _(absent in NAPCO export)_ | Device ID |
| address / trouble / model | _(absent in NAPCO export)_ | Address, Trouble, Model |

`SIMStatus` is the SIM **provisioning** state (the sample is 100% `Active`), not a
live comm status — so liveness comes from **LastSignalReceived recency**, and
`network_status=online` is applied **only** alongside a fresh `last_comm`.
`GenTech` is archived for diagnostics, **not** written to `Device.carrier`
(it is network tech, not a carrier name). A file with **none** of serial / ICCID /
device-id columns is rejected (nothing written).

> The export is the dealer's **entire** radio list, so non-RH `SubscriberName`
> rows can appear; they simply don't match the RH tenant's devices and become
> review-required — never written.

### Matching rules
1. **Serial number** first — `RadioNumber` vs `Device.serial_number` (case-insensitive).
2. **ICCID** second — `ICCID` vs `Device.iccid` (the **strongest** join for these
   cellular communicators; present on both sides).
3. **Device ID** third (if the export carries one).
4. **Name/address fallback** → row flagged **review-required**, never
   auto-applied. The operator resolves these by aligning the serial/ICCID.

### Proposed updates (apply only)
A **whitelist** of telemetry fields — nothing else is writable here:
- `last_heartbeat` + `last_network_event` ← parsed **last communication**
- `network_status` ← portal status (`trouble`/`offline` are **non-healthy**)
- `telemetry_source` ← `napco_portal` (marks the monitoring source)
- `carrier` ← only when currently empty (backfill, never overwrite)

Each applied row gets one `audit_log` entry (category `device_health`, action
`napco_xls_import`) and the parsed row is archived to `integration_payloads`
(source `napco_portal`, inbound). **E911, lifecycle status, and Assurance labels
are never touched.**

### Staleness guard
`last_heartbeat`/`last_network_event` are written **only if newer** than what's
stored — a stale "last communication" cannot move a device's heartbeat backwards,
and a stale row does **not** regress `network_status` (logged `skipped stale`).
A heartbeat is only ever a vendor's real timestamp — never fabricated.

## Sample dry-run output (against the real `RadioList` export)
```
NAPCO StarLink portal status import — tenant 'restoration-hardware'
  mode: DRY RUN (no writes)
  columns detected: {'serial': 'RadioNumber', 'iccid': 'ICCID', 'portal_status': 'SIMStatus',
                     'last_comm': 'LastSignalReceived', 'name': 'SubscriberName',
                     'config': 'Plan', 'gen_tech': 'GenTech'}
  RH-...7721           match=iccid status='Active' -> net=online last_comm=2026-06-03 07:19:47+00:00
      would update {'telemetry_source': 'napco_portal', 'last_heartbeat': ..., 'last_network_event': ..., 'network_status': 'online'}
  RH-...9777           match=iccid status='Active' -> net=(unchanged) last_comm=2025-05-07 20:30:30+00:00
      · skipped stale last communication (2025-05-07... <= stored 2026-06-01...) — no regression
  REVIEW  serial='10719648' iccid='8914...7854' name='Restoration Hardware 632 Vero Beach' — no serial/ICCID/device_id match; operator review required
SUMMARY
  rows:99  matched_serial:0  matched_iccid:<n>  matched_device_id:0  review_required:<99-n>  updated:0(dry)  stale_skipped:<s>  offline_or_trouble:0
```
The exact `matched_iccid` / `review_required` split depends on how many of the 99
exported radios have a corresponding `Device.iccid` in the RH tenant — that
requires running where the database is reachable (read-only; `DRY_RUN` rolls back).

## Risks
- **Looking online without being online** — mitigated: only the real last-comm
  timestamp is written, guarded against staleness; `network_status` is not set
  from a stale row.
- **Wrong-device write** — mitigated: serial/device-id match only; name/address
  is review-required, never auto-applied.
- **Scope creep** — write whitelist makes E911/status/Assurance unwritable here.
- **Column drift** — if the portal renames columns, detection logs what it found
  and rejects a file with no serial/device-id column rather than guessing.

## Rollback
- **Dry run** writes nothing.
- **Apply** only advances telemetry timestamps/state and marks
  `telemetry_source`; it never deletes and never touches identity/E911/status.
  Prior values remain in the `audit_log` detail; re-run after fixing the export
  (the staleness guard prevents regressions). No migration → no schema rollback.

## Migration impact
**None.** Writes only existing Device columns and appends `integration_payloads`
rows. Adds `openpyxl` to `requirements.txt` (XLS reader) — a dependency, not a
migration.

## RH impact
Reclassifies the bulk of RH's "unknown" inventory as `napco_starlink` /
`napco_xls_import` (no longer `unknown_device_type` in the discovery audit) and
gives them a real, auditable liveness source from the portal export — moving them
toward fresh `last_heartbeat` and lifting the device-health score component.

## Next operator steps
1. Export the StarLink device report from the NAPCO portal.
2. Dry-run: `NAPCO_IMPORT_FILE=export.xlsx python -m app.import_napco_portal_status`.
3. Resolve any **review-required** rows by capturing the device serial.
4. Apply with `DRY_RUN=false` once the dry run looks right.
5. Re-run the RH telemetry / score audits to confirm the StarLink fleet is fresh.
