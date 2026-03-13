# Onboarding Checklist: R&R Technologies

## Pre-Onboarding Data Needed

- [ ] Customer name, billing email, phone, address
- [ ] Verizon ThingSpace account credentials (configured in API env vars)
- [ ] Site list with addresses (CSV or spreadsheet)
- [ ] System types per site (elevator_phone, fire_alarm, etc.)
- [ ] Device serials and/or IMEIs (if not from Verizon Sync)
- [ ] POC contact info (per-site or single contact)

## Step 1: Create Customer Record

1. Navigate: Sidebar → **Customers**
2. Click **"Add Customer"** (top-right, red button)
3. Enter:
   - Name: `R&R Technologies`
   - Billing Email: _(from intake form)_
   - Phone: _(from intake form)_
   - Address: _(from intake form)_
4. Click **Create**
5. Verify customer appears in the list with "active" status

## Step 2: Run Verizon Sync

_Skip if R&R does not use Verizon SIMs._

1. Navigate: Sidebar → **Integration Sync**
2. Select **Verizon Sync** tab
3. Confirm green "Verizon ThingSpace Configured" status
4. Click **Preview** first — review:
   - SIMs to Create
   - Devices to Create
   - Any conflicts (cross-tenant ICCID collisions)
5. If preview looks correct, click **Sync Now**
6. Confirm in the modal
7. Check Sync History panel for success entry

## Step 3: Import Sites via CSV

1. Navigate: Sidebar → **Imports** → **Site Import**
2. Download the template (or use `onboarding/site_import_template.csv`)
3. Fill in one row per system per site:
   - **Required:** `site_name`, `system_type`
   - **Recommended:** `customer_name` (must match "R&R Technologies" exactly), address fields, device_serial, carrier, sim_iccid
4. Upload CSV → **Preview**
5. Review: sites to create, devices to create, any errors/warnings
6. If no errors → **Commit**

## Step 4: Verify Devices & SIM Linking

1. Navigate: Sidebar → **Devices**
2. Filter by carrier or search for R&R device IDs
3. Confirm each device shows:
   - Correct hardware model
   - SIM assigned (ICCID visible)
   - Status: `provisioning` or `active`
4. Click any device → Edit → check SIM panel shows linked SIM

## Step 5: Verify SIM Inventory

1. Navigate: Sidebar → **SIMs**
2. Filter carrier = `verizon`
3. Confirm SIMs show correct statuses (active/inventory)
4. Verify MSISDN and ICCID match expected values

## Step 6: Verify Sites

1. Navigate: Sidebar → **Sites**
2. Search for "R&R Technologies" in search bar
3. Confirm all imported sites appear with correct:
   - Site name
   - Customer name = "R&R Technologies"
   - Address fields populated
   - Status (may be "Unknown" until first heartbeat)

## Post-Onboarding Verification

- [ ] All sites appear on Deployment Map (if lat/lng provided)
- [ ] Device heartbeats are arriving (check Last Heartbeat column)
- [ ] SIM statuses match Verizon ThingSpace
- [ ] Run Reconciliation (Integration Sync → Reconciliation tab) to check line counts

## Data Source Reference

| Data | Source |
|------|--------|
| ICCID, MSISDN, IMEI, SIM status | Verizon Sync (automatic) |
| Site name, address, customer name | CSV Import (manual) |
| Building type, system type | CSV Import (manual) |
| Device-to-site assignment | CSV Import or manual edit |
| E911 address confirmation | Manual verification |
