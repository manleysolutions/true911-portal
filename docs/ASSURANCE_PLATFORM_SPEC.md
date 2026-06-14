# True911+ — ASSURANCE PLATFORM SPEC

> **Constitution-level document.** Defines True911 *as a platform*: the assurance
> model, the status vocabulary, the evidence/proof requirements, and the rules
> every screen must satisfy. This is the product-level companion to the
> engineering spec in `docs/ASSURANCE_ENGINE.md` (which owns the deterministic
> decision matrix, reason codes, and code mapping). Where they overlap, the
> decision logic is authoritative in `ASSURANCE_ENGINE.md`; the customer-facing
> model and proof contract are authoritative here.
>
> Governed by `docs/PRODUCT_MANIFESTO.md`.

---

## 1. The Platform Model

True911 is organized end-to-end around one chain. Every datum, status, screen,
and action maps onto it:

```
Asset → Communication Path → Protection Status → Business Impact
      → Recommended Action → Proof
```

| Stage | Definition | Source axes |
|---|---|---|
| **Asset** | The physical element at a location (device, line, SIM, radio, ATA). | Device/SIM/Line inventory |
| **Communication Path** | The end-to-end route a 911 call would traverse from this asset. | Operational health (telemetry), carrier/line state |
| **Protection Status** | The single calm label for the location. | Composition of all axes (see §3) |
| **Business Impact** | Commercial consequence: revenue at risk, accounts affected, compliance exposure. | Zoho lifecycle (read-only), account mapping |
| **Recommended Action** | The single safest next step to restore/maintain protection. | Reason codes → action map |
| **Proof** | Evidence the status is true. | Evidence types (§5) + Assurance Timeline |

**Rule:** no stage may be skipped on a customer surface. A status with no proof,
or a problem with no recommended action, is an incomplete product.

## 2. The Core Question Every Screen Must Answer

> **"Why should I believe this?"**

Every customer-facing screen must make the answer reachable in one interaction
(the **View Proof** affordance — see `docs/SCREEN_BY_SCREEN_SPEC.md`). A screen
that asserts a status it cannot justify is not allowed to ship.

## 3. Status Vocabulary

Six labels. Three carry alarm semantics (Protected / Attention Needed /
Critical); three are non-alarm states that prevent false alarms (Pending Install /
Inactive-Deactivated / Unknown). The deterministic ordering that assigns them
(first-match-wins) is owned by `docs/ASSURANCE_ENGINE.md §5`.

Each status is defined by the full anatomy below. **No status may render without
all of these populated.**

### 3.1 Protected
- **Label:** Protected *(internal/clinical equivalent: "Active & Verified")*
- **Plain-language meaning:** Emergency calling is active and verified working.
- **Technical basis:** Service active; operational state Online; E911 address
  present + dispatchable verified + no confirmation required; SIM/line active; no
  open Critical incident. (Test recency is a warning trigger, never a gate.)
- **Evidence required:** recent liveness signal; verified E911 address; active
  service/line; "as of" timestamp.
- **Customer-facing message:** *"This location's emergency calling is active and
  verified (as of <time>)."* Always paired with the disclaimer.
- **Internal reason codes:** (none firing) — the absence of any gate/critical/
  warning code, with `value` evidence captured per axis.
- **Recommended action:** None required; optionally "schedule next verification
  test."
- **Proof artifacts:** verified-E911 record, last heartbeat/call timestamps, last
  passing test, monitoring freshness, Recent Manley activity.

### 3.2 Attention Needed *(the "Warning" tier)*
- **Label:** Attention Needed
- **Plain-language meaning:** Likely working, but a human should check one item.
- **Technical basis:** Service active AND a soft issue: operational Attention (low
  signal / SIP unregistered / brief network blip but fresh) · E911 confirmation
  required · test overdue or none on record · open non-critical incident/ticket ·
  recent failed sync/job.
- **Evidence required:** the specific soft signal(s) with timestamps; proof the
  service is still otherwise live.
- **Customer-facing message:** *"This location is working, but we're reviewing an
  item to keep it fully protected."*
