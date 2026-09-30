# T-Mobile PIT certification record — 2026-09-01 (Network Profile)

> **Follow-up 2026-09-30.** After T-Mobile Engineering received this failure's
> trace identifiers they asked for a re-test. Exactly one carrier-directed
> request on 2026-09-30 returned HTTP 200 / `SUCCESS` / `100`; `query_network`
> is now `PIT_TESTED` (still `SINGLE_RUN_ONLY`). The GENS-0005 condition below
> was not reproduced. This record is kept exactly as written — see
> `TMOBILE_PIT_CERTIFICATION_20260930.md`.

> **Result: LIVE PIT ATTEMPTED · CARRIER ERROR · NOT CERTIFIED.** One controlled
> live request to the Network Profile read operation. OAuth succeeded; the
> resource request returned HTTP 500 / `GENS-0005`. `query_network` remains
> `MOCK_CERTIFIED`. Nothing was retried and the certification sequence is
> paused.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-09-01 |
| **Environment** | PIT (`TMOBILE_ENV=pit`), deployed main merge commit `bbde649` (PR #181) |
| **Operation** | `query_network` — `POST /wholesale/v1/subscriber/network-profile`, class **A / READ_ONLY** |
| **Related** | `TMOBILE_PIT_CERTIFICATION_20260828.md` · `TMOBILE_OPERATION_READINESS.md` · `TMOBILE_READONLY_GO_LIVE_PLAN.md` · `TMOBILE_CARRIER_QUESTIONS_OPEN.md` §4 · `TMOBILE_PIT_OPERATOR_RUNBOOK.md` |

Identifiers here are masked to their last four. Unmasked selectors, the full
evidence bundles, and the carrier trace identifiers live only in the operator's
private evidence store — handling policy in
`TMOBILE_PIT_CERTIFICATION_20260828.md` §6.

---

## 1. What was attempted, and what came back

One request. The selector was the carrier-provided approved PIT ICCID `…2715`,
already activated on 2026-08-28 and independently confirmed `Active` by
Subscriber Inquiry that same day.

| Stage | Result |
|---|---|
| OAuth token request | **HTTP 200** |
| `POST /wholesale/v1/subscriber/network-profile` | **HTTP 500** |
| Carrier error code | `GENS-0005` |
| Carrier `userMessage` | *"Unexpected Exception: Please notify your system administrator"* |

The carrier returned its own trace identifiers with the failure — a correlation
id, a work-flow id, a service-transaction id, and our own
partner-transaction-id echoed back. All four are recorded in the private
evidence store and are quoted into carrier correspondence from there. **They are
deliberately not in this repository**, which is public.

**None of those four may be assumed to be the `transactionId` the Transaction
Status API expects.** That question is open and unchanged — §1 of
`TMOBILE_CARRIER_QUESTIONS_OPEN.md` — and seeing more identifiers is not the
same as learning which one belongs in that field.

## 2. How this is classified, and why not otherwise

**Carrier/resource endpoint failure after successful authentication.**

That is as far as the evidence reaches, and it is worth stating precisely
because two easier classifications are both wrong:

- **Not an authentication failure.** OAuth returned HTTP 200 and the resource
  request was accepted, routed, and answered by the Network Profile gateway with
  a structured carrier error. Recording this as an auth problem would send the
  next session chasing credentials, PoP signing, or partner headers — all of
  which demonstrably worked.
- **Not "T-Mobile is broken."** `GENS-0005` is a generic unexpected-exception
  code. A PIT backend issue, partner/account provisioning, subscriber test-data,
  an endpoint-specific entitlement, and an undocumented request requirement on
  our side are all still live possibilities. We do not know the cause and this
  document does not assert one.

**What the run does prove:** credentials, PoP signing, partner headers, routing
and the exact vendor-documented path all carry a request to the correct gateway
and get a structured answer back. That is useful certification evidence about
*reach*. It is not evidence about *operation behaviour*, which is what
certification of this operation would require.

### 2.1 Maturity is unchanged — and that is the point

`query_network.readiness` remains **`MOCK_CERTIFIED`**.

The ladder is `IMPLEMENTED → MOCK_CERTIFIED → PIT_TESTED → PRODUCTION_APPROVED`,
and `PIT_TESTED` means *successfully exercised against the carrier PIT gateway
with acceptable evidence retained* (D-2026-08-28). A failed attempt satisfies
neither half. Promoting on the strength of "we reached the gateway" would make
the maturity column mean *we tried*, which is not a claim anyone should be able
to build on.

**A failed live carrier attempt is not PIT certification.** No new state was
invented to say so: the distinction between *not attempted* and *attempted and
failed* is carried by the operation's existing `test_status` and
`pit_restrictions` fields, which now record the date, the code, and the fact
that nothing advanced. `query_usage` keeps its `"Never sent live."` wording, so
the two are still distinguishable at a glance.

Send authorization was untouched: `query_network` stays `SINGLE_RUN_ONLY`, which
is what it was before the attempt. Maturity and authorization are separate axes
and neither moved.

## 3. What the harness did, and what it refused to do

The failure path behaved as designed. **No defect was found and the harness was
not changed.** Its behaviour is now pinned by
`api/tests/test_tmobile_pit_network_failure.py` (43 tests), which drives the
harness end to end against a mocked carrier returning this exact 500:

| Invariant | Behaviour |
|---|---|
| Evidence written on failure | ✅ JSON + text bundle written, `ok: false`, error text redacted |
| Operation recorded as failed | ✅ exit code 1, `STOP` guidance printed |
| One-shot authorization consumed | ✅ cleared in the `finally` block; a second attempt finds no grant |
| No retry | ✅ exactly one resource request; no retry wrapper on this path |
| No polling | ✅ none |
| No maturity advance | ✅ the registry is source-controlled data; no run can write it |
| No ledger reconciliation from a failed read | ✅ reconciliation runs only in the success branch — the ledger was untouched. Mutation-tested: moving reconciliation onto the failure path fails 3 of these tests |
| No automatic next operation | ✅ one subcommand, one operation, per invocation; no scheduler exists |

The harness printed, correctly:

```
STOP — this operation did not succeed. Do NOT retry and do NOT advance to the
next operation. Classify the failure first.
```

That instruction was followed. **No retry, no Usage request, no Transaction
Status request, no subscriber mutation, no reserve-SIM activity.**

### 3.1 The disabled-live rehearsal that preceded it

Before the live attempt, the execute path was exercised with
`TMOBILE_PIT_LIVE_CALLS_ENABLED=false`. It stopped at the live-send gate:

```
TMOBILE_PIT_LIVE_CALLS_ENABLED is not true. Nothing was sent.
```

That rehearsal established — with **no carrier request** — that argparse
selector handling, typed request validation, explicit subscriber nomination, the
confirmation gates, the operator requirement, and the read-only allowlist all
worked before the switch was ever opened. It is the pattern to repeat.

## 4. Operator ergonomics — a shell-local variable was lost between commands

Two live attempts before the successful invocation reached the explicit-subscriber
gate with **no nominated selector** and were refused:

```
A subscriber must be explicitly nominated: pass exactly one of
--iccid / --msisdn / --imsi. There is no default and no 'latest' subscriber.
```

**No carrier request was sent during either.** The gate did exactly its job.

The cause was environmental, not logical: a preview run using `$PIT_ICCID`
succeeded, and the two later copied command blocks ran in a context where that
shell-local value was no longer set. An invocation that derived the ICCID inline
from `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST` then passed every selector and
allowlist gate.

**The fix is to remove the shell-session dependency, not the nomination.** The
runbook now recommends deriving the designated ICCID inline from the allowlist
environment variable at invocation time — the selector is still explicit, still
passed on the command line, still allowlist-checked, and still shown masked in
the preflight block that the operator reads before confirming. See
`TMOBILE_PIT_OPERATOR_RUNBOOK.md` §2c.

What must **not** change: there is no "latest subscriber", no default
subscriber, and no implicit selection. An empty or multi-valued allowlist makes
the command fail loudly rather than pick one.

## 5. Evidence handling — and an unfinished archival step

The evidence bundle was written on the Render instance under `/tmp/pit-evidence/`
and copied, in the same session, to `~/tmobile-pit-evidence/` (JSON + text,
stamped `20260901T190310Z`).

⚠️ **Neither location is durable.** On Render, `/tmp` and the home directory
live in the instance's ephemeral filesystem: both are lost on redeploy, restart,
or instance replacement unless a persistent disk is attached and the files are
written to its mount path. A copy from `/tmp` to `~/` buys separation from
`/tmp` cleanup, not survival across a deploy.

This is the same exposure recorded for the 2026-08-28 bundles
(`TMOBILE_PIT_CERTIFICATION_20260828.md` §3.3), where the documented remedy on
loss is to leave the ledger alone and read the carrier state from the record —
never to resend anything.

**Open action, NOT completed:** download both files from the Render instance to
the operator's private evidence store (`.private-evidence/`, git-ignored and
guarded by `test_tmobile_vendor_confidentiality.py`) before the next deploy.
This document does not claim that archive exists — as of writing it does not,
and the facts summarised here are the durable record.

