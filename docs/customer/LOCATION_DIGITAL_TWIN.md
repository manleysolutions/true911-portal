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

**Location Workspace** (`web/src/components/customer/LocationCommandCenter.jsx`) —
a single building record with sections: Overview · Digital Twin Health · Life
Safety Services (equipment grouped) · Equipment · E911 · Documents · Photos ·
Inspection History · Recent Activity · Site Contacts · Emergency Procedures ·
Service Requests · Billing · Notes.

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

## 8. Files

- Backend: `services/customer/command_center.py` (+5 loaders), `serialize.py`
  (+ `service_with_equipment` enrichment, `carrier_label`, `timeline_entry`,
  `location_contacts`, documents/photos/inspections placeholders, catalogs),
  `routers/customer.py` (+5 endpoints).
- Frontend: `components/customer/LocationCommandCenter.jsx` (Workspace),
  `CustomerAssuranceView.jsx` (deep-link).
- Tests: `api/tests/test_location_digital_twin.py`.
