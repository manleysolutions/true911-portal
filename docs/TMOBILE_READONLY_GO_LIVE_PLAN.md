# T-Mobile read-only certification and production go-live plan

> **Update 2026-09-01.** Step 2 (QueryNetwork) **was attempted once and did not
> succeed**: OAuth returned HTTP 200 and the resource request returned HTTP 500
> / `GENS-0005`. It is **NOT certified** and stays `MOCK_CERTIFIED`. **The
> sequence is paused here** — step 3 (Usage) has not been attempted and must not
> be until the failure is understood. See
> `TMOBILE_PIT_CERTIFICATION_20260901.md` and question 4 of
> `TMOBILE_CARRIER_QUESTIONS_OPEN.md`.

> **Update 2026-08-28.** Step 1 (SubscriberInquiry) **has been executed** and
> succeeded against a carrier-confirmed `Active` line. Steps 2 and 3 are
> certification-ready and unexecuted; step 4 is now refused outright pending a
> carrier answer. See `TMOBILE_PIT_CERTIFICATION_20260828.md`. No production
> access has been enabled.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-07-21 |
| **Scope** | Read-only operations only. No lifecycle mutation appears anywhere in this plan. |
| **Related** | `TMOBILE_PIT_OPERATOR_RUNBOOK.md` · `TMOBILE_PIT_CERTIFICATION_PLAN.md` · `TMOBILE_PRODUCTION_READINESS.md` |

---

## 1. Where this actually stands

Four read-only operations are implemented, typed, mock-certified, and each has
its own single-run PIT authorization. **One of the four has now been executed.**

| Required input | Status |
|---|---|
| A nominated PIT subscriber, added to `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST` | ✅ present, carrier-confirmed `Active` — derive it inline at invocation time, `TMOBILE_PIT_OPERATOR_RUNBOOK.md` §2c |
| PIT credentials in the executing environment | ✅ present |
| A known PIT transaction id for QueryTransactionStatus | ❌ absent — **and not the blocker** |

| # | Operation | Maturity | Status |
|---|---|---|---|
| 1 | SubscriberInquiry | **`PIT_TESTED`** | ✅ **live PIT certified 2026-08-28**, HTTP 200 / `SUCCESS` / `100`, `subscriberStatus: Active` |
| 2 | QueryNetwork | `MOCK_CERTIFIED` | ⚠️ **live attempted 2026-09-01 — carrier HTTP 500 / `GENS-0005`. NOT certified.** No retry; sequence paused here |
| 3 | QuerySubscriberUsage | `MOCK_CERTIFIED` | ⏸️ **never sent live** — deliberately not attempted while step 2 is unexplained |
| 4 | QueryTransactionStatus | `MOCK_CERTIFIED` | ⛔ **grant REFUSED** — `transactionId` semantics unresolved |

**Step 2 did not advance anything.** A failed live attempt is not PIT
certification: maturity stayed `MOCK_CERTIFIED`, send authorization stayed
`SINGLE_RUN_ONLY`, the one-shot grant was consumed and cleared, the operator
ledger was not reconciled from the failed read, and nothing was retried. What
the run does prove is *reach* — credentials, PoP, partner headers and the exact
vendor path carry a request to the correct gateway and get a structured answer.
That is not evidence about the operation's behaviour.

**None of the four is generally live-sendable, including the certified one.**
Each live run costs its own explicit one-shot grant, before and after
certification alike. Being live PIT certified records what has been proven; it
authorizes nothing.

Step 4's blocker is no longer a missing input. Even given a transaction id we do
not know which of the four identifiers our activation returned belongs in the
field, and a wrong id is indistinguishable from an expired one. The harness now
refuses to issue a grant for it at all. `TMOBILE_CARRIER_QUESTIONS_OPEN.md` §1
holds the exact question.

## 2. Certification sequence

Run in this order. **Do not advance until the previous step is reconciled.**

| # | Operation | Command |
|---|---|---|
| 1 | SubscriberInquiry | `subscriber-inquiry --iccid <ICCID>` |
| 2 | QueryNetwork | `query-network --iccid <ICCID>` |
| 3 | QuerySubscriberUsage | `query-usage --iccid <ICCID>` |
| 4 | QueryTransactionStatus | `query-transaction-status --transaction-id <TXN>` |

Steps 2 and 3 have been previewed and every gate inspected — exact vendor
path, read-only class, no callback, ICCID accepted, no certification blocker,
single-run grant available, not generally sendable, and a request body carrying
the ICCID alone (usage takes **no** date range). Preview was audited to open no
outbound socket and perform no DNS lookup.

**A live run must be executed from an environment that has PIT credentials, the
designated ICCID on `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST`, and
`TMOBILE_PIT_LIVE_CALLS_ENABLED=true`.** A development workstation without those
is refused at the allowlist gate before anything else is evaluated, which is the
intended behaviour and not a configuration error to work around.

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

Each operation needs **its own** grant, every time — certification does not
buy a standing permission. An inquiry authorization does not authorize a network
query; a network authorization does not authorize usage; a transaction-status
authorization binds to one exact transaction id and is currently refused
outright. Every grant is consumed on use.

**After each step:** capture the evidence bundle, confirm the response parsed,
note any unknown fields, and reconcile against the fabricated fixture before
starting the next. On any non-success: **stop, do not retry, classify.**

That last rule was exercised on 2026-09-01 and held: step 2 failed, the harness
printed its STOP guidance, and step 3 was not run. **Do not resume the sequence
at step 3 while step 2 is unexplained** — a second uninterpreted result is worse
than one, and step 2 must not be re-attempted with nothing changed either.
Procedure for a structured carrier error: `TMOBILE_PIT_OPERATOR_RUNBOOK.md` §4.

A read whose response carries a `subscriberStatus` also reconciles the operator
ledger — that is how a line reaches `active` on class-C carrier-verified
evidence. Check it afterwards with
`python ../scripts/tmobile_pit.py state --iccid <ICCID>`. A `CONFLICT` there
means two observations disagree and is a stop condition, not a warning.

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
