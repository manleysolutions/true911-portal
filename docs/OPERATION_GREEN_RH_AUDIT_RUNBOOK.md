# True911+ — OPERATION GREEN RH: Read-Only Audit Runbook

> The operator run sequence for the **read-only** Operation Green audits — exact
> commands and expected artifacts, grounded in each script's actual CLI/env. These
> audits **only read**; they assemble the gap picture and the operator inputs that the
> later (gated, dry-run-first) write applies consume.
>
> **Authority Level:** 4 — Process. **Governed by:** `CONSTITUTION.md` (§3 Safety;
> §4.2 read-only first), `OPERATION_GREEN_RH.md`, `SIVMEY_OPERATIONS.md`. Prepared:
> 2026-06-23.

---

## Guarantees (all four audits)
Strictly **READ-ONLY** (SELECT-only, `db.rollback()`), **no `DRY_RUN`**, **no writes**,
**no flag change**, **RH-tenant only**, never touches another tenant. `--export` /
`--export-plan` write *output artifacts*, never production data. Run where the RH data
lives (prod or a read replica — `DATABASE_URL` set). Run **in order**; each feeds the next.

---

## 1. `audit_rh_readiness` — the baseline scorecard (run first)
*Purpose:* the Operation Green dashboard — per-site E911 readiness, per-device
monitorability (why health is 0/N), the service-unit gap, and the Assurance scorecard
(computed by the **real** engine).
```bash
RH_AUDIT_TENANT=restoration-hardware python -m app.audit_rh_readiness | tee /tmp/rh_readiness_$(date +%F).txt
```
- **Env:** `RH_AUDIT_TENANT` (default `restoration-hardware`).
- **Artifact:** console scorecard (no `--export`; capture with `tee`/redirect) →
  `/tmp/rh_readiness_<date>.txt`.
- **Expect (today, pre-remediation):** 1 customer · 42 sites · 51 devices · **0 service
  units** · **E911 verified 0/42** · **device health fresh 0/51** · **Health Score
  ~30/100**; E911 buckets dominated by `address_complete_needs_validation`.
- **Feeds:** confirms the gap list + the E911 verified-site candidates (P0) and the
  service-unit gap (P3).

## 2. `audit_rh_device_identity` — per-device monitorability + mapping template
*Purpose:* for each device, what it is and what identity it's missing — turns unknown
inventory into an operator checklist **and the P1 mapping template**.
```bash
RH_IDENTITY_TENANT=restoration-hardware python -m app.audit_rh_device_identity            # console
python -m app.audit_rh_device_identity --export /tmp/rh_device_identity_audit.json        # JSON
python -m app.audit_rh_device_identity --export /tmp/rh_device_identity_audit.csv         # CSV (by extension)
```
- **Env:** `RH_IDENTITY_TENANT` (default `restoration-hardware`).
- **Artifacts:** `/tmp/rh_device_identity_audit.json` (machine + **mapping template** for
  the P1 `backfill_rh_device_identity` importer) and `/tmp/rh_device_identity_audit.csv`
  (human review).
- **Expect:** ~51 devices flagged not-yet-monitorable with reasons (no vendor adapter /
  no identifier / no heartbeat).
- **Feeds:** the **P1 device mapping file** (Sivmey corrects → Stuart approves → Eng
  applies dry-run-first).

## 3. `audit_rh_iccid_coverage` — ICCID coverage + NAPCO match-readiness
*Purpose:* measure `Device.iccid` coverage/validity/duplication and how many RH devices
could match the NAPCO export today vs need backfill (ICCID is the strongest join).
```bash
RH_ICCID_AUDIT_TENANT=restoration-hardware python -m app.audit_rh_iccid_coverage          # console
python -m app.audit_rh_iccid_coverage --export /tmp/rh_iccid_audit.csv                    # CSV artifact
# optional cross-check against the NAPCO export:
python -m app.audit_rh_iccid_coverage --export /tmp/rh_iccid_audit.csv \
    --napco-export /path/to/RH_Radiolist.xlsx
```
- **Env:** `RH_ICCID_AUDIT_TENANT` (default `restoration-hardware`).
- **Input (optional):** the NAPCO StarLink **Radiolist.xlsx** export (for the
  `--napco-export` cross-check).
- **Artifact:** `/tmp/rh_iccid_audit.csv` (per-device ICCID coverage/validity/dupes +
  match-readiness).
- **Feeds:** prioritizes which devices the P1 mapping must fix (missing/invalid ICCID)
  before NAPCO match.

## 4. `audit_rh_napco_radio_match` — NAPCO RadioNumber match + ICCID backfill plan
*Purpose:* match RH devices to the NAPCO export by RadioNumber/ICCID and produce the
**ICCID backfill plan** that feeds P1.
```bash
# requires the NAPCO Radiolist export:
NAPCO_EXPORT_FILE=/path/to/RH_Radiolist.xlsx python -m app.audit_rh_napco_radio_match      # console
python -m app.audit_rh_napco_radio_match --napco-export /path/to/RH_Radiolist.xlsx \
    --export-plan /tmp/rh_napco_iccid_backfill_plan.json                                   # JSON plan artifact
```
- **Env:** `RH_TENANT` (default `restoration-hardware`); `NAPCO_EXPORT_FILE` (or
  `--napco-export`).
- **Input (required):** the RH NAPCO StarLink **Radiolist.xlsx**. *(A sample fixture
  exists at `api/tests/fixtures/napco_radiolist_sample.xlsx` for shape reference — the
  real run needs RH's actual export.)*
- **Artifact:** `/tmp/rh_napco_iccid_backfill_plan.json` (matched radios → proposed ICCID
  backfill — a **plan, not an apply**).
- **Feeds:** the **P1 mapping file** (combined with #2) for the device-identity backfill.

---

## Run order & what to review
1. **#1 readiness** → confirms the gap + the E911/service-unit/device-health targets.
2. **#2 identity** → the device mapping template.
3. **#3 ICCID** + **#4 NAPCO** → ICCID coverage + the backfill plan that completes the mapping file.

**Reviewable outputs:** `/tmp/rh_readiness_<date>.txt`,
`/tmp/rh_device_identity_audit.{json,csv}`, `/tmp/rh_iccid_audit.csv`,
`/tmp/rh_napco_iccid_backfill_plan.json`.

**Prerequisites to gather before running #3/#4:** the RH **NAPCO Radiolist.xlsx** export.

**Still gated (not in this step):** no `DRY_RUN=false`, no RH data modified, no
`FEATURE_CUSTOMER_API` enablement. The write applies (P0 E911 → P1 identity → P2
telemetry → P3 service units) and P4 validation come **after** these read-only audits are
reviewed and the operator inputs (verified-site list, mapping file) are assembled and
Stuart-approved.

---

*Runbook — read-only audit commands. Reads nothing destructive, writes no data, changes
no behavior, enables no flag.*
</content>
