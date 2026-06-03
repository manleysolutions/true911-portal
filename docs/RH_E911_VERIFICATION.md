# RH E911 Verification Tool (PR #80)

**P0** of the RH readiness plan (`docs/RH_READINESS_AUDIT.md`). Moves
Restoration Hardware sites whose dispatchable address is **already complete**
from "needs validation" to `e911_status = validated` — **dry-run-first,
refusal-gated, audit-logged.**

```bash
# 1. See eligible sites (no list yet — read-only):
python -m app.verify_rh_e911

# 2. Dry-run a verified set:
RH_E911_VERIFIED_SITES="RH-TAMPA-01,RH-MIAMI-02" python -m app.verify_rh_e911

# 3. Apply (only after the dry run looks right):
DRY_RUN=false RH_E911_VERIFIED_SITES="RH-TAMPA-01,RH-MIAMI-02" \
    RH_E911_ACTOR="you@manleysolutions.com" python -m app.verify_rh_e911
```

## The life-safety guard
The tool **does not decide an address is correct.** A script cannot verify an
address against a PSAP authority, and bulk auto-validating would create false
life-safety confidence. So:

- The **operator names** the sites they have verified against the authoritative
  source via `RH_E911_VERIFIED_SITES`. There is **deliberately no "validate all"
  shortcut.**
- The tool only **enforces eligibility** (complete address, not already
  verified), writes the status, and records an audit entry naming the actor.

## Contract
| Rule | Behaviour |
|---|---|
| `DRY_RUN` | defaults **true** — nothing written unless `DRY_RUN=false`. |
| Eligible | only sites in the `address_complete_needs_validation` bucket (all 4 address parts present, status not already verified). |
| Named-but-incomplete | **REFUSES the whole batch** — never validate an incomplete address. |
| Named-but-not-found | **REFUSES the whole batch.** |
| Named-but-already-verified | skipped as a **no-op** (not a refusal). |
| Other tenants | never touched. |

The batch is **all-or-nothing**: any refusal ⇒ `to_validate` is empty and nothing
is written.

## What it writes (apply only)
Per validated site, inside one transaction:
- `e911_status` → `"validated"`
- `e911_confirmation_required` → `false`
- one `audit_log` entry: category `e911`, action `verify_address`, with the
  actor and the old/new status + the address in `detail` (full audit trail).

No other field is touched. No deletes, no migrations.

## Tests
`tests/test_verify_rh_e911.py` — pure planner: validates eligible complete
addresses, refuses the batch on missing parts / unknown sites, treats
already-verified as a no-op, lists eligible sites when none are named. Full
backend suite passes.

## Next in sequence
After P0 lands, **PR #81** backfills device identity / vendor mapping so the
device-health classifier yields probe vendors (unblocks monitorability).
