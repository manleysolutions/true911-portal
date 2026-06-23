# True911+ — RH SECURITY READINESS (tenant-isolation sweep)

> **Pre-credential security assessment for Restoration Hardware.** A read-only audit
> of **every API GET endpoint** for tenant filtering, RBAC enforcement, and
> cross-tenant data-exposure paths **before RH credentials are issued.** Assessment
> only — no code, no PRs, no behavior change.
>
> **Authority Level:** 3 — Execution (security gate). **Governed by:**
> `CONSTITUTION.md` (§3 priority order — Security #3; §4.7 tenant isolation is sacred).
> **Companion:** `RH_ROLE_MATRIX.md` (RBAC). **Method:** full sweep of ~50 routers /
> ~140 GET endpoints against the auth model in `api/app/dependencies.py`.
> Prepared: 2026-06-22. Branch: `main`.

---

## 1. Headline verdict

**Tenant isolation is fundamentally sound — but RBAC enforcement is inconsistent,
and a clean, minimal customer surface does not yet exist.** Issuing Judy credentials
is **CONDITIONAL GO**: clear a small, bounded fix set first (one HIGH defect + a
handful of customer-reachable defense-in-depth gaps + one customer-reachable config
leak), and address the structural RBAC gap in `RH_ROLE_MATRIX.md`.

- ✅ **No CRITICAL findings.** No endpoint trusts a caller-supplied `tenant_id` /
  `customer_id` to select data. Every DB-backed GET that returns tenant data filters
  on `current_user.tenant_id`. Single-row path lookups (`/sites/{id}`,
  `/devices/{id}`, `/incidents/{id}`, …) **AND the tenant predicate**, so an
  out-of-tenant id returns 404 rather than leaking. Service-layer loaders
  (`load_site_assurance_signals`, `build_device_health`, `list_port_states/events`)
  were confirmed to filter by the passed `tenant_id`.
- ⚠️ **1 HIGH** cross-tenant defect (internal-privileged path, not customer-reachable).
- ⚠️ **2 MED** + **4 LOW** items, several **customer-reachable**, all small/bounded.
- 🧱 **1 structural RBAC gap:** a large set of GETs are guarded by **bare
  `get_current_user` with no permission**, so they are reachable by *any* authenticated
  user (including a customer) and **cannot be removed via `permissions.json` alone.**
  This is the real work to give Judy a safe, minimal surface — detailed in
  `RH_ROLE_MATRIX.md`.

> **UPDATE 2026-06-22 — PR-S1 landed (branch `fix/rh-p1-tenant-isolation`).** All five
> §5 must-fix items — **H1, M2, L1, L2, L3 — are CLOSED.** Additive `WHERE tenant_id ==`
> predicates + the `ImportBatch` ownership gate + the `VIEW_INTEGRATIONS` guard on
> `/api/zoho/config`. New regression suite `tests/test_rh_p1_tenant_isolation.py`
> (11 tests) green; full backend suite **2379 passed**; frontend build green. The
> structural RBAC gap (bare-`get_current_user`) remains PR-B1/PR-B2 work.

## 2. The auth model (ground truth — `api/app/dependencies.py`)

| Mechanism | Enforces | Does **not** enforce |
|---|---|---|
| `get_current_user` | authentication; resolves `current_user.tenant_id` (incl. SuperAdmin `X-Act-As-Tenant` impersonation) | **no tenant scoping**, **no RBAC** — any authenticated user passes |
| `require_permission("PERM")` | RBAC (role can do PERM) | **no tenant scoping** — each query must filter itself |
| `require_platform_role("PERM")` | RBAC **+ rejects customer-tenant callers and impersonation** → internal/platform only | — |
| *(no dependency)* | nothing — **PUBLIC / unauthenticated** | — |

**Consequence:** tenant isolation is a **per-query responsibility**, not a framework
guarantee. The sweep therefore verified the actual `WHERE` clause of every GET, not
just its signature. The good news: the per-query discipline is applied **consistently**
across the codebase. The gap is that RBAC guards are applied **inconsistently** (many
GETs omit a permission entirely).

## 3. Findings (ranked)

### 🔴 CRITICAL — none.

### 🟠 HIGH (1)

**H1 — `GET /api/subscriber-import/batches/{batch_id}/rows` is not tenant-scoped.** ✅ **CLOSED (PR-S1).**
- **File:** `subscriber_import.py:154` → service `get_batch_rows(db, batch_id)`
  (`subscriber_import_engine.py:1336`) selects `ImportRow WHERE batch_id == batch_id`
  with **no tenant filter**; the caller-supplied `batch_id` is trusted.
- **Exposure:** any holder of `SUBSCRIBER_IMPORT` (Admin / DataEntry / DataSteward /
  UX_QA_ANALYST), or **SuperAdmin while impersonating**, who knows/guesses another
  tenant's `batch_id` retrieves that tenant's import rows — including resolved
  `site_id`/`device_id`/`line_id`. **Not reachable by the customer "User" role**
  (perm not held) → HIGH, not CRITICAL. **But Sivmey holds this perm + SuperAdmin**,
  so it is a live internal cross-tenant gap.
- **Why it matters for RH:** violates §4.7 (tenant isolation is sacred) regardless of
  who can reach it; the lone outlier among the import GETs (siblings `/batches`,
  `/verify`, `/verify/site/{id}` all pass `tenant_id`).
- **Fix (1 line + signature):** resolve the `ImportBatch` by `(batch_id,
  current_user.tenant_id)` (404 if not owned) **or** pass `tenant_id` into
  `get_batch_rows` and add `.where(ImportRow.tenant_id == tenant_id)`.

### 🟡 MED (2)

**M2 — `GET /api/zoho/config` reachable by any authenticated user (incl. customer).** ✅ **CLOSED (PR-S1)** — now behind `VIEW_INTEGRATIONS`.
- **File:** `zoho_crm.py:13` — guarded by **bare `get_current_user`**; returns
  `config_summary()` (integration configured-or-not + non-secret settings). No tenant
  data, no secrets. **But it is the lone integration `/config` not behind
  `VIEW_INTEGRATIONS`** (carrier_verizon, zoho_review, integration_webhooks all gate
  it). Judy should not see platform integration internals.
- **Fix:** add `dependencies=[Depends(require_permission("VIEW_INTEGRATIONS"))]`.

**M1 — `GET /api/hardware-models` is PUBLIC (unauthenticated).**
- **File:** `hardware_models.py:12,29` — no dependency; returns the **global**
  hardware catalog (`HardwareModel` has no `tenant_id`). **Not cross-tenant customer
  data**, but unauthenticated exposure of vendor/model inventory. Labeled intentional
  ("no auth needed for onboarding").
- **Fix (product call):** if undesired, add `Depends(get_current_user)`. Not a
  tenant-isolation defect; low urgency for RH.

### 🟢 LOW (4) — defense-in-depth (safe today, harden before external customer)

**L1 — `GET /api/sites/{site_pk}/infrastructure` child queries omit tenant filter.** ✅ **CLOSED (PR-S1).**
- `sites.py:391-404`: parent `Site` is tenant-gated first (L383), but child
  `Device`/`Sim`/`Line` queries filter only on `site_id`. **Customer-reachable**
  (`get_current_user`). Safe **only because** `site_id` strings are sourced from a
  tenant-gated parent — but `site_id` is a **non-unique business key** by design
  (`DATA_MODEL.md`). **Fix:** add `tenant_id == current_user.tenant_id` to each child query.

**L2 — `GET /api/devices/{device_pk}/sims` SIM join omits tenant filter.** ✅ **CLOSED (PR-S1).**
- `devices.py:542-549`: device is tenant-gated first; the SIM join filters only on
  `DeviceSim.device_id`. **Customer-reachable.** **Fix:** add
  `Sim.tenant_id == current_user.tenant_id` to the join.

**L3 — Vendor name lookups omit tenant filter.** ✅ **CLOSED (PR-S1).**
- `command_vendors.py:120` and `command_contracts.py:54`: `Vendor.id.in_(vendor_ids)`
  has no tenant filter; safe because `vendor_ids` come only from tenant-scoped
  assignments/contracts. **Customer-reachable** (`COMMAND_VIEW_VENDORS` held by User).
  **Fix:** add `Vendor.tenant_id == current_user.tenant_id` for defense-in-depth.

**L4 — `GET /public/registrations/{id}` has no rate-limit/CAPTCHA.**
- `public.py:221`: public, **resume-token-gated** (constant-phrasing 403 on
  missing/wrong token, no existence leak), pre-tenant staging rows (no tenant data).
  **Not a tenant-isolation defect**, but the file's own SECURITY TODO flags missing
  rate-limiting (brute-force/abuse). **Track separately** (already known).

### Cleared / by design (no action)
- All `require_platform_role` GETs (registrations queue) — not customer-reachable;
  global ops-tenant queue is intentional.
- `GET /command/templates` returns `is_global` rows — deliberate shared catalog.
- T-Mobile callback GET probes (`tmobile_callback.py`) — return static acks only, no
  DB read, no tenant data; token gate applies to the POST ingest path.
- `GET /health/system` — status strings only, safe public probe.
- `support.py` session detail — tenant-gated (404 cross-tenant) + internal-note
  sanitization for non-admins. Correctly built.

## 4. Cross-tenant exposure paths — summary table

| Path class | Count audited | Result |
|---|---|---|
| Caller-supplied `tenant_id`/`customer_id` trusted | 0 | ✅ none exist |
| Single-row path-id lookups missing tenant predicate | 0 | ✅ all AND tenant_id |
| DB-backed GET with no tenant filter, customer-reachable | 0 direct | ✅ (L1/L2/L3 are child-query, parent-gated) |
| DB-backed GET with no tenant filter, privileged-reachable | 1 | 🟠 H1 (subscriber-import rows) |
| Service-layer loaders dropping the passed tenant_id | 0 | ✅ all confirmed filtered |
| PUBLIC GET returning tenant data | 0 | ✅ none (public GETs return acks/catalog/staging only) |

**Net: there is no path by which Judy (customer "User") can read another tenant's
data through a GET endpoint today.** The isolation core is GREEN.

## 5. Pre-credential fix set (bounded — one small PR)

**Must-fix before RH credentials are issued** (all additive `WHERE tenant_id ==`
one-liners, smallest-safe-slice, flag-free) — ✅ **DONE in PR-S1 (2026-06-22):**
- [x] **H1** — tenant-scope `get_batch_rows` via parent `ImportBatch` (foreign → 404).
- [x] **L1** — tenant-filter child queries in `/sites/{id}/infrastructure`.
- [x] **L2** — tenant-filter SIM join in `/devices/{id}/sims`.
- [x] **L3** — tenant-filter vendor-name lookups (vendors + contracts).
- [x] **M2** — gate `GET /api/zoho/config` behind `VIEW_INTEGRATIONS`.

> Verified: `tests/test_rh_p1_tenant_isolation.py` (11 tests) + full suite 2379 passed;
> frontend build green. Files: `subscriber_import.py`/`subscriber_import_engine.py`,
> `sites.py`, `devices.py`, `command_vendors.py`, `command_contracts.py`, `zoho_crm.py`.

**Structural — required for a clean customer surface (see `RH_ROLE_MATRIX.md`):**
- [ ] Resolve the **bare-`get_current_user` GET** problem so the customer role can be
      restricted to customer-safe surfaces (add permission guards or a customer
      allowlist). This is the larger pre-go-live RBAC task, not a one-liner.

**Track separately (not RH-credential-gating):**
- [ ] **M1** — auth on the public hardware catalog (product decision).
- [ ] **L4** — rate-limit/CAPTCHA on public registration lookup (existing TODO).

## 6. Security go / no-go for issuing RH credentials

| Gate | Status | Verdict |
|---|---|---|
| No caller-trusted tenant_id; no cross-tenant GET reachable by customer | ✅ met | GO |
| Single-row lookups tenant-gated | ✅ met | GO |
| Service loaders tenant-filtered | ✅ met | GO |
| H1 internal cross-tenant defect fixed | ✅ met (PR-S1) | GO |
| Customer-reachable defense-in-depth gaps (L1/L2/L3) closed | ✅ met (PR-S1) | GO |
| Customer-reachable config leak (M2) closed | ✅ met (PR-S1) | GO |
| Customer role restricted to safe surfaces (no internal ops tooling) | ❌ open | **`RH_ROLE_MATRIX.md` — required** |
| JWT in `localStorage`, CORS-wildcard guard, default-JWT-secret refuse-to-start | ⚠️ debt | track (BACKLOG H3/H4/H5) — not isolation-blocking |

**Verdict: CONDITIONAL GO.** The tenant-isolation foundation is safe to put a
customer in front of. Do **not** issue Judy's credentials until §5 must-fix items
land **and** her role is scoped per `RH_ROLE_MATRIX.md` — otherwise she would reach a
wall of internal operations endpoints (jargon + operational internals; a §7
Constitution violation even where tenant-safe).

---

*Assessment only — writes nothing, changes no behavior, creates no PRs.*
</content>
