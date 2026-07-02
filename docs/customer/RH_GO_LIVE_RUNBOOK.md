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
    --csv /tmp/rh_zoho_reconciliation.csv --json /tmp/rh_zoho_reconciliation.json \
    --report /tmp/rh_zoho_sync_report.md
# Zoho v5 sometimes needs an explicit field list — override the safe default with:
#   --fields "Account_Name,Billing_Street,Billing_City,Billing_State,Billing_Code,\
#             Shipping_Street,Shipping_City,Shipping_State,Shipping_Code,Phone"
```

Read-only (SELECTs + the existing authenticated Zoho GET layer — **never writes
Zoho or True911**). Matches by store name, address, city/state, phone, and
device/line label; writes CSV + JSON + a Markdown **sync report** (matched /
inconsistencies / needs-investigation / punch list) and prints a summary.
`--fields` is a safe default for the Accounts module and can be overridden.
Exit codes:
**0** clean · **1** findings present · **2** error / Zoho not configured. Flags:
Zoho location missing in True911 · True911 location missing in Zoho · address
mismatch · missing device · missing service unit · missing callback number · E911
unverified · duplicate sites · duplicate phone numbers. Requires the `ZOHO_CRM_*`
credentials to be configured; run against the prod-read DB. Work the CSV to zero
(or knowingly-accepted) findings — E911-unverified rows also appear on the internal
gaps worklist (§4).

## 4b. Portfolio certification (read-only — the go-live gate)

The **RH Portfolio Certification Wizard** takes the latest Zoho subscription CSV
export as the immediate source of truth and certifies that *every* RH location,
subscription, line, and device is represented correctly in True911 **before Judy's
invite is sent**. It ingests the Zoho data (CSV export or live Zoho CRM),
normalizes each RH row into a canonical
portfolio record, reads True911 production (sites/devices/service units/lines/E911),
matches the two sides, classifies every result (A–L), and prints a go-live verdict
(**PASS / CONDITIONAL / BLOCKED**).

It reads from **either** an offline CSV export **or** live Zoho CRM (exactly one
source required — both produce the same CSV/JSON/MD outputs):

```bash
# offline CSV mode (backward compatible)
cd api && python -m scripts.rh_portfolio_certification \
    --tenant restoration-hardware \
    --zoho-csv /path/to/Subscription_Mgmnt_2026_07_01.csv \
    --csv /tmp/rh_portfolio_certification.csv \
    --json /tmp/rh_portfolio_certification.json \
    --report /tmp/rh_portfolio_certification.md

# live Zoho mode (reuses the existing OAuth client + pagination — needs ZOHO_CRM_* configured)
cd api && python -m scripts.rh_portfolio_certification \
    --tenant restoration-hardware --zoho-live --module Accounts \
    --report /tmp/rh_portfolio_certification.md \
    --csv /tmp/rh_portfolio_certification.csv \
    --json /tmp/rh_portfolio_certification.json
# override the live field set with --fields "Account_Name,Billing_Street,..." if needed
# handles large portfolios: fetch_records switches to Zoho page_token cursor
# pagination automatically past the first 2000 records (no manual paging needed)
```

Read-only (SELECTs only + reads the operator-supplied CSV **or** the authenticated
Zoho GET layer — **never writes Zoho or
True911, never marks E911 verified, never fabricates missing data**). It emits CSV +
JSON + an **executive Markdown report** (portfolio at-a-glance, A–L sections, top-25
issues, operator punch list) and prints a summary. Exit codes: **0** PASS · **1**
CONDITIONAL · **2** BLOCKED · **3** error (e.g. CSV unreadable).

Classes flagged: A matched · B possible/needs-review · C missing in True911 · D
missing in Zoho · E duplicate Zoho · F duplicate True911 · G address mismatch · H
phone/callback mismatch · I device mismatch · J missing service unit · K E911
unverified · L weird RH label. **Blocking** gates (C/F/I/J/K) must reach zero;
**conditional** items (B/D/E/G/H/L) need explicit operator sign-off. **Judy's invite
stays blocked until this reads PASS** (or CONDITIONAL with sign-off).

**Known special RH locations.** Operator-confirmed non-standard locations
(Greenwich 265, RHNYC, Beverly Modern, Patterson Warehouse, MDC, Linden House) are
recognized from a registry, canonicalized with the right site type, counted as
legitimate RH locations, and listed under **"Known special RH locations"** in the
report — they are **not** flagged as weird labels, but are still checked for
missing/address/duplicate/device/service-unit/E911. To confirm another special
location, add it to `KNOWN_RH_LOCATIONS` in the script. Full spec:
`docs/customer/RH_PORTFOLIO_CERTIFICATION.md`.

## 4c. Portfolio Fusion Engine (read-only — multi-source Building Digital Twin)

Where §4b certifies Zoho ↔ True911, the **Portfolio Fusion Engine** fuses **four**
trusted sources — Zoho CRM, Napco StarLink (alarm radios), T-Mobile Genesis
(MS130v4 modems), and True911 — into one canonical **Building Digital Twin** per
location, resolved by store number, address, and device identifiers (radio # / IMEI
/ ICCID / MSISDN).

```bash
cd api && python -m scripts.rh_portfolio_fusion \
    --tenant restoration-hardware \
    --zoho-csv /path/to/Subscription_Mgmnt.csv \
    --napco-csv /path/to/napco_radiolist.csv \
    --genesis-csv /path/to/genesis_ms130.csv \
    --csv /tmp/rh_fusion.csv --json /tmp/rh_fusion.json --report /tmp/rh_fusion.md
