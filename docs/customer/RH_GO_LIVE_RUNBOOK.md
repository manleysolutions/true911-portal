# True911+ — RH Customer Go-Live Runbook

> Operator runbook to put **Restoration Hardware (Judy)** into the customer login
> experience TODAY, with operational status greened via Customer Assurance Mode
> (`ASSURANCE_ENGINE.md`) and **E911 held to the truth**.
>
> **Authority Level:** 3 — Execution (release). Companions:
> `ASSURANCE_ENGINE.md`, `../CUSTOMER_EXPERIENCE_BOUNDARY.md` (§F),
> `../CUSTOMER_DATA_BOUNDARY.md` (§6a), `../FEATURE_CUSTOMER_API_ROLLOUT.md`.
> Prepared: 2026-07-01.

---

## 0. Model (read first)

- **Judy / RH users are `CUSTOMER_*` roles — never the legacy `User` role.** The
  `CUSTOMER_*` roles hold no `INTERNAL_OPS` grant, so they are isolated from every
  internal page/endpoint. (`User` is internally-privileged and must not be used
  for a customer.)
- The customer dashboard for `CUSTOMER_*` roles is sourced entirely from the
  read-only `/api/customer/*` Assurance API — **not** `/command/summary`.
- Operational status is preview-greened + evidence-backed; **E911 is never
  preview-overridden** and shows verified only when the stored record is verified.

## 1. Required environment variables

Set on **BOTH** `true911-api` **and** `true911-worker` (M4 parity — mismatched
env has bitten prod before):

| Variable | Value | Purpose |
|---|---|---|
| `FEATURE_CUSTOMER_API` | `true` | enables the `/api/customer/*` namespace |
| `CUSTOMER_API_TENANT_ALLOWLIST` | `restoration-hardware` | RH-only for the customer API |
| `FEATURE_CUSTOMER_PREVIEW` | `true` | enables Customer Assurance Mode (operational green) |
| `CUSTOMER_PREVIEW_TENANT_ALLOWLIST` | `restoration-hardware` | RH-only for the preview |

Frontend (static build) — optional cosmetic gate, if used:
`VITE_FEATURE_CUSTOMER_API=true`. The API is the real gate.

> All four default **OFF**. With them off, `/api/customer/*` 404s and no customer
> sees anything — safe by default.

Use the exact RH tenant slug (`restoration-hardware`). Confirm with the readiness
check (§4) which reads the same `settings`.

## 2. Create / invite customer users (no hardcoded credentials)

Two safe paths — both create the user **inactive** with a 7-day invite token; the
user sets their own password on accept (`/AuthGate?invite=<token>` →
`POST /auth/invite/{token}/accept`). Never share or hardcode a password.

**Path A — Admin UI / API** (`MANAGE_USERS`; accepts `CUSTOMER_*` roles):
```
POST /api/admin/users/invite
{ "email": "judy@…", "name": "Judy", "role": "CUSTOMER_ADMIN",
  "tenant_id": "restoration-hardware" }
```
Deliver the returned `invite_url` to Judy out-of-band.

**Path B — Provisioning script** (dry-run first; for environments without the UI):
```bash
# preview (writes nothing):
python -m scripts.create_customer_user --email judy@rh.example --name "Judy" \
    --role CUSTOMER_ADMIN --tenant restoration-hardware

# create the invite:
python -m scripts.create_customer_user --email judy@rh.example --name "Judy" \
    --role CUSTOMER_ADMIN --tenant restoration-hardware --apply
# (set PUBLIC_APP_URL to get a full invite link)
```

**Roles to assign** (all isolated from internal; grants in `permissions.json`):

| Person / kind | Role | Capabilities |
|---|---|---|
| Judy (account owner) | `CUSTOMER_ADMIN` | full customer surface + support + billing + export |
| Cindy / staff manager | `CUSTOMER_MANAGER` | full view + manage support + billing view + export |
| Support contact | `CUSTOMER_SUPPORT` | view + manage support cases |
| Auditor / read-only | `CUSTOMER_VIEWER` | view-only (no manage/billing/export) |

> The design also keeps `CUSTOMER_USER` / `CUSTOMER_BILLING` / `CUSTOMER_READONLY`
> (original names) as valid roles; `MANAGER≈USER`, `VIEWER≈READONLY` in spirit.

## 3. Enablement order (day of)

1. Confirm the RH tenant exists and has data (readiness check, §4).
2. Set the four env vars (§1) on **api + worker**; redeploy/restart both.
3. Create Judy as `CUSTOMER_ADMIN` (+ any staff roles) — §2.
4. Re-run the readiness check → expect **READY** (or a documented CONDITIONAL with
   E911 gaps honestly shown; E911 gaps are blockers to a clean READY).
5. Verify login (§5).

## 4. Run the readiness check (read-only)

```bash
python -m scripts.rh_customer_readiness_check            # console
python -m scripts.rh_customer_readiness_check --json     # machine-readable
python -m scripts.rh_customer_readiness_check --tenant restoration-hardware
```

Exit codes: **0** ready · **1** blockers (E911 gaps / no users / no sites) ·
**2** config missing or cannot evaluate. It reports the four flags/allowlists,
customer users, location/device/service-unit counts, and the E911 posture
(address present, verified, missing/unverified, missing endpoint detail). It
prints no secrets. E911 gaps are surfaced (also via `GET /api/e911-changes/gaps`)
so ops can correct them **before** verification — E911 is never greened.

## 4a. Zoho reconciliation (read-only)

Verify every RH location / device / E911 record in **Zoho CRM** exists correctly in
**True911** (and vice-versa) before go-live:

