# Restoration Hardware Subscription Classification

**Read-only.** Explains why RH has ~91 Zoho `Subscription_Mgmt` records but only ~51
True911 devices, by classifying every RH subscription against the True911 footprint
(customer-scoped) and producing a remediation roadmap.

## Command
```bash
python -m app.audit_rh_subscription_classification --customer "Restoration Hardware" \
  --export-json rh.json --export-csv rh.csv
```

## Per-subscription output
Subscription ID · Account · Facility · MSISDN · ICCID · Device Identifier · Device
Activation Status · Subscription Type · Connection Type · matching True911 Site /
Device / Line · classification.

> ICCID / Device Identifier are read from the staged subscription's sanitized
> `raw_json` when present (the core staging columns don't store them). RH devices
> currently have **0 ICCID**, so most matching is by **MSISDN**.

## Classifications
| Class | Rule |
|---|---|
| `matched_service` | a True911 device/line carries the MSISDN/ICCID and the sub is active |
| `historical_subscription` | De-activated billing record (with or without a stale device) |
| `duplicate_subscription` | MSISDN/ICCID/device identifier shared by >1 subscription |
| `replacement_subscription` | a De-activated member of a shared-identifier group that has an **active** sibling (superseded) |
| `missing_device` | active, has identifiers, but no True911 device/line carries them |
| `missing_iccid` | active cellular sub with an MSISDN but **no ICCID** (RH data gap) |
| `missing_site` | no identifiers and the facility matches no True911 site |
| `unresolved` | none of the above |

## Why 91 ≠ 51 (the decomposition)
The gap = `historical_subscription` + `duplicate_subscription` +
`replacement_subscription` + `missing_device` + `missing_iccid` + `missing_site`.
Example (simulated):
```
matched_service          : 51
historical_subscription  : 30   ← De-activated billing, no live device (most of the gap)
duplicate_subscription   : 3
missing_iccid            : 7    ← active subs not matchable until ICCID backfilled
zoho_subscriptions=91  true911_devices=51
```

## Recommended remediation roadmap
1. **`historical_subscription`** — archive/close in Zoho. No True911 action; they are
   not missing devices, just retired billing.
2. **`duplicate_subscription` / `replacement_subscription`** — consolidate: keep the
   active subscription, retire the superseded ones.
3. **`missing_iccid`** — run the RH RadioNumber→ICCID backfill (PRs #87/#90 path) so
   the active cellular subs become matchable, then re-classify.
4. **`missing_device`** — import the device (NAPCO StarLink import) before mapping.
5. **`missing_site`** — create/align the True911 site.
6. **`matched_service`** — already reconciling; confirm mappings.

## Safety
Read-only — only SELECTs. No writes, no migrations, no mapping changes, no imports,
no status changes.