Nothing from the bundle is committed: no raw carrier payloads, no OAuth or
access tokens, no JWTs, no key material, no complete subscriber identifiers.

## 6. Certification status after this run

| Operation | Class | Maturity | General live send | One-shot grant | Live evidence |
|---|---|---|---|---|---|
| `activate_subscriber` | B | `PIT_TESTED` | operator harness only | not eligible | ✅ 07-21, 08-28 |
| `subscriber_inquiry` | A | `PIT_TESTED` | **NO** | eligible | ✅ 08-28 |
| `query_network` | A | **`MOCK_CERTIFIED`** | **NO** | eligible | ⚠️ attempted 09-01 — **HTTP 500 / GENS-0005, not certified** |
| `query_usage` | A | `MOCK_CERTIFIED` | **NO** | eligible | ❌ **never sent live** |
| `query_transaction_status` | A | `MOCK_CERTIFIED` | **NO** | **REFUSED** | ❌ never sent live |
| `suspend` / `restore` / `change_sim` / `deactivate` | B / C | `MOCK_CERTIFIED` | **NO** | not eligible | ❌ never sent live |

### 6.1 Usage is untouched and stays that way for now

`query_usage` has **not** been sent live, and the certification sequence is
paused before it. Running Usage now would be advancing past an unclassified
failure on the previous step — precisely what the harness's STOP message exists
to prevent — and if it also failed we would have two uninterpreted results
instead of one. It is deliberately still recorded as never sent live.

