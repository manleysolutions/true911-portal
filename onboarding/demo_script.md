# True911+ Internal Demo Script

**Duration:** ~15 minutes
**Audience:** Internal team / stakeholders
**Goal:** Show end-to-end customer onboarding flow from empty state to verified deployment

---

## Setup (before demo)

- Log into True911+ portal as Admin user
- Ensure demo environment has Verizon ThingSpace configured (or demo mode active)
- Have `site_import_template.csv` ready with 2-3 sample rows for "R&R Technologies"

---

## Scene 1: Customer Creation (2 min)

**Narration:** "Let's onboard our first real customer, R&R Technologies."

1. Click **Customers** in sidebar
2. Point out the **Onboarding Checklist** at the bottom — "We built an in-app guide so operators always know the exact steps"
3. Click **"Add Customer"**
4. Fill in: Name = "R&R Technologies", email, phone
5. Click **Create**
6. Show customer appears in list with active status

---

## Scene 2: Verizon Sync (3 min)

**Narration:** "R&R uses Verizon SIMs. We pull their SIM inventory directly from Verizon ThingSpace."

1. Click **Integration Sync** in sidebar
2. Show the green **"Verizon ThingSpace Configured"** indicator
3. Click **Preview** — "We always preview first. No changes are made."
4. Walk through the preview results:
   - "X SIMs found on Verizon"
   - "X devices would be auto-created"
   - "Any conflicts are flagged here"
5. Click **Sync Now** → confirm
6. Show the **Sync History** panel — "Every sync is audited with who ran it, when, and exact counts"
7. Point out: "SIMs, devices, and device-SIM links are all created automatically"

---

## Scene 3: Site Import (3 min)

**Narration:** "Now we import R&R's site locations. This is the data Verizon doesn't have — addresses, building types, system types."

1. Click **Imports** → **Site Import**
2. Click **Download Template** — "We provide a pre-filled template"
3. Upload the prepared CSV
4. Show the **Preview** screen:
   - Sites to create
   - Devices to create (if serials included)
   - Any warnings or errors highlighted
5. Click **Commit**
6. "Sites are now in the system with all their metadata"

---

## Scene 4: Verify Everything (3 min)

**Narration:** "Let's verify the onboarding is complete."

1. Click **Sites** → search "R&R Technologies"
   - Show sites with addresses, status, customer name
2. Click **Devices** → filter or search
   - Show devices with SIM assignments, carrier badges, hardware models
   - Click a device → show the SIM panel with linked ICCID
3. Click **SIMs** → filter by Verizon
   - Show SIM inventory with statuses from Verizon

---

## Scene 5: Safety Features (2 min)

**Narration:** "We built production safety into every action."

1. On **SIMs** page, point out the **amber warning banner**: "Carrier API not connected — actions are local only"
2. Click a SIM action (activate) → show the **confirmation dialog** explaining local-only behavior
3. Cancel the action
4. "When we connect the live Verizon API, this banner disappears and actions go through to ThingSpace. The feature flag is a single env var."

---

## Scene 6: Audit Trail (2 min)

**Narration:** "Every action is logged."

1. Go to **Integration Sync** → show **Sync History** with timestamped entries
2. Go to **Events** page → filter for integration events
3. "We record who did what, when, and the exact data counts. Full auditability for compliance."

---

## Closing

**Key points to emphasize:**
- End-to-end onboarding in under 10 minutes
- Verizon data pulled automatically — no manual SIM entry
- CSV import for site data with validation and preview
- Every action audited
- Carrier write operations safely gated until ready
- Same flow works for Benson Systems or any new customer
