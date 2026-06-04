# UX & QA Analyst role (`UX_QA_ANALYST`)

An **additive** RBAC role for Sivmey and future Platform Operations Analysts.
It does not remove, weaken, or modify any existing role, admin function, or
customer access. RBAC is data-driven from `permissions.json` (read by both the
backend `api/app/services/rbac.py` and the frontend `web/src/contexts/AuthContext.jsx`
via the `@permissions` alias), so the role is defined in **one** place.

## What it can do
Baseline = the existing safe **`DataSteward`** grant set **plus** `GENERATE_REPORT`
and `COMMAND_EXPORT_REPORTS`. Concretely:

- **Customers** — view, create, edit (incl. ownership corrections via gated tools)
- **Sites** — view, create, edit; **correct addresses / E911 address fields**
  (the `e911_*` fields ride `EDIT_SITES`; every edit is audited)
- **Devices** — view, create, edit metadata, update assignments / ownership
- **Billing visibility / metadata** — view lines & recordings; create/edit service
  units, SIMs, lines (subscription metadata, billing-mapping corrections)
- **Mapping confirmation** — onboarding review + import verification (view & manage),
  registrations & provisioning queue (view)
- **Imports** — site import, subscriber import
- **Reporting** — generate reports, export reports, view assurance / health scores

## What it cannot do (denied by omission)
User/role admin, security settings, API/carrier credentials, environment/system
config, deployment, database administration, integrations/providers, device-key
rotation, reconciliation engine, all `DELETE_*`, and all `MANAGE_*` admin surfaces.

## Two capabilities intentionally deferred (REQUIRES REVIEW — not granted)
1. **Heavy `UPDATE_E911` command** stays **Admin-only**. The role spec itself
   requires that *E911 changes go through an approval workflow*; that workflow does
   not exist yet, so granting the raw life-safety write would violate the safeguard.
   Address-level E911 correction is already available through `EDIT_SITES` (audited).
2. **Read-only customer impersonation** is **not** granted. Today `X-Act-As-Tenant`
   is SuperAdmin-only and grants the impersonated role's *full* permissions — there
   is no read-only enforcement. Granting it now would be privilege escalation. A
   true read-only impersonation mode should be designed separately before this role
   receives it.

## Safeguards (already enforced by the platform)
- **All writes are audit-logged** via `AuditLogEntry` on the existing router paths.
- **E911 / billing / ownership edits** flow through the same audited endpoints used
  by Admin/DataEntry — no new unaudited write path is introduced.
- **Remediation tools** remain dry-run-first and gated by their own `FEATURE_*`
  flags; this role grants the data access to *review* dry-runs, not a new apply path.

## Impact
- **Database:** none. `users.role` is free-form `String(50)` — no migration.
- **API:** `ALLOWED_ROLES` in `api/app/routers/admin.py` extended so the role is
  assignable; no endpoint behavior changed.
- **UI:** `AdminUsers.jsx` gains the role option in the two role pickers + a badge
  color; `AuthContext.jsx` gains normalization variants. No portal redesign.
- **Feature flag:** **not used** — the role grants nothing until a user is explicitly
  assigned it, so it cannot affect any existing user. A flag would add risk without
  benefit.

## Assigning the role
- **Preferred:** Admin UI → Users → set role to "UX & QA Analyst".
- **Scripted (idempotent, operator-run):**
  ```bash
  cd api
  python -m scripts.create_ux_qa_analyst \
      --email sivmey@manleysolutions.com --name "Sivmey" \
      --tenant default --password 'ChangeMeNow123'
  ```
  Creates or updates a single user row (role `UX_QA_ANALYST`, `must_change_password=True`)
  + one audit entry. Refuses if the tenant does not exist. Never deletes or touches
  other tables. To make Sivmey a *platform* user (so internal-only surfaces like the
  registration queue appear), attach her to an internal tenant listed in
  `settings.INTERNAL_TENANT_IDS`.

## Rollback
1. **Revoke from a user:** set their role back to `User` (or `is_active=false`) in the
   Admin UI — instant, no deploy.
2. **Remove the role entirely:** revert these files — `permissions.json`,
   `api/app/services/rbac.py`, `web/src/contexts/AuthContext.jsx`,
   `api/app/routers/admin.py` (`ALLOWED_ROLES`), `web/src/pages/AdminUsers.jsx`,
   `api/scripts/inspect_user_access.py`, and the test additions in
   `api/tests/test_rbac_matrix.py`. No migration to undo. Any user still carrying the
   string `UX_QA_ANALYST` would then normalize to itself and, absent the matrix entry,
   `can()` returns `False` for every action (safe-closed — they lose access rather
   than gain it).
