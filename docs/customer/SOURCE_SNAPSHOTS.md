# Operational Source Snapshots (D-024)

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`,
> `DECISIONS.md` D-024. PR #187 of the RH Customer Completion Program
> (`RH_COMPLETION_PROGRAM.md`).

## 1. What a snapshot is

One imported export file for one tenant, stored as **immutable evidence**:

| Source | `source_system` | Parser | Status map |
|---|---|---|---|
| NAPCO StarLink RadioList (xlsx/csv) | `NAPCO` | `napco_radiolist.v1` | `napco.simstatus.v1` |
| T-Mobile / Infatrac (Genesis) inventory | `T_MOBILE` | `tmobile_infatrac.v1` | `tmobile.infatrac.v1` |
| Verizon ThingSpace inventory export | `VERIZON` | `verizon_thingspace.v1` | `verizon.thingspace.v1` |
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

## 2. Status interpretation

Each source has one versioned map; only documented statuses are mapped. **Every
unmapped or empty status is `UNKNOWN` — never active.** The raw value and the rule
(`<map version>:<normalised raw>-><LIFECYCLE>`) are stored with every record so a
later map version can re-interpret history.

| Source | CURRENT | SUSPENDED | DECOMMISSIONED | Deliberately UNKNOWN |
|---|---|---|---|---|
| NAPCO `SIMStatus` | Active | Suspend | Terminate | anything else |
| T-Mobile | Active, Activated | Suspend(ed) | Deactivated, Cancelled, Terminated, Disconnected | Hotlined, pending states |
| Verizon `State` | active | suspend(ed) | deactive, deactivated, terminated | pre-active, ready, **connected** (activity, not lifecycle) |
| Red Pocket (provisional) | Active | Suspend(ed) | Cancelled, Deactivated, Terminated | **Expired** (plan lapse is not decommissioning) |

Lifecycle is **currentness only**. NAPCO / carrier ACTIVE never means healthy,
monitored, tested or E911-verified; activity (NAPCO `LastSignalReceived`, Verizon
last connection) is stored separately as `activity_at` and is not interpreted.

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

## 5. Freshness

`SOURCE_SNAPSHOT_FRESHNESS_DAYS = 7` (inventory certification only). Measured from
the **source effective time** (operator-supplied `--effective-at`, or the NAPCO
RadioList filename timestamp) — never the import time. A snapshot without an
effective time is `UNDATED` and never fresh. Freshness says nothing about
operational monitoring health.

## 6. Production workflow

```bash
# 1. upload the export to /tmp on the Render api shell (never into the repo)
# 2. dry-run (default) - masked report, nothing written
python -m scripts.source_snapshot_import --tenant restoration-hardware --source NAPCO --file /tmp/Radiolist-<ts>.xlsx
# 3. review attribution / ambiguous / invalid rows, then apply
python -m scripts.source_snapshot_import --tenant restoration-hardware --source NAPCO --file /tmp/Radiolist-<ts>.xlsx --apply --imported-by <you>
# 4. verify the persisted snapshot
python -m scripts.source_snapshot_import --tenant restoration-hardware --show <id>
# 5. delete the raw file from /tmp (the snapshot and its SHA-256 remain)
```

Carrier files without a timestamp in their name need `--effective-at <ISO time>`
(the export time) or they are stored `UNDATED`. Re-running an import of the same
file reports `UNCHANGED`. Red Pocket stays provisional until a production export
is reviewed; its absence does not block the architecture.
