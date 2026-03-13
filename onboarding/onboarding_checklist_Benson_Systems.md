# Onboarding Checklist: Benson Systems

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
   - Name: `Benson Systems`
   - Billing Email: _(from intake form)_
   - Phone: _(from intake form)_
   - Address: _(from intake form)_
4. Click **Create**
5. Verify customer appears in the list with "active" status

## Step 2: Run Verizon Sync

_Skip if Benson does not use Verizon SIMs._

1. Navigate: Sidebar → **Integration Sync**
2. Select **Verizon Sync** tab
3. Confirm green "Verizon ThingSpace Configured" status
4. Click **Preview** first — review:
   - SIMs to Create
   - Devices to Create
   - Any conflicts
5. If preview looks correct, click **Sync Now**
6. Confirm in the modal
7. Check Sync History panel for success entry

## Step 3: Import Sites via CSV

1. Navigate: Sidebar → **Imports** → **Site Import**
2. Download the template (or use `onboarding/site_import_template.csv`)
3. Fill in one row per system per site:
   - **Required:** `site_name`, `system_type`
   - **Recommended:** `customer_name` = "Benson Systems" (exact match), address fields, device_serial, carrier, sim_iccid
4. Upload CSV → **Preview**
5. Review: sites to create, devices to create, any errors/warnings
6. If no errors → **Commit**

## Step 4: Verify Devices & SIM Linking

1. Navigate: Sidebar → **Devices**
2. Confirm each device shows:
   - Correct hardware model
   - SIM assigned (ICCID visible)
   - Status: `provisioning` or `active`

## Step 5: Verify SIM Inventory

1. Navigate: Sidebar → **SIMs**
2. Filter carrier = `verizon`
3. Confirm SIMs show correct statuses

## Step 6: Verify Sites

1. Navigate: Sidebar → **Sites**
2. Search for "Benson Systems"
3. Confirm all sites appear with correct data

## Post-Onboarding Verification

- [ ] Sites visible on Deployment Map
- [ ] Device heartbeats arriving
- [ ] SIM statuses match Verizon
- [ ] Reconciliation shows no mismatches