```bash
cd api && python -m scripts.rh_zoho_reconciliation \
    --tenant restoration-hardware --module Accounts \
    --csv /tmp/rh_zoho_reconciliation.csv --json /tmp/rh_zoho_reconciliation.json
```

Read-only (SELECTs + the existing authenticated Zoho GET layer — **never writes
Zoho or True911**). Matches by store name, address, city/state, phone, and
device/line label; writes a CSV + JSON report and prints a summary. Exit codes:
**0** clean · **1** findings present · **2** error / Zoho not configured. Flags:
Zoho location missing in True911 · True911 location missing in Zoho · address
mismatch · missing device · missing service unit · missing callback number · E911
unverified · duplicate sites · duplicate phone numbers. Requires the `ZOHO_CRM_*`
credentials to be configured; run against the prod-read DB. Work the CSV to zero
(or knowingly-accepted) findings — E911-unverified rows also appear on the internal
gaps worklist (§4).

## 5. Verify login

- Judy accepts her invite, sets a password, signs in.
- She lands on **Home** (the `/api/customer` Assurance view): portfolio status
  banner (green when all Protected), location list, and per-location **E911**
  drawer (real address + verified state + emergency endpoints).
- Negative checks: Judy → any internal URL (`/Command`, `/NetworkDashboard`,
  `/SimManagement`, …) redirects (no `INTERNAL_OPS`); Judy → `/command/summary`
  or another tenant's data → 403/404.
- Confirm no "API pending" / "telemetry pending" language and no raw jargon.
- **E911 review:** in a location's E911 section, a submitter role (ADMIN/MANAGER/
  SUPPORT/USER) can **Confirm Emergency Record** or **Request Correction**; a
  read-only role sees status only. Operators triage via `GET /api/e911-changes/reviews`
  and approve/reject — customer submissions never change the official record. See
  `docs/customer/E911_CUSTOMER_REVIEW_WORKFLOW.md`.
- The Home view is now the **Customer Command Center**: executive portfolio metrics
  + monthly health score, a zoom-to-fit **map** with legend and list↔map sync,
  **enterprise search** (name/#/city/state/phone/service), and a **Location Command
  Center** drawer (Overview · Life Safety Services with grouped equipment · E911 +
  history · Timeline · Documents/Billing/Notes placeholders). Service-first nav shows
  future sections as "Soon". See `docs/customer/CUSTOMER_COMMAND_CENTER.md`.

## 5a. Judy pre-send checklist (final gate before you send the invite)

Run through this immediately before delivering Judy's invite link. Do **not**
send until every box is checked.

**Config & isolation**
- [ ] All four env vars set on **both** `true911-api` and `true911-worker` (§1),
      services redeployed/restarted.
- [ ] Readiness check (§4) run — verdict **READY** (or a knowingly-accepted
      CONDITIONAL with E911 gaps shown honestly, never greened).
- [ ] Judy exists as **`CUSTOMER_ADMIN`**, tenant `restoration-hardware`,
      invite-pending (not the legacy `User` role).
- [ ] Spot-check isolation: a `CUSTOMER_*` token → `/command/summary` and an
      internal page URL both blocked (403 / redirect).

**Dashboard usefulness (log in as a test `CUSTOMER_VIEWER` or via a staging user)**
- [ ] **List view** shows all RH locations; **search** by name/city/state works;
      **status** and **E911** filters work.
- [ ] **Map view** plots locations with coordinates; the "N not shown (no
      coordinates)" note appears if any lack lat/lng.
- [ ] **Location drawer** (from list *and* map) shows: site name, full service
      address, operational status, E911 state, emergency endpoints (where real),
      and devices (equipment + model/identifier where real). Nothing fabricated.
- [ ] Green banner reads **"All listed locations are currently protected."** (no
      raw timestamp) when everything is Protected.
- [ ] E911 **"Not yet verified"** is visible but calm (amber, not red), with the
      "Manley Solutions is verifying" note.
- [ ] No "API pending" / "telemetry pending" / raw jargon anywhere in the view.

**Data truth**
- [ ] Every location's E911 `verified` reflects the real stored status; any
      unverified/missing addresses are on the internal worklist
      (`GET /api/e911-changes/gaps`) with an owner.

**Deliver**
- [ ] Send Judy the invite link out-of-band; confirm she can set a password and
      reach **Home**; brief her that any "being verified" address is in progress.

## 6. Rollback (immediate, data-safe)

Pick the lowest tier that resolves the issue:

1. **Preview off for RH:** remove `restoration-hardware` from
   `CUSTOMER_PREVIEW_TENANT_ALLOWLIST` → operational status reverts to real
   assurance labels; E911 unaffected. No deploy.
2. **Customer API off for RH:** clear `CUSTOMER_API_TENANT_ALLOWLIST` →
   `/api/customer/*` 404s for RH; the customer view shows a calm "being finalized"
   message.
3. **Global off:** `FEATURE_CUSTOMER_PREVIEW=false` and/or
   `FEATURE_CUSTOMER_API=false` (api + worker).
4. **Revoke a user:** set the user `is_active=false` (immediate 401 on next
   request/refresh).
5. **Preserve audit logs** — make no deletions.

## 7. Retire preview per location (graduation)

Preview is a **bridge**. As real evidence arrives for a location (live telemetry /
carrier status / a successful test), that evidence supersedes the operator
attestation in the Assurance engine automatically. Track telemetry coverage; once
enough RH locations report to stand on real evidence, drop RH from
`CUSTOMER_PREVIEW_TENANT_ALLOWLIST` so the whole tenant renders from real signals.
Until then, unverified E911 remains **Critical** and is worked off via the E911
gaps worklist (§4) — the truth is never deferred.
