# T-Mobile Wholesale — production-readiness gap review

> Written 2026-07-21, immediately after the **first successful PIT activation**.
> PIT success proves the wire contract. It does **not** make the integration
> production-ready — this page is the honest distance between the two.
>
> **Nothing here enables production access or changes a production flag.** Every
> item is a gate to be closed deliberately, not a task to be swept.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Status** | 4 of 23 gates closed (updated 2026-07-21 by the certification harness) |
| **Related** | `TMOBILE_PIT_ACTIVATION_PAYLOAD.md` · `tmobile_taap_setup.md` · `TMOBILE_INTEGRATION_AUDIT.md` · `TMOBILE_CALLBACK_AUTH.md` · `TMOBILE_PRIVATE_KEY_REMEDIATION.md` |

---

## 1. Status legend

| Mark | Meaning |
|---|---|
| ✅ | Done and verified |
| 🟡 | Implemented, **not verified** against the real integration |
| ❌ | Not done |
| 🚫 | Deliberately blocked (a hard gate) |

---

## 2. The checklist

### Integration proof

| # | Gate | State | Notes |
|---|---|---|---|
| 1 | **PIT activation success** | ✅ | `2026-07-21T03:18:33Z`, HTTP 201, result `100`. Record: `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md`. Fixture: `api/tests/fixtures/tmobile_pit_success_20260721T031833Z.json`. |
| 2 | **Callback received + processed for that activation** | ❌ | **UNVERIFIED.** No callback has been confirmed for this activation. `scripts/tmobile_callback_inspect.py` is the read-only check; it has not been run. The account ID was recovered from the **synchronous 201 body**, not from a callback — so the callback path remains unproven on the success case. |
| 3 | **Subscriber status queried post-activation** | ❌ | **UNVERIFIED.** `scripts/tmobile_subscriber_status.py` exists (SubscriberInquiry + NetworkQuery, read-only) and has not been run. |
| 4 | **Activation state persisted to our database** | 🟡 | `tmobile_callback_processor` writes `sims.meta.tmobile_account_id` / `tmobile_msisdn` **on the callback path only**. A synchronous-201 activation run from the operator script writes **nothing** — the evidence bundle is the only record. **Gap:** persist the synchronous result. |

### Environment and credentials

| # | Gate | State | Notes |
|---|---|---|---|
| 5 | **Production credentials** | ❌ | Only PIT consumer key/secret are held. Production key/secret must be issued by T-Mobile and stored as Render secrets — never in `.env` or the repo. |
| 6 | **Production base URLs** | ❌ | `TMOBILE_BASE_URL` / `TMOBILE_TOKEN_URL` currently point at `wholesaleapi-test.t-mobile.com`. Production hosts are not yet supplied. |
| 7 | **Production gateway onboarding** | ❌ | The PIT gateway required T-Mobile to **recreate the configuration** before it worked (§3). Assume production needs the same explicit onboarding, and confirm it **before** the first production attempt rather than discovering it through a failure. |
| 8 | **Certificate / key rotation** | 🚫 | **Hard gate — BACKLOG C3 / D-003.** The RSA private key is in git history. It **must** be rotated (new pair → register public key with T-Mobile → deregister old → `TMOBILE_PRIVATE_KEY_PEM` as a Render secret) before any non-PIT exposure. See `TMOBILE_PRIVATE_KEY_REMEDIATION.md`. |

### Callback path

| # | Gate | State | Notes |
|---|---|---|---|
| 9 | **Callback authentication** | 🟡 | Implemented behind `FEATURE_TMOBILE_CALLBACK_AUTH` (shared secret + optional IP allowlist, `app/security/tmobile_callback_auth.py`). HMAC signature verification is deferred until T-Mobile publishes a signing spec. Must be **on** in production. |
| 10 | **Callback replay protection** | ⚠️ partial | **CORRECTION (2026-07-21):** an earlier revision of this row said "no timestamp window". That was wrong — `TMOBILE_CALLBACK_MAX_AGE_SECONDS` (default 600) refuses *promotion* of a callback whose event timestamp is stale, and it is tested. What is genuinely missing is a **nonce / delivery-id dedupe**: a replay *inside* the window is accepted. See `TMOBILE_CALLBACK_CERTIFICATION.md` #3. |
| 11 | **Idempotency** | ❌ | `Job.idempotency_key` exists on the model and `job_service.create_and_enqueue` accepts it, but the callback router does **not** pass one. A duplicate delivery mints a fresh `payload_id` and enqueues a second job. Effects converge (writes are absolute, not incremental) but the audit trail double-counts. |
| 12 | **Duplicate activation prevention** | 🟡→✅ *for the harness path* | Two operator gates (`--confirm-live` **and** `TMOBILE_PIT_LIVE_CALLS_ENABLED`), and the runner never retries — pinned by `TestOperatorRunnerNeverRetries`. **Improved 2026-07-21:** `scripts/tmobile_pit.py` adds a persisted lifecycle state machine that refuses a duplicate activation on an `active` line and refuses any state change while a prior request is unreconciled. Still **no server-side check** at T-Mobile's end. |
| 12a | **Undocumented-operation prevention** | ✅ *new* | `tmobile_operations.py` blocks any operation whose path we derived rather than received from T-Mobile — 7 of 8 operations. Cannot be lifted by config. See `TMOBILE_API_INVENTORY.md`. |
| 12b | **Correlation of callbacks to requests** | ❌ | Transaction ids are archived but never correlated. `TMOBILE_CALLBACK_CERTIFICATION.md` #4 — the prerequisite for closing #10 and quarantine. |

