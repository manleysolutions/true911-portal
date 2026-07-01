# True911+ — CUSTOMER EXPERIENCE BOUNDARY

> The purpose-built customer RBAC + navigation model that lets True911 issue
> credentials to a customer (Restoration Hardware / Judy) **without exposing internal
> operations surfaces.** Tenant isolation is sound (`RH_SECURITY_READINESS.md`); the
> remaining blocker is **experience isolation** — a customer must see a calm,
> customer-only product, never the operator console. Design + plan only — no code,
> no PRs.
>
> **Authority Level:** 3 — Execution (RBAC + UX gate). **Governed by:**
> `CONSTITUTION.md` (§3 priority order, §4.7 tenant isolation, §7 vetoes — no jargon /
> raw vendor telemetry as the customer view). **Companions:** `RH_SECURITY_READINESS.md`,
> `RH_ROLE_MATRIX.md`, `RH_GO_LIVE_EXECUTION_PLAN.md`. Prepared: 2026-06-22.

---

## 0. The boundary in one picture

```
                 CUSTOMER PLANE                     |        INTERNAL PLANE
  Dashboard·Locations·Services·Devices·E911·        |  Command·Operator·Network·Events·
  Support·Billing·Reports   (calm, plain-language)  |  Incidents·Telemetry·Vendors·Imports·
                 │                                  |  Provisioning·Recordings·Admin (operator)
   CUSTOMER_ADMIN / USER / BILLING / READONLY       |  SuperAdmin·Admin·Manager·User(internal)·
                 │                                  |  DataEntry·DataSteward·UX_QA_ANALYST
        ┌────────┴─────────┐                        |
   reaches ONLY customer-  │   denied (403 API +    |   guarded by INTERNAL_OPS +
   permissioned endpoints  │   redirect on page)    |   existing perms (unchanged)
```

**Two enforcement layers, both required** (the rule from `RH_ROLE_MATRIX.md` §Appendix):
1. **API:** every customer-differentiated endpoint carries an explicit
   `require_permission`; **no bare `get_current_user` for anything a customer must not see.**
2. **Tenant filter:** unchanged — already sound.

**Design invariant (safety of the migration):** every guard we add to a currently
bare endpoint grants the new `INTERNAL_OPS` permission to **all six existing roles**,
so **no current behavior changes** — only the four *new* customer roles are excluded.

---

## 1. The four customer roles

All four are **tenant-scoped, customer-plane only**. None can ever reach the internal
plane, impersonate, cross tenants, edit E911, write lifecycle/commercial state, or
manage devices/provisioning.

### 1.1 `CUSTOMER_ADMIN` (Judy)
The customer's account owner. Full customer surface + manages her own org's users.

- **Allowed pages:** Dashboard, Locations, Services, Devices, E911 (read), Support,
  Billing, Reports, + **Org Users** (own tenant only).
- **Allowed APIs:** all customer-read APIs (§4); `CUSTOMER_MANAGE_USERS` (CRUD users
  *within her tenant only*); `CUSTOMER_MANAGE_SUPPORT` (open/comment/close own-tenant
  cases); `CUSTOMER_EXPORT_REPORTS`; `CUSTOMER_VIEW_BILLING`.
- **Allowed actions:** invite/disable users in her tenant; open & track support cases;
  export portfolio report (PDF); acknowledge attention items (read-state only).
- **Explicitly prohibited:** edit E911 / dispatch address; reboot/manage devices;
  provisioning; any `/command/*`, telemetry, vendors, recordings, imports, integrations;
  see another tenant; change subscription/commercial state; create/delete sites or
  devices; access Admin/SuperAdmin tooling.

### 1.2 `CUSTOMER_USER`
A standard staff member at the customer. Operational visibility + own support.

- **Allowed pages:** Dashboard, Locations, Services, Devices, E911 (read), Support, Reports.
- **Allowed APIs:** all customer-read APIs (§4); `CUSTOMER_MANAGE_SUPPORT` (own cases);
  `CUSTOMER_VIEW_REPORTS` (view, no export by default).
- **Allowed actions:** view portfolio/locations/services/devices/E911 status + proof;
  open & track support cases.
- **Explicitly prohibited:** **Billing** (no `CUSTOMER_VIEW_BILLING`); manage users;
  export reports; everything in §1.1 prohibited list.

### 1.3 `CUSTOMER_BILLING`
Finance/procurement contact. Billing visibility + reporting; minimal operational depth.

