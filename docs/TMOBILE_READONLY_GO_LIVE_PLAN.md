# T-Mobile read-only certification and production go-live plan

> Prepared, **not executed**. No live PIT request has been made and no
> production access has been enabled.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-07-21 |
| **Scope** | Read-only operations only. No lifecycle mutation appears anywhere in this plan. |
| **Related** | `TMOBILE_PIT_OPERATOR_RUNBOOK.md` · `TMOBILE_PIT_CERTIFICATION_PLAN.md` · `TMOBILE_PRODUCTION_READINESS.md` |

---

## 1. Where this actually stands

Four read-only operations are implemented, typed, mock-certified, and each has
its own single-run PIT authorization. **None has been executed**, because three
operator inputs are missing:

| Required input | Status |
|---|---|
| A nominated PIT subscriber, added to `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST` | ❌ absent |
| A known PIT transaction id for QueryTransactionStatus | ❌ absent |
| PIT credentials in the executing environment | ❌ absent |

Everything downstream of execution — persistence, the internal view, the
certification report to T-Mobile, production rollout — is blocked on those
three, not on code.

## 2. Certification sequence

Run in this order. **Do not advance until the previous step is reconciled.**

| # | Operation | Command |
|---|---|---|
| 1 | SubscriberInquiry | `subscriber-inquiry --iccid <ICCID>` |
| 2 | QueryNetwork | `query-network --iccid <ICCID>` |
| 3 | QuerySubscriberUsage | `query-usage --iccid <ICCID>` |
| 4 | QueryTransactionStatus | `query-transaction-status --transaction-id <TXN>` |

Preview is the default and opens no connection:

```powershell
cd api
python ../scripts/tmobile_pit.py query-network --iccid <PIT_ICCID>
```

To send exactly one request:

```powershell
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "true"
python ../scripts/tmobile_pit.py query-network --iccid <PIT_ICCID> `
    --execute --confirm-live --confirm-subscriber-approved --operator <you>
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "false"
```

Each operation needs **its own** grant. An inquiry authorization does not
authorize a network query; a network authorization does not authorize usage; a
transaction-status authorization binds to one exact transaction id. Every grant
is consumed on use.

**After each step:** capture the evidence bundle, confirm the response parsed,
note any unknown fields, and reconcile against the fabricated fixture before
starting the next. On any non-success: **stop, do not retry, classify.**

## 3. Deliberately not built yet

Three sprint items were left undone on purpose, and the reason is the same for
all three: **there is no observed response to build them against.**

- **Carrier observation persistence.** The Alembic graph still has two
  unresolved heads sharing revision `049`, so a new table would compound the
  branch — an explicit stop condition. More importantly, designing a schema for
  a response shape nobody has seen would be guessing, which is the failure mode
  this whole integration has been correcting for.
- **The internal super-admin view.** It would render an empty table backed by
  that absent persistence.
- **A manual sync control.** Same.

These become straightforward once one real response exists. Building them first
would mean inventing the thing the certification run is supposed to discover.

## 4. Production go-live gates

None of these is satisfied. All are prerequisites, not steps.

| Gate | State |
|---|---|
| Written T-Mobile approval to proceed to production read-only | ❌ |
| Confirmed production OAuth endpoint | ❌ |
| Confirmed production API base URL | ❌ |
| Production credentials configured outside Git | ❌ |
| Production PoP validated | ❌ |
| Private key rotated (D-003 hard gate) | ❌ |
| Tenant allowlist defined | ❌ |
| Asset allowlist defined | ❌ |
| Super-admin-only execution enforced | ❌ |
| Rollback / disable switch | 🟡 flags exist |
| Audit and alerting | 🟡 partial |

### Staged rollout, once the gates close

- **Stage 0** — validate credentials only. No subscriber request if credential validation can be isolated.
- **Stage 1** — one Manley-owned or explicitly approved subscriber. SubscriberInquiry only.
- **Stage 2** — QueryNetwork and QuerySubscriberUsage for that same subscriber.
- **Stage 3** — a small customer allowlist, manual sync only.
- **Stage 4** — restricted scheduled read-only sync, **only** after a soak and a rate review with T-Mobile.

**Stage 4 is explicitly out of scope** and no scheduler exists in the codebase.

## 5. Standing constraints

These hold regardless of how far the rollout progresses:

- **All four lifecycle mutations remain blocked** and are not reachable through the single-run authorization — its allowlist is read-only operations by construction.
- **Callback lifecycle authority remains off.** The typed rules run in shadow only and cannot become authoritative until lifecycle transactions are persisted.
- **No customer-triggered refresh**, no bulk mode, no polling, no automatic retry.
- **PIT data is never presented as production data.**
