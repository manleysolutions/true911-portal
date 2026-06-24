# AI Customer Operations Center / Support Center

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Status: **Phase 1 backend IMPLEMENTED**, flag-gated `FEATURE_OPS_CENTER`
> (default OFF). Created 2026-06-24. Companion docs:
> `SUPPORT_CENTER_ARCHITECTURE.md`, `ASSET_IDENTITY_MODEL.md`,
> `SUPPORT_VERIFICATION_WORKFLOW.md`, `SUPPORT_ESCALATION_MATRIX.md`.

## 1. Purpose

A foundation for an **AI-assisted Tier-1 support workflow** for True911
customers contacting us about billing, location, device, elevator phone,
FACP / fire panel, gate phone, area-of-refuge, emergency phone, and
general support issues.

This is **not** voice AI. It is the internal/customer-facing **support
workflow, data model, API foundation, and documentation** that a voice or
chat front-end can be attached to later. The whole module self-gates on
`FEATURE_OPS_CENTER`; when the flag is off (the default everywhere) every
`/api/ops-center/*` route returns 404 and nothing changes.

## 2. The core problem: no account number

Callers usually **cannot** give an account number. They can read a
real-world identifier off the equipment — an elevator phone number, an
MSISDN, a Napco radio number, an ICCID, a Starlink ID, a panel location,
or a site/building name. The system matches on **whatever identifier the
caller has** (see `ASSET_IDENTITY_MODEL.md`).

## 3. Relationship to the existing AI Support Assistant

True911 already has an internal **AI Support Assistant** (`/api/support`,
tables `support_*`) that serves **authenticated users** (an operator chat
with diagnostics + Zoho Desk escalation). The Operations Center is a
**separate namespace** (`/api/ops-center`, tables `asset_identities` +
`ops_*`) for the **caller-driven, account-less, OTP-verified** flow. The
two are intentionally not merged: their identity models differ (a verified
*user* vs. an *unauthenticated caller* proving control of a contact
number). See `SUPPORT_CENTER_ARCHITECTURE.md` §2.

## 4. End-to-end workflow

1. Caller states an issue and any known identifier.
2. System searches `asset_identities` + native Device/Site/ServiceUnit/Line
   fields → returns **redacted** matches (no billing/sensitive/private data).
3. System resolves the **authorized contact on file** (site POC) for the match.
4. System sends a **verification code by SMS** to that contact (masked to the caller).
5. Caller provides the code.
6. System verifies → creates a **verified temporary support session**.
7. Before verification, billing/sensitive-device/customer-private data stays hidden.
8. For a **life-safety emergency**, a limited incident can be opened **while
   verification continues** (the emergency path never blocks on OTP).

After verification: **triage** (diagnostic hooks) and, if unresolved,
**human escalation** with a full handoff summary.

## 5. Phased delivery

| Phase | Scope | Status |
|-------|-------|--------|
| **1** | Architecture, data model, API, backend, tests, workflow docs | **Implemented** (this PR) |
| **2** | Support Center UI placeholder, lookup UI, session/verification/handoff views | Backlog `OPS-P2.*` |
| **3** | Real SMS-OTP provider (Twilio/Telnyx) behind the existing abstraction; rate-limiting | Backlog `OPS-P3.*` |

## 6. API surface (Phase 1)

All under `/api/ops-center` (404 unless `FEATURE_OPS_CENTER=true`):

| Method & path | Purpose | Permission |
|---------------|---------|------------|
| `GET  /meta` | Controlled vocabularies (issue categories, sources, identifier types) | `OPS_CENTER_VIEW` |
| `POST /lookup-asset` | Find assets by identifier → redacted matches | `OPS_CENTER_OPERATE` |
| `POST /session` | Open a session (optional immediate match / emergency) | `OPS_CENTER_OPERATE` |
| `GET  /sessions` | List sessions (tenant-scoped) | `OPS_CENTER_VIEW` |
| `GET  /session/{id}` | Session detail + audit trail (sensitive fields gated) | `OPS_CENTER_VIEW` |
| `POST /session/{id}/send-otp` | Send OTP to authorized contact | `OPS_CENTER_OPERATE` |
| `POST /session/{id}/verify-otp` | Verify the code | `OPS_CENTER_OPERATE` |
| `POST /session/{id}/triage` | Run diagnostics (verified/emergency only) | `OPS_CENTER_OPERATE` |
| `POST /session/{id}/escalate` | Build handoff summary; optional incident | `OPS_CENTER_OPERATE` |
| `POST /asset-identities` · `GET /asset-identities` | Register/list identifiers (internal) | `OPS_CENTER_MANAGE_ASSETS` |

## 7. Security posture (summary)

- **Feature-gated** 404 when off — the surface is invisible.
- **Tenant isolation:** platform operators may search across tenants (a rep
  doesn't know the caller's tenant yet); customer-tenant users are restricted
  to their own tenant. The matched tenant is recorded on the session.
- **Pre-verification redaction:** `matched_tenant_id` and `matched_device_id`
  are withheld from the session view, and triage is blocked, until the caller
  is verified (or the session is a declared emergency).
- **OTP secrecy:** codes are generated with `secrets`, stored only as a salted
  SHA-256 hash, compared in constant time, attempt-limited and time-boxed.
- **Auditing:** every lookup / OTP / verification / triage / escalation appends
  an `ops_session_events` row; tenant-known security events also write a central
  `AuditLogEntry`.

Full detail in `SUPPORT_CENTER_ARCHITECTURE.md` and
`SUPPORT_VERIFICATION_WORKFLOW.md`.

## 8. Configuration

| Setting | Default | Meaning |
|---------|---------|---------|
| `FEATURE_OPS_CENTER` | `false` | Master switch (404 when off). |
| `OPS_CENTER_OTP_PROVIDER` | `stub` | `stub` (no send) · `console` (dev log) · `twilio`/`telnyx` (Phase 3). |
| `OPS_CENTER_OTP_CODE_LENGTH` | `6` | OTP digits. |
| `OPS_CENTER_OTP_TTL_SECONDS` | `300` | OTP validity window. |
| `OPS_CENTER_OTP_MAX_ATTEMPTS` | `5` | Wrong-code attempts before lockout. |
| `OPS_CENTER_HANDOFF_NUMBER` | `""` | Default human-escalation number. |

## 9. Assumptions & follow-ups

- Phase 1 is **operator-driven**: an authenticated internal agent (or the AI
  on the caller's behalf) drives the endpoints. A self-service caller/customer-
  portal front-end (`source=customer_portal`) is supported in the data model
  but needs Phase 2 UI + Phase 3 rate-limiting before public exposure.
- "Authorized contact on file" currently resolves to the matched **Site POC
  phone** (`sites.poc_phone`). A dedicated multi-contact authorization model is
  a natural Phase 2+ extension (`ASSET_IDENTITY_MODEL.md` §6).
- The OTP provider is a **stub** by default — no SMS is sent until a real
  provider is implemented and configured (Phase 3).
- Triage diagnostic hooks **gracefully degrade** to `unavailable` for
  integrations not yet wired (carrier/SIM, SIP/ATA, signal, events, tickets).
