# T-Mobile Wholesale — operation readiness

> Status only. This page deliberately carries **no** request/response schemas,
> no vendor prose, and no source citations — see §4.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Last reviewed** | 2026-09-30, after the carrier-directed Network Profile re-test returned HTTP 200 / SUCCESS (the 2026-09-01 attempt had returned HTTP 500 / GENS-0005) |
| **Evidence reference** | `TMO-REST-RECON-001` |
| **Related** | `TMOBILE_API_INVENTORY.md` · `TMOBILE_PIT_CERTIFICATION_PLAN.md` · `TMOBILE_PRODUCTION_READINESS.md` · `TMOBILE_PIT_CERTIFICATION_20260828.md` · `TMOBILE_PIT_CERTIFICATION_20260901.md` · `TMOBILE_PIT_CERTIFICATION_20260930.md` |

---

## 1. Readiness

**Certification maturity is not send authorization.** The two columns below
are independent, and neither implies the other. *Maturity* answers "how far has
this been certified"; *general live send* answers "may we transmit it right
now". Advancing maturity has no effect on authorization — that is enforced in
code, not by convention.

| Operation | Maturity | General live send | One-shot PIT grant | Live evidence | Risk | Unresolved blocker |
|---|---|---|---|---|---|---|
| Activate subscriber | `PIT_TESTED` | **Operator harness only** | not eligible | yes (07-21, 08-28) | B reversible | — |
| Subscriber inquiry | **`PIT_TESTED`** | **NO** | eligible | **yes (08-28)** | A read-only | — |
| Query network | **`PIT_TESTED`** | **NO** | eligible | **yes (09-30, carrier-directed re-test)**; 09-01 attempt HTTP 500 / GENS-0005 | A read-only | — (09-01 question resolved by observation) |
| Query subscriber usage | `MOCK_CERTIFIED` | **NO** | eligible | no — **never sent live** | A read-only | Not yet exercised; needs its own grant |
| Suspend subscriber | `MOCK_CERTIFIED` | **NO** | not eligible | no | B reversible | Not yet exercised in PIT |
| Restore subscriber | `MOCK_CERTIFIED` | **NO** | not eligible | no | B reversible | Not yet exercised in PIT |
| Change SIM | `MOCK_CERTIFIED` | **NO** | not eligible | no | **C destructive** | Replaced SIM ages out; no customer-facing inverse |
| Deactivate subscriber | `MOCK_CERTIFIED` | **NO** | not eligible | no | **C destructive** | Treated as terminal; reactivation not implemented |
| Query transaction status | `MOCK_CERTIFIED` | **NO** | **REFUSED** | no | A read-only | **`transactionId` semantics unconfirmed — carrier answer required** |

Read the terms precisely:

- **`PIT_TESTED` = live PIT certified.** Successfully exercised against the
  carrier PIT gateway, with acceptable evidence retained. It does **not** mean
  production authorized, and it does not permit an unauthorized send.
- **Operator harness only** means the client boundary permits it, and every
  harness gate still applies — allowlist tier, state machine, operator
  confirmations, the live switch. It is **not** ordinary application-path
  sendability, which would require `PRODUCTION_APPROVED`.
- **Eligible for a one-shot PIT grant** means an explicit, consumed, single-run
  certification authorization may be issued. It does **not** mean generally
  live-sendable, and eligibility does not change when maturity advances.

**Activation remains the only operation that is generally sendable**, and only
through the operator harness. The read-only family is reachable only through a
single-run PIT authorization: one operation, one nominated subscriber, one
request, consumed on use. Being certification-*ready* is not the same as being
sendable — and neither is having been certified. `subscriber_inquiry` is live
PIT certified and remains just as un-sendable as it was the day before — and
so, since 2026-09-30, is `query_network`.

**QueryNetwork is `PIT_TESTED` as of 2026-09-30.** T-Mobile Engineering,
holding the 09-01 failure's trace identifiers, asked for a re-test; exactly one
request under a one-shot grant returned HTTP 200 / `SUCCESS` / `100` for the
approved PIT subscriber and parsed cleanly. Maturity advanced; authorization did
not — still `SINGLE_RUN_ONLY`. Record: `TMOBILE_PIT_CERTIFICATION_20260930.md`.

**Lifecycle evidence is declared, not inferred (D-026).** Only operations whose
registry entry sets `lifecycle_evidence` — `subscriber_inquiry` and
`query_network` — may settle the ledger from a `subscriberStatus`. Usage and
Transaction Status never do, whatever they return.