# --zoho-live works here too; True911 is always loaded from the tenant DB as the spine
```

Each Building Twin carries: building · services · devices (unified across sources) ·
E911 · **source confidence** (True911 40 · Zoho 25 · Napco 20 · Genesis 15) ·
**missing assets** (device in a vendor but not True911, no service unit, E911
unverified) · **duplicate assets**. The report opens with an executive dashboard
(buildings, fully-fused count, per-source coverage, category mix, gaps). Read-only —
never writes any source, never marks E911 verified, never fabricates data. Use it to
see, at a glance, which buildings are fully corroborated across all four systems and
which have inventory/E911 gaps before go-live. Full spec:
`docs/customer/PORTFOLIO_FUSION_ENGINE.md`.

## 4d. Portfolio Registry (persistent Digital-Twin identity + approval workflow)

The Fusion Engine reconciles each run against a permanent, operator-**approved**
**Portfolio Registry** (`portfolio_buildings` + aliases + device mappings) instead of
rediscovering the portfolio. Approved mappings resolve a building **before** any
heuristic (device → alias → store # → address); anything unmapped becomes a **review
item** (new building / possible merge / duplicate / address conflict / device
conflict / unknown alias). The run is **read-only** and never writes the registry.

```bash
# read-only fusion, reconciled against the approved registry (report shows the queue)
cd api && python -m scripts.rh_portfolio_fusion --tenant restoration-hardware \
    --zoho-csv sub.csv --napco-csv napco.csv --genesis-csv genesis.csv \
    --report /tmp/rh_fusion.md
#   --no-registry         bootstrap/discovery (everything a new-building suggestion)
#   --sync-review-queue   persist pending review items to the queue (queue only)
```

Bootstrapping RH: run once (registry empty → every building is a `new_building`
suggestion), then an operator **approves** each building via the approval workflow
(`app.services.portfolio_registry.approve_new_building`, which stamps
`approved_by` / `approved_at` and records aliases + device mappings). Subsequent runs
resolve those buildings instantly and only surface genuinely new/ambiguous data.
**Registry changes require explicit approval — nothing is applied automatically.**
Full spec: `docs/customer/PORTFOLIO_REGISTRY.md`.

## 4e. Registry-backed customer view — the go-live gate

The RH dashboard reads legacy `Site` rows until the registry-backed view is enabled.
Fusion discovered **56 canonical buildings** while the legacy view still shows 42, so
the customer count must move to the registry. Gate sequence (do NOT send Judy's
invite until step 6 is green):

1. **Run fusion** — `python -m scripts.rh_portfolio_fusion --tenant restoration-hardware …`
2. **Sync the review queue** — add `--sync-review-queue` (persists pending items only).
3. **Approve registry mappings** — an operator approves each building
   (`approve_new_building` / `approve_alias` / `approve_device_mapping`). Nothing is
   auto-approved; E911 is never auto-verified.
4. **Enable the registry-backed customer view** — set (per-service, api + worker):
   - `FEATURE_CUSTOMER_PORTFOLIO_REGISTRY=true`
   - `CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST=restoration-hardware`
   - (internal preview only) `CUSTOMER_PORTFOLIO_PREVIEW_PENDING=true` +
     `CUSTOMER_PORTFOLIO_PREVIEW_TENANT_ALLOWLIST=restoration-hardware`
5. **Verify the RH Test dashboard count** — run the audit and confirm the mode:
   `python -m scripts.customer_registry_view_audit --tenant restoration-hardware`
   (should read `registry_mode` with `customer_visible_count` = approved buildings).
6. **Only then send Judy's invite** — once the RH Test dashboard shows canonical
   buildings (not 42/42) and no raw source labels leak.

Flags default OFF, so until step 4 the customer view is byte-for-byte the legacy
behavior. Rollback: flip `FEATURE_CUSTOMER_PORTFOLIO_REGISTRY=false` — instant, no
deploy, no data change. Full spec: `docs/customer/PORTFOLIO_REGISTRY.md`,
`docs/customer/CUSTOMER_COMMAND_CENTER.md` §8e.

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