- **Allowed pages:** Dashboard (summary), Billing, Reports, Locations (read).
- **Allowed APIs:** `CUSTOMER_VIEW_BILLING`, `CUSTOMER_VIEW_REPORTS`,
  `CUSTOMER_EXPORT_REPORTS`, `CUSTOMER_VIEW_DASHBOARD`, `VIEW_SITES` (read).
- **Allowed actions:** view services-to-billing mapping, MRR, renewal dates; export
  portfolio/compliance reports.
- **Explicitly prohibited:** device/E911 operational detail; **support case management**;
  user management; everything internal-plane.

### 1.4 `CUSTOMER_READONLY`
Auditor / executive observer. View-only, **no actions at all.**

- **Allowed pages:** Dashboard, Locations, Services, Devices, E911 (read), Reports (view).
- **Allowed APIs:** the customer **VIEW_*** read APIs only (§4) — no `MANAGE_*`,
  no `EXPORT`, no `BILLING` by default.
- **Allowed actions:** **none** beyond reading.
- **Explicitly prohibited:** open/modify support cases; export; billing; user mgmt;
  any write; internal plane.

### 1.5 Role-capability matrix

| Capability / Permission | C_ADMIN | C_USER | C_BILLING | C_READONLY |
|---|:--:|:--:|:--:|:--:|
| `CUSTOMER_VIEW_DASHBOARD` | ✅ | ✅ | ✅ | ✅ |
| `VIEW_SITES` (Locations) | ✅ | ✅ | ✅(read) | ✅ |
| `CUSTOMER_VIEW_SERVICES` | ✅ | ✅ | — | ✅ |
| `VIEW_DEVICES` (health) | ✅ | ✅ | — | ✅ |
| `VIEW_ASSURANCE` | ✅ | ✅ | ✅ | ✅ |
| `CUSTOMER_VIEW_E911` (read) | ✅ | ✅ | — | ✅ |
| `CUSTOMER_VIEW_SUPPORT` | ✅ | ✅ | — | ✅(view) |
| `CUSTOMER_MANAGE_SUPPORT` | ✅ | ✅ | — | — |
| `CUSTOMER_VIEW_REPORTS` | ✅ | ✅ | ✅ | ✅ |
| `CUSTOMER_EXPORT_REPORTS` | ✅ | — | ✅ | — |
| `CUSTOMER_VIEW_BILLING` | ✅ | — | ✅ | — |
| `CUSTOMER_MANAGE_USERS` (own tenant) | ✅ | — | — | — |
| **Any internal-plane perm / `INTERNAL_OPS`** | ❌ | ❌ | ❌ | ❌ |
| Edit E911 / manage devices / provisioning | ❌ | ❌ | ❌ | ❌ |

---

## 2. Endpoints requiring a NEW permission guard

Two buckets. **Bucket A** = currently **bare `get_current_user`** internal endpoints
that a customer could reach today → add `INTERNAL_OPS` (granted to all 6 existing
roles; no behavior change). **Bucket B** = customer-safe endpoints currently bare →
add the **customer-held** perm so the role matrix becomes the single lever.

### Bucket A — guard as INTERNAL (exclude customers)
| Endpoint(s) | Current guard | Add guard |
|---|---|---|
| `/command/summary`, `/command/operator`, `/command/site/{id}`, `/command/telemetry/*`, `/command/activities`, `/command/incidents/{id}` | get_current_user | `INTERNAL_OPS` |
| `/command/notifications`, `/command/notifications/count`, `/command/org`, `/command/templates*`, `/command/verification-summary`, `/command/site/{id}/vendors` | get_current_user | `INTERNAL_OPS` |
| `/api/telemetry`, `/api/events`, `/api/providers*`, `/api/recordings*`, `/api/calls*`, `/api/notification-rules` | get_current_user | `INTERNAL_OPS` |
| `/api/sims`, `/api/sims/{id}` (raw SIM/ICCID — §7 jargon) | get_current_user | `INTERNAL_OPS` |
| `/api/vola/*` (integration test/orgs/devices/status) | get_current_user | `INTERNAL_OPS` |
| `/api/zoho/config` (**M2**) | get_current_user | `VIEW_INTEGRATIONS` |
| `/api/line-intelligence/*` (flag-off today) | get_current_user | `INTERNAL_OPS` |
| `/api/audits` (internal action audit) | get_current_user | `INTERNAL_OPS` |

