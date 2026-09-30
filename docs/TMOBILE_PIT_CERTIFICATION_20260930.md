# T-Mobile PIT certification record — 2026-09-30 (Network Profile, carrier-directed re-test)

> **Result: LIVE PIT CERTIFIED.** One controlled Network Profile request, sent
> at T-Mobile Engineering's written request, returned HTTP 200 / `SUCCESS` /
> `100` for the approved PIT subscriber and was parsed by the existing client.
> `query_network` advances `MOCK_CERTIFIED` → **`PIT_TESTED`**. Send
> authorization is **unchanged — `SINGLE_RUN_ONLY`**. The 2026-09-01 failure is
> preserved as history in `TMOBILE_PIT_CERTIFICATION_20260901.md`.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-09-30 |
| **Environment** | PIT (`TMOBILE_ENV=pit`), Wholesale PIT gateway |
| **Operation** | `query_network` — `POST /wholesale/v1/subscriber/network-profile`, class **A / READ_ONLY** |
| **Decision** | `DECISIONS.md` D-026 |
| **Related** | `TMOBILE_PIT_CERTIFICATION_20260901.md` · `TMOBILE_PIT_CERTIFICATION_20260828.md` · `TMOBILE_OPERATION_READINESS.md` · `TMOBILE_READONLY_GO_LIVE_PLAN.md` · `TMOBILE_CARRIER_QUESTIONS_OPEN.md` §4 |

Identifiers are masked to their last four. The unmasked selector, the full
evidence bundle and the carrier trace identifiers live only in the operator's
private evidence store — handling policy in `TMOBILE_PIT_CERTIFICATION_20260828.md` §6.

---

## 1. History — why there was a second request

| Date | Event |
|---|---|
| 2026-09-01 | One controlled request. OAuth HTTP 200; resource **HTTP 500 / `GENS-0005`** ("Unexpected Exception"). No retry, no polling, no mutation, no follow-up Usage request. Not certified; maturity unchanged (`TMOBILE_PIT_CERTIFICATION_20260901.md`). |
| 2026-09-30 | The private carrier trace identifiers of the 09-01 failure were supplied to T-Mobile Engineering, who replied in writing: *"Can you please re-test this now and confirm the response?"* |
| 2026-09-30 | That written carrier instruction authorized **one** new controlled request — the run recorded here. |

The re-test was carrier-directed, not a retry: the 09-01 failure was left
standing while the carrier investigated, and a new request was sent only on the
carrier's explicit instruction.

## 2. What was sent and what came back

| Item | Value |
|---|---|
| Harness authorization | one-shot grant `TMO-PIT-b2844d238da2` — **consumed and cleared** after the request |
| Selector | ICCID `…2715` — the approved, carrier-provided PIT subscriber (same line as 2026-08-28 and 2026-09-01) |
| OAuth token request | **HTTP 200** |
| `POST /wholesale/v1/subscriber/network-profile` | **HTTP 200** |
| `status` | `SUCCESS` |
| `result` | `100` / `SUCCESS` |
| `iccidStatus` | `INUSE` |
| `subscriberStatus` | `ACTIVE` |
| `simNetworkType` | `M2M` |
| APN | `iot.infatrac` |
| Other content | network / product / profile information including LTE, VoLTE, IMS and network-specification attributes — preserved by the client as unrecognised fields, not reproduced here |
| Subscriber in the response | the same approved PIT subscriber that was requested |
| Parsing | parsed successfully by the existing implementation (`TMobileResponseEnvelope`) |

**Exactly one** Network Profile request. **No** retry, **no** polling, **no**
follow-up carrier query, **no** subscriber mutation, **no** `query_usage`, **no**
`query_transaction_status`, **no** reserve-SIM activity. The raw response is not
reproduced in this public repository.

## 3. Classification

