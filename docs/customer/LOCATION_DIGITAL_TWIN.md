# True911+ — Location Digital Twin

> Every customer location becomes a **complete operational record for that
> building** — a Digital Twin. Built additively on the Customer Command Center
> (`CUSTOMER_COMMAND_CENTER.md`, PR #143): same `CUSTOMER_*` plane, Assurance
> Engine, Preview Mode, and `/api/customer/*` API.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.5 explainable, §4.6 no green without evidence, §7 no jargon), `DECISIONS.md`
> (D-005 six-label vocab, D-006 separate axes, D-016 Customer Assurance Mode).
> Companions: `CUSTOMER_COMMAND_CENTER.md`, `ASSURANCE_ENGINE.md`,
> `../CUSTOMER_EXPERIENCE_BOUNDARY.md`, `../CUSTOMER_DATA_BOUNDARY.md`.
> Prepared: 2026-07-01.

---

## 1. UX philosophy

A customer opens any building and understands, **without telecom knowledge**:

- **What is protected** and **what needs attention** (Assurance status),
- **What services exist** (Fire Alarm, Elevator, Area of Refuge, Emergency Phone,
  BDA/DAS, Generator Monitoring),
- **What equipment supports those services** (grouped beneath the service),
- **What documentation exists**, **what inspections have occurred**,
- **What actions are needed.**

Customers think in **Buildings · Services · Protection · History · Documentation ·
Compliance.** Equipment *supports* those concepts — it never defines them.

## 2. Architecture

The Command Center hierarchy, deepened at the Location tier into a full record:

```
Enterprise → Portfolio → Location(=Digital Twin) → Life Safety Service → Equipment → Carrier
```

**Building Workspace** (`web/src/components/customer/LocationCommandCenter.jsx`) —
a single building record, reorganised into four workspaces (see §9):

- **Building Summary** — Overview · Building Health (separated factors + maturity)
- **Operations** — Life Safety Services (primary; equipment grouped & de-emphasised
  under a collapsible) · Service Requests · Recent Activity
- **Compliance** — E911 · Inspection History · Emergency Procedures
- **Administration** — Site Contacts · Documents · Photos · Notes · Billing

Life-safety **services are the primary objects**; supporting equipment is
collapsed. Most sections carry a neutral `+ Add …` contribution control (§9).

**Service model** (Phase 2) — each Life-Safety Service is modeled independently of
hardware and carries: protection status, equipment count, carrier (network *name*
only), telephone numbers, last test, last inspection, and attention items.
`serialize.service_with_equipment(...)` is additive (new fields default to
null/empty; legacy callers unchanged).

## 3. API hierarchy (`/api/customer/*` — read-only, two-key gated, `CUSTOMER_*`)

Existing (Command Center): `/portfolio/summary`, `/portfolio/health`, `/search`,
`/locations`, `/locations/{ref}`, `/locations/{ref}/services`,
`/locations/{ref}/e911`, `/locations/{ref}/timeline`.

**Added by the Digital Twin (all additive, `CUSTOMER_VIEW_LOCATIONS`):**

| Endpoint | Purpose | Data |
|---|---|---|
| `GET /locations/{ref}/documents` | Document record | placeholder + categories (Phase 3) |
| `GET /locations/{ref}/photos` | Photo record | placeholder (Phase 3) |
| `GET /locations/{ref}/contacts` | Site contacts | **real** (customer-safe) |
| `GET /locations/{ref}/inspections` | Inspection history | **real-only** (empty today) |
| `GET /locations/{ref}/health` | Building health score | **real signals** (Phase 5) |

Aggregation: `services/customer/command_center.py`; allow-list shaping:
`serialize.py`. Existing responses are unchanged.

## 4. Digital Twin Health (Phase 5)

Per-location health via `serialize.health_score(...)` — a weighted average over the
**known** components; **confidence** is the share of total weight that is known.
Inputs (0-100 or *unknown*): operational services, verified E911, live telemetry
(offline-equipment inverse), inspection/alarm-test freshness, carrier health.
Unknown inputs lower confidence, never the score; nothing is fabricated (Phase 6).
Open service requests / recent alarm tests / AI confidence are future inputs.

## 5. Location navigation (Phase 6)

- **Permanent, shareable URL:** `?location=<ref>` deep-links the workspace; the
  `ref` is opaque (HMAC-signed, no raw ids) → a customer-safe shareable link.
- **Breadcrumb:** Portfolio → Location.
- **Quick actions:** Share link (live), Request service (Soon).

## 6. Security boundaries (Phase 8)

The Digital Twin adds **no** internal surface. Every endpoint is tenant-scoped,
two-key flag-gated, and `CUSTOMER_*`-guarded. `CUSTOMER_*` roles hold no
`INTERNAL_OPS`/`COMMAND_*`/admin grant and cannot reach internal ops, carrier
APIs, provisioning, billing admin, raw telemetry, or audit APIs. **Never emitted:**
IMEI, ICCID, firmware, SIM ids, carrier *credentials*/account ids, internal owner
identifiers, raw coordinates (map pin only). Carrier *name* (e.g. "T-Mobile") is
customer-safe and shown at the service level; credentials are not. E911 is derived
only from stored records and is never fabricated.

## 7. Roadmap

- **Documents / Photos storage** (Phase 3): signed-URL retrieval over a customer
  document store — permits, floor plans, inspection reports, photos, carrier
  paperwork, service contracts, E911 docs.
- **Timeline sources** (Phase 4): `timeline_entry` schema is ready for
  installation / alarm test / carrier migration / firmware update / technician
  visit / customer note / inspection / AI events; emitted only from real sources.
