# True911+ — Customer Command Center

> The enterprise Life-Safety Operating System a customer sees when they log in.
> Not a device dashboard — a command center for an entire life-safety portfolio,
> understandable in **under 30 seconds**. Built additively on the `CUSTOMER_*`
> plane, the Assurance Engine, Preview Mode, and the `/api/customer/*` API.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.5 explainable, §4.6 no green without evidence, §7 no jargon), `DECISIONS.md`
> (D-005 six-label vocabulary, D-006 separate axes, D-016 Customer Assurance Mode).
> Companions: `ASSURANCE_ENGINE.md`, `RH_GO_LIVE_RUNBOOK.md`,
> `../CUSTOMER_EXPERIENCE_BOUNDARY.md`, `../CUSTOMER_DATA_BOUNDARY.md`.
> Prepared: 2026-07-01.

---

## 1. Vision

When Judy (Restoration Hardware) logs in she immediately understands:

- **Every location** in her portfolio and its protection status,
- **Every life-safety service** (Fire Alarm, Elevator, Area of Refuge, …) and
  whether it is protected,
- **Overall enterprise health** (an evidence-graded score),
- **Which locations need attention** — ranked, plain-language,

…**without ever thinking about a device**. It should feel like operating an
enterprise life-safety command center, not a telecom portal.

## 2. Architecture — the life-safety hierarchy

```
Enterprise → Portfolio → Location → Life Safety Service → Equipment → Carrier
```

**Equipment exists to support services.** Customers reason about *services*
(Fire Alarm, Elevator, Area of Refuge, Burglar Alarm, Emergency Phone, BDA/DAS,
Generator Monitoring), never about device models (LM150 / MS130 / Cisco ATA).
The service catalog (`serialize.SERVICE_CATALOG` → `enterprise_service_label`)
maps a raw `ServiceUnit.unit_type` to the enterprise service name; equipment is
grouped **beneath** the service it powers.

This is additive: the legacy `_SERVICE_LABELS` (older clients/tests depend on its
exact strings) is untouched; the enterprise catalog is a separate mapping.

## 3. API hierarchy (`/api/customer/*` — read-only, two-key gated, `CUSTOMER_*`)

