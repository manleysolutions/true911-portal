# T-Mobile PIT certification record — 2026-08-28

> First carrier-backed **activation + independent readback** against T-Mobile
> Wholesale PIT. Two live requests were sent, one each, with no retry.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-08-28 |
| **Environment** | PIT (`TMOBILE_ENV=pit`) |
| **Related** | `TMOBILE_OPERATION_READINESS.md` · `TMOBILE_PIT_OPERATOR_RUNBOOK.md` · `TMOBILE_READONLY_GO_LIVE_PLAN.md` · `TMOBILE_CARRIER_QUESTIONS_OPEN.md` |

Identifiers below are masked to their last four. The unmasked values, the full
evidence bundles, and the carrier trace identifiers live only in the operator's
private evidence store — see `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md`
for the handling policy.

---

## 1. What is now proven live

| Capability | Status |
|---|---|
| OAuth token acquisition | ✅ proven |
| PoP signing (`Content-Type;Authorization;uri;http-method;body`) | ✅ proven |
| Partner headers (`partner-id`, `sender-id`, `partner-transaction-id`) | ✅ proven |
| `POST /wholesale/v1/subscriber/activation` | ✅ proven |
| Activation request schema | ✅ proven |
| Synchronous success response (HTTP 201 / `SUCCESS` / result `100`) | ✅ proven |
| MSISDN assignment | ✅ proven |
| `accountId` assignment | ✅ proven |
| `POST /wholesale/v1/subscriber/profile` (SubscriberInquiry) | ✅ proven |
| Carrier `subscriberStatus: Active` readback | ✅ proven |

### 1.1 Activation

One request. `marketZip` **30338**, as instructed by T-Mobile Engineering for
the supplied PIT inventory.

- HTTP **201**, `status: SUCCESS`, `result: 100 / SUCCESS`
- ICCID `…2715` (carrier-supplied PIT activation SIM)
- MSISDN `…2101` assigned
- `accountId` `…5704` assigned

T-Mobile documented the account id as arriving asynchronously via
`call-back-location`; it arrived in the **synchronous** 201 body, as it did on
the 2026-07-21 activation. That remains an observation, not a contract.

### 1.2 SubscriberInquiry

One request, selector ICCID `…2715`, sent under a single-run PIT authorization
which was consumed and cleared.

- HTTP **200**, `status: SUCCESS`, `result: 100 / SUCCESS`
- `subscriberStatus: Active`
- `simNetworkType: M2M` · `billingIndicator: Postpaid` · `embeddedSim: false`
- `portOutIndicator: No` · `baseProductId: Infatrac Internet Access Plan`
- Activation and status-change dates both `2026-08-28T10:13:23-07:00`

No retry, no follow-up query, no polling, no subscriber mutation.

### 1.3 Reserve inventory — untouched

T-Mobile supplied three reserve activation ICCIDs alongside the one used. **None
was activated and none is on any allowlist.** They stay that way until there is
a stated reason to spend one.

---

## 2. Observed carrier behaviour recorded, not normalized

### 2.1 `marketZip` returned differs from `marketZip` requested

