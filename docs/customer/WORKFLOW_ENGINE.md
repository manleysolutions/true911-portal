# True911+ — Customer Workflow Engine (Contribution & Review)

> The customer-plane Workflow Engine turns the Location Workspace into a
> **collaborative Building Workspace**: customers *contribute* to their Digital
> Twin (contacts, inspections, photos, documents, procedures, notes, service
> requests) through a **submission → review** workflow. A contribution is a
> **request stored as data** — it never writes a protected record directly.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.6 no green without evidence, §7 no jargon), `../CUSTOMER_DATA_BOUNDARY.md`.
> Companions: `LOCATION_DIGITAL_TWIN.md`, `DIGITAL_TWIN_MATURITY_MODEL.md`,
> `E911_CUSTOMER_REVIEW_WORKFLOW.md`. Prepared: 2026-07-01.

---

## 1. Scope & boundary

This is the **customer-facing** workflow layer only. It is deliberately distinct
from any internal operational automation — customers never see, trigger, or
depend on internal engines. Every customer action is one of two safe shapes:

1. **Contribution** — the customer submits information to enrich the twin.
2. **Review** (existing) — the customer confirms/corrects the E911 record.

Both share the same safe substrate: an **append-only `ActionAudit` event chain**.
There is no new table (migration-free), and the current state of any item is
*derived* from its events — the audit trail is intrinsic, not bolted on.

## 2. The contribution workflow

`app/services/customer/contributions.py`

- `record_contribution(db, user, site, *, ctype, payload, note)` — writes one
  append-only `customer_contribution` audit event and returns
  `{contribution_id, type, status, message}`. Raises `ValueError` on an unknown
  type. **Never** writes `Site` / `ServiceUnit` / `Line` / E911.
- `list_contributions(db, tenant_id, site_id)` — the location's contribution log
  (newest first) + `by_type` counts + per-item `payload` for display.
- `contribution_counts(...)` — by-type counts, consumed by the maturity/health
  signals.

**Types:** `contact · inspection · photo · document · procedure · note ·
service_request`. `note` is self-serve (`status = recorded`); every other type is
`submitted` and awaits operator review. File types (`photo/document/procedure`)
record **metadata only** today — real blob storage is a later, controlled step;
nothing is fabricated in the meantime.

## 3. API (additive, two-key gated)

| Method | Endpoint | Permission | Purpose |
|---|---|---|---|
| `POST` | `/api/customer/locations/{ref}/contributions` | `CUSTOMER_CONTRIBUTE` | Submit a contribution |
| `GET`  | `/api/customer/locations/{ref}/contributions` | `CUSTOMER_VIEW_LOCATIONS` | Read the contribution log |

Both keep the standard two-key gate (`require_customer_api`: `FEATURE_CUSTOMER_API`
+ tenant allowlist → 404 when off) **plus** the `CUSTOMER_*` permission. Unknown
contribution type → `422`; missing/foreign location → `404`.

## 4. RBAC

`CUSTOMER_CONTRIBUTE` is granted to **ADMIN / MANAGER / SUPPORT / USER** (the
submitter roles — the same set as `CUSTOMER_SUBMIT_E911_REVIEW`). Read-only roles
(**VIEWER / READONLY / BILLING**) can *view* the log but cannot submit. The grant
lives in the shared `permissions.json` (frontend + backend). CUSTOMER_* remains
fully isolated from internal `INTERNAL_OPS` / `COMMAND_*` permissions.

## 5. Frontend

`web/src/components/customer/LocationCommandCenter.jsx` — the Building Workspace,
organised into four workspaces (**Building Summary · Operations · Compliance ·
Administration**). A reusable `<Contribute type=…>` control renders the neutral
`+ Add …` button and inline form, POSTs the contribution, then refreshes the log
and health/maturity. Submitted items render as **"Awaiting review"** pending
rows. The `+` controls appear only when the user holds `CUSTOMER_CONTRIBUTE`.

## 6. Guarantees

- **No direct writes to protected data** — contributions are requests, stored as
  data; applying one stays a controlled operator step.
- **Additive** — new service, endpoints, permission, and fields; nothing existing
  changed shape.
- **Neutral** — no operating-company references in any customer-facing string;
  actor labels are "Verification team" / "Support team".
- **Auditable** — every contribution is an immutable, tenant-scoped audit event.