### Operations

| # | Gate | State | Notes |
|---|---|---|---|
| 13 | **Reconciliation** | ❌ | No job compares T-Mobile's view of a line against ours. `inventory_reconciliation/` exists for other carriers and is the pattern to follow. |
| 14 | **Subscriber status polling** | ❌ | No scheduled poll. The read-only script is manual only. |
| 15 | **Deactivation / suspension safeguards** | 🟡 *materially improved 2026-07-21* | The client methods themselves are still ungated — calling `deactivate_subscriber` directly bypasses everything. But they are now **unreachable through the sanctioned path**: `scripts/tmobile_pit.py` blocks them outright (undocumented paths) and, even once documented, requires `--confirm-live` + `--confirm-destructive` + `--reason` + destructive-tier allowlisting. **Remaining work:** add a fail-closed guard to the client methods themselves so the safety does not depend on which entry point an operator picks. |
| 15a | **Designated test-SIM allowlist** | ✅ *new* | Three nested tiers (`destructive ⊆ lifecycle ⊆ read-only`), empty by default, no wildcards, validated at parse time, masked in logs. The first-activation ICCID is additionally protected. `TMOBILE_PIT_TEST_SIM_POLICY.md`. |
| 16 | **Audit trail** | 🟡 | Correlation + partner-transaction ids are logged for every outbound request; callbacks archive to `integration_payloads`. Not yet written to `AuditLogEntry`, so there is no operator-visible activation history. |
| 17 | **Redaction** | ✅ | Allowlist-based capture (`tmobile_evidence.py`); credential headers are presence-only; body content is hashed, never recorded; `mask_tail` masks identifiers in committed artifacts. Pinned by the evidence and closeout suites. |
| 18 | **Monitoring / alerting** | ❌ | No alert on activation failure, callback drought, or a `webhook.tmobile` job stuck at `queued`. The callback soak runbook is manual (`TMOBILE_CALLBACK_SOAK_RUNBOOK.md`). |
| 19 | **Operator permissions** | ❌ | Activation is a script run with database and secret access, not an RBAC-guarded action. No role currently distinguishes "may activate a line". |
| 20 | **Rollout flags · rollback · pilot allowlist** | 🟡 | Flags exist (`TMOBILE_PIT_LIVE_CALLS_ENABLED`, `FEATURE_TMOBILE_CALLBACK_INGEST`, `FEATURE_TMOBILE_CALLBACK_AUTH`) and rollback is "set the flag to false". **Pilot ICCID allowlist: DONE** (item 15a). Still missing: a written rollback procedure for a line already activated at T-Mobile — and note there may be none, since deactivation is undocumented and terminal. |

---

## 3. What PIT success does and does not prove

**Proven.** The client's OAuth + PoP contract, the activation payload, the
partner/sender headers, and the `partner-transaction-id` / `call-back-location`
headers are all accepted by T-Mobile's gateway, and the response is parsed
correctly (HTTP 201, `status=SUCCESS`, result `100`).

**Not proven.** That a callback arrives and is processed; that our database
reflects the activation; that the line actually passes traffic; that any of this
behaves the same against a production gateway with production credentials.

**Newly established 2026-07-21 — the API surface is one operation wide.** A
provenance audit (`TMOBILE_API_INVENTORY.md`) found **no T-Mobile OpenAPI spec,
Postman collection, or written contract anywhere in this repository**. Seven of
our eight wholesale operations use paths our own code derived by string-joining
an operation name onto a base path — and that derivation is provably wrong,
since the derived activation path (`/activate`) is not the one that works
(`/activation`). Those seven are now **blocked from sending**. Production
readiness therefore requires T-Mobile to supply the contracts, not merely to
grant access.

**Root cause of the preceding failures.** Resolved by T-Mobile gateway
configuration recreation. The available evidence indicates the client request
contract was valid at the time of the successful activation, and no additional
Partner Foundation header was required. Exact internal T-Mobile root cause is not
independently observable from the client.

---

## 4. Suggested order

1. **#2 and #3** — run both read-only scripts. Cheapest, and they close the two
   biggest unknowns about the line that already exists.
2. **#15** — put a fail-closed gate on the destructive lifecycle methods. This is
   a small change guarding the worst outcome.
3. **#4, #11, #10** — make the activation → persistence path durable and
   replay-safe.
4. **#8** — key rotation, before anything leaves PIT.
5. Everything else is production onboarding proper.
