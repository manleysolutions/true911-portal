# True911+ — Life Safety Service Intelligence Model

> Teach True911 what each building actually **protects**. The backend converts an
> equipment inventory into a **Life Safety Service** model: services (Fire Alarm,
> Elevator, Area of Refuge, Emergency Phone, BDA/DAS, Generator Monitoring, Mass
> Notification, Burglar Alarm) become first-class entities; equipment *supports*
> them. Additive on the Customer Command Center + Location Digital Twin.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.5 explainable, §4.6 no green without evidence, §7 no jargon), `DECISIONS.md`
> (D-005/D-006/D-016). Companions: `CUSTOMER_COMMAND_CENTER.md`,
> `LOCATION_DIGITAL_TWIN.md`, `ASSURANCE_ENGINE.md`. Prepared: 2026-07-01.

---

## 1. Design goal

A customer should **never need to understand devices**. They understand
**Buildings · Services · Protection · Risk**. Everything else supports those
concepts. The service is the unit of meaning; equipment is how a service is
delivered (one service may be delivered by multiple devices).

## 2. The service catalog

`service_inference.SERVICE_TYPES` — the only service types:
**Fire Alarm · Elevator · Area of Refuge · Emergency Phone · BDA/DAS · Generator
Monitoring · Mass Notification · Burglar Alarm** (+ a generic *Life Safety Service*
fallback for the honestly-unclassified).

## 3. Inference engine (Phase 1/2) — `services/customer/service_inference.py`

**Pure, deterministic, no I/O.** Classifies each equipment item and groups items
into services.

- **Signals** (real only): device model, device/equipment type, notes,
  manufacturer, carrier, line label, and any anchoring `ServiceUnit` (unit type /
  name / location). Underscored enums (`emergency_call_station`, `fire_alarm`) are
  normalized so keyword rules match.
- **Priority:** an explicit `ServiceUnit` type is **authoritative** (Confirmed);
  otherwise ordered keyword rules infer the type; no signal → generic *Life Safety
  Service* at **Low** confidence (an honest "we don't know yet", never fabricated).
- **Confidence:** `Confirmed` (ServiceUnit or override) · `High` (specific
  model/keyword, e.g. MS130/LM150/"fire alarm"/"elevator") · `Medium` (generic
  keyword) · `Low` (unclassified).
- **Grouping (multi-device):** items group by `(service_type, where)`. A Fire
  Alarm panel + its communicator in the same location = **one** service with two
  devices; Elevator 1 and Elevator 2 = **two** services. `ServiceUnit`s with no
  device still surface as services (0 equipment) so nothing is lost.
- **Manual override wins:** `{device_id: service_type}` forces a device's service
  (Confirmed) — see §7.

Example mappings: `MS130 + Fire Adapter → Fire Alarm`; `LM150 + ATA → Elevator`;
emergency-phone adapters → `Emergency Phone`.

## 4. Service health (Phase 3)

Each service carries: status (**Protected · Attention · Offline/Critical ·
Unknown**), **confidence**, last test, last inspection (null until a real source),
and its **supporting equipment**. Status derives from the service's equipment (the
Assurance engine per device), aggregated worst-first — never a raw device count.
Preview Mode greens the operational axis (operator attestation).

## 5. Location & Portfolio health (Phase 4/5)

- **Location health derives from SERVICE health** — the protected share of the
  location's services (not raw equipment health).
- **Portfolio derives from BUILDING health** — the executive metrics count
  protected *locations* and protected *services* (service/building-derived), never
  a raw device count. `/customer/portfolio/services` returns the service inventory
  (total, protected, attention, by-type).

All health uses `serialize.health_score`: weighted over **known** inputs; unknown
inputs lower **confidence**, never the score. Nothing fabricated (§4.6).

## 6. Customer APIs (Phase 6/7) — additive, `CUSTOMER_*`-guarded

| Endpoint | Returns |
|---|---|
| `GET /customer/locations/{ref}/services` | inferred services + grouped equipment + confidence (populates the Digital Twin) |
| `GET /customer/portfolio/services` | portfolio service inventory (total / protected / attention / by-type) |
| `GET /customer/locations/{ref}/health` | building health (now service-derived) |

Existing responses are unchanged (`service`, `equipment`, `status`, … all still
present) — the new `confidence` is additive. The Digital Twin's "No life-safety
services" empty state now only shows when a building genuinely has no equipment.

## 7. Internal Operations (Phase 8) — `MANAGE_SERVICE_CLASSIFICATION`

Operations can **approve / override / merge / split** a site's classification:

| Endpoint | Purpose |
|---|---|
| `GET /api/service-classification/{site_id}` | review inferred services + confidence + device detail + current overrides |
| `POST /api/service-classification/override` | approve / override / merge / split (one or more devices) |
| `GET /api/service-classification/{site_id}/overrides` | override audit trail |

- **Merge** = assign multiple devices to one service; **split** = reassign a
  device to a different service; **approve** = accept the inferred classification.
- **Every override is logged.** Overrides persist as **append-only `ActionAudit`
  records** — persistence and logging in one, no new table/migration. The customer
  inference engine reads the *latest* override per device and applies it, so an
  operator correction immediately reshapes what the customer sees.
- **Internal only.** `MANAGE_SERVICE_CLASSIFICATION` is held by Admin / Manager /
  DataSteward / UX_QA_ANALYST — **no `CUSTOMER_*` role holds it** (isolation).

## 8. Security boundaries (Phase 8)

Customer plane: only inferred, customer-safe service cards (no IMEI/ICCID/firmware/
SIM/carrier-credentials; carrier *name* only). Internal classification surface is
`CUSTOMER_*`-isolated. Everything tenant-scoped; customer endpoints two-key
flag-gated. No E911 or telemetry is fabricated; "unknown" is a real outcome.

## 9. Roadmap

Persisted-override → ServiceUnit promotion; richer rules (vendor/carrier metadata,
customer metadata); real last-test / last-inspection sources; per-service history;
AI-assisted classification confidence; a merge/split UI in the internal console.

## 10. Files

- Engine: `services/customer/service_inference.py`.
- Internal ops: `services/service_classification.py`, `routers/service_classification.py`,
  `permissions.json` (`MANAGE_SERVICE_CLASSIFICATION`).
- Customer wiring: `services/customer/command_center.py` (inference-sourced services,
  service-derived location health, `/portfolio/services`), `serialize.service_card`.
- Tests: `api/tests/test_service_inference.py` (+ updated command-center / digital-twin).
