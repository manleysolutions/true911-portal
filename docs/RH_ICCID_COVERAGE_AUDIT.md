# Restoration Hardware — ICCID Coverage & NAPCO Match-Readiness Audit

**Read-only.** Measures exactly how many RH devices can match the NAPCO StarLink
export *today* and the minimum data cleanup needed to make the rest monitorable.

PR #87 validated that the NAPCO export carries an **ICCID for every radio** and
that **ICCID is the strongest join** into True911. Import coverage therefore
depends on `Device.iccid` being populated for RH — this audit quantifies that.

> Depends on PR #87 (NAPCO classifier recognition + importer parse helpers).

## What it does NOT do
Read-only — **only SELECTs**. No data updates, no ICCID backfill, no import
apply, no E911 / T-Mobile / Assurance changes. `--export` writes a CSV report the
operator requested; that is an output artifact, never a change to production data.

## Run
```bash
# Console report (default tenant restoration-hardware):
python -m app.audit_rh_iccid_coverage

# Write the per-device audit to CSV:
python -m app.audit_rh_iccid_coverage --export /tmp/rh_iccid_audit.csv

# Cross-reference against an actual NAPCO RadioList export:
python -m app.audit_rh_iccid_coverage --napco-export /path/to/Radiolist.xlsx

# Other tenant:
python -m app.audit_rh_iccid_coverage --tenant some-tenant
```

## Per-device report (task #2)
For every RH device: `device_id`, `device_name`, `site_id`, `site_name`,
`serial_number`, `iccid` (+ `iccid_normalized`), `imei`, `msisdn`, `carrier`,
`vendor`, `model`, classifier result (`classifier_family`, `is_napco_candidate`),
and the assigned **category**.

## Categories (task #3)
Each device gets exactly one primary category (matchability-first for NAPCO
candidates; non-candidates are out of scope for NAPCO import):

| Category | Meaning |
|---|---|
| `ready_for_napco_import` | NAPCO candidate with a valid, **unique** ICCID — matches today |
| `napco_candidate_no_iccid` | NAPCO candidate with **no** ICCID — needs backfill |
| `invalid_iccid` | ICCID present but malformed (bad prefix / length / non-numeric) |
| `duplicate_iccid` | Valid ICCID shared by >1 RH device — ambiguous, needs dedupe |
| `conflicting_identity` | ICCID appears in the **serial** column, or serial holds a *different* valid ICCID |
| `non_napco_device` | Classifier does not route it to the NAPCO portal — out of scope |

`missing_iccid` is also reported as a summary count (all devices with no ICCID,
NAPCO or not); `napco_candidate_no_iccid` is the high-priority subset.

### ICCID validity
A value is treated as a plausible SIM ICCID when, after normalisation (digits
only, trailing `F` pad dropped), it **starts with `89`** and is **18–22 digits**.
This is a format/matchability check, **not** a Luhn/issuer check — a legitimately
stored ICCID without a check digit is never flagged invalid.

## Summary (task #4)
`total_devices`, `devices_with_iccid`, `devices_missing_iccid`,
`duplicate_iccid_values` / `duplicate_iccid_devices`, `invalid_iccids`,
`conflicting_identity`, `napco_candidates`, `napco_candidate_no_iccid`,
`import_ready`, and **`estimated_match_coverage_pct`** = `import_ready /
napco_candidates × 100` (share of the NAPCO population that can match today).

## Cross-reference vs the NAPCO export (task #5)
With `--napco-export`, the audit parses the real export (reusing the validated
importer helpers — read-only) and reports:
- `match_today_by_iccid` — RH import-ready devices whose ICCID is in the export.
- `match_today_by_radionumber_serial` — fallback match on `RadioNumber` vs `serial_number`.
- `need_iccid_backfill` — NAPCO candidates with no ICCID.
- `need_manual_review` — invalid / duplicate / conflicting ICCIDs.
- `export_iccids_with_no_rh_device` — radios in the export with no RH device yet.

## Example output (synthetic fleet; export cross-ref is real)
```
--- PER-DEVICE ---
  rh-d-001  rh-351  SLE-LTEVI-FIRE  8914800000…6132  ready_for_napco_import
  rh-d-004  rh-700  SLE-LTEVI-FIRE  -                napco_candidate_no_iccid
  rh-d-005  rh-700  SLE-LTEVI-FIRE  12345            invalid_iccid
  rh-d-006  rh-815  SLE-LTEVI-FIRE  8901170327…0971  duplicate_iccid
  rh-d-007  rh-815  SLE-LTEVI-FIRE  8901170327…0971  duplicate_iccid
  rh-d-008  rh-902  SLE-LTEVI-FIRE  -                conflicting_identity   (ICCID in serial col)
  rh-d-009  rh-351  LM150           8911…1111        non_napco_device

--- SUMMARY ---
  total_devices                 : 9
  devices_with_iccid            : 7
  devices_missing_iccid         : 2
  duplicate_iccid_devices       : 2
  invalid_iccids                : 1
  napco_candidates              : 8
  import_ready                  : 3
  estimated_match_coverage_pct  : 37.5

--- CROSS-REFERENCE vs NAPCO EXPORT ---
  export_rows                         : 99
  match_today_by_iccid                : 2
  need_iccid_backfill                 : 1
  need_manual_review                  : 4
  export_iccids_with_no_rh_device     : 96
```

## Migration impact
**None.** No schema change, no migration, no writes. Pure SELECTs + an optional
operator-requested CSV.

## Recommended next action
1. Run with `--export` and `--napco-export <RadioList.xlsx>` where the DB is
   reachable to get the real `import_ready` count and coverage %.
2. Drive an **ICCID backfill** for `napco_candidate_no_iccid` devices — the
   single biggest lever (the export's ICCIDs/RadioNumbers are the source).
3. Resolve `duplicate_iccid` / `conflicting_identity` rows by hand (swapped
   serial/ICCID columns, shared ICCIDs).
4. Re-run the audit to confirm coverage, then run the NAPCO import in DRY_RUN.