- **Internal reason codes:** `SIGNAL_LOW`, `SIP_UNREGISTERED`,
  `E911_CONFIRMATION_REQUIRED`, `TEST_OVERDUE`, `NO_TEST_ON_RECORD`,
  `INCIDENT_OPEN`, `TICKET_OPEN`, `SYNC_FAILED`, `JOB_FAILED` (per
  `ASSURANCE_ENGINE.md §7`).
- **Recommended action:** the single safest item (e.g. "Confirm the 911 address,"
  "Run a verification test").
- **Proof artifacts:** the soft-signal evidence + the still-green axes.

### 3.3 Critical
- **Label:** Critical
- **Plain-language meaning:** Emergency calling may not work right now.
- **Technical basis:** Service active/expected-live AND any hard fail: operationally
  Offline · **E911 address missing** · **dispatchable location not verified** ·
  SIM/line suspended while active · **a failed test on record** · open Critical
  incident. Site-level E911 gate applies even if devices report Online.
- **Evidence required:** the specific hard-fail signal with timestamp; what is
  known-bad and what is unknown.
- **Customer-facing message:** *"This location needs immediate attention —
  emergency calling may not work. Manley Solutions has been alerted."*
- **Internal reason codes:** `DEVICE_OFFLINE`, `E911_ADDRESS_MISSING`,
  `E911_NOT_VERIFIED`, `SIM_INACTIVE`, `LINE_INACTIVE`, `CARRIER_SUSPENDED`,
  `TEST_FAILED`, `INCIDENT_OPEN_CRITICAL`.
- **Recommended action:** the immediate remediation; auto-escalation to Manley.
- **Proof artifacts:** the failure evidence, last-known-good timestamp, the
  alert/escalation record, Recent Manley activity showing response.

### 3.4 Pending Install
- **Label:** Pending Install
- **Plain-language meaning:** Being set up; protection confirmed after install +
  test.
- **Technical basis:** commercial lifecycle pending_install OR pre-active
  deployment (onboarding/provisioning) OR never observed live and not yet expected.
- **Evidence required:** the deployment/lifecycle state showing pre-active.
- **Customer-facing message:** *"This location is being set up. Protection will be
  confirmed once installation and testing are complete."*
- **Internal reason codes:** `LIFECYCLE_PENDING_INSTALL`, deployment-status codes.
- **Recommended action:** complete onboarding steps / schedule install test.
- **Proof artifacts:** onboarding checklist progress, expected-live date.

### 3.5 Inactive / Deactivated
- **Label:** Inactive / Deactivated
- **Plain-language meaning:** Service intentionally not active. **Alarms
  suppressed.**
- **Technical basis:** commercial lifecycle suspended/deactivated OR device
  decommissioned. (If still transmitting → internal-only
  `RECON_DEACTIVATED_BUT_TRANSMITTING`, never a customer Critical.)
- **Evidence required:** the lifecycle record showing intentional inactivity.
- **Customer-facing message:** *"Service at this location is not currently active."*
- **Internal reason codes:** `LIFECYCLE_DEACTIVATED`, `LIFECYCLE_SUSPENDED`,
  `DEVICE_DECOMMISSIONED`, (ops) `RECON_DEACTIVATED_BUT_TRANSMITTING`.
- **Recommended action:** none for the customer; ops reconciliation if mismatched.
- **Proof artifacts:** lifecycle source record + effective date.

### 3.6 Unknown
- **Label:** Unknown
- **Plain-language meaning:** Not enough data to assert status.
- **Technical basis:** active/expected-live but no liveness signal and not clearly
  pending, or key inputs missing. **Missing data is never "healthy."**
- **Evidence required:** explicit statement of which inputs are absent.
- **Customer-facing message:** *"We're confirming the status of this location."*
- **Internal reason codes:** `INSUFFICIENT_DATA` (+ which axis is missing).
- **Recommended action:** ops investigates; restore signal/data.
- **Proof artifacts:** the inventory of missing inputs (honest gap disclosure).

## 4. The "Why Should I Believe This?" Rule

For **every** Protected / Attention Needed / Critical label, the platform must be
able to surface, on demand, all of the following (the **View Proof** contract):