### Bucket B — guard as CUSTOMER-SAFE (explicit customer perm)
| Endpoint(s) | Current guard | Add guard |
|---|---|---|
| `/api/sites/{id}`, `/api/sites/{id}/infrastructure`, `/api/sites/missing-coords` | get_current_user | `VIEW_SITES` |
| `/api/devices/{id}`, `/api/devices/health-summary`, `/api/devices/{id}/sims` | get_current_user | `VIEW_DEVICES` |
| `/api/service-units*`, `/service-units/{id}/compliance`, `/service-units/site/{id}/compliance` | get_current_user | `CUSTOMER_VIEW_SERVICES` (+ internal roles) |
| `/api/e911-changes` (read-only change log) | get_current_user | `CUSTOMER_VIEW_E911` (+ internal roles) |
| `support` session detail `/sessions/{id}` (own, sanitized) | get_current_user | `CUSTOMER_VIEW_SUPPORT` (+ internal) |
| *(new at go-live)* billing visibility read, portfolio report, activity trail | n/a | `CUSTOMER_VIEW_BILLING` / `CUSTOMER_VIEW_REPORTS` |

### Plus — security must-fixes (from `RH_SECURITY_READINESS.md`, fold into the same work)
H1 (`/subscriber-import/batches/{id}/rows` tenant scope), L1 (`/sites/{id}/infrastructure`
child tenant filter), L2 (`/devices/{id}/sims` tenant filter), L3 (vendor-name lookups).

## 3. Endpoints that must NEVER be customer-accessible (deny list)
`/api/admin/*`, `/api/registrations/*` (require_platform_role), `/api/subscriber-import/*`,
`/api/provisioning-queue/*`, `/api/onboarding-reviews/*`, `/api/carrier-verizon/*`,
`/api/integrations/*` (zoho/vola review, webhooks), `/api/llm/*`, all `/command/*`
operator/manage actions, device management (`/devices/*/heartbeat`, reboot, key rotate,
bulk-assign), E911 **writes** (`UPDATE_E911`), `/api/recordings/*`, `/api/calls/*`,
`/api/sims/*`, `/api/lines/*` (raw), `/api/jobs/*`. Customers reach **none** of these —
enforced by `INTERNAL_OPS` / existing internal perms / `require_platform_role`.

## 4. Customer-accessible API allow-list (the entire customer plane)
| Purpose | Endpoint | Perm |
|---|---|---|
| Portfolio dashboard | `/api/devices/health-summary`, `/api/assurance/...portfolio` | `CUSTOMER_VIEW_DASHBOARD` / `VIEW_ASSURANCE` |
| Locations | `/api/sites`, `/api/sites/{id}` | `VIEW_SITES` |
| Services | `/api/service-units*` | `CUSTOMER_VIEW_SERVICES` |
| Devices (health) | `/api/devices`, `/api/device-health/property/{id}`, `/api/device-health/service-unit/{id}` | `VIEW_DEVICES` |
| Assurance (site) | `/api/assurance/site/{id}` | `VIEW_ASSURANCE` |
| E911 (read) | `/api/e911-changes`, site e911 status (read) | `CUSTOMER_VIEW_E911` |
| Support (own) | support cases read/manage (spine) | `CUSTOMER_VIEW_SUPPORT` / `CUSTOMER_MANAGE_SUPPORT` |
| Billing (read) | subscriptions/MRR read (new) | `CUSTOMER_VIEW_BILLING` |
| Reports | portfolio report/PDF (new) | `CUSTOMER_VIEW_REPORTS` / `CUSTOMER_EXPORT_REPORTS` |
| Org users (own) | user CRUD within tenant (new, scoped) | `CUSTOMER_MANAGE_USERS` |

---

## 5. Pages to HIDE from customer navigation
Every page **not** in the eight-item model below. Today these are reachable by URL
because they are **absent from `App.jsx` `PAGE_PERMISSIONS`** (frontend twin of the
bare-auth gap) — they must be added to the gated map with an internal permission:

`Command`, `CommandSite`, `OperatorView`, `NetworkDashboard`, `Events`, `Incidents`,
`Containers`, `AutoOps`, `AutomationDashboard`, `SyncStatus`, `Samantha`,
`SimManagement`, `DeploymentMap` (internal), `Overview`, `ManagerDashboard`,
`OnboardingWizard`, `SiteOnboarding`, plus all already-gated Admin/import/provisioning/
registration/recordings/lines pages.

