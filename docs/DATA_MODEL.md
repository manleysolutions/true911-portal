# True911+ — DATA MODEL

> The canonical entity hierarchy and identity anchors. This is the single source of
> truth for *what the objects are and how they relate*. Resolution logic (how a
> record is matched into this hierarchy) lives in `TRUTH_ENGINE.md`; system
> structure/runtime in `ARCHITECTURE.md`; terminology in `GLOSSARY.md`.

| Metadata | |
|---|---|
| **Authority Level** | 2 — Architecture (canonical) |
| **Owner** | Principal Architect |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Medium (on structural change) |
| **Governed By** | `CONSTITUTION.md` (§4.3 separate axes, §4.8 one identity) |
| **Detailed In** | `TRUTH_ENGINE.md` (resolution), model files in `api/app/models/` |
| **Related Decisions** | `DECISIONS.md` → D-006 (separate-axes invariant) |

---

## 1. The Canonical Hierarchy

```
Tenant
 └─ Customer
     └─ Site
         └─ Service Unit
             ├─ Device
             │   └─ SIM ── MSISDN
             └─ (E911 — dispatchable location, anchored at Site)
```

Worked example (Restoration Hardware):

```
Restoration Hardware (Tenant)
 └─ Restoration Hardware, Inc. (Customer)
     └─ Jacksonville Store (Site)
         └─ Elevator 1 (Service Unit)
             └─ RTL Kit (Hardware Package)
                 ├─ MS130 (Device)
                 │   └─ SIM (ICCID) ── MSISDN
                 └─ E911 (verified dispatchable address @ Site)
```

## 2. Entities, Authoritative Keys, and Ownership

Each entity has **exactly one authoritative key** and owns **one axis** of truth.
(Field-level truth is the model files; this is the canonical summary.)

| Entity | Table | Authoritative key | Axis owned | Key identity/link fields |
|---|---|---|---|---|
| **Tenant** | `tenants` | `tenant_id` (str) | Isolation boundary | `tenant_id` |
| **Customer** | `customers` | `id` (int) | Commercial / billing identity | `zoho_account_id`, `customer_number`, `tenant_id` |
| **Site** | `sites` | `site_id` (str, unique) | Location + **E911 / compliance** | `customer_id` (FK, *nullable — see §4*), `tenant_id`, `e911_street/city/state/zip`, `e911_status`, `e911_confirmation_required` |
| **Service Unit** | `service_units` | `unit_id` (str, unique) | Emergency endpoint at a site | `site_id`, `device_id`, `line_id`, `sim_id`, `unit_type` |
| **Device** | `devices` | `device_id` (str, unique) | **Operational** hardware/telemetry | `iccid`, `imei`, `serial_number`, `msisdn`, `sim_id`, `site_id`, `carrier`, `identifier_type` |
| **SIM** | `sims` | `iccid` (str, **globally unique**) | Cellular subscriber identity | `msisdn`, `imsi`, `imei`, `device_id`, `site_id`, `customer_id`, `carrier` |
| **Line / Voice Line** | `lines` | `line_id` (str) | Voice service | `site_id`, `device_id`, `customer_id`, `subscription_id` |
| **Crosswalk** | `external_record_map` | (`source`,`module`,`external_record_id`) | External↔internal mapping | `customer_id`, `site_id`, `device_id`, `line_id`, `map_status` |

## 3. Relationships

- **Tenant → Customer** (1:N) · **Customer → Site** (1:N) · **Site → Service Unit**
  (1:N) · **Site → Device / Line** (1:N).
- **Device ↔ SIM** (1:1 typical) via `device.sim_id` / `sim.device_id`; both
  nullable to support **inventory pools** (unassigned devices/SIMs).
- **MSISDN** is an attribute of a SIM/line/device, **not** a table and **not a
  unique key** (ambiguity-prone — see `TRUTH_ENGINE.md` resolution precedence).
- **E911** is an attribute set on the **Site** (and `lines.e911_*`), not a separate
  entity.

## 4. Known Gaps (the integrity work)

- **`sites.customer_id` is nullable.** FK + indexes exist (migration 039); backfill
  is pending (Operation Green / Phase 2), with the `NOT NULL` flip deferred. Until
  then, Site→Customer can be absent → an orphan signal in the Identity Audit.
- **Service Unit underused.** It is the correct anchor for "Elevator 1 → RTL Kit";
  many sites currently hang devices directly off the site without a service unit.
- **MSISDN non-uniqueness** can produce ambiguous device↔SIM matches; handled, never
  silently guessed, by the Truth Engine.

## 5. Invariants (constitutional)

- **Separate axes never collapse** (`CONSTITUTION.md` §4.3, `DECISIONS.md` D-006):
  Operational (Device) ≠ Commercial (Customer/lifecycle) ≠ E911 (Site) ≠ Deployment
  (Service Unit / onboarding). One owner per axis; reads compose, writes never
  overwrite another axis.
- **One authoritative identity per object** (`CONSTITUTION.md` §4.8): every record
  resolves to exactly one node in this hierarchy. The mechanism is the Truth Engine.

## 6. Terminology

All entity names are defined canonically in `GLOSSARY.md` (including the renames:
*Endpoint Type → Service Type*, *Kit Type → Hardware Package*).
