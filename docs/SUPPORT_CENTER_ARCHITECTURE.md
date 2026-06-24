# Support Center — Architecture

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Companion to `AI_CUSTOMER_OPERATIONS_CENTER.md`. Status: Phase 1 implemented.

## 1. Component map

```
                         ┌──────────────────────────────────────────┐
  caller / AI / chat ──▶ │  router  app/routers/ops_center.py        │
                         │  • FEATURE_OPS_CENTER gate (404 when off) │
                         │  • RBAC (OPS_CENTER_*) + tenant context   │
                         │  • pre-verification redaction             │
                         └───────────────┬──────────────────────────┘
                                         │
        ┌────────────────────────────────┼───────────────────────────────┐
        ▼                                 ▼                               ▼
  lookup.py                        sessions.py                      triage.py
  asset matching                   session lifecycle,               diagnostic hooks
  (identities + native             OTP issue/verify,                (graceful degrade)
   field fallback)                 escalation, handoff
        │                                 │
        ▼                                 ▼
  asset_identities          ops_support_sessions / ops_otp_challenges / ops_session_events
  Device/Site/ServiceUnit/Line          │
                                         ▼
                                 otp/  (OtpProvider abstraction)
                                 stub · console · twilio/telnyx (future)
```

Files:

| Concern | Path |
|---------|------|
| Router | `api/app/routers/ops_center.py` |
| Models | `api/app/models/ops_center.py` |
| Schemas | `api/app/schemas/ops_center.py` |
| Migration | `api/alembic/versions/048_ops_center.py` |
| Normalization | `api/app/services/ops_center/normalize.py` |
| Asset lookup | `api/app/services/ops_center/lookup.py` |
| Session/OTP/escalation | `api/app/services/ops_center/sessions.py` |
| Triage | `api/app/services/ops_center/triage.py` |
| OTP providers | `api/app/services/ops_center/otp/` |
| Tests | `api/tests/test_ops_center.py` |

## 2. Why a separate namespace from `/api/support`

| | AI Support Assistant (`/api/support`, `support_*`) | Operations Center (`/api/ops-center`, `ops_*`) |
|---|---|---|
| Actor | Authenticated **user** (operator) | Unauthenticated **caller** proving control of a contact number |
| Identity | JWT user + `user_id` | Caller phone + **SMS-OTP** to a contact on file |
| Entry | Already inside a tenant | **No account number** → identifier lookup, possibly cross-tenant |
| Data gate | Normal RBAC | RBAC **plus** verification-gated sensitive fields |

Merging them would force one of the two identity models onto the other.
They share concepts (diagnostics, escalation, Zoho Desk) but not schema.

## 3. Data model

Four additive tables (migration `048`, all guarded by existence checks):

- **`asset_identities`** — `(tenant_id, identifier_type,
  identifier_value_normalized)` unique index pointing at an asset
  (`asset_kind` + `asset_ref` + loose `site_id`/`device_id`/`service_unit_id`).
  Carries no sensitive data — it's an index, not a record. See
  `ASSET_IDENTITY_MODEL.md`.
- **`ops_support_sessions`** — the caller session: caller phone, source,
  issue, lifecycle (`status` + `verification_status`), matched context,
  escalation/handoff, operator, audit-friendly `meta`.
- **`ops_otp_challenges`** — one row per OTP: masked destination, **hashed**
  code, provider, attempts/expiry, status.
- **`ops_session_events`** — append-only per-session audit trail.

## 4. Request lifecycle (verified path)

```
POST /session            → open (status=open, verification=unverified)  [+session_created event]
POST /lookup-asset       → redacted matches; attach best → status=matched [+asset_matched]
POST /session/{id}/send-otp  → resolve contact → hash+store code → provider.send → otp_sent [+otp_sent]
POST /session/{id}/verify-otp → constant-time compare → verified           [+otp_verified]
POST /session/{id}/triage     → diagnostics (verified only)                 [+triage_run]
POST /session/{id}/escalate   → handoff summary (+optional incident)        [+escalated]
```

## 5. Tenant-context rules

`_restrict_tenant(user)` returns `None` for **platform operators**
(`is_platform_user`) — a support rep searches across all tenants because the
caller's tenant is unknown — and the user's own `tenant_id` for
**customer-tenant** users. Customer-tenant users may only load sessions whose
`matched_tenant_id` or `opened_by_tenant_id` equals their tenant. The matched
tenant is stamped on the session, every challenge, and every audit row.

## 6. Verification-gated serialization

`_serialize_session` blanks `matched_tenant_id` and `matched_device_id`
unless `verification_status == "verified"` **or** the session is a declared
emergency. `triage` returns 403 (and logs `sensitive_access_blocked`) for an
unverified, non-emergency session. This is the enforcement point for
"unverified sessions cannot access sensitive information".

## 7. Extensibility

- **OTP delivery** is fully behind `OtpProvider` (`otp/base.py`). A real
  provider implements one async `send()` and is registered in
  `otp/factory.py`; no workflow/router change. The default `stub` never sends.
- **Triage hooks** are independent functions that degrade to `unavailable`,
  so wiring a real carrier/SIM, SIP/ATA, or Zoho-Desk lookup is additive.
- **Asset lookup** prefers the `asset_identities` index but falls back to
  native Device/Site/ServiceUnit/Line fields, so it works before the index is
  populated.

## 8. Testing strategy

The project has no Postgres/aiosqlite test fixture, so `test_ops_center.py`
uses: pure-function unit tests (normalization, hashing, redaction, handoff),
a small queued in-memory `AsyncSession` substitute for the OTP send/verify
round-trip and triage, and `TestClient` + dependency overrides for router
gating (feature-off 404, validation 422, triage-403-unverified, permission
403). 30 tests; full suite green (3233 passed).