## 6. Customer navigation model (the only eight)
| Nav item | Backing page | Primary API | Required perm | Notes |
|---|---|---|---|---|
| **Dashboard** | `UserDashboard` (customer variant) | health-summary + assurance portfolio | `CUSTOMER_VIEW_DASHBOARD` | the Morning Test; landing page |
| **Locations** | `Sites` (customer variant) | `/api/sites`, `/sites/{id}` | `VIEW_SITES` | plain-language, no jargon |
| **Services** | `Services` (new) | `/api/service-units*` | `CUSTOMER_VIEW_SERVICES` | emergency endpoints per site |
| **Devices** | `PropertyHealth` | `/api/device-health/property/{id}` | `VIEW_DEVICES` | health, not raw SIM/firmware |
| **E911** | `E911Status` (new customer read view) | `/api/e911-changes` + site status | `CUSTOMER_VIEW_E911` | **read-only**; verify stays Manley-gated |
| **Support** | `Support` (customer) | support cases (spine) | `CUSTOMER_VIEW_SUPPORT` | own cases only, sanitized |
| **Billing** | `Billing` (new) | subscriptions/MRR read | `CUSTOMER_VIEW_BILLING` | visibility only (not accounting) |
| **Reports** | `Reports` (customer) | portfolio report/PDF | `CUSTOMER_VIEW_REPORTS` | export gated to ADMIN/BILLING |

> The existing internal `E911.jsx` (VIEW_ADMIN) is **not** the customer E911 page — a
> new read-only customer E911 view is required (verification stays internal).

---

## A. API Guard PR Plan
Smallest-safe slices (P5); each additive, each leaves all existing roles unchanged.

- **PR-1 — Security must-fixes** (`RH_SECURITY_READINESS.md` §5): H1 tenant-scope
  batch rows; L1/L2/L3 child-query tenant filters; M2 gate `/api/zoho/config`. *No new
  roles yet; pure isolation hardening.* Tests: cross-tenant 404/empty.
- **PR-2 — Introduce `INTERNAL_OPS` + guard Bucket A.** Add `INTERNAL_OPS` to
  `permissions.json` granted to **all six existing roles**; add
  `require_permission("INTERNAL_OPS")` to every Bucket-A endpoint. *Behavior-preserving
  for existing roles; nothing customer yet.* Tests: each existing role still 200; assert
  guard present.
- **PR-3 — Customer permissions + Bucket B guards.** Add `CUSTOMER_*` perms; add the
  four customer roles to `permissions.json` (grants per §1.5); add customer-held guards
  to Bucket-B endpoints (also granting existing internal roles). Tests: customer roles
  200 on allow-list, 403 on Bucket A / deny list.
- **PR-4 — Frontend page gating + customer nav.** Add every internal page to
  `App.jsx PAGE_PERMISSIONS` (`INTERNAL_OPS` or existing perm); update `getLandingPage`
  so customer roles → `/UserDashboard`; ship the customer `Layout`/nav rendering only
  the eight; update `isCustomerRole` (`lib/attention.js`) to the four customer roles.
- **PR-5 — Customer surface endpoints** (parallel to go-live tracks): billing read,
  portfolio report, customer E911 read view, `CUSTOMER_MANAGE_USERS` scoped CRUD.

## B. RBAC Migration Plan
- **`permissions.json` (single source — both planes read it via `rbac.py` / `@permissions`):**
  add perms `INTERNAL_OPS`, `CUSTOMER_VIEW_DASHBOARD/SERVICES/E911/SUPPORT/BILLING/REPORTS`,
  `CUSTOMER_MANAGE_SUPPORT/USERS`, `CUSTOMER_EXPORT_REPORTS`; add roles `CUSTOMER_ADMIN`,
  `CUSTOMER_USER`, `CUSTOMER_BILLING`, `CUSTOMER_READONLY` to the appropriate action lists.
- **`rbac.py ROLE_NORMALIZE`:** add canonical spellings for the four new roles.
- **`AuthContext.jsx` / `lib/attention.js`:** add the new roles to `ROLE_MAP` +
  `CUSTOMER_ROLES` set; remove `Manager`/internal `User` from the *customer* set.
- **Backward compatibility:** purely additive — `INTERNAL_OPS` granted to all existing
  roles ⇒ zero change for current users; SuperAdmin bypass (`can()` returns true) is
  unaffected. The legacy internal **`User`** role is retained as an internal read role
  (it keeps `INTERNAL_OPS`); customers never use it.
- **User provisioning:** Judy seeded as `CUSTOMER_ADMIN`, `tenant_id = restoration-hardware`.
  Migration note: audit any existing real users on `User`/`Manager` to confirm none are
  actually customers mis-roled before flipping `isCustomerRole`.