- **Inspection history**: ingest real inspection records (fire alarm/elevator/
  sprinkler/generator/annual).
- **Health inputs**: open service requests, alarm-test freshness, carrier health,
  AI confidence scoring.
- **Service Requests / Emergency Procedures / Billing**: real integrations.
- **Frontend test runner** (Vitest) — no runner exists yet; backend carries the
  tested logic today.

## 7a. Life Safety Service Intelligence (services are now inferred)

The Twin's Life-Safety Services are no longer limited to explicit `ServiceUnit`
rows — a **service inference engine** classifies equipment (device model/type/
notes/manufacturer/carrier + line label + ServiceUnit) into first-class services
(Fire Alarm, Elevator, Area of Refuge, Emergency Phone, BDA/DAS, Generator
Monitoring, Mass Notification, Burglar Alarm), groups multiple devices under one
service, and attaches a **confidence**. Location health now derives from **service**
health. Operations can approve/override/merge/split classifications (logged as
append-only audit). The "No life-safety services" empty state now appears only when
a building truly has no equipment. Full spec: `LIFE_SAFETY_SERVICE_MODEL.md`.

## 7b. Customer E911 confirmation & correction

The E911 section of the Location Workspace now lets CUSTOMER_* users **Confirm
Emergency Record** or **Request Correction** — participation without ever
overwriting the official record. Status reads: *Not yet verified · Customer
confirmed · Correction requested · Awaiting Review · Verified*. Submit is
gated on `CUSTOMER_SUBMIT_E911_REVIEW` (read-only roles view only); operators
review via `/api/e911-changes/reviews`. Append-only audited; never fabricated.
Full spec: `E911_CUSTOMER_REVIEW_WORKFLOW.md`.

## 8. Files

- Backend: `services/customer/command_center.py` (+5 loaders), `serialize.py`
  (+ `service_with_equipment` enrichment, `carrier_label`, `timeline_entry`,
  `location_contacts`, documents/photos/inspections placeholders, catalogs),
  `routers/customer.py` (+5 endpoints).
- Frontend: `components/customer/LocationCommandCenter.jsx` (Workspace),
  `CustomerAssuranceView.jsx` (deep-link).
- Tests: `api/tests/test_location_digital_twin.py`.

## 9. Building Workspace (collaborative Digital Twin)

The Location Workspace becomes a **collaborative Building Workspace** — same APIs,
refined experience. Additive across the whole stack:

- **Reorganised** into four workspaces — *Building Summary · Operations ·
  Compliance · Administration* (§2). Life-safety **services are primary**;
  supporting equipment is de-emphasised under a collapsible.
- **Contributions** — customers enrich their twin (contacts, inspections, photos,
  documents, procedures, notes, service requests) through the **submission →
  review** workflow. A contribution is a request stored as an append-only audit
  event; it never writes a protected record. Gated on `CUSTOMER_CONTRIBUTE`
  (ADMIN/MANAGER/SUPPORT/USER). Full spec: `WORKFLOW_ENGINE.md`.
- **Separated health** — building health is split into four factors (Operational
  40% · Completeness 25% · Compliance 20% · Documentation 15%); the composite is
  shown **after** the factors (Constitution §4.5). Unknown factors lower
  confidence, never the score.
- **Maturity tier** — Bronze / Silver / Gold / Platinum over seven dimensions,
  with concrete next steps. Full spec: `DIGITAL_TWIN_MATURITY_MODEL.md`.
- **Neutral wording** — no operating-company references anywhere in the customer
  UI; statuses read *Verification Pending · Verification Requested · Awaiting
  Review · Verified*; actor labels are *Verification team* / *Support team*.

**Added files:** `services/customer/contributions.py`, `serialize.separated_health`
+ `serialize.building_maturity`, two `/contributions` endpoints,
`permissions.json` (`CUSTOMER_CONTRIBUTE`),
`api/tests/test_customer_contributions.py`. Docs:
`WORKFLOW_ENGINE.md`, `DIGITAL_TWIN_MATURITY_MODEL.md`.

## 10. Persistent identity — the Portfolio Registry

The Digital Twin's **identity** is now permanent, not rediscovered each run. The
Portfolio Fusion Engine reconciles Zoho / Napco / Genesis / True911 against an
operator-**approved Portfolio Registry** (`portfolio_buildings` + aliases + device
mappings). Approved mappings resolve a building **before** any heuristic; anything
unmapped becomes a **review item** (new building / possible merge / duplicate /
address conflict / device conflict / unknown alias) rather than silently reshaping
the portfolio. The registry is written **only** through an explicit approval
workflow — a fusion run is read-only. This gives every customer Digital Twin a
stable spine across data refreshes. Full spec: `PORTFOLIO_REGISTRY.md` (and
`PORTFOLIO_FUSION_ENGINE.md` §7).

**Customer rendering (flag-gated).** When `FEATURE_CUSTOMER_PORTFOLIO_REGISTRY` is on
for the tenant, the customer dashboard + this Workspace render from the approved
registry (canonical `PortfolioBuilding` rows) via
`services/customer/portfolio_registry_view.py` — canonical display names (*Chicago
Gallery #147*), de-duplicated building counts, and KPIs derived from fusion services
(no more "0 services" / placeholder health). Aliases and all source-system internals
are hidden; pending buildings show only under a preview flag with calm wording. Off
(or registry empty) → unchanged legacy Site behavior. See
`CUSTOMER_COMMAND_CENTER.md` §8e.
