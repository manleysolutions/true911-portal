# Open questions for T-Mobile — prepared, not sent

> **Status: DRAFT, NOT SENT.** Nothing here has been transmitted to T-Mobile.
> Sending it is a deliberate operator action.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-08-28 |
| **Basis** | The 2026-08-28 PIT activation + readback — `TMOBILE_PIT_CERTIFICATION_20260828.md` · the 2026-09-01 Network Profile attempt — `TMOBILE_PIT_CERTIFICATION_20260901.md` |
| **Last reviewed** | 2026-09-30 — **question 4 RESOLVED / superseded**: the carrier-directed Network Profile re-test returned HTTP 200 / SUCCESS (`TMOBILE_PIT_CERTIFICATION_20260930.md`). Questions 1–3 unchanged. |
| **Related** | `TMOBILE_OPERATION_READINESS.md` · `TMOBILE_READONLY_GO_LIVE_PLAN.md` |

Each question below is one our own evidence and the authorized vendor
documentation **cannot** answer. Questions already answered by that
documentation are deliberately absent — re-asking them wastes the carrier
relationship and invites a contradictory second answer.

Do not paste live identifiers into carrier correspondence beyond what the
carrier already holds; the trace ids for these requests are in the operator's
private evidence store and can be quoted from there if T-Mobile asks for them.
That includes the correlation, work-flow, service-transaction and
partner-transaction ids for the 2026-09-01 Network Profile failure: T-Mobile
already holds them and will want them, but they are carrier trace identifiers
and this repository is public, so they stay in the private store
(`TMOBILE_PIT_CERTIFICATION_20260828.md` §6). Paste them into the email from
there at send time.

---

## 0. Ready-to-send draft

> **2026-09-30:** question 4 is resolved — **remove it from the draft** before
> sending. The 09-01 failure's trace identifiers were supplied to T-Mobile
> Engineering, who asked for a re-test, and the re-test succeeded. Questions 1–3
> are unaffected.

Reviewed 2026-09-01 after the Network Profile live attempt returned HTTP 500 /
GENS-0005. That run added **question 4**; the set below is now four. Paste as-is;
the reasoning behind each question is in §§1–4 and is deliberately **not** in
the email.

> **Subject:** True911 — four follow-up questions from our PIT activation,
> subscriber readback and Network Profile attempt
>
> Hi Aman,
>
> Thanks again for the PIT inventory and the marketZip guidance. We completed a
> clean activation and readback against Wholesale PIT, and have since made one
> controlled Network Profile attempt that did not succeed. We wanted to close
> out four points before we go any further.
>
> What worked, for context: OAuth and PoP signing, the partner headers, the
> activation itself (HTTP 201, status SUCCESS, result 100, with the MSISDN and
> accountId both returned synchronously), and a subsequent Subscriber Inquiry
> that returned subscriberStatus Active. We sent exactly one of each request,
> with no retries, and we have not touched the three reserve ICCIDs you
> supplied.
>
> **1. Query Transaction Status — what value is `transactionId`?**
>
> For `POST /wholesale/v1/transaction`, should `request.transactionId` be the
> per-request partner-transaction-id our client already sends as a header, or a
> separate T-Mobile-assigned identifier? If it is a T-Mobile-assigned
> identifier, which response field or header carries it?
>
> Our activation returned four distinct identifiers — partner transaction id,
> correlation id, work-flow id and service transaction id — and we would rather
> ask than pick one and send a request we cannot interpret. We have this
> operation blocked in our tooling until we hear from you.
>
> **2. marketZip — we sent 30338 and 99722 came back**
>
> We activated the PIT ICCID using marketZip 30338 as instructed, and the
> activation succeeded. The subsequent subscriber profile returned marketZip
> 99722.
>
> Is that expected in PIT, and what does the returned value represent — the
> market the line was actually assigned to, a PIT placeholder, a billing market,
> or something else? We have recorded both values as observed and have not
> reconciled them in our system.
>
> **3. Callback on a synchronous success**
>
> Our activation returned the complete result synchronously, including the
> MSISDN and the generated accountId. We have not seen a matching callback at
> our `call-back-location`.
>
> For that synchronous-success case, should we also expect an activation
> callback? If so, what event type and roughly what timing, and which source
> addresses does T-Mobile deliver from? We would like to confirm our ingest is
> correct before we rely on callbacks for the lifecycle operations, where the
> synchronous answer is only an acceptance.
>
> **4. Network Profile returned HTTP 500 / GENS-0005**
>
> On 2026-09-01 we made a single controlled request to
> `POST /wholesale/v1/subscriber/network-profile` for the PIT subscriber you
> supplied — the same one that Subscriber Inquiry reports as Active.
>
> OAuth succeeded (HTTP 200). The resource request returned HTTP 500 with
> `GENS-0005`, "Unexpected Exception: Please notify your system administrator".
> We sent it once and did not retry, and we have paused our certification
> sequence rather than moving on to Usage.
>
> Could you confirm whether the Network Profile endpoint is enabled for our
> partner id in PIT, whether any additional partner or subscriber provisioning
> is required for it, whether that test subscriber is valid for this operation,
> and whether anything is missing from our request? We have the correlation id,
> work-flow id, service-transaction id and our partner-transaction-id for that
> exact call and can send them to you on request.
>
> Happy to supply the correlation and transaction ids for any of these requests
> if that helps you locate them in your logs.
>
> Best,
> Stuart Manley
> Manley Solutions / True911+

