# Hardware-Agnostic Device Health Layer

**Date:** 2026-06-01
**Flag:** `FEATURE_DEVICE_HEALTH` (default `false`)
**Status:** Backend foundation complete and tested (1612 tests green). Additive,
flag-gated, tenant-isolated. Belle Terre / Integrity is the **pilot dataset only**.

> Design principle: vendor-specific logic lives **only** in
> `app/services/device_health/adapters/*`. Everything else is generic and reads
> the same for a Vola LM150, an MS130v4, an Inseego+Cisco ATA, or a future
> Teltonika / PR12 endpoint.

---

## 1. Architecture (what we reused vs. added)

This layer is mostly connective tissue over scaffolding that already existed.

**Reused (unchanged):**
- `app/services/health/` — the canonical normalizer (`compute_device_state`,
  `HealthSignals`, `CanonicalDeviceState`, thresholds). This layer is now a
  second, governed consumer of it (behind `FEATURE_DEVICE_HEALTH`).
- `app/integrations/vola.py` + `vola_service.get_vola_client` — Vola client.
- `app/integrations/tmobile_taap.py` — real T-Mobile TAAP (OAuth2 + RSA PoP) client.
- `app/models/integration_payload.py` — safe raw-payload storage (JSONB).
- `app/services/audit_logger.log_audit` — audit trail.

**Added (this change):**

| File | Role |
|---|---|
| `app/services/device_health/status.py` | `NormalizedStatus` (Online/Offline/Attention Needed/Unknown) + mapping from `CanonicalDeviceState` |
| `app/services/device_health/reason_codes.py` | Generic `ReasonCode` enum + priority ordering |
| `app/services/device_health/classifier.py` | `classify()` → vendor cloud / connection_type / voice_type / carrier / probe adapters (hardware-agnostic, table-driven) |
| `app/services/device_health/scoring.py` | Pure `score()` fusing normalizer state + SIM/VoLTE/vendor reasons |
| `app/services/device_health/recommended_action.py` | Reason → customer-friendly action |
| `app/services/device_health/models.py` | `VendorStatus` + `DeviceHealth` (+ `to_customer_view()`) |
| `app/services/device_health/service.py` | DB assembly of `DeviceHealth` (read-only, tenant-scoped, O(1) round-trips) |
| `app/services/device_health/adapters/` | `StatusProbeAdapter` base + registry; `VolaCloudAdapter` (live), `TMobileAdapter` (live MSISDN), Telnyx/Inseego/CiscoAta/MS130/Future stubs |
| `app/routers/device_health.py` | 4 flag-gated read APIs |
| `app/sync_device_health.py` | Generic idempotent sync (`DRY_RUN` default) |
| `app/sync_integrity_lm150.py` | Thin pilot alias (scope only; no special logic) |
| `tests/test_device_health.py` | 36 tests |

**Normalized model:** Tenant → Customer → Site/Property → Service Unit → Device →
SIM → Carrier Connection → Voice Path → Vendor Cloud Link → Health Status →
Last Check-In → Last Call Activity → Recommended Action.

**Normalized status:** `Online | Offline | Attention Needed | Unknown`.

**Generic reason codes:** `OK, DEVICE_OFFLINE, SIM_INACTIVE, SIP_UNREGISTERED,
VOLTE_NOT_READY, NO_RECENT_HEARTBEAT, NO_RECENT_CALL_ACTIVITY,
VENDOR_API_UNAVAILABLE, MISSING_CREDENTIALS, DEVICE_NOT_FOUND, CONFIG_MISMATCH`.
Vendor-specific detail stays in `VendorStatus.raw_payload`.

---

## 2. APIs (gated by `FEATURE_DEVICE_HEALTH`, tenant-scoped)

| Method / path | Audience | Permission |
|---|---|---|
| `GET /api/device-health` | Global device health (this tenant) | `VIEW_DEVICES` |
| `GET /api/device-health/property/{site_id}` | Customer property health — simple language | `VIEW_SITES` |
| `GET /api/device-health/service-unit/{unit_id}` | One service unit's device | `VIEW_DEVICES` |
| `GET /api/device-health/adapters` | Vendor adapter status (no secrets) | `MANAGE_INTEGRATIONS` (admin) |

Read APIs read **persisted DB fields only** — they never make live vendor calls,
so a page load never blocks on Vola / T-Mobile. Live enrichment is done by the
sync command, which writes the fields the APIs then reflect.

The customer property view (`to_customer_view`) renders: Property, Unit
(Elevator/Fire Alarm/Line), Device, Carrier, Voice Path, Status, Last Check-In,
Last Call, Recommended Action.

---

## 3. Vendor status — what's live vs. pending