| Endpoint | Purpose | Perm |
|---|---|---|
| `GET /customer/portfolio/summary` | Executive metrics + monthly health score | `CUSTOMER_VIEW_DASHBOARD` |
| `GET /customer/portfolio/health` | Health score + component breakdown | `CUSTOMER_VIEW_DASHBOARD` |
| `GET /customer/locations` | Location list + `map_point` | `CUSTOMER_VIEW_LOCATIONS` |
| `GET /customer/locations/{ref}` | Location overview (address, status, devices) | `CUSTOMER_VIEW_LOCATIONS` |
| `GET /customer/locations/{ref}/services` | Life-Safety Services + grouped equipment | `CUSTOMER_VIEW_SERVICES` |
| `GET /customer/locations/{ref}/e911` | Emergency record (truth) | `CUSTOMER_VIEW_E911` |
| `GET /customer/locations/{ref}/timeline` | Real activity timeline | `CUSTOMER_VIEW_LOCATIONS` |
| `GET /customer/search` | Enterprise search (name/#/city/state/phone/service) | `CUSTOMER_VIEW_LOCATIONS` |

All are **additive** — existing responses are unchanged. Every route keeps the
two-key flag gate (`require_customer_api`) plus a `CUSTOMER_*` permission. Aggregation
lives in `services/customer/command_center.py`; allow-list shaping in `serialize.py`.

## 4. Customer UX philosophy

- **Service-first.** Equipment is always shown under the service it supports.
- **Six-label vocabulary only** (D-005): Protected · Attention Needed · Critical ·
  Pending Install · Inactive · Unknown.
- **No jargon** (§7): no IMEI/ICCID/firmware/carrier/SIM/IP ever. Friendly
  equipment labels; a model string only when it exists (never fabricated).
- **E911 is the truth and stays calm.** `verified` derives only from the stored
  `e911_status`. When "Not yet verified" it renders **amber, never alarming red**,
  with "Manley Solutions is verifying this emergency record."
- **No green without evidence** (§4.6). Operational green in Preview Mode carries
  an honest operator attestation; the **health score** uses only real signals and
  unknowns lower *confidence* (never fabricated).
- **No "API pending" / "telemetry pending" language.**

## 5. Screens (Phase 1–5)

- **Executive Portfolio Dashboard** — metric cards: Locations Protected, Life
  Safety Services, Protected Services, Requires Attention, Critical Sites, Devices,
  Telephone Numbers, E911 Verification %, Service Availability %, Monthly Health,
  Recent Activity, Upcoming Maintenance.
- **Interactive Portfolio Map** — zoom-to-fit, status colors, legend, list↔map
  highlight sync, click → Location Command Center. (Marker *clustering* is roadmap —
  see §7.)
- **Enterprise Search** — server-side across store name/number, city, state, phone
  number, and service/equipment type; results open the Location Command Center.
- **Location Command Center drawer** — Overview · Life Safety Services (equipment
  grouped beneath) · E911 (record + verification history) · Timeline · Documents
  (placeholder) · Billing (placeholder) · Notes.
- **Service-first navigation** — Portfolio (live) + Locations/Services/Devices/
  Documents/Reports/Support/Billing/Settings as "Soon".

## 6. Portfolio Health (Phase 6)

`serialize.health_score(components)` — a weighted average over the **known**
components; **confidence** is the share of total weight that is known. Inputs
(each 0-100 or *unknown*): E911 verification, service coverage, live telemetry,
alarm testing, carrier health. Unknown inputs reduce confidence, never the score,
and are flagged `known:false`. Nothing is fabricated (Phase 6 / §4.6).

## 7. Roadmap (what is stubbed / next)

- **Marker clustering** — add `leaflet.markercluster` + `react-leaflet-cluster`;
  today the map uses zoom-to-fit + colored markers.
- **Reports** (Phase 7) — catalog defined (Monthly Summary, E911, Equipment, Alarm
  Testing, Carrier, Maintenance; CSV/PDF). Nav shows "Soon"; routed report pages +
  export endpoints are the next slice.
- **Timeline event types** — install / replacement / service call / carrier
  migration / alarm test / inspection. The API returns real E911-log activity
  today; the schema is ready for these sources when they exist.
- **Documents / Billing / Notes** — placeholder sections; wire to real customer
  document store + billing integration when available.
- **Store # / Region** — Region is derived from state; a real store-number field
  can be surfaced when modeled (never fabricated).
- **Per-location health** and **AI confidence scoring** — health is portfolio-level
  today; per-location + AI confidence are future health inputs.

## 8. Security & isolation (Phase 9)

The Command Center adds **no** internal surface. `CUSTOMER_*` roles hold no
`INTERNAL_OPS` / `COMMAND_*` / admin grant and cannot reach Internal Ops, the
operator Command Center, carrier APIs, provisioning, billing admin, raw telemetry,
or audit APIs (enforced by `require_permission` + the frontend `INTERNAL_OPS` page
gate; verified by `test_customer_rbac_posture.py`). Every new endpoint is
tenant-scoped and flag-gated. See `../CUSTOMER_EXPERIENCE_BOUNDARY.md`.

## 8a. Location Digital Twin (deepening — additive)

The Location tier has graduated into a **Digital Twin** — each building is a
complete operational record (Overview · Health · Services+Equipment · E911 ·
Documents · Photos · Inspections · Timeline · Contacts · Emergency Procedures ·
Service Requests · Billing). Additive endpoints (`/locations/{ref}/documents`,
`/photos`, `/contacts`, `/inspections`, `/health`), an enriched service model
(carrier name, phone numbers, equipment count, last test/inspection, attention
items), and permanent `?location=<ref>` deep-links. Full spec:
`docs/customer/LOCATION_DIGITAL_TWIN.md`.

## 8b. Life Safety Service Intelligence

Services are now **inferred from equipment** (not just explicit ServiceUnits) by a
rules engine, grouped multi-device, and carried with a **confidence**; location
and portfolio health derive from **service** health, not raw device counts. Adds
`/customer/portfolio/services` (service inventory) and an internal
`MANAGE_SERVICE_CLASSIFICATION` approve/override/merge/split surface (append-only
audit; `CUSTOMER_*`-isolated). Full spec: `docs/customer/LIFE_SAFETY_SERVICE_MODEL.md`.

## 8c. Customer E911 confirmation & correction

Customers can now **confirm** an emergency record or **request a correction** from
the Location Workspace — never overwriting the official record (append-only
audited; `CUSTOMER_SUBMIT_E911_REVIEW` for submit, internal review via
`/api/e911-changes/reviews`). Spec: `docs/customer/E911_CUSTOMER_REVIEW_WORKFLOW.md`.

## 9. Files

- Backend: `api/app/services/customer/command_center.py` (new),
  `serialize.py` (+ service catalog, health score, portfolio summary, service-first
  grouping, timeline, region), `routers/customer.py` (+ 5 endpoints).
- Frontend: `web/src/components/customer/CustomerAssuranceView.jsx` (Command Center
  dashboard), `LocationCommandCenter.jsx` (new drawer), `Layout.jsx` (service-first
  nav).
- Tests: `api/tests/test_customer_command_center.py`.
