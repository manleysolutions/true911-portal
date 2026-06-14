# True911+ — GLOSSARY

> The single authoritative definition of every True911 term. Other documents use
> terms *as defined here* and link to this file on first use; they do not redefine
> them (`CONSTITUTION.md` P1).

| Metadata | |
|---|---|
| **Authority Level** | 2 — Architecture (canonical) |
| **Owner** | Principal Architect + Data Steward |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Low–Medium |
| **Governed By** | `CONSTITUTION.md`, `DATA_MODEL.md` |
| **Detailed In** | `DATA_MODEL.md`, `TRUTH_ENGINE.md`, `ASSURANCE_ENGINE.md` |
| **Related Decisions** | `DECISIONS.md` → D-005 (labels), D-006 (axes) |

**Format:** *Term* — Meaning · **Is** · **Is not** · Example · Canonical source.

---

### Core hierarchy

- **Tenant** — the top-level org / data-isolation boundary (`tenants.tenant_id`).
  *Is:* the isolation root, "who owns the login." *Is not:* the billing customer.
  *Ex:* `restoration-hardware`. → `DATA_MODEL.md`
- **Customer** — a billing account under a tenant (`customers.id`, Zoho-linked).
  *Is:* the commercial entity invoiced. *Is not:* a location or a device. *Ex:*
  "Restoration Hardware, Inc." → `DATA_MODEL.md`
- **Site** — a physical location (`sites.site_id`). *Is:* where protection is
  delivered; the E911 anchor. *Is not:* a device or a customer. *Ex:* "RH
  Jacksonville Store." → `DATA_MODEL.md`
- **Service Unit** — a distinct emergency-communications endpoint at a site
  (`service_units.unit_id`). *Is:* the anchor for "Elevator 1 → RTL Kit." *Is not:*
  the hardware or the SIM. *Ex:* "Elevator 1 emergency phone." → `DATA_MODEL.md`
- **Device** — a physical hardware asset (`devices.device_id`). *Is:* the thing that
  reports heartbeat/telemetry; owns the operational axis. *Is not:* the SIM, the
  line, or the service. *Ex:* an MS130 communicator. → `DATA_MODEL.md`
- **SIM** — the cellular subscriber module (`sims.iccid`, globally unique). *Is:* an
  identity carrier (ICCID/IMSI). *Is not:* the MSISDN or the device. *Ex:* a
  T-Mobile SIM. → `DATA_MODEL.md`
- **MSISDN** — the dialable phone number on a SIM/line. *Is:* the phone number.
  *Is not:* a unique device key (not globally unique → ambiguity-prone). *Ex:*
  `+18563081391`. → `TRUTH_ENGINE.md` (precedence)
- **Line / Voice Line** — a voice service instance (`lines.line_id`). *Is:* the
  voice-service axis. *Is not:* the device or the SIM.
- **E911** — the dispatchable-location compliance axis on a site (`sites.e911_*`).
  *Is:* proof a 911 call routes correctly. *Is not:* device health or commercial
  status. *Ex:* verified street address + PSAP. → `DATA_MODEL.md`

### Hardware / classification

- **RTL Kit** — the packaged hardware bundle deployed at a Restoration Hardware
  unit. *Is:* a **Hardware Package** (device + SIM + mounting). *Is not:* a single
  device. *Ex:* "RTL Kit = MS130 + T-Mobile SIM."
- **Endpoint Type** *(legacy)* → **Service Type** — the classification of a service
  unit's function. *Is:* the service's role. *Is not:* a hardware model. *(Rename
  recorded; old term retained only in legacy data.)*
- **Kit Type** *(legacy)* → **Hardware Package** — see RTL Kit.

### Roles & systems

- **Data Steward** — the role (Sivmey) responsible for data trustworthiness. *Is:*
  operator of Import→Validate→Reconcile→Approve→Publish. *Is not:* a UI/color
  reviewer; not an approver of life-safety state changes outside gated planners.
  → `OPERATING_LOOP.md`, `TRUTH_ENGINE.md`
- **Truth Engine** — the identity/normalization subsystem. *Is:* the layer that
  resolves every record into the canonical hierarchy before writes. *Is not:* a UI,
  an AI feature, or an autonomous writer of life-safety state. → `TRUTH_ENGINE.md`
- **Operation Green Dashboard** — the initiative to make ≥95% of genuinely-healthy
  live devices auto-green and correctly mapped. *Is:* making the portal reflect
  reality. *Is not:* making the portal "look green" / cosmetic. → `PRODUCT_VISION.md` (North Star)
- **Assurance Engine** — the deterministic engine that composes axes into an
  assurance label. *Is:* read-only, explainable. *Is not:* a writer of source-of-
  truth state. → `ASSURANCE_ENGINE.md`

### Status & evidence vocabulary

- **Assurance Label** — the calm status for a device/site/portfolio. One of:
  **Protected · Attention Needed · Critical · Pending Install · Inactive/Deactivated
  · Unknown** (`DECISIONS.md` D-005).
- **Protected** — active and **verified** working, shown "as of <time>" + disclaimer
  (`DECISIONS.md` D-004). *Is not:* a guarantee 911 connects.
- **Reason Code** — the machine-stable code behind a status (`ASSURANCE.*`,
  `IDENTITY.*`). *Is:* the "why." *Is not:* customer-facing raw text.
- **Confidence** — a 0.0–1.0 score on an identity match. → `TRUTH_ENGINE.md`
- **Resolved / Ambiguous / Orphan** — Identity Audit outcomes: fully chained /
  multiple-or-contradictory candidates / missing required link. → `TRUTH_ENGINE.md`
- **View Proof** — the affordance exposing the evidence behind any status.
  → `SCREEN_BY_SCREEN_SPEC.md`
- **Data Health Score** — the steward's aggregate trustworthiness metric.
  → `TRUTH_ENGINE.md`

*(Add new terms here as they become load-bearing — P3.)*
