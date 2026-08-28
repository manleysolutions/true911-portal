# Open questions for T-Mobile — prepared, not sent

> **Status: DRAFT, NOT SENT.** Nothing here has been transmitted to T-Mobile.
> Sending it is a deliberate operator action.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-08-28 |
| **Basis** | The 2026-08-28 PIT activation + readback — `TMOBILE_PIT_CERTIFICATION_20260828.md` |
| **Related** | `TMOBILE_OPERATION_READINESS.md` · `TMOBILE_READONLY_GO_LIVE_PLAN.md` |

Each question below is one our own evidence and the authorized vendor
documentation **cannot** answer. Questions already answered by that
documentation are deliberately absent — re-asking them wastes the carrier
relationship and invites a contradictory second answer.

Do not paste live identifiers into carrier correspondence beyond what the
carrier already holds; the trace ids for these two requests are in the operator's
private evidence store and can be quoted from there if T-Mobile asks for them.

---

## 1. QueryTransactionStatus — what is `transactionId`?

> For `POST /wholesale/v1/transaction`, is `request.transactionId` expected to
> be the per-request **partner-transaction-id** our client already sends as an
> HTTP header, or a separate T-Mobile-assigned identifier?
>
> If it is a T-Mobile-assigned identifier, which response field or response
> header supplies it?

**Why we cannot resolve this ourselves.** Our successful activation returned
four distinct identifiers — partner transaction id, correlation id, work-flow
id, and service transaction id. The contract says "the customer transaction id
of a previously submitted request", which is consistent with more than one of
them. Choosing by naming resemblance would be a guess, and the resulting test
would be uninterpretable: a wrong identifier returns "not found", and so does a
correct identifier for a transaction that has aged out.

**Blocking effect.** QueryTransactionStatus is the only read-only operation we
are refusing to certify. It is not merely un-run — it is refused at the point a
single-run authorization would be issued, so no operator can send it by
accident. It stays that way until this answer is recorded in writing.

---

## 2. `marketZip` — requested 30338, returned 99722

> We activated the carrier-provided PIT ICCID using the `marketZip` **30338**
> that T-Mobile Engineering instructed us to use. The subsequent Query
> Subscriber / subscriber profile response returned `marketZip` **99722**.
>
> Is that expected PIT behaviour, and what does the returned value represent —
> the market the line was actually assigned to, a PIT placeholder, a billing
> market, or something else?

**Why it matters beyond curiosity.** If the returned value is the line's real
market assignment, then the value we send is a request rather than a
determination, and anything we build that reasons about a subscriber's market
must read it back rather than assume it. If it is a PIT artifact, it must not be
propagated into any production expectation.

We have deliberately **not** normalized, rewritten, or reconciled the
discrepancy anywhere in the code. It is recorded as observed.

---

## 3. Callback on a synchronous success

> Our activation returned a synchronous **HTTP 201** with `status: SUCCESS`,
> `result: 100`, and both the assigned MSISDN and the generated `accountId` in
> the response body. We have observed no matching callback to our
> `call-back-location`.
>
> Should a callback also be expected for a successful activation when the
> complete result is returned synchronously? If so, what is its expected event
> type and timing, and from which source addresses does T-Mobile send it?

**Context we can supply if asked.** Our callback ingest was enabled at the time.
We cannot prove that no callback was sent — persistence requires both our ingest
flag and our authenticity gate to pass, and our logging architecture does not
let us assert authoritatively that no delivery was refused. So the accurate
statement is that none was *observed or persisted*, not that none arrived.

This does not currently block us: the synchronous result was complete, and an
independent SubscriberInquiry confirms the line is `Active`. It matters for
lifecycle operations where the synchronous answer is only an acceptance.
