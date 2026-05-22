# Phase 0 Onboarding Runbook — US Courts – Probation Tampa

First Red Tag Line / True911 managed POTS replacement deployment.

| | |
|---|---|
| **Status** | Phase 0 — onboard as a system of record, existing UI only, no code changes |
| **Prerequisite** | Phase 1 (PR #50) merged and deployed |
| **Audience** | True911 operator with SuperAdmin access |

This runbook onboards the deployment into True911 using existing admin UI only.

---

## ⚠️ Prerequisite

Phase 1 (PR #50) must be **merged and live** before you start. Phase 0 depends on three Phase 1 additions:

- **Inseego FX3100 / FX3110** in the hardware-model dropdown (migration 042)
- **WAN/LAN IP** fields on the device form, **FXS Port** field on the line form (migration 043)

If you onboard before Phase 1 deploys, the modem model will not be in the catalog (you would pick "custom") and the IP/port fields will not exist. **Wait for the deploy.**

---

## Before you begin — collect these values

**Provided in the deployment brief:**

| Item | Value |
|---|---|
| Customer / tenant | US Courts – Probation Tampa |
| Modem WAN / static IP | `162.190.64.189` |
| Modem model | Inseego FX3100 *or* FX3110 (confirm which) |
| ATA model | Cisco ATA191-MPP |
| ATA LAN / local IP | `192.168.1.43` |
| SIP provider / proxy | Telnyx / `sip.telnyx.com` |
| Carrier | T-Mobile |
| Line 1 DID | `+1-904-567-9026` |
| Line 2 DID | *pending — new Tampa number from Telnyx* |

**Must collect from the install / hardware / Telnyx (not in the brief):**

- [ ] Physical **street address** of the Tampa site (for E911)
- [ ] Modem **IMEI** and/or SIM **ICCID** — a cellular device requires at least one
- [ ] SIM **MSISDN** / **IMSI** (optional)
- [ ] ATA **MAC address** — required to create the ATA device
- [ ] Modem & ATA **serial numbers** (optional)
- [ ] **Line 2's Tampa DID** once Telnyx provisions it
- [ ] Customer's portal-user **name + email**
- [ ] Site **contact** name / phone / email (optional)

**Suggested naming** (adjust to your convention):

| Object | Suggested value |
|---|---|
| Tenant ID (slug) | `us-courts-probation-tampa` |
| Modem Device ID | `USC-TPA-MODEM-01` |
| ATA Device ID | `USC-TPA-ATA-01` |
| Line 1 / Line 2 ID | `USC-TPA-LINE-01` / `USC-TPA-LINE-02` |

---

## Part A — Create the tenant *(as SuperAdmin)*

Sign in as SuperAdmin. Do **not** be in "View As" mode.

1. Sidebar → **Admin → Tenants** (`AdminTenants`).
2. Click **Create Tenant**.
3. Fill:
   - **Tenant ID (slug):** `us-courts-probation-tampa`
   - **Display Name:** `US Courts – Probation Tampa`
4. Click **Create**.

---

## Part B — Onboard the deployment *(via "View As")*

To file every record under the new tenant, switch into its context first.

> **About the "read-only" banner:** When you start "View As" you will see a *"read-only mode"* banner. That is informational. Creating onboarding records (customer, site, device, line, SIM) **works while viewing as the Admin role** — the platform stamps each new record to the US Courts tenant automatically. This is exactly *why* "View As" matters: it prevents records being mis-filed under the platform `default` tenant. If any create button is unavailable in your build, the fallback is to create a tenant **Admin** login and sign in as that account for Part B.

**Start "View As":** sidebar footer → **View As…** → search and select **US Courts – Probation Tampa** → set **View as Role = Admin** → **Start Impersonation**.

### B1 — Customer record

1. Sidebar → **Customers** → **Add Customer**.
2. Fill: **Customer Name** = `US Courts – Probation Tampa`; billing email / phone / address if known.
3. Click **Create Customer**.

### B2 — Site

1. Sidebar → **Sites** → **Add Site**.
2. Fill:
   - **Site Name:** `US Courts Probation – Tampa`
   - **Customer:** start typing "US Courts" → select the customer from B1
   - **Street / City / State / ZIP:** the physical Tampa address (this is the E911 location)
   - **Contact** name / phone / email if known
3. Click **Create Site**.

> The site create form has no static-IP field — that is expected. The modem's static IP lives on the **modem device record** (B4), which is its correct home.

### B3 — SIM record *(optional but recommended)*

Skip if you do not yet have the ICCID — you can still capture ICCID/IMEI on the modem device in B4.

1. Sidebar → **SIM Management** → **Add SIM**.
2. Fill: **ICCID** (required), **MSISDN** / **IMSI** if known, **Carrier = T-Mobile**, **Status = inventory** (or `active`).
3. Click **Add SIM**.

### B4 — Inseego modem device

1. Sidebar → **Devices** → **Register Device**.
2. Fill:
   - **Internal Device ID:** `USC-TPA-MODEM-01`
   - **Hardware Model:** **Inseego FX3100** (or FX3110 — match the unit)
   - **IMEI** and/or **SIM ICCID:** at least one is required
   - **MSISDN / Carrier:** MSISDN if known; **Carrier = T-Mobile**
   - **WAN / Static IP:** `162.190.64.189`
   - **LAN / Local IP:** leave blank (or the modem LAN gateway if known)
   - **Serial Number:** if known
   - **Assign to Site:** the site from B2
3. Click **Register Device**. A one-time device API key is shown — **the Inseego modem does not post heartbeats to True911, so you can disregard the key**; click **Done**.

### B5 — Cisco ATA device

1. **Devices** → **Register Device**.
2. Fill:
   - **Internal Device ID:** `USC-TPA-ATA-01`
   - **Hardware Model:** **Cisco ATA191**
   - **MAC Address:** the ATA's MAC (**required**)
   - **LAN / Local IP:** `192.168.1.43`
   - **WAN / Static IP:** leave blank
   - **Serial Number:** if known
   - **Assign to Site:** the site from B2
3. Click **Register Device** → disregard the API key → **Done**.

### B6 — Line 1 (Red Tag Line 1)

1. Sidebar → **Lines** → **Add Line**.
2. Fill:
   - **Line ID:** `USC-TPA-LINE-01`
   - **DID / Phone:** `+19045679026`
   - **Provider:** Telnyx
   - **Protocol:** SIP
   - **Site:** the site from B2
   - **ATA Device ID:** `USC-TPA-ATA-01` (binds the line to the ATA)
   - **FXS Port:** `1`
   - **SIP URI:** `sip:+19045679026@sip.telnyx.com`
   - **E911 Address:** same as the Tampa site address
3. Click **Add Line**.

### B7 — Line 2 (Red Tag Line 2 — second FXS)

Create this **once Telnyx has provisioned the new Tampa DID** (the DID field is required). Repeat B6 with:

- **Line ID:** `USC-TPA-LINE-02`
- **DID:** the new Tampa number
- **ATA Device ID:** `USC-TPA-ATA-01`
- **FXS Port:** `2`
- **SIP URI:** `sip:<new-did>@sip.telnyx.com`

**When B1–B7 are done:** exit "View As" — click **Exit** on the banner (or **Exit Impersonation** in the sidebar).

---

## Part C — Customer portal login *(as SuperAdmin)*

Create the account the customer signs in with. Do this as **real SuperAdmin** (not impersonating) so the **Tenant** field is available.

1. Sidebar → **Admin → Users** → **Create User**.
2. Fill:
   - **Name / Email:** the customer's contact
   - **Role:** **User**
   - **Tenant:** `US Courts – Probation Tampa`
   - **Creation Mode:** **Invite Link** (recommended — the customer sets their own password)
3. Click **Send Invite** → copy the invite URL → send it to the customer.

---

## Part D — Verify what the customer will see

Confirm scoping before handing off.

1. Sidebar footer → **View As…** → select **US Courts – Probation Tampa**, **Role = User** → **Start Impersonation**.
2. Confirm the **Status** dashboard shows the Tampa site, and **no other tenant's** sites/devices/lines appear.
3. Open the site → confirm the device(s) appear in the site drawer.
4. Click **Exit** to leave impersonation.

---

## Set expectations — what the customer sees after Phase 0

Phase 0 makes the deployment **a complete record**. It does **not** yet deliver the full managed-POTS portal experience. Communicate this to the customer / account team:

| Customer can see now | Not visible until later phase |
|---|---|
| Their Tampa site + status bucket | Call history / CDRs → **Phase 2** |
| Site detail drawer (a primary device) | Live line registration status → **Phase 3** |
| | Live modem/SIM telemetry — device health shows **"unknown"** (these devices do not heartbeat) |
| | Both devices, static IP, DIDs, FXS lines surfaced in the customer drawer → **Phase 4** |

---

## Post-onboarding checklist

- [ ] Tenant created (`us-courts-probation-tampa`)
- [ ] Customer record created
- [ ] Site created with the correct E911 address
- [ ] SIM record created *(optional)*
- [ ] Inseego modem registered — WAN IP `162.190.64.189`, IMEI/ICCID set
- [ ] Cisco ATA registered — LAN IP `192.168.1.43`, MAC set
- [ ] Line 1 created — DID `+19045679026`, FXS Port 1, bound to ATA
- [ ] Line 2 created once the Tampa DID is provisioned — FXS Port 2
- [ ] Customer "User" account invited
- [ ] Verified scoping via "View As → User"
- [ ] *(After install confirmed)* edit devices/lines `provisioning` → `active`
