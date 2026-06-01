# Onboarding — Integrity Property Management / Belle Terre at Sunrise

**Date:** 2026-06-01
**Scope:** Onboard 3 × FlyingVoice/Vola **LM150** VoLTE elevator phones (T-Mobile VoLTE
SIMs) under a new property, **Belle Terre at Sunrise**, for the parent tenant
**Integrity Property Management**.
**Status:** Code + idempotent onboarding tooling complete and tested. **Not yet
applied to production** — apply step is operator-run (`DRY_RUN=false`).

> ⚠️ Life-safety: these are elevator emergency phones. No e911 address is ever
> fabricated. Devices/SIMs are created from the verified intake sheet; the three
> sibling properties without a confirmed address are created as **pending
> placeholders** with no e911 data and must not route emergency calls until an
> address is supplied.

---

## 1. Architecture mapping (verified against the codebase)

| Onboarding concept | True911 model / table | Key fields used |
|---|---|---|
| Parent account / tenant | `Tenant` (`tenants.tenant_id` slug) | `tenant_id="integrity-pm"`, `zoho_account_id` |
| Billing account | `Customer` (`customers`) | `zoho_account_id`, `customer_number`, `billing_email` |
| Property / location | `Site` (`sites`) | `site_id`, `e911_street/city/state/zip`, `customer_id` FK |
| Elevator endpoint | `ServiceUnit` (`service_units`) | `unit_type="elevator_phone"`, `device_id` |
| Device | `Device` (`devices`) | `serial_number`, `imei`, `iccid`, `msisdn`, `carrier`, `model`, `hardware_model_id`, `vola_org_id` |
| SIM | `Sim` (`sims`) + `DeviceSim` | `iccid` (unique), `carrier`, `meta.volte_enabled` |
| Hardware catalog | `HardwareModel` | `flyingvoice-lm150` (added by migration 046) |
| Login / RBAC | `User.tenant_id` + `require_permission(...)` | invite user, role `Admin` |

**RBAC isolation** is enforced per request: every list query is scoped
`.where(Model.tenant_id == current_user.tenant_id)` (see `routers/sites.py`,
`routers/devices.py`, `routers/service_units.py`). An Integrity user therefore
sees only Integrity sites/devices and nothing from other tenants.

---

## 2. What already existed

**In Zoho CRM (confirmed read-only on 2026-06-01):**

| Record | Status in Zoho | Notes |
|---|---|---|
| **Integrity Property Management** | ✅ exists — account `337391000069074135` | Industry "Property Management / Building Owner"; billing contact Cindy Whittle, `Cindy@ipmflorida.com`, (954) 346-0677; account # 15137. This is the parent. |
| The Pointe of Pompano Beach Condo Association | ✅ exists — child of Integrity | Spelled "Pointe" in Zoho; flagged **test location** ("House Account - Test location"). |
| Tiffany Gardens - East | ✅ exists | Parent link **not** set to Integrity yet. |
| Tiffany Gardens North | ❌ not found | — |
| Belle Terre at Sunrise | ❌ not found as an Account | — |
| The 3 LM150 devices | ❓ not found | No `Devices`/`Products` match for the serials/IMEIs — device records, if present, live in a Zoho module not exposed here. |

**In True911:** nothing. No `integrity-pm` tenant, no customer, no sites, devices,
SIMs, or users existed. The `LM150` was **not** in the hardware catalog.

---

## 3. What was added (this change)

| File | Purpose |
|---|---|
| `api/alembic/versions/046_seed_flyingvoice_lm150_model.py` | Idempotent migration: adds `flyingvoice-lm150` to `hardware_models` (auto-runs on deploy). |
| `api/app/seed_integrity.py` | Idempotent onboarding (`DRY_RUN` default true). Tenant → Customer → 4 Sites → 3 ServiceUnits → 3 Devices → 3 SIMs → DeviceSim links → Admin invite. Pure, unit-tested builders. |
| `api/app/verify_integrity.py` | Read-only verifier: DB visibility report, Vola lookup by serial, T-Mobile readiness. Writes nothing. |
| `api/tests/test_onboard_integrity.py` | 22 tests — builders, idempotency keys, RBAC, Vola mock success/failure, T-Mobile readiness, visibility gaps. |
| `docs/INTEGRITY_BELLE_TERRE_ONBOARDING.md` | This report. |

**Records the onboarding will create** (all `tenant_id="integrity-pm"`):