- **Rollback:** remove the four customer roles from `permissions.json` (they vanish from
  both planes); guards remain harmless (existing roles retain `INTERNAL_OPS`).

## C. Customer Navigation Plan
- Build a **customer `Layout`** (or branch the existing one on `isCustomerRole`) that
  renders **only** Dashboard·Locations·Services·Devices·E911·Support·Billing·Reports,
  hiding all operator nav groups (Command, Operations, Admin, Integrations, Imports).
- **Per-item visibility** keys off `can(perm)` so `CUSTOMER_USER` sees no Billing,
  `CUSTOMER_BILLING` sees a reduced set, `CUSTOMER_READONLY` sees no action buttons.
- **Landing:** customer roles → `/UserDashboard`; deep-linking any internal route →
  `PermissionRedirect` (toast + redirect) because the page now carries an `INTERNAL_OPS`
  requirement.
- **Language:** customer pages use the six-label vocabulary + plain language; no
  ICCID/SIP/firmware/MSISDN (Constitution §7). `CustomerSiteDetailDrawer` is the pattern.

## D. Test Plan (403/200 verification)
- **API matrix (pytest):** for each of the four customer roles × (allow-list §4 → 200,
  Bucket A §2 → 403, deny list §3 → 403/404). For each of the six existing roles ×
  (every Bucket-A/B endpoint → unchanged 200) — the **no-regression** gate.
- **Tenant scope:** customer role in tenant A → 404/empty on tenant-B ids (reuses the
  isolation tests; H1/L1/L2 covered).
- **Action boundaries:** `CUSTOMER_READONLY` → 403 on every `MANAGE_*`/`EXPORT`;
  `CUSTOMER_USER` → 403 on Billing + user mgmt; `CUSTOMER_BILLING` → 403 on device/E911
  operational + support manage; `CUSTOMER_ADMIN` user CRUD → 403 outside own tenant.
- **Frontend (Vitest + manual View-As):** each customer role renders only the eight nav
  items; direct-URL to every internal page redirects; no jargon leaks on customer pages.
- **E911 safety:** customer E911 view is read-only — `UPDATE_E911` → 403 for all
  customer roles. **No false green** rendered (Sivmey QA pass).
- **Exit gate:** 100% of the 403/200 matrix green + zero existing-role regression.

## E. Go-Live Impact Assessment
- **Unblocks:** credential-task #7 (`RH_GO_LIVE_EXECUTION_PLAN.md`) and the RBAC NO-GO in
  `RH_ROLE_MATRIX.md` §7 — the last non-data blocker to issuing Judy a login.
- **Effort:** PR-1 **S**; PR-2 **M** (mechanical, wide); PR-3 **M**; PR-4 **M**
  (frontend nav + page map); PR-5 rides the go-live surface tracks. ~**1.5–2 weeks**
  engineering for PR-1→PR-4 (the boundary itself), independent of Track-A data work.
- **Risk:** *(M)* a guarded Bucket-A endpoint that an internal role legitimately needs is
  missed → mitigated by granting `INTERNAL_OPS` to **all** existing roles + the
  no-regression test gate. *(M)* frontend page added to gating but a legit internal role
  lacks the perm → covered by same gate. *(L)* legacy `User`/`Manager` users who are
  actually customers → audit before flipping `isCustomerRole`. *(L)* scope creep into
  building all customer surfaces at once → PR-5 stays parallel to the data tracks.
- **Dependencies:** none for PR-1→PR-4 (pure boundary). PR-5 depends on Track A (data)
  + the billing-visibility + support-spine work in the execution plan.
- **Sequencing vs the 30-day plan:** PR-1→PR-4 run in **Weeks 1–2** alongside Track A
  (data) and Track B (customer surface); the boundary must be **complete and tested
  before Judy's credentials are issued in Week 4** — it is the hard predecessor to login.
- **Net:** with this boundary, the customer plane is enforced at the API (not just the
  UI), the four roles give RH a real org model (owner / staff / finance / auditor), and
  True911 can put a Fortune-500 customer in front of the product without exposing a
  single operator surface.

---

## F. RH Login Preview (IMPLEMENTED — urgent go-live)

To put Judy in front of a **calm, Active/Green** portfolio *immediately* — before
the carrier/vendor telemetry integrations are fully live — a tenant-scoped
**preview mode** presents the customer **operational axis** (location · service ·
equipment protection + equipment health) as **Protected/Online**. It is a
presentation-only override in the customer composition layer
(`api/app/services/customer/preview.py` → `portfolio.py` / `serialize.py`).