**Do not send automatically.** Sending is Stuart's action.

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

---

## 4. Network Profile — HTTP 500 / GENS-0005 after a successful OAuth — ✅ RESOLVED / SUPERSEDED 2026-09-30

> **Resolution.** On 2026-09-30 the private trace identifiers of the 09-01
> failure were supplied to T-Mobile Engineering, who asked in writing for a
> re-test. Exactly one request returned **HTTP 200 / `SUCCESS` / `100`** for the
> same approved PIT subscriber. **The prior GENS-0005 condition was not
> reproduced during the T-Mobile-engineering-directed 2026-09-30 re-test.** We do
> not know what, if anything, changed on the carrier side and do not claim it.
> `query_network` is now `PIT_TESTED`, still `SINGLE_RUN_ONLY`. Record:
> `TMOBILE_PIT_CERTIFICATION_20260930.md`. The history below is kept as written.

> On 2026-09-01 we sent exactly one request to
> `POST /wholesale/v1/subscriber/network-profile` for the carrier-provided PIT
> subscriber, which Subscriber Inquiry had independently confirmed as
> `Active` on 2026-08-28.
>
> OAuth returned **HTTP 200**. The resource request returned **HTTP 500**,
> carrier code **GENS-0005**, `userMessage`: *"Unexpected Exception: Please
> notify your system administrator"*.
>
> Please confirm:
>
> 1. Is `POST /wholesale/v1/subscriber/network-profile` enabled for our partner
>    id in the Wholesale PIT gateway?
> 2. Is any additional partner-level or subscriber-level provisioning required
>    before this operation can be used?
> 3. Is the carrier-provided active test subscriber valid for this operation?
> 4. Is anything missing or malformed in our request that GENS-0005 would
>    surface as a generic server error?

**What the evidence does and does not support.** OAuth succeeded, the request
reached the Network Profile gateway, and T-Mobile answered with a structured
carrier error carrying its own trace identifiers. That is enough to classify
this as a **carrier/resource endpoint failure after successful authentication**
— it is *not* an authentication failure, and it is *not* a client-side refusal.

It is **not** enough to locate the cause. GENS-0005 is a generic
"unexpected exception", and every one of these remains possible: a PIT backend
issue, partner or account provisioning, a test-data problem on the subscriber,
an endpoint-specific entitlement, or an undocumented request requirement on our
side. We are not asserting the fault is T-Mobile's, and nothing in our tooling
records it as such.

**Effect on our side.** `query_network` stays at maturity `MOCK_CERTIFIED`. A
failed live attempt is not PIT certification, so nothing was promoted. We did
not retry, did not poll, did not query Transaction Status, and did not advance
to Usage — the certification sequence is paused at this step by design. The one
single-run authorization for the attempt was consumed and cleared.

**Trace identifiers.** T-Mobile already holds all four (correlation, work-flow,
service transaction, and our partner-transaction-id). They are carrier trace
identifiers and this repository is public, so they are held in the operator's
private evidence store and are quoted into carrier correspondence from there —
see `TMOBILE_PIT_CERTIFICATION_20260901.md` §5.