Its authorization is independent: a grant is issued per operation and consumed on
use, so the `query_network` grant could never have covered it, before or after
the failure.

### 6.2 Transaction Status remains blocked

`query_transaction_status` keeps its `certification_blockers` entry and is still
refused at the point a grant would be cut. Today's failure surfaced four carrier
identifiers, and that changes nothing: none has been confirmed by T-Mobile as
the `transactionId` the operation expects, and a blocker outranks both maturity
and one-shot authorization. Clearing it needs T-Mobile's written answer plus a
reviewed code change — never a config toggle.

## 7. Standing constraints, unchanged

- All four lifecycle mutations remain blocked and unreachable through the
  single-run path.
- Callback lifecycle authority remains **non-authoritative** (shadow only).
- The three reserve PIT ICCIDs remain untouched and on no allowlist.
- No destructive operation is authorized. No Render environment variable was
  changed by this record.
- PIT data is never presented as production data.

## 8. Next actions, in order

1. Send `TMOBILE_CARRIER_QUESTIONS_OPEN.md` — now **four** questions, with §4
   covering this failure. Operator action; nothing has been sent.
2. Archive the evidence bundle off the Render instance (§5).
3. Wait for T-Mobile's answer before any further `query_network` attempt. A
   re-attempt with nothing changed is a retry with extra steps.
4. Leave `query_usage` unattempted until the Network Profile result is
   understood.
