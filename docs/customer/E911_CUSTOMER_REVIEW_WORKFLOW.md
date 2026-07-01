# True911+ — Customer E911 Confirmation & Correction Workflow

> Let CUSTOMER_* users participate in E911 data validation **without ever
> overwriting the official E911 record**. Customers can **confirm** an emergency
> record is correct or **request a correction**; Manley operators review, approve,
> or reject. Every action is append-only audited. Additive on the Location Digital
> Twin.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.6 no green without evidence, §7 no jargon; E911 is life-safety), `DECISIONS.md`
> (D-006/D-015 — E911 axis, never collapse; never fabricate). Companions:
> `LOCATION_DIGITAL_TWIN.md`, `../CUSTOMER_DATA_BOUNDARY.md`, `RH_GO_LIVE_RUNBOOK.md`.
> Prepared: 2026-07-01.

---

## 1. Principle

The customer is a **participant, never an author** of the official E911 record. A
confirmation is a signed "this looks right"; a correction is a *request*, stored
as data. Neither writes `Site.e911_*` / ServiceUnit / Line. Making a change
official stays the controlled, Manley-gated `UPDATE_E911` step (`/api/e911-changes`).

## 2. Persistence — append-only, migration-free

Reviews are stored as append-only **`ActionAudit`** events (no new table); a
review's current state is derived from its event chain, keyed by `review_id`. This
makes the audit trail intrinsic (every confirm / correction / approve / reject /
apply is a logged event) and avoids an Alembic migration.

| Event `action_type` | Meaning |
|---|---|
| `e911_customer_confirm` | customer confirmed the shown record |
| `e911_correction_request` | customer requested a correction (stored, not applied) |
| `e911_review_approve` / `_reject` | operator decision |
| `e911_review_apply` | operator asserts the change was made via the controlled UPDATE_E911 flow |

## 3. Customer flow

- **Confirm** (`POST /api/customer/locations/{ref}/e911/confirm`) — snapshots the
  record the **server** currently shows (address + endpoints + verification), plus
  an optional note. Does **not** mark the official record verified. UI: *"Customer
  confirmed — pending Manley verification."*
- **Request Correction** (`POST …/e911/correction-request`) — a small form:
  corrected address, suite/floor/unit, callback number, service/elevator/FACP
  identifier, note/reason. Creates a **pending** request; official records
  untouched. UI: *"Correction submitted — under Manley review."*
- **Review status** (`GET …/e911/review-status`) — the friendly state (own tenant
  only): **Not yet verified · Customer confirmed · Correction requested · Under
  Manley review · Verified**.

## 4. Internal Operations

- `GET /api/e911-changes/reviews?status=pending` — the review queue.
- `POST /api/e911-changes/reviews/{id}/approve` (opt. `apply`) · `POST …/reject`.
- Applying to the official record remains the existing `UPDATE_E911`
  `/api/e911-changes` flow (E911ChangeLog) — never automatic from customer input.

## 5. RBAC

| Capability | Roles |
|---|---|
| Submit confirm / correction | **`CUSTOMER_SUBMIT_E911_REVIEW`** → CUSTOMER_ADMIN / MANAGER / SUPPORT / USER |
| View review status (own tenant) | `CUSTOMER_VIEW_E911` (incl. VIEWER / READONLY) |
| Review / approve / reject / apply | `UPDATE_E911` **or** `MANAGE_SERVICE_CLASSIFICATION` (internal only) |

**Policy decision:** read-only customer roles (**VIEWER / READONLY**) may **view**
review status but may **not submit** — validation is an action, reserved for
account owner / staff / support. Customers can **never** overwrite official E911,
mark it verified, access another tenant, or reach the internal review queue
(enforced server-side; opaque location refs only; two-key flag gate).

## 6. Data safety

Never fabricate E911. Never overwrite official E911 from customer input. Never
expose internal identifiers. Confirm snapshots the server-authoritative record
(not client-supplied content). Correction fields are stored as a *request* only.
Existing E911 APIs (`GET/POST /api/e911-changes`, `/gaps`) are unchanged (additive).

## 7. Files

- Service: `api/app/services/e911_review.py`.
- Customer endpoints: `api/app/routers/customer.py` (confirm / correction-request /
  review-status). Internal: `api/app/routers/e911.py` (reviews / approve / reject).
- Guard: `dependencies.require_any_permission`; perm `CUSTOMER_SUBMIT_E911_REVIEW`
  (`permissions.json`).
- UI: `web/src/components/customer/LocationCommandCenter.jsx` (E911 section).
- Tests: `api/tests/test_e911_review.py`.

## 8. Roadmap

Operator apply → auto-create an `E911ChangeLog` draft from an approved correction;
notify the customer on decision; per-review detail view in the internal console;
optional policy to allow a confirmation to set an interim "customer-confirmed"
sub-state on the record (still Manley-gated for `verified`).
