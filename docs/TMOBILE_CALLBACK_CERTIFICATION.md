# T-Mobile callback certification checklist

> Ten properties a production callback path must have. Six hold today; four do
> not. Each gap is pinned by a `test_GAP_*` test asserting the **current**
> behavior, so it stays visible and cannot be mistaken for coverage.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-07-21 |
| **Status** | 6 of 10 met · 4 gaps |
| **Tests** | `api/tests/test_tmobile_callback_certification.py` (+ existing auth / processor / integration suites) |
| **Related** | `TMOBILE_CALLBACK_AUTH.md` · `TMOBILE_PIT_CERTIFICATION_PLAN.md` · `TMOBILE_PRODUCTION_READINESS.md` |

---

> **Update 2026-07-21.** The typed lifecycle layer now implements exact-correlation
> callback application, duplicate idempotency, replay-after-completion refusal,
> conflicting-identifier and conflicting-operation quarantine, and manual-review
> routing for results that are not understood — closing gaps #3, #4, #6 and #7 at
> the model level. These are **not yet wired into the live ingest path**; that is
> part of the read-only PIT certification work that follows. The checklist below
> still describes the deployed ingest path.

## Checklist

| # | Property | State | Evidence |
|---|---|---|---|
| 1 | Callbacks reach the correct environment | 🟡 unverified in practice | Six event paths + a generic one are deployed with GET probes for T-Mobile's validator. **No callback has ever been confirmed for the successful activation.** |
| 2 | Callback authentication succeeds | ✅ | Shared secret (header or `?token=`), constant-time compare, optional IP allowlist, fail-closed when the token is unset. `test_tmobile_callback_auth.py` (11 tests). **Must be ON in production.** |
| 3 | Replayed callbacks rejected or safely idempotent | ⚠️ **partial** | A stale callback (event timestamp older than `TMOBILE_CALLBACK_MAX_AGE_SECONDS`, default 600) is archived but never promoted. **Gap:** a replay *inside* the window is accepted — no nonce, no delivery id, no record of what was already processed. |
| 4 | Transaction IDs correlate to the originating request | ❌ **gap** | The processor never reads `partner-transaction-id`, `work-flow-id`, or `service-transaction-id`. Correlation is by ICCID/MSISDN only. A callback for an activation we never sent is indistinguishable from a real one if the ICCID matches. The ids *are* archived, so `scripts/tmobile_callback_inspect.py` can find them — manual, not automatic. |
| 5 | Out-of-order callbacks handled | ⚠️ **gap** | Promotion writes `last_network_event = now` (arrival), not the event timestamp, so a late-arriving older event overwrites a newer one. Bounded by the 10-minute window, but no ordering guarantee exists. |
| 6 | Duplicate callbacks do not duplicate state changes | ✅ *effects* / ⚠️ *audit* | Promotion writes absolute values (`last_network_event`, activation meta keys) — never increments or appends — so duplicates converge. **Gap:** each delivery mints a fresh `payload_id` and enqueues another job with **no idempotency key**, so the audit trail double-counts and the worker redoes work. |
| 7 | Unknown-transaction callbacks quarantined or flagged | ❌ **gap** | An unmatched callback is archived and silently marked processed. `IntegrationPayload` has no `quarantined` column and there is no operator surface listing callbacks for subscribers we do not know. Ambiguous matches *are* refused rather than guessed (good), but that refusal is invisible to an operator. |
| 8 | Callback payloads sanitized in logs | ✅ | Header and query names matching `/auth\|token\|secret\|key\|cookie\|password/i` are `[REDACTED]` — including `?token=`, which the registered callback URL may carry. Identifiers masked via `_redact_identifier`. |
| 9 | Callbacks update the correct subscriber record | ✅ | Matched on globally-unique `Sim.iccid`, with a Device fallback; **ambiguous matches are refused, never guessed**. Account-ID capture find-or-creates a single Sim keyed on the ICCID, so it is never duplicated. `test_tmobile_callback_processor.py`, `test_tmobile_account_capture.py`. |
| 10 | Failed callback processing is recoverable | ✅ | The raw body, headers, and parsed body are archived before processing, so any payload can be reprocessed. A missing row reports `error:not_found` rather than crashing. Archive failures still return HTTP 200 — a retry storm is worse than one lost archive. |

---

## The four gaps, and what closes them

**#4 Transaction correlation** *(largest)* — persist the outgoing
`partner-transaction-id` at request time, then match the callback against it.
This also closes #7: a callback carrying an unknown transaction id becomes
detectable rather than merely unmatched. Prerequisite for #3.

**#3 Replay inside the window** — with a stored transaction id (or a hash of
payload + ids), reject a repeat outright. Until then the 10-minute window is the
only defense, and it defends against *stale* replay, not *fast* replay.

**#7 Quarantine** — add a `quarantined` flag plus an operator report of
unmatched callbacks. Cheap, and it turns a silent archive into a visible signal.

**#6 Idempotency key** — pass an idempotency key to
`job_service.create_and_enqueue` (it already accepts one) derived from the
callback's transaction ids. One-line change once #4 lands.

**#5 Ordering** — compare the incoming event timestamp against the stored one
and refuse a regression. Lowest priority; the window bounds the damage.

> Do **not** implement #3–#7 by guessing which transaction id T-Mobile echoes
> back. Confirm the callback payload schema first — the same rule that blocks
> seven operations in `TMOBILE_API_INVENTORY.md`.

---

## Operator verification

```powershell
# Read-only. Pure SELECT — opens no network connection.
python -m scripts.tmobile_callback_inspect `
    --iccid <ICCID> `
    --partner-transaction-id <ptx> `
    --work-flow-id <wf> `
    --service-transaction-id <svc>
```

Reports matched callbacks, receipt time, event type, authentication/acceptance,
the `webhook.tmobile` job outcome, and the resulting `sims.meta` — all with
identifiers masked and header values allowlisted.

**Reading a "no callback found" result:** it is *not* proof T-Mobile sent none.
A callback is persisted only when `FEATURE_TMOBILE_CALLBACK_INGEST` is on **and**
the authenticity gate passes. Check both flags and the
`T-Mobile callback ingest DENIED` log line before concluding.