- Tenant `integrity-pm` "Integrity Property Management" (zoho `337391000069074135`)
- Customer "Integrity Property Management" (zoho-linked, account # 15137)
- Sites: `IPM-BELLE-TERRE` (**active**, full e911); `IPM-POMPANO`
  ("The Pointe of Pompano Beach Condo Association" — **pending + test**,
  Zoho-flagged test location, inert); `IPM-TIFFANY-EAST`, `IPM-TIFFANY-NORTH`
  (**pending**, no e911)
- Service units: `IPM-BELLE-TERRE-EL1/EL2/EL3` (`elevator_phone`)
- Devices + SIMs (Belle Terre):

  | Elevator | device_id | Serial | IMEI | ICCID | MSISDN |
  |---|---|---|---|---|---|
  | 1 | `VOLA-VOLA00325600226` | VOLA00325600226 | 355893730016754 | 8901240204219433645 | 7542697860 |
  | 2 | `VOLA-VOLA00325600227` | VOLA00325600227 | 355893730016762 | 8901240204219433652 | 7542528836 |
  | 3 | `VOLA-VOLA00325600230` | VOLA00325600230 | 355893730016796 | 8901240204219166351 | 7542653349 |

  All: `carrier=tmobile`, `model=LM150`, `manufacturer=FlyingVoice`,
  `hardware_model_id=flyingvoice-lm150`, VoLTE recorded in `Sim.meta.volte_enabled`.

- Admin invite user (env `INTEGRITY_ADMIN_EMAIL`, default `admin@ipmflorida.com`),
  role `Admin`, `is_active=False` + invite token (no email is sent by the script).

---

## 4. What failed / still requires credentials or vendor support

| Item | State | Action needed |
|---|---|---|
| **Vola device verification** | Not run here (no creds in this env) | Set `VOLA_EMAIL`/`VOLA_PASSWORD`/`VOLA_ORG_ID` (Render) and run `python -m app.verify_integrity`. Confirms online/offline, last heartbeat, firmware by serial. |
| **`vola_org_id` on devices** | Left null if `VOLA_ORG_ID` unset at apply time | Set `VOLA_ORG_ID` before applying, or let the Vola sync back-fill on first poll. |
| **T-Mobile synchronous lookup** (ICCID/IMEI/MSISDN → activation, VoLTE, usage, static IPv4) | ❌ Not implemented — `carrier_provider/tmobile.py` is a stub (`is_configured=False`) | Requires T-Mobile TAAP client implementation + `TMOBILE_*` creds. Today only **inbound callback ingest** is live (`FEATURE_TMOBILE_CALLBACK_INGEST`), matching by ICCID→MSISDN→Device fallback and updating `Device.last_network_event`. |
| **Static IPv4 field** | No dedicated column surfaced for these devices | Device has `wan_ip`/`lan_ip`; populate when T-Mobile supplies the static IP, or via the static-ip callback. |
| **VoLTE flag** | No native column | Stored in `Sim.meta.volte_enabled=true` + device notes (documented gap). |
| **Per-device Zoho link** | No native column | Zoho link is on the Customer (`zoho_account_id`); device notes carry the account id. |
| **3 sibling properties** | Pending placeholders, no e911 | Supply verified addresses, then activate (portal or re-run with addresses). |
| **Pompano / Tiffany East parent link** | Exists in Zoho but not linked to Integrity parent | Optional Zoho cleanup (link child → Integrity, fix "Point"/"Pointe" spelling). |

---

## 5. Exact commands to run

All from the `api/` directory.

```bash
# 0. (once) ensure deps + DB are at head — this also applies migration 046
alembic upgrade head

# 1. Unit tests (no DB / no creds needed)
python -m pytest tests/test_onboard_integrity.py -q

# 2. Dry run — prints the full plan, writes NOTHING (default)
python -m app.seed_integrity

# 3. Apply for real (writes). Provide the admin email you want invited:
DRY_RUN=false INTEGRITY_ADMIN_EMAIL=cindy@ipmflorida.com python -m app.seed_integrity

# 4. Read-only verification (DB visibility + Vola + T-Mobile)
python -m app.verify_integrity
```

Re-running step 3 is safe and idempotent: existing tenant/customer/site/device/
SIM/user rows are matched on their natural keys and left untouched (only a
missing `customer_id`/`zoho_account_id` is back-filled).

**Render note:** migration 046 runs automatically via the existing
`alembic upgrade head` build step. The `seed_integrity` apply (step 3) is run
manually (e.g. Render Shell) because it writes customer data and is intentionally
not in the auto-deploy path.

---

## 6. How to verify in the browser

1. Apply the onboarding (step 3 above) in the target environment.
2. Accept the Admin invite for the Integrity user (portal invite/accept flow),
   or have an existing SuperAdmin impersonate via `X-Act-As-Tenant: integrity-pm`.
3. Log in as the Integrity Admin and confirm:
   - **Customers** → "Integrity Property Management" is present and Zoho-linked.
   - **Sites** → 4 properties listed; **Belle Terre at Sunrise** shows the
     7800 W Oakland Park Blvd, Sunrise FL 33351 e911 address and status *active*;
     the other three show status *pending* with an "awaiting e911 address" note.
     "The Pointe of Pompano Beach Condo Association" is additionally marked
     *test* (`onboarding_status=test`) and must never be activated.
   - **Belle Terre → Service Units** → Elevator 1, 2, 3 (`elevator_phone`).
   - **Devices** → 3 × LM150, carrier T-Mobile, with serial/IMEI/ICCID/MSISDN
     and health/status.
   - **Isolation** → log in as a different tenant's user (e.g. `rh`); none of the
     Integrity sites/devices are visible.

---

## 7. Constraints honored

- No existing tenants/workflows touched — additive only; insert-if-absent.
- No secrets hardcoded — all API creds read from env (`VOLA_*`, `TMOBILE_*`,
  `ZOHO_CRM_*`).
- Backward compatible — no schema changes beyond one additive catalog row.
- Life-safety — no fabricated e911 addresses; placeholders flagged and inert.