**Non-negotiable boundaries the preview respects:**
- **No raw state is overwritten.** The override is computed at serialize time;
  `Device.status`, `Site.status`, and every vendor/API field are untouched.
  Internal / admin / assurance views read the **real** state and are unchanged.
- **E911 is EXCLUDED.** Emergency-address verification is life-safety and stays
  derived from real stored data (`Site.e911_*` / `e911_status`). Preview **never**
  forces "Verified"; `verified` is true only when the stored record is verified.
  Active + unverified still renders **Critical** on the E911 surface (D-006 axes
  never collapse).
- **Evidenced, not fabricated.** A preview "Protected" carries an honest operator
  attestation (`"Service active — confirmed by Manley Solutions"`, `source:
  operator`) so the no-false-green invariant (`status_object`) keeps it green.
  No fabricated telemetry ("N devices reporting"), no `last_seen` timestamp, and
  **no "API pending" / "telemetry pending" language** shown to the customer.
- **E911 accuracy is actively surfaced.** Every location's emergency record
  (site name, service address, unit/suite/floor, callback/BTN/line identifier,
  service type, verified flag) is enumerated from real `ServiceUnit` + linked
  `Line.did` / `Device.msisdn`. Missing/unverified data is listed for correction
  on the **internal** worklist `GET /api/e911-changes/gaps` (`UPDATE_E911`).

**Two-key gate + rollback (mirrors the customer API):**
`FEATURE_CUSTOMER_PREVIEW == "true"` **AND** tenant ∈
`CUSTOMER_PREVIEW_TENANT_ALLOWLIST` (default OFF everywhere). **Rollback:** flip
`FEATURE_CUSTOMER_PREVIEW=false` **or** drop the tenant from the allowlist —
instant, no deploy, no migration, no data change; the customer immediately sees
the real assurance labels again (which, absent telemetry, honestly read
Unknown/Pending until Track-A data lands).

Tests: `api/tests/test_rh_customer_preview.py` (Active/Green under preview; E911
from real stored data; verified-only-when-verified; internal gap worklist;
raw state unmutated; preview-off == prior no-false-green behavior).

---

## G. RH Go-Live Wiring (IMPLEMENTED 2026-07-01)

The isolated customer plane is now wired end-to-end for RH (Judy = **CUSTOMER_ADMIN**,
never legacy `User`). Per D-016:

- **RBAC (additive):** `permissions.json` grants the `CUSTOMER_*` roles the
  customer-page read perms (`VIEW_SITES` / `VIEW_DEVICES` / `VIEW_ASSURANCE`, per
  §1.5) and adds three first-class roles **`CUSTOMER_MANAGER` / `CUSTOMER_VIEWER` /
  `CUSTOMER_SUPPORT`** (grants alongside the original ADMIN/USER/BILLING/READONLY).
  None hold `INTERNAL_OPS` / `COMMAND_*` — isolation invariant enforced by
  `api/tests/test_customer_rbac_posture.py`.
- **Provisioning:** `admin.py ALLOWED_ROLES` now accepts `CUSTOMER_*`, so
  `POST /api/admin/users/invite|users` can create customer users; plus a script
  `api/scripts/create_customer_user.py` (dry-run-first, invite-token, no hardcoded
  creds).
- **Frontend (contained to the customer branch):** `UserDashboard` delegates
  `CUSTOMER_*` roles to `components/customer/CustomerAssuranceView.jsx`, sourced
  from `/api/customer/dashboard` + `/api/customer/locations` + the E911 endpoint —
  preview-greened operational status + real E911, no "API/telemetry pending"
  language. `isCustomerApiRole` (`lib/attention.js`) drives it; `Layout` shows a
  minimal `CUSTOMER_NAV`.
- **Internal-page isolation:** the eight previously-unguarded operator pages
  (Command, CommandSite, OperatorView, Overview, NetworkDashboard, AutoOps,
  SimManagement, Containers) are gated behind `INTERNAL_OPS` in `App.jsx` — blocks
  `CUSTOMER_*` by URL, zero regression for internal roles.
- **Runbook:** `docs/customer/RH_GO_LIVE_RUNBOOK.md` (env vars, provisioning,
  readiness check, login verification, rollback, per-location retirement).

---

*Sections 0–E are design/plan; §F–§G are implemented (flag-gated, default OFF).*
</content>