*History, as recorded on 2026-09-01:* **QueryNetwork was attempted live on
2026-09-01 and stayed `MOCK_CERTIFIED`.**
One controlled request; OAuth returned HTTP 200 and the resource request
returned HTTP 500 / `GENS-0005`. A failed live attempt is not PIT
certification — `PIT_TESTED` means *successfully* exercised with acceptable
evidence retained, and neither half holds here — so maturity did not move and
neither did authorization. The distinction between *not attempted* and
*attempted and failed* is carried by the operation's `test_status` and
`pit_restrictions` fields, so `query_usage` is still legibly "never sent live"
while `query_network` is not. Detail:
`TMOBILE_PIT_CERTIFICATION_20260901.md`; carrier question:
`TMOBILE_CARRIER_QUESTIONS_OPEN.md` §4.

**QueryTransactionStatus is now refused at the grant, not merely un-run.** An
operation carrying an unresolved carrier question about *what to put on the
wire* is not certifiable even once (`Operation.certification_blockers`): a wrong
`transactionId` returns "not found", and so does a correct one for an expired
transaction, so the run could not be interpreted either way. See
`TMOBILE_CARRIER_QUESTIONS_OPEN.md` §1.

### 1b. Certification maturity is not send authorization

Until 2026-08-28 the readiness state doubled as live-send authorization:

```python
LIVE_SENDABLE_READINESS = {PIT_TESTED, PRODUCTION_APPROVED}
is_sendable = provenance and classification and readiness in LIVE_SENDABLE_READINESS
```

Recording the truth about a successful controlled PIT run — advancing
`subscriber_inquiry` to `PIT_TESTED` — would therefore have silently converted
it from "needs an explicit one-shot key" into "send freely". One certified call
would have bought unlimited uncertified ones, and nobody would have had to
decide that; it would have happened as a side effect of honest bookkeeping.

The two are now separate axes:

- **`ReadinessState`** — maturity only. The canonical ladder is
  `IMPLEMENTED → MOCK_CERTIFIED → PIT_TESTED → PRODUCTION_APPROVED`. There is
  exactly one taxonomy; the remaining enum members are finer waypoints on it.
- **`SendAuthorization`** — an explicit, reviewed, per-operation declaration:
  `NONE` · `SINGLE_RUN_ONLY` · `OPERATOR_HARNESS_ONLY` · `PRODUCTION`.

**Maturity can veto a send. It can never grant one.** `is_sendable` requires an
explicit authorization first; maturity is then consulted only to shut things
down, and `PRODUCTION` additionally requires `PRODUCTION_APPROVED` — necessary
for ordinary sendability, sufficient for nothing. A certification blocker
outranks both and shuts the operation at any maturity, by any route.

Enforced at import by `_validate_authorization_policy()`, so a future edit fails
the process rather than a reviewer's attention, and pinned by
`test_tmobile_send_authorization_matrix.py`.

## 1a. Carrier-state authority (2026-08-28)

What we believe about a line and *why* are now recorded separately, and the
distinction is load-bearing:

| Class | Meaning | What it settles |
|---|---|---|
| A `request_submitted` | we sent something | nothing |
| B `carrier_sync_ack` | the carrier answered **our request** | nothing on its own |
| C `carrier_verified` | the carrier described **its own record** | the line |
| D/E/F `callback_confirmed` | callback received, authentic, correlated | the line, if not already verified |
| G `conflict` | two observations disagree | nothing — routed to a human |

A class-C observation may be applied live, or replayed offline from its own
evidence bundle via `tmobile_pit.py reconcile`. Either route runs the same
reconciler; the ledger records which one it was in `carrier_verified_source`.
Replaying an activation bundle is refused — that is class B.

Three things that are **not** interchangeable, and are never collapsed:

| | |
|---|---|
| Live carrier attestation | the carrier answered us just now |
| Replay of captured carrier evidence | the carrier answered us before, and we kept the response |
| Manual operator assertion | **not accepted** — a status word cannot be typed in |

A synchronous acceptance is still not a completion. What changed is that an
**independent read now settles the line without a callback**: a read is not a
transition, so it is gated by neither the transition table nor the
pending-duplicate rule. Gating a query on already knowing the state is circular,
and was why a successful activation plus a confirming inquiry still left the
ledger reading `activation_requested`. Full account:
`TMOBILE_PIT_CERTIFICATION_20260828.md` §3.

## 2. What changed, and what did not

