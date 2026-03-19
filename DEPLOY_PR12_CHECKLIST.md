# PR12 Deployment Checklist

Step-by-step guide to deploy 2 FlyingVoice PR12 devices using True911+.

## Prerequisites

- True911+ backend running (`uvicorn app.main:app`)
- True911+ frontend running (`npm run dev`)
- VOLA Cloud account credentials (email + password)
- 2 PR12 devices powered on and connected to VOLA Cloud
- Migration 032 applied (`alembic upgrade head`)

## Environment Setup

Set these in your `.env` (or Render env vars):

```
VOLA_BASE_URL=https://cloudapi.volanetworks.net
VOLA_EMAIL=your-vola-email
VOLA_PASSWORD=your-vola-password
VOLA_ORG_ID=              # optional — auto-switch to this org
```

Or skip env vars and store credentials per-tenant in the Provider record (step 3).

---

## Deployment Steps

### 1. Create Customer

1. Navigate to **Customers** in the sidebar
2. Click **Add Customer**
3. Fill in:
   - **Name**: Customer company name
   - **Email**: Primary contact email
4. Click **Save**

### 2. Create Site

1. Navigate to **Sites** in the sidebar
2. Click **Add Site**
3. Fill in:
   - **Site Name**: e.g. "Main Office" or location name
   - **Site ID**: Short identifier like `SITE-001` (remember this for provisioning)
   - **Address**: Physical address for E911
4. Click **Save**

### 3. Add VOLA Provider

1. Navigate to **Providers** in the sidebar
2. Click **Add Provider**
3. Fill in:
   - **Provider ID**: `vola-prod` (or any unique slug)
   - **Type**: Select `vola`
   - **Display Name**: `VOLA Cloud`
4. In the **VOLA Cloud Credentials** section that appears:
   - **Email**: Your VOLA Cloud login email
   - **Password**: Your VOLA Cloud password
   - **Org ID**: (optional) If you need to target a specific VOLA org
   - **Base URL**: Leave blank to use default `https://cloudapi.volanetworks.net`
5. Check **Enabled**
6. Click **Add Provider**

### 4. Test Connection

1. Navigate to **VOLA / PR12** in the sidebar (under PLATFORM)
2. Click **Test Connection**
3. Verify you see a green banner: "Successfully authenticated with VOLA API"
4. If red: check your VOLA credentials in the provider record

### 5. Fetch VOLA Devices

1. On the same VOLA / PR12 page, click **Fetch VOLA Devices**
2. You should see your PR12 devices listed with SN, MAC, model, status
3. Verify both target devices appear and show "online" or correct status

### 6. Sync Devices to True911

1. Click **Sync to True911**
2. Check the green banner: should show "2 imported" (or "updated" if already synced)
3. The devices are now in the Devices table with `VOLA-<SN>` IDs

### 7. Assign Devices to Site

1. Navigate to **Devices** in the sidebar
2. Find your 2 synced PR12 devices (search for "VOLA-")
3. Option A — **One at a time**: Click the edit (pencil) icon, set "Assign to Site" to your site, save
4. Option B — **Bulk**: Check both devices, click "Assign Selected to Site", pick your site
5. Verify both devices now show the correct site name in the table

### 8. Apply Basic Provisioning

1. Go back to **VOLA / PR12** page
2. Click **Fetch VOLA Devices** to reload the device list
3. Expand the first device card (click on it)
4. In the **Quick Provision** section:
   - Enter your site code (e.g. `SITE-001`)
   - Click **Provision**
5. Watch the **action result banner** — should show green "success" with applied parameters:
   - `ProvisioningCode=SITE-001`
   - `PeriodicInformInterval=300`
6. Repeat for the second device

### 9. Reboot (if needed)

1. Expand a device card
2. Click **Reboot**
3. Verify the action result shows "success" with a task_id
4. The device will restart and pick up the new configuration
5. Repeat for the second device if needed

### 10. Verify Parameters

1. Expand a device card
2. Click **Read Status**
3. Check the parameters table that appears:
   - **ProvisioningCode** should match what you set (e.g. `SITE-001`)
   - **PeriodicInformInterval** should be `300`
   - **SoftwareVersion** and **ModelName** confirm the device responded
4. If parameters show your values: deployment is successful
5. Repeat for the second device

### 11. Final Verification

- [ ] Both devices show in Devices page with correct site assignment
- [ ] Both devices have status "active" (auto-promoted from "provisioning" on site bind)
- [ ] ProvisioningCode confirmed via Read Status on both devices
- [ ] PeriodicInformInterval confirmed as 300 on both devices
- [ ] Devices are reporting heartbeats (check "Last HB" column in Devices page)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Connection failed" on test | Check VOLA email/password in Provider config. Ensure the provider is **Enabled**. |
| "VOLA API error: 401" | VOLA password may have changed. Update provider config. |
| "0 devices found" | Check VOLA org_id — you may need to set it to see devices in a specific org. |
| Sync shows "0 imported, 2 skipped" | Devices already synced. Check Devices page. |
| Provision shows "failed" | Device may be offline. Check VOLA Cloud dashboard for device status. |
| Provision shows "timeout" | Device is slow to respond. Try again — TR-069 can take 20-30s. Increase timeout if needed. |
| "Permission denied" (403) | You need Admin or SuperAdmin role. Check your user role. |
| Read Status shows empty values | Device may not support those TR-069 paths. Try other parameter names. |
