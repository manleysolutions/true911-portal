# Webber Zoho ↔ True911 Mapping Review

**Read-only.** Puts each Zoho `Subscription_Mgmt` record side-by-side with its
closest True911 candidates (line/device by MSISDN, site by normalized facility
name) and a recommended operator action — the worksheet for confirming mappings
by hand. It **confirms nothing** and writes nothing.

> Use after the reconciliation audit flags mismatches. Reconciliation says *what*
> is wrong; this says *what to do about each record*.

## Command
```bash
python -m app.audit_webber_mapping_review
python -m app.audit_webber_mapping_review --customer "Webber Infra" \
    --export-json webber_map.json --export-csv webber_map.csv
```
Customer defaults to `Webber Infra` (override with `--customer` or
`WEBBER_REVIEW_CUSTOMER`). The True911 side is loaded with the **customer-scoped**
loader (PR #96), so counts reflect Webber's real footprint, not the whole tenant.

## Per-record output
`zoho_subscription_id`, `zoho_account_name`, `zoho_facility_name`, `zoho_msisdn`,
`zoho_activation_status` (+ derived `zoho_lifecycle`), the closest True911
**line/device by MSISDN**, the closest True911 **site by normalized name**, the
match classification, and a **recommended action**.

### Classification
| Class | Meaning | Action |
|---|---|---|
| `exact` | MSISDN matches exactly one True911 line/device | Confirm + map |
| `duplicate` | MSISDN matches >1 True911 entity | Resolve duplicate first |
| `fuzzy` | No MSISDN match, but a site name lead exists | Verify by site, then map |
| `missing` | No MSISDN match and no site lead | Locate / provision / import |

Site match is `exact` (normalized name equal), `fuzzy` (substring either way), or
`missing`. When a matched entity is **active** while Zoho is **De-activated**, the
action carries a lifecycle-review note.

## Sample (Webber)
```
• sub_id=SM-W4  msisdn=7869600490  [EXACT]
    zoho: facility='Dodge Island - Red Phone' status='De-activated' (deactivated)
    true911 MSISDN match: exact -> line:WL-1 (status=active)
    true911 site match : fuzzy -> Dodge Island (WS1)
    ACTION: Confirm: MSISDN matches one True911 line/device — map it.
            | Zoho De-activated but matched True911 entity is ACTIVE — review lifecycle
• sub_id=SM-W3  msisdn=7869600498  [DUPLICATE] -> 2 entities: device:WD-100, device:WD-101
• sub_id=SM-W2  msisdn=7866457618  [FUZZY]    -> site: Dodge Island
• sub_id=SM-W1  msisdn=3054577324  [MISSING]
SUMMARY: records=4 exact=1 duplicate=1 fuzzy=1 missing=1
```

## Recommended manual cleanup sequence
1. **`duplicate`** first — two True911 devices share a Zoho MSISDN; decide which
   is correct (the other is likely a stale/duplicate device row) before mapping.
2. **`exact`** — confirm the line/device, then map the subscription. Where Zoho is
   De-activated but True911 is active, decide the lifecycle action separately
   (this report does not change status).
3. **`fuzzy`** — use the site lead to find the right device/line, attach the
   MSISDN if missing, then it becomes `exact`.
4. **`missing`** — no True911 record exists; provision/import the device/line/site
   (e.g. via the existing import paths) before mapping.
5. Re-run this review until everything is `exact`, then confirm mappings in the
   read-only Zoho review surface, then re-run the reconciliation audit.

## Migration impact
**None** — no schema change, no migration, no writes, no webhook/auth/status
changes. `--export-*` write only the operator-requested report file.
