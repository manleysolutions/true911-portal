# Operational Source Snapshots (D-024)

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`,
> `DECISIONS.md` D-024. PR #187 of the RH Customer Completion Program
> (`RH_COMPLETION_PROGRAM.md`).

## 1. What a snapshot is

One imported export file for one tenant, stored as **immutable evidence**:

| Source | `source_system` | Parser | Status map |
|---|---|---|---|
| NAPCO StarLink RadioList (xlsx/csv) | `NAPCO` | `napco_radiolist.v1` | `napco.simstatus.v1` |
| T-Mobile / Infatrac inventory (csv) | `T_MOBILE` | `tmobile_infatrac.v2` | `tmobile.infatrac.v1` |
| Verizon wireless inventory (csv/xlsx) | `VERIZON` | `verizon_inventory.v2` | `verizon.servicestatus.v1` |
| Red Pocket inventory | `RED_POCKET` | `redpocket.v0-provisional` | `redpocket.v0-provisional` |

Snapshots are evidence, **not** mirrors of the source system. They are written
once, never updated, never deleted, and de-duplicated by the file's SHA-256 per
(tenant, source). A newer export is a new snapshot; the older one stays
auditable. Importing never writes a source system, canonical services, E911, the
registry or operator decisions. The lifecycle reconciliation that consumes
snapshots is PR #188.

Tables (migration `055`): `source_snapshots` (file SHA-256, basename, size,
parser / status-map / attribution-rule versions, source effective time + basis,
import time + operator, row counts, masked summary) and `source_snapshot_records`
(row number, source record key, identifier type, normalised MSISDN / ICCID / IMEI
/ NAPCO radio, **raw status + interpreted lifecycle + rule**, activity time,
location hint, attribution basis + confidence, raw-row SHA-256, allow-listed
attributes).

### Actual export structures (headers matched after normalisation)

Header matching lower-cases and ignores whitespace / punctuation, so the leading
spaces the Infatrac CSV carries on some headers match; source **values** are never
altered. A file carrying another source's signature headers is rejected.

* **NAPCO RadioList (28):** RadioNumber, ICCID, DealerId, SubscriberName,
  DealerCompany, DealerEmail, LastSignalReceived, OnlineDate, SIMStatus,
  FirmwareVer, DebounceTime, PollingRate, AutoEnrollCSTel, AutoEnrollCSAcct,
  Primary / Backup / Duplicate / DuplicateBackup CS Receiver / Acct / ReceiverType,
  Plan, GenTech. Read: RadioNumber (key), ICCID, SIMStatus, LastSignalReceived
  (activity), SubscriberName (label), OnlineDate, FirmwareVer, DebounceTime,
  PollingRate, Plan, GenTech, receiver types; receivers reduced to
  configured yes/no. Never read: dealer id / company / email, AutoEnroll and all
  CS account numbers.
* **T-Mobile / Infatrac (13):** Partner, MSISDN, Status, Package, Last CDR date,
  Idle, Unbilled / Daily / 3-Day / 7-Day / 14-Day / 30-Day Voice min, Label. MSISDN
  is the key; Last CDR date is activity; Label is tenant-attribution / location
  evidence **only and never assigns a service type**; the other columns are kept as
  operational attributes.
* **Verizon (13):** Unnamed: 0, Billing account name, Billing account number, Cost
  Center, Mobile number, Username, Wireless ID, Equipment Model, Upgrade date,
  Device ID, SIM ID, Service status, Suspended date. Read: Mobile number (key),
  Device ID (IMEI, or a 14-hex MEID kept and flagged `IMEI_NONSTANDARD_MEID`), SIM
  ID (ICCID), Service status, Cost Center (label), Equipment Model, Upgrade date,
  Suspended date. **Never read or stored:** `Unnamed: 0` (CSV index), Billing account
  name / number, Username, Wireless ID — no canonical need, privacy by default.

## 2. Status interpretation

Each source has one versioned map; only documented statuses are mapped. **Every
unmapped or empty status is `UNKNOWN` — never active.** The raw value and the rule
(`<map version>:<normalised raw>-><LIFECYCLE>`) are stored with every record so a
later map version can re-interpret history.

| Source | CURRENT | SUSPENDED | DECOMMISSIONED | Deliberately UNKNOWN |
|---|---|---|---|---|
| NAPCO `SIMStatus` | Active | Suspend | Terminate | anything else |
| T-Mobile `Status` (observed Active / Suspended / Deactivated) | Active, Activated | Suspend(ed) | Deactivated, Cancelled, Terminated, Disconnected | Hotlined, porting, pending states |
| Verizon `Service status` (observed Active) | Active | Suspend(ed) | Deactive, Deactivated, Terminated | pre-active, ready, **connected** (activity, not lifecycle), anything unseen |
| Red Pocket (provisional) | Active | Suspend(ed) | Cancelled, Deactivated, Terminated | **Expired** (plan lapse is not decommissioning) |

Lifecycle is **currentness only**. NAPCO / carrier ACTIVE never means healthy,
monitored, tested or E911-verified; activity (NAPCO `LastSignalReceived`, Infatrac
`Last CDR date`) is stored separately as `activity_at` and is not interpreted.

## 3. Tenant attribution

Carrier and dealer exports contain many customers. A row is stored for a tenant
only when:

* **A — identifier (HIGH):** an exact normalised identifier matches an asset this
  tenant holds (devices, lines, SIMs, registry mappings, canonical assets) and no
  other tenant holds it; or
* **B — label (MEDIUM):** the label passes the tenant profile's explicit rule. RH
  profile `rh.attribution.v1`: the full phrase "Restoration Hardware" / "Restoration
  Hdwr", or the standalone token "RH" **with a 3–4 digit store code** ("RH 147",
  "RH-506", "RH Houston #130").

Never attributed: rows with no tenant evidence, rows whose identifier belongs to
another tenant. **AMBIGUOUS** (reported, never stored): a bare "RH" without a store
code, an identifier held by two tenants, an RH label on another tenant's
identifier. A label establishes the **tenant only**, never a building. Tenants
without a profile attribute by identifier only.

## 4. Privacy

Attributes are allow-listed per adapter. Dealer ids/emails, central-station
receiver numbers and account numbers are **never stored** (NAPCO receivers are
reduced to `primary_cs_configured` / `backup_cs_configured` booleans for later
monitoring evidence). A SHA-256 of the complete raw row is kept so a stored record
can be proven against the original export without retaining it. Reports mask
ICCID / IMEI / radio ids. Malformed identifiers (scientific notation, wrong
length) are dropped with a recorded issue, never repaired; NAPCO's 20-character
alphanumeric SIM ids for 3G:CDMA radios are kept and flagged `ICCID_NONSTANDARD`.

## 5. Effective time and freshness

The effective time is the moment the SOURCE produced the export. Precedence —
never guessed:

1. **OPERATOR** — explicit `--effective-at` (ISO-8601 **with timezone**). Use it
   for every first production import.
2. **SOURCE** — a source-native, timezone-aware timestamp the parser documents as
   authoritative (none of the current adapters has one).
3. **FILENAME** — a file-name timestamp only when the parser establishes its
   timezone. The NAPCO RadioList name carries a timestamp whose timezone is **not**
   established, so it is recorded as `filename_timestamp_candidate` and never used.
4. **UNDATED** — otherwise. Stored, but it can never establish freshness.

`SOURCE_SNAPSHOT_FRESHNESS_DAYS = 7` (inventory certification only), measured from
the effective time, never the import time. Freshness says nothing about
operational monitoring health.

## 6. Production workflow

```bash
# 1. upload the export to /tmp on the Render api shell (never into the repo)
# 2. dry-run (default) - masked report, nothing written
python -m scripts.source_snapshot_import --tenant restoration-hardware --source NAPCO --file /tmp/Radiolist-<ts>.xlsx --effective-at 2026-09-30T12:29:03-04:00
# 3. review attribution / ambiguous / invalid rows, then apply
python -m scripts.source_snapshot_import --tenant restoration-hardware --source NAPCO --file /tmp/Radiolist-<ts>.xlsx --effective-at 2026-09-30T12:29:03-04:00 --apply --imported-by <you>
# 4. verify the persisted snapshot
python -m scripts.source_snapshot_import --tenant restoration-hardware --show <id>
# 5. delete the raw file from /tmp (the snapshot and its SHA-256 remain)
```

Every file needs `--effective-at <export time with timezone>`; without it the
snapshot is stored `UNDATED` and can never be fresh. Re-running an import of the same
file reports `UNCHANGED`. Red Pocket stays provisional until a production export
is reviewed; its absence does not block the architecture.