Activation was requested with `marketZip` **30338** (T-Mobile's instruction).
The subsequent subscriber profile returned `marketZip` **99722**.

This is **recorded as observed** and deliberately **not** rewritten,
normalized, or "corrected" anywhere in the code. We do not know what the
returned value represents — a market assignment, a PIT default, a billing
market, or something else — and mapping it by resemblance would be a guess.
It is question 2 in `TMOBILE_CARRIER_QUESTIONS_OPEN.md`.

### 2.2 No callback observed

`FEATURE_TMOBILE_CALLBACK_INGEST=true`. Inspection for the activated ICCID
returned `matched_callback_count = 0` across 5 scanned inbound T-Mobile
payloads: no callbacks, no jobs, no SIM record.

**This is not proof that T-Mobile sent none.** Persistence requires both the
ingest flag *and* the authenticity gate, and the deployment's logging
architecture means the absence of a `T-Mobile callback ingest DENIED` line under
`/var/log` is not authoritative either. The honest statement is *no callback was
observed or persisted*, and the ledger records exactly that — every callback
field is `null`, which is different from recording a negative.

Because the full result arrived synchronously **and** an independent read
confirms `Active`, the missing callback does **not** block the carrier-state
determination. It is a separate open issue, and question 3 for T-Mobile.

---

## 3. The local ledger defect, and what changed

### 3.1 Root cause

After the 201, the operator ledger read `state: activation_requested`,
`confirmed: True` — while an independent carrier read said `Active`.

Nothing was wrong with either call. There was **no code path by which any
observation could settle the ledger**:

- `scripts/tmobile_pit.py::cmd_run` wrote `observed = expected`, and `expected`
  is `next_state("activate_subscriber", unknown)` → `activation_requested`. The
  synchronous body was serialized into the evidence bundle and never classified.
- `tmobile_lifecycle.settle()`, which resolves `activation_requested → active`,
  **had no caller** outside a test.
- The read-only certification path (`cmd_read_only`) wrote an evidence bundle
  and never touched the ledger at all.
- The callback processor writes to the application database, not to this
  operator file.

So the only thing that ever wrote the ledger was the request itself, and a
request can only ever say *I asked*.

A second, quieter defect sat next to it: `bundle["ok"]` was set from "no
exception raised", and `_request` raises only on HTTP ≥ 400. A 2xx carrying
`status: FAILURE`, or no status at all, would have been recorded as a
successful activation.

### 3.2 The model now implemented

State and evidence are recorded **separately**, because they are different
claims. `python ../scripts/tmobile_pit.py state --iccid <ICCID>` prints both.

| Class | Meaning | Set by |
|---|---|---|
| A `request_submitted` | we sent something | `run <op>` |
| B `carrier_sync_ack` | the carrier answered **our request** | 2xx whose body reads as an acceptance |
| C `carrier_verified` | the carrier described **its own record** | `subscriber-inquiry` / `query-network` returning a known `subscriberStatus` |
| D/E/F `callback_confirmed` | callback received, authenticated, correlated | callback path |
| G `conflict` | two observations disagree | either reconciler |

Rules that follow from it:

- **A synchronous acceptance never settles a line.** It is class B; the line
  stays `activation_requested`. That is the pre-existing architectural
  principle and it was right — the gap was that nothing could ever move past it.
- **An independent carrier read settles the line, without a callback.** A read
  is not a transition, so it is not gated by `next_state` or by the
  pending-duplicate rule — gating a query on already knowing the state is
  circular, and is precisely how the ledger got stuck.
- **Nothing is guessed.** A `subscriberStatus` outside the reconciled
  vocabulary (`Active` / `Suspended` / `Deactivated`) raises rather than being
  mapped by resemblance. An absent status reconciles nothing.
- **Contradictions are surfaced, never absorbed.** A carrier read that
  contradicts a settled state, or a late callback that contradicts an
  independent read, sets `reconciliation_required` and leaves the recorded
  state alone.
- **An apparent success we cannot read fails closed** — recorded `failed`, with
  no carrier-ack evidence.

Applied to 2026-08-28, the sequence is:
`unknown` → (activation 201) `activation_requested` / class **B** →
(SubscriberInquiry `Active`) `active` / class **C**, with every callback field
still `null`.

### 3.3 Rebuilding the ledger without spending another carrier call

The reconciliation above is driven by a live response envelope, which left a
practical gap: the 2026-08-28 SubscriberInquiry **already happened** and its
answer is already written down, but the only way to settle the ledger was to
send a second one.

`reconcile --iccid <ICCID> --evidence <bundle>.json` closes that. It opens no
socket, parses the carrier's own recorded response out of the evidence bundle
(matched by the operation's **exact** wire path, never by position), and runs it
through the same `reconcile_from_carrier_read`. The ledger records
`carrier_verified_source: replayed:<path>` so an audit can tell a watched answer
from a replayed one.

It is a replay, not an operator attestation — a status word cannot be typed in.
It refuses an activation bundle outright: that is class-B evidence, and
replaying one as class C would reintroduce precisely the confusion §3.1
describes.

**Prerequisite:** the evidence bundle must still exist. The 2026-08-28 bundles
were written to `/tmp` on the operator host. If that host's `/tmp` has been
cleared or the run happened in an ephemeral deploy container, the bundles are
gone and the ledger cannot be reconciled from them — in which case the correct
response is to leave the ledger where it is and record the carrier state from
this document, **not** to resend anything.

---

## 4. Operator-experience defect fixed

`cmd_run` printed:

```
python -m scripts.tmobile_callback_inspect --iccid <ICCID>
```

That command **cannot work** from `api/`, which is the working directory the
runbook documents. There is a second, unrelated `api/scripts` package; from
`api/` it wins the import, so the module form fails with `ModuleNotFoundError`.
The `python -m scripts.<name>` convention is correct for `api/scripts/*` and
does not carry over to the repository-root `scripts/` directory.

The harness now emits — and this doc set now uses — the path form that every
other command in the harness already documents:

```powershell
cd api
python ../scripts/tmobile_callback_inspect.py --iccid <ICCID>
```

Pinned by `test_the_emitted_command_runs_from_the_documented_directory`, which
actually runs it, and by a companion test asserting the module form still fails
so the fix cannot silently drift back.

---

## 5. Certification status after this run

| Operation | Class | Live status |
|---|---|---|
| `activate_subscriber` | B reversible | ✅ PIT-tested (2026-07-21, 2026-08-28) |
| `subscriber_inquiry` | A read-only | ✅ PIT-tested (2026-08-28) |
| `query_network` | A read-only | ⏳ certification-ready — see §5.1 |
| `query_usage` | A read-only | ⏳ certification-ready — see §5.1 |
| `query_transaction_status` | A read-only | ⛔ blocked on a carrier answer — §5.2 |
| `suspend` / `restore` / `change_sim` / `deactivate` | B / C | ⛔ blocked, unchanged |

### 5.1 QueryNetwork and QuerySubscriberUsage — ready, still gated

Both now meet every prerequisite SubscriberInquiry met before it was run:

- authoritative vendor path, reconciled and pinned as an exact literal;
- schemas reconciled (usage carries **no** date range — that was removed
  because it is not in the contract);
- mock-certified, read-only, no callback;
- the designated subscriber is **carrier-confirmed `Active`**;
- OAuth, PoP and partner-header behaviour proven live;
- the ICCID is on `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST` and nowhere else.

**No code change was needed to make them certifiable** — the single-run
authorization that unlocked SubscriberInquiry already covers them, one operation
and one subscriber at a time, consumed on use. Neither has been promoted to
generally sendable and neither should be: `readiness` stays `mock_certified`
until a live run justifies moving it.

The exact commands are in `TMOBILE_READONLY_GO_LIVE_PLAN.md` §2. A live run is
an operator decision, not a consequence of this document.

**Verified 2026-08-28 (offline, no carrier contact):**

| Check | query_network | query_usage |
|---|---|---|
| Exact vendor-documented path | ✅ `POST /wholesale/v1/subscriber/network-profile` | ✅ `POST /wholesale/v1/subscriber/usage` |
| Classification | ✅ A read-only | ✅ A read-only |
| Callback behaviour | ✅ none, synchronous only | ✅ none, synchronous only |
| ICCID accepted as selector | ✅ | ✅ |
| Certification blocker | ✅ none | ✅ none |
| Eligible for single-run grant | ✅ | ✅ |
| Generally live-sendable | ✅ **NO — BLOCKED** | ✅ **NO — BLOCKED** |
| Preview renders correct body | ✅ `{iccid}` only | ✅ `{iccid}` only — **no date range** |
| Preview opens no connection | ✅ audited: 0 outbound sockets, 0 DNS lookups | ✅ same |

Neither has been sent. Preview was audited with a `sys.addaudithook` on
`socket.connect` / `socket.getaddrinfo`: the only event observed was asyncio's
own loopback self-pipe, and no name resolution occurred at all.

### 5.3 Readiness taxonomy — a decision, not an oversight

`subscriber_inquiry` was exercised live on 2026-08-28 and its `readiness` still
reads `mock_certified`. That is deliberate and needs an owner's decision, because
of how the taxonomy is currently wired:

```
LIVE_SENDABLE_READINESS = {PIT_TESTED, PRODUCTION_APPROVED}
is_sendable = provenance OK and classification OK and readiness in LIVE_SENDABLE_READINESS
```

Advancing it to `pit_tested` would therefore make it **generally live-sendable**
and silently remove its single-run gate — one exercised call would buy unlimited
future calls. That is almost certainly not what "we ran it once in PIT" should
mean.

The canonical ladder is `IMPLEMENTED → MOCK_CERTIFIED → PIT_TESTED →
PRODUCTION_APPROVED`, and it should stay the only one. The suggested fix is to
stop treating `PIT_TESTED` as self-authorizing — drop it from
`LIVE_SENDABLE_READINESS`, leaving `PRODUCTION_APPROVED` as the only state that
authorizes an ungated send, and keep the single-run grant as the route to a PIT
call at any readiness. That is a policy change with its own review, so it is
recorded here rather than made in passing.

### 5.2 QueryTransactionStatus — blocked, and now enforced

`transactionId` is documented as "the customer transaction id of a previously
submitted request". The activation returned **four** distinct identifiers
(partner transaction id, correlation id, work-flow id, service transaction id)
and nothing states which one belongs in that field.

Previously the operation was single-run authorizable like the other three. It is
now refused at the point a grant is cut, via a new
`Operation.certification_blockers` field: an operation with an unresolved
question about *what to put on the wire* is not certifiable even once, because
a wrong id returns "not found" and so does a correct id for an expired
transaction — the run could not be interpreted either way.

Clearing it is a reviewed code change with T-Mobile's written answer recorded,
never a config toggle.

---

## 6. Confidentiality

Public in this repository: implementation, tests, generic docs, architecture,
sanitized examples, masked identifiers.

Private, in the operator's evidence store only: vendor documentation and prose,
full evidence bundles, unmasked ICCID / MSISDN / account id, carrier trace
identifiers, OAuth payloads, credentials, keys.