- **Verified timestamp** ("as of <time>")
- **Device evidence** (last heartbeat, last carrier event)
- **Carrier evidence** (line/SIM active, carrier status)
- **E911 evidence** (address present, dispatchable verified, confirmation state)
- **Test-call evidence** (last test result + time)
- **Monitoring evidence** (freshness of the signals used)
- **Recent Manley activity** (what we did to protect this site)
- **View Proof** affordance (one interaction to the full evidence bundle)

If any of these cannot be produced for a status, the status must degrade
conservatively (toward Attention/Unknown) and say so. **We never assert
confidence we cannot evidence.**

## 5. Evidence Types (the proof model)

| Evidence type | What it proves | Primary source(s) |
|---|---|---|
| **Verified timestamp** | Recency of the assertion | engine `as_of` / `computed_at` |
| **Device evidence** | The asset is reachable | `Device.last_heartbeat`, `last_network_event` |
| **Carrier evidence** | The path/service is live | SIM/line status, carrier event, CDR |
| **E911 evidence** | 911 will route correctly | `sites.e911_*`, `lines.e911_*`, e911 change log |
| **Test-call evidence** | A call actually worked | `verification_tasks`, `infra_test_results` |
| **Monitoring evidence** | We are actively watching | signal freshness, sync/job success |
| **Recent Manley activity** | We acted to protect | `action_audit`, `command_activity`, jobs, incidents |

These are additive and read-only. As richer signals land (VOLA online, T-Mobile
activation, Telnyx SIP, PSAP validation), each becomes a new evidence row + reason
code without changing the status vocabulary (see `ASSURANCE_ENGINE.md §19`).

## 6. Business Impact Layer

Each status, at site and portfolio scope, carries a **Business Impact** read
(internal/executive, never exposed as raw commercial data to the wrong tenant):

- Revenue at risk (sites tied to renewing/at-risk accounts).
- Accounts/communities affected.
- Compliance exposure (E911 unverified count, overdue tests).
- Upsell signal (Critical sites on a basic assurance tier).

Sourced read-only from Zoho lifecycle + account mapping. The engine never writes
commercial state.

## 7. Features That Should Never Be Built

This is the authoritative veto list referenced by `PRODUCT_MANIFESTO.md §7`.
Adding any of these requires overturning the manifesto.

1. **Generic network monitoring** (we assure life-safety paths, not general IT).
2. **Customer-configurable scoring algorithms** (one canonical, deterministic
   logic — no per-customer truth).
3. **AI making autonomous safety decisions** (AI explains; humans decide).
4. **Multiple competing health scores** (one label per axis, composed; no rival
   numbers).
5. **Technical jargon on customer dashboards** (ICCID/IMSI/SIP/firmware never the
   default customer view).
6. **Red/green indicators without explanations** (every status carries its why).
7. **Customer-facing numeric readiness score** (invites accepting life-safety
   risk; we show a label + reasons).
8. **Auto-remediation of life-safety status without human approval.**
9. **A guarantee that 911 will always connect** (we assert verified status as of a
   time, never an absolute guarantee).
10. **Cross-tenant benchmarking** (tenant isolation is sacred).
11. **Raw vendor telemetry as the primary customer experience.**

## 8. Customer Data Exposure Policy

Never exposed by default on customer surfaces (internal/support views only):
ICCID, IMSI, SIP registration detail, firmware version, raw vendor events,
internal reconciliation codes (`RECON_*`), raw AI uncertainty. Customer text uses
the plain-language mappings in `ASSURANCE_ENGINE.md §8`. Jargon appears only when
intentionally expanded with a plain-language explanation.

## 9. Related Documents

- `docs/PRODUCT_MANIFESTO.md` — product philosophy (governs this doc).
- `docs/ASSURANCE_ENGINE.md` — deterministic decision matrix, reason codes, code map.
- `docs/CUSTOMER_EXPERIENCE.md` — persona experiences.
- `docs/SCREEN_BY_SCREEN_SPEC.md` — Home/Site/View Proof/Assurance Timeline, etc.
- `docs/DESIGN_SYSTEM.md` — language + visual rules for rendering status & proof.
