# Support Verification Workflow (SMS OTP)

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Companion to `AI_CUSTOMER_OPERATIONS_CENTER.md`. Status: Phase 1 implemented.

## 1. Goal

Prove that an account-less caller controls an **authorized contact number on
file** for a matched asset, before exposing any billing / sensitive-device /
customer-private information — while never blocking a **life-safety emergency**.

## 2. States

`ops_support_sessions.verification_status`:

| State | Meaning |
|-------|---------|
| `unverified` | No code sent yet. |
| `otp_sent` | A code is outstanding. |
| `verified` | Caller proved control of the contact number. |
| `failed` | Delivery failed, or attempts exhausted. |
| `bypassed_emergency` | Emergency path opened a limited incident without OTP. |

`status`: `open → matched → verifying → verified → escalated → resolved/closed`
(`abandoned` for stale).

## 3. Happy path

```
1. POST /session                      caller phone + issue (+ optional identifier)
2. POST /lookup-asset {session_id}    match asset → resolve Site POC contact
3. POST /session/{id}/send-otp        code hashed+stored; SMS to masked contact
4. POST /session/{id}/verify-otp      constant-time compare → verified
5. POST /session/{id}/triage          diagnostics now permitted
6. POST /session/{id}/escalate        handoff if unresolved
```

The caller only ever sees the contact **masked** (`•••-•••-1391`). The operator
never sees the full code; the API never echoes it.

## 4. Code handling (security)

`app/services/ops_center/sessions.py`:

- **Generation:** `secrets.randbelow` per digit, length `OPS_CENTER_OTP_CODE_LENGTH`
  (default 6, clamped 4–10).
- **Storage:** only `code_hash = SHA-256("{session_id}:{code}:{JWT_SECRET}")`.
  The plaintext code is **never** written to the DB or logs (the `stub`
  provider doesn't log it; the `console` provider logs it and is **dev-only**).
- **Binding:** the hash is salted with `JWT_SECRET` and bound to the session id,
  so a hash is useless against another session.
- **Comparison:** `hmac.compare_digest` (constant time).
- **Expiry:** `expires_at = now + OPS_CENTER_OTP_TTL_SECONDS` (default 300 s).
- **Attempt limit:** `OPS_CENTER_OTP_MAX_ATTEMPTS` (default 5); on exhaustion the
  challenge → `failed` and the session → `failed`.
- **Re-issue:** sending a new code cancels any outstanding `sent` challenge.

## 5. No contact on file

If the matched asset has no `poc_phone` (and no `destination_override` is
supplied), `send-otp` returns `otp_status=failed` with a message to **escalate
to a human agent** to verify the caller out-of-band. An `otp_failed` event is
recorded. The caller is **not** verified and sensitive data stays hidden.

## 6. Pre-verification data boundary

Until `verified` (or emergency), the API withholds:

- `matched_tenant_id` and `matched_device_id` from the session view
  (`_serialize_session`);
- the **same** fields from the **escalation handoff summary**
  (`build_handoff_summary(..., reveal_sensitive=…)` is driven by the identical
  verified-or-emergency rule, so an unverified, non-emergency escalation never
  exposes the customer/device the caller *claimed* — `customer` and `device_id`
  come back `null`; non-sensitive context like `site_id`/`asset_label` mirrors
  what the session view keeps);
- **all triage** (device health, last-seen, carrier/SIM, SIP/ATA, signal,
  events, tickets, billing) — `POST /triage` returns **403** and logs
  `sensitive_access_blocked`.

The lookup response is always redacted: contact masked, `has_contact_on_file`
boolean only, and `tenant_id` shown only to platform operators.

### `destination_override` (internal-only)

`POST /send-otp` accepts an optional `destination_override` so an operator can
send the code to a number other than the contact on file. It is **abuse-
sensitive** (send to an arbitrary number) and gated twice:

1. **Internal platform operators only** — a non-platform / customer-tenant
   context gets **403**. It is **never** exposed to a customer/public flow.
2. **Disabled while a real sending provider is configured** (`twilio`/`telnyx`)
   until OTP rate-limiting exists → **403** (`provider_sends_real_sms`). Today
   every provider is simulated, so this is inert; it becomes a hard gate the
   moment a live provider is wired without rate-limiting.

## 7. Emergency path (life-safety)

When a session is created with `is_emergency=true`:

- a **limited** `Incident` (`category=life_safety`, `severity=critical`,
  `source=ops_center`) is created **immediately**, with only non-sensitive
  detail (session ref, issue category, free-text summary);
- `verification_status` is set to `bypassed_emergency`;
- verification can still continue in parallel.

This satisfies "allow creation of a limited emergency incident while
verification continues" without exposing the full record. Emergencies also
reveal the matched context in the session view (a responder needs it).

**Emergency is INTERNAL-OPERATOR ASSERTED ONLY (for now).** Because the
emergency flag bypasses verification, `is_emergency=true` is rejected (**403**)
when the request comes from a self-service/public source (`source=customer_portal`)
**or** a non-platform context. Customer roles already lack `OPS_CENTER_*`
entirely; this is the second layer that also blocks an internal operator
relaying a public flow. A self-service caller cannot self-declare an emergency
until an explicit policy + rate-limiting exists (`OPS-P3.2`).

## 8. Audit

Every step appends an `ops_session_events` row (`session_created`,
`asset_matched`, `otp_sent`, `otp_verified`, `otp_failed`, `triage_run`,
`escalated`, `emergency_incident_created`, `sensitive_access_blocked`). When
the matched tenant is known, `otp_sent` / `otp_verified` / `otp_failed` /
`escalated` / `asset_matched` also write a central `AuditLogEntry`
(`category=security`).

## 9. Follow-ups before public/customer-portal exposure

- **Rate-limiting / abuse controls** on `lookup-asset` and `send-otp`
  (per-caller, per-destination, per-IP) — *required* before `source=customer_portal`
  or any internet-facing front-end. Tracked as `OPS-P3.2`. Until then,
  `destination_override` is internal-only **and** auto-disabled for a real
  sending provider (see §6), and `is_emergency` is internal-operator-only (§7).
- **Real OTP provider** (Twilio/Telnyx) — `stub` sends nothing today (`OPS-P3.1`).
- **Per-destination cooldown** between re-issues.
- **Authorized-contact model** beyond the single Site POC (`ASSET_IDENTITY_MODEL.md` §6).

### Already hardened (pre-enablement)

- **Handoff redaction** aligned with the session view (§6).
- **`console` OTP provider refused in production** app mode (`APP_MODE=production`)
  → falls back to `stub` (fail-closed), so a misconfigured prod env can never log
  an OTP code. Allowed only in demo/dev.
- **Cross-tenant session isolation** (`_load_session` 404 for a foreign tenant)
  is regression-tested.