Against the existing definition on `ReadinessState` — *"successfully exercised
this operation against the live carrier PIT environment and retained acceptable
evidence"* — every term holds: the exact vendor-documented endpoint; the
approved PIT subscriber; explicit operator confirmation; a one-shot
authorization; successful OAuth; a successful carrier resource response;
successful parsing; a matching subscriber; evidence retained; no retry; no
mutation. **`query_network`: `MOCK_CERTIFIED` → `PIT_TESTED`.**

No new standard was invented, and nothing else advanced:

| Operation | Maturity | Send authorization |
|---|---|---|
| `query_network` | `MOCK_CERTIFIED` → **`PIT_TESTED`** | `SINGLE_RUN_ONLY` → **`SINGLE_RUN_ONLY`** (unchanged) |
| `query_usage` | `MOCK_CERTIFIED` (unchanged, **never sent live**) | `SINGLE_RUN_ONLY` (unchanged) |
| `query_transaction_status` | `MOCK_CERTIFIED` (unchanged) | grant **refused** — `transactionId` blocker unchanged |
| destructive operations | unchanged | `NONE` (unchanged) |

`PIT_TESTED` is certification maturity only. `query_network` is still **not**
generally sendable: every future run needs its own explicit, operation- and
subscriber-specific one-shot grant, consumed on use.

## 4. The Network Profile carrier question

The prior GENS-0005 condition was **not reproduced** during the
T-Mobile-engineering-directed 2026-09-30 re-test, which returned HTTP 200 /
`SUCCESS`. The Network Profile question (`TMOBILE_CARRIER_QUESTIONS_OPEN.md` §4
— is the endpoint enabled for our partner, is the subscriber valid) is therefore
**resolved by observation / superseded**. We do **not** know what, if anything,
T-Mobile changed between the two runs, and this record does not claim it.

## 5. Lifecycle ledger reconciliation (audited)

The run printed `LEDGER RECONCILED FROM AN INDEPENDENT CARRIER READ`, settling
the local ledger `unknown` → `active` on `carrier_verified` evidence. That was
audited before being accepted (D-026):

- **Intended.** The evidence model (`TMOBILE_PIT_CERTIFICATION_20260828.md`
  §3.2) names `subscriber-inquiry` **and** `query-network` as class-C
  carrier-verified sources, and the reconciled Network Profile contract returns
  the carrier's own `subscriberStatus` for the requested subscriber.
- **Trigger.** The response's top-level `subscriberStatus` (`ACTIVE`), mapped
  through the fixed vocabulary `Active` / `Suspended` / `Deactivated`.
- **Gap found and closed.** Eligibility had been inferred from the field being
  present, so a Usage or Transaction Status response that happened to carry a
  `subscriberStatus` would also have reconciled. It is now an explicit, reviewed
  per-operation declaration (`Operation.lifecycle_evidence`: `subscriber_inquiry`
  and `query_network` only, validated at import to be read-only). This did not
  change today's result.
- **Fail-closed, unchanged:** an absent status reconciles nothing; an
  unrecognised status raises; a status contradicting a settled state is a
  `CONFLICT` that leaves the recorded state alone and sets
  `reconciliation_required`.

The observed carrier evidence was not altered.

## 6. Evidence

`tmobile-pit-evidence-20260930T183727Z.json` / `.txt` — copied from ephemeral
`/tmp` into the operator's private Render-side evidence location. **Not in
git.** Private carrier trace identifiers are retained in the operator evidence
store and were supplied to T-Mobile Engineering, who were notified of the
successful result. No full ICCID, MSISDN, IMSI, token, PoP JWT, key or complete
carrier transaction identifier appears in this repository.

## 7. Still open

- `query_usage` — never sent live; certification sequence step 3.
- `query_transaction_status` — `transactionId` semantics
  (`TMOBILE_CARRIER_QUESTIONS_OPEN.md` §1); nothing learned here bears on it.
- `marketZip` (§2) and callback-on-synchronous-success (§3) questions — unchanged.
- Durable off-Render archiving of the private evidence store — confirm.