| Vendor | Adapter | State |
|---|---|---|
| **Vola Cloud** | `VolaCloudAdapter` | **Live** when `VOLA_EMAIL/PASSWORD` set. Looks up by serial → IMEI fallback; returns online/offline, firmware, IP, raw payload. |
| **T-Mobile** | `TMobileAdapter` | Interface live over the real TAAP client. **Blocked on creds** (`TMOBILE_CONSUMER_KEY/SECRET` + RSA key not provisioned) → returns `MISSING_CREDENTIALS`. SubscriberInquiry is **MSISDN-primary**; ICCID/IMEI reverse lookup returns `DEVICE_NOT_FOUND` (not invented). Inbound **callback ingest remains the primary T-Mobile signal**. |
| Telnyx / Inseego / Cisco ATA / MS130 / Future | stubs | Correctly-shaped interface stubs (`MISSING_CREDENTIALS` + note). Fill in `probe()` later — no core change. |

**Logged vendor gaps (not fabricated):** VoLTE status, static IPv4, and usage are
only surfaced if the vendor actually returns them; otherwise the field stays
`null` and the gap is logged.

---

## 4. Generic sync command

```
python -m app.sync_device_health                 # dry run (default) — writes nothing
DRY_RUN=false python -m app.sync_device_health   # apply
DRY_RUN=false DEVICE_HEALTH_TENANT=integrity-pm DEVICE_HEALTH_SITE=IPM-BELLE-TERRE \
    python -m app.sync_device_health             # scoped
python -m app.sync_integrity_lm150               # pilot alias (scope only)
```

- Idempotent: only **updates** Device/SIM health fields — never creates devices,
  SIMs, or units, so it cannot duplicate them.
- Persists raw vendor payloads to `integration_payloads` (source = vendor).
- Writes an audit log per updated device (`category="device_health"`).
- `DRY_RUN` default true.

---

## 5. Exact Render commands

Run in the **`true911-api`** service Shell (Dashboard → `true911-api` → Shell):

```bash
cd /opt/render/project/src/api

# 1) Apply migrations (incl. 046 LM150 hardware model)
alembic upgrade head

# 2) T-Mobile callback soak check (read-only) — confirms callbacks are landing
#    (PowerShell soak script lives at scripts/tmobile_soak_check.ps1; from the
#    Linux shell, the equivalent read-only check is the verify tool below.)
python -m app.verify_integrity      # section [3] reports T-Mobile readiness + callback flag

# 3) Vola verification (read-only) — lookup each LM150 by serial
python -m app.verify_integrity      # section [2] reports online/offline/firmware

# 4) Device-health sync — DRY RUN (writes nothing)
DEVICE_HEALTH_TENANT=integrity-pm DEVICE_HEALTH_SITE=IPM-BELLE-TERRE \
    python -m app.sync_device_health
#   or the pilot alias:
python -m app.sync_integrity_lm150

# 5) Device-health sync — APPLY
DRY_RUN=false DEVICE_HEALTH_TENANT=integrity-pm DEVICE_HEALTH_SITE=IPM-BELLE-TERRE \
    python -m app.sync_device_health

# 6) Turn the read APIs on (Render env var on true911-api), then redeploy:
#    FEATURE_DEVICE_HEALTH=true
```

**Confirm Cindy’s customer view + API payloads** (set `API` + a token — see
`docs/INTEGRITY_BELLE_TERRE_ONBOARDING.md` §5 for the login/invite flow):

```bash
API=https://true911-api.onrender.com
TOKEN=...   # Cindy's access token (Integrity Admin)

# Her tenant only
curl -s "$API/api/auth/me" -H "Authorization: Bearer $TOKEN" | jq '{email,role,tenant_id}'

# Property health in simple language (Belle Terre — Elevators 1/2/3)
curl -s "$API/api/device-health/property/IPM-BELLE-TERRE" \
  -H "Authorization: Bearer $TOKEN" | jq '{property,status,units}'

# Global (her tenant) device health
curl -s "$API/api/device-health" -H "Authorization: Bearer $TOKEN" \
  | jq '{summary, devices: [.devices[] | {device_name,status,reason_codes,recommended_action}]}'

# Admin: which vendor adapters are configured
curl -s "$API/api/device-health/adapters" -H "Authorization: Bearer $TOKEN" | jq
```

Tenant isolation is enforced server-side (`.where(tenant_id == current_user.tenant_id)`
on every query), so Cindy sees only Integrity / Belle Terre and never another tenant.

---

## 6. What still requires credentials or vendor support

| Item | Needed |
|---|---|
| T-Mobile live lookup | `TMOBILE_CONSUMER_KEY/SECRET` + RSA key provisioned; confirmation of ICCID/IMEI reverse-lookup endpoint and the VoLTE/static-IP/usage response schema |
| Vola `vola_org_id` on devices | `VOLA_ORG_ID` set before sync (or Vola sync back-fills) |
| Telnyx / Inseego / Cisco ATA / MS130 live probes | Implement each adapter's `probe()` when vendor APIs/creds are available |
| Customer portal page | Frontend (`web/`) work — deferred (this pass is backend only) |

---

## 7. Governance note

Two static guard tests that previously locked the health package and the
T-Mobile callback flag to their MVP scope were updated to allow the new,
governed consumers:
- `services/device_health/**` may import `app.services.health` (it reuses the
  canonical normalizer by design).
- `verify_integrity.py` may reference `FEATURE_TMOBILE_CALLBACK_INGEST` for a
  **read-only readiness report** (it reports the flag; it does not gate on it).

Both guards otherwise remain strict.
