# Customer Retirement Planner (gated, dry-run-first)

Plans — and, only when explicitly authorized, applies — a retirement for **one**
customer: setting the customer / its sites / devices / lines to retired statuses
and marking its Zoho `external_record_map` rows `retired`. Built for Webber Infra
(Zoho all De-activated, every True911 asset stale, yet customer still `active`).

## Commands
```bash
# DRY RUN (default — writes nothing):
python -m app.plan_customer_retirement --customer "Webber Infra"

# APPLY (writes — requires the flag AND passing safety gates):
FEATURE_CUSTOMER_RETIREMENT=true \
  python -m app.plan_customer_retirement --customer "Webber Infra" --apply

# With exports:
python -m app.plan_customer_retirement --customer "Webber Infra" \
  --export-json webber_retire.json --export-csv webber_retire.csv
```

## Proposed changes (status only — never deletes)
| Entity | Field | Retired value |
|---|---|---|
| customer | `status` | `inactive` |
| site | `status` | `decommissioned` |
| device | `status` | `decommissioned` |
| line | `status` | `disconnected` |
| external_record_map | `map_status` | `retired` |

Rows already at the retired value produce no change (idempotent).

## Safety gates (ALL required before `--apply` writes)
1. **Feature flag** — `FEATURE_CUSTOMER_RETIREMENT=true`.
2. **`--apply`** explicitly passed (default is dry run).
3. **Zoho lifecycle** — every Zoho subscription for the customer derives to
   `deactivated` (none active).
4. **No live assets** — no device/line shows liveness within 30 days (heartbeat /
   network event / call / telemetry).
5. **Customer resolved** — the name matched exactly one customer scope.

`--apply` without the flag, or with any gate failing, **downgrades to a dry run**
and prints the blockers. Each applied change is **audit-logged**; nothing is ever
deleted; only the named customer's entities are touched (customer-scoped via the
reconciliation scoper).

## Sample dry-run
```
Customer Retirement Plan — Webber Infra  —  DRY RUN (no writes)
  customer='Webber Infra' id=5 status='active' tenant=default
  GATES: zoho_deactivated=True no_active_liveness=True customer_resolved=True  -> safe_to_apply=True
  PROPOSED CHANGES (9):
    customer 5            status: 'active' -> 'inactive'
    site WS1             status: 'Not Connected' -> 'decommissioned'
    device WD1           status: 'provisioning' -> 'decommissioned'
    line WL1             status: 'provisioning' -> 'disconnected'
    external_record_map 11  map_status: 'unmapped' -> 'retired'
    ...
```

## Migration impact
**None** — no schema change, no migration. Adds the `FEATURE_CUSTOMER_RETIREMENT`
flag (default off). Writes only existing `status` / `map_status` columns, and only
under the gates above.
