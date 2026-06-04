# R&R Device↔Line Pairing Diagnostic

**Read-only.** Explains why PR #102's device+line collapse did **not** reduce R&R's
`duplicate_candidate` count, by classifying every shared-MSISDN pairing for the
customer.

## Why #102 didn't collapse R&R
#102 collapses a device and a line into one `service` **only when the line is
linked by `lines.device_id == devices.device_id`**. On R&R's live data that link is
NULL — the line carries the same MSISDN (`device.msisdn == line.did`) and sits on
the same site, but `line.device_id` was never populated. So each MSISDN still
matched two entities (device + its own line) → `duplicate_candidate`.

The diagnostic confirms this: the dominant class is **`collapsible_by_msisdn_site`**
(same MSISDN + same site + same customer, `line.device_id` NULL).

## Command
```bash
python -m app.audit_rr_device_line_pairing
python -m app.audit_rr_device_line_pairing --customer "R&R Realty Group" --export-json rr.json
```

## Per-MSISDN fields
MSISDN · `device_id` / `device.msisdn` / `device.site_id` / device customer (via
`site.customer_id`) · `line_id` / `line.did` / `line.device_id` / `line.site_id` /
`line.customer_id` · `msisdn_equal` · `device_id_linked` · `site_match` ·
`customer_match` · classification · reason · `would_collapse_under`.

## Classifications
| Class | Meaning | Collapses under |
|---|---|---|
| `collapsible_exact` | linked by `device_id` + same site | **exact** (today, #102) |
| `collapsible_by_msisdn_site` | same MSISDN + same site + same customer, `line.device_id` NULL | **relaxed** (proposed) |
| `line_device_id_missing` | `device_id` NULL and site/customer can't be confirmed equal | no |
| `line_device_id_mismatch` | `line.device_id` points to a different device | no |
| `site_mismatch` | device and line on different sites | no |
| `customer_mismatch` | device and line owned by different customers | no |
| `true_duplicate` | >1 device or >1 line share the MSISDN | no |
| `missing_line` / `missing_device` | only one side carries the MSISDN | no |

## Recommended safe matcher update
Relax `_t911_msisdn_entities` to also collapse the **`collapsible_by_msisdn_site`**
case — i.e. collapse a device + line when:
- `normalize(device.msisdn) == normalize(line.did)`, **and**
- same site (`line.site_id` is NULL or equals `device.site_id`), **and**
- same customer (`line.customer_id` is NULL or equals the device's owning customer),
- **even when `line.device_id` is NULL** (no device-id link required).

Keep the hard gates that preserve true duplicates: **never** collapse on
`line_device_id_mismatch`, `site_mismatch`, `customer_mismatch`, or when >1
device / >1 line share the MSISDN. This is a precise, conservative relaxation — it
only collapses pairs already proven to be the same MSISDN + site + customer.

Expected effect on R&R: the ~54 `collapsible_by_msisdn_site` pairs become
`matched_ok`, dropping `duplicate_candidate` to the genuine remainder (true
duplicates / mismatches only).

## Safety
Read-only — only SELECTs (via the reconciliation customer-scoped loader). No writes,
no migrations, no mapping changes, no webhook changes, no matcher change (this PR
is diagnostic-only; the relaxation above is a recommendation).