Implementation was **reconciled against authorized vendor documentation reviewed
privately** on 2026-07-21. The reconciliation was substantial: the previously
derived paths were wrong for every operation, four operations used the wrong
HTTP method, and every lifecycle request body was wrong.

What did **not** change is the send policy. Obtaining a contract answers *what*
to send; it says nothing about whether this client sends it correctly. Readiness
is therefore a separate gate from provenance, and only real PIT evidence opens
it. All eight non-activation operations stay blocked.

## 2a. Typed contract and lifecycle foundation (2026-07-21)

Requests and responses are now typed models rather than hand-built dicts, and
the subscriber lifecycle has one authoritative state vocabulary.

- **Outbound models forbid unknown fields**, so an undocumented field is a local
  error rather than something that reaches the wire. Validation runs before OAuth.
- **Inbound models preserve unknown fields**, so a response is never rejected for
  carrying an attribute the carrier added after we shipped.
- **Synchronous acceptance is modelled separately from asynchronous completion.**
  A mutation moves the line to a `*_pending` state; only an async result settles
  it. Acceptance means authenticated and validated — not provisioned.
- **Callbacks apply only on exact correlation**, with no latest-pending and no
  timestamp fallback. Duplicates are idempotent; replays after completion, stale,
  conflicting, ambiguous, and uncorrelatable callbacks are quarantined without
  changing state.
- **Mutations fail closed on unknown or unconfirmed state.** Reads do not — a
  query is how the state is learned.
- Identifiers are masked in reprs, validation errors, and the normalized carrier
  snapshot.

Typed models confer **no** permission to send: a test pins that every blocked
operation stays blocked despite having a model.

## 2b. Read-only PIT certification tooling (2026-07-21)

The tooling to certify `SubscriberInquiry` in PIT is in place: a preview-by-default
operator command and a single-run authorization covering one read-only operation,
one nominated subscriber, one request, PIT-only, time-boxed, consumed on use, and
auditable.

**No live inquiry has been executed.** `SubscriberInquiry` remains
mock-certified and live-blocked. The run requires an operator-nominated PIT
subscriber and configured PIT credentials, neither of which is available in the
environment where this work was prepared. Readiness advances only on real
evidence.

The authorization cannot cover a lifecycle mutation: its allowlist is read-only
operations by construction, and a grant for anything else raises.

## 3. Safety properties

- **Fail-closed at the client boundary.** The check runs before the OAuth token
  is fetched, so a blocked operation costs zero network calls. Calling a client
  method directly is not a way around the operator gates.
- **Paths and methods are exact literals.** No route builder may reconstruct
  them from a naming convention; a regression test asserts none of them is
  reproducible by the old derivation.
- **No automatic retry on provisioning operations**, regardless of what any
  response code suggests. After a successful synchronous acceptance the request
  is already in flight — inspect the transaction rather than resending.
- **Query operations are on-need only** — for operator investigation, delayed
  async troubleshooting, certification, or an authorized support workflow. Never
  keep-alives, never bulk monitoring, never scheduled across subscribers.

## 4. Confidentiality boundary

This repository is **public**. The vendor documentation is confidential material
supplied to Manley Solutions as the intended recipient, and its legend prohibits
retransmission. Therefore:

- The source documents and their extracted contents are **not** in this
  repository and never will be.
- What is published here is the **minimum needed for the integration to
  function**: exact paths, methods, wire field names, header names, state logic,
  and safety gates.
- The detailed contract matrix, the full response-code analysis, source
  citations, and document hashes are retained in the operator's **private
  evidence store**, outside version control.
- Public references use an opaque evidence reference such as
  `TMO-REST-RECON-001` rather than a document title, version, page, or quotation.

Automated guards enforce this (`api/tests/test_tmobile_vendor_confidentiality.py`):
no vendor binary or export filename is tracked; the private store is ignored and
untracked; the public response-code mapping cannot grow into a catalogue; no
document hash, reconstructing citation, or absolute operator path is committed.

## 5. Still outstanding

- **No live testing was performed.** No live T-Mobile call was made and no
  subscriber state changed during this reconciliation.
- Machine-readable API definitions have not been obtained; there is still no
  automated structural validation of requests against a vendor schema.
- A small number of contract questions remain open with T-Mobile and are tracked
  privately; the affected operations stay blocked regardless.
- Callback correlation gaps from the previous review are unchanged — see
  `TMOBILE_CALLBACK_CERTIFICATION.md`.
