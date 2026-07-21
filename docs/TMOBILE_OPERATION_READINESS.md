# T-Mobile Wholesale — operation readiness

> Status only. This page deliberately carries **no** request/response schemas,
> no vendor prose, and no source citations — see §4.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Last reviewed** | 2026-07-21 |
| **Evidence reference** | `TMO-REST-RECON-001` |
| **Related** | `TMOBILE_API_INVENTORY.md` · `TMOBILE_PIT_CERTIFICATION_PLAN.md` · `TMOBILE_PRODUCTION_READINESS.md` |

---

## 1. Readiness

| Operation | Implemented | Mock-certified | PIT-tested | Live-send | Risk | Unresolved blocker |
|---|---|---|---|---|---|---|
| Activate subscriber | Yes | Yes | Yes | **Allowed** | B reversible | — |
| Subscriber inquiry | Yes | Yes | No | **Blocked** | A read-only | Not yet exercised in PIT |
| Query network | Yes | Yes | No | **Blocked** | A read-only | Not yet exercised in PIT |
| Query subscriber usage | Yes | Yes | No | **Blocked** | A read-only | Not yet exercised in PIT |
| Suspend subscriber | Yes | Yes | No | **Blocked** | B reversible | Not yet exercised in PIT |
| Restore subscriber | Yes | Yes | No | **Blocked** | B reversible | Not yet exercised in PIT |
| Change SIM | Yes | Yes | No | **Blocked** | **C destructive** | Replaced SIM ages out; no customer-facing inverse |
| Deactivate subscriber | Yes | Yes | No | **Blocked** | **C destructive** | Treated as terminal; reactivation not implemented |
| Query transaction status | Yes | Yes | No | **Blocked** | A read-only | Identifier semantics unconfirmed |

**Activation remains the only operation that may be transmitted live.**

## 2. What changed, and what did not

Implementation was **reconciled against authorized vendor documentation reviewed
privately** on 2026-07-21. The reconciliation was substantial: the previously
derived paths were wrong for every operation, four operations used the wrong
HTTP method, and every lifecycle request body was wrong.

What did **not** change is the send policy. Obtaining a contract answers *what*
to send; it says nothing about whether this client sends it correctly. Readiness
is therefore a separate gate from provenance, and only real PIT evidence opens
it. All eight non-activation operations stay blocked.

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
