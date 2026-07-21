# T-Mobile PIT API certification plan

> T-Mobile Engineering has authorized True911 to run the remaining PIT API calls
> needed to complete the development and testing cycle:
> *"Please run other API calls to complete your development and testing cycle."*
>
> **That authorization is necessary but not sufficient.** Permission to call an
> API is not a specification for it. Seven of our eight operations have no
> T-Mobile-supplied contract in this repository, so this plan's first live step
> is a request for documentation, not a request to a gateway.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-07-21 |
| **Status** | Plan only — **no step below has been executed** |
| **Related** | `TMOBILE_API_INVENTORY.md` · `TMOBILE_PIT_OPERATOR_RUNBOOK.md` · `TMOBILE_CALLBACK_CERTIFICATION.md` · `TMOBILE_PIT_TEST_SIM_POLICY.md` |

---

## 1. Scope

| In scope | Out of scope |
|---|---|
| PIT environment only | Any production gateway or credential |
| Designated PIT test SIMs on the allowlists | Any customer or production ICCID |
| One operation per invocation, operator-reviewed | Batch or automated sequences |
| Mocked negative tests | Malformed auth/crypto sent to T-Mobile |

**Cryptographic negative tests stay mocked.** Deliberately sending a bad PoP, an
expired token, or a corrupted body hash to T-Mobile risks tripping gateway abuse
protections and muddying their logs. Ask before ever sending one live.

---

## 2. Blocking dependency — the documentation request

Before steps 6 onward can run at all, T-Mobile must supply the contract for the
operations we intend to exercise. Send them this, per operation:

1. Exact HTTP method and path in the Wholesale PIT gateway.
2. Exact request body schema, and which identifier keys are required.
3. Exact synchronous response schema, including the **full result-code vocabulary** (we have only ever seen `100`).
4. Synchronous, asynchronous via `call-back-location`, or both — and which callback event type it emits.
5. Whether the PoP ehts set differs from `Content-Type;Authorization;uri;http-method;body`.
6. Prerequisite state, and the exact state the line is left in.
7. Reversibility, and the inverse operation.
8. PIT restrictions or rate limits.

Plus, specifically:

- **Suspend** — maximum duration? auto-deactivation? billing impact?
- **Restore** — is the original MSISDN retained?
- **Deactivate** — is the MSISDN released? any grace period? reversible in PIT?
- **ChangeSim** — can a swapped-out ICCID be re-attached?
- **QueryUsage** — required date format?
- **Activation** — the full result-code list, and whether an activation callback should have fired for `true911-pit-d1475fec-…` on 2026-07-21.

`python ../scripts/tmobile_pit.py show <operation>` prints this list verbatim.

---

## 3. Certification matrix

Legend — **Status:** ⬜ not run · ✅ passed · ❌ failed · ⛔ blocked.

### 3.1 Positive matrix

| # | Operation | Prereq | Test SIM | Expected request | Expected sync response | Expected callback | Expected final state | Rollback | Evidence | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | `activate_subscriber` (already done) | ICCID inactive | `…7538` (protected) | `POST /wholesale/v1/subscriber/activation`, nested body | `201` `SUCCESS` result `100` | account ID (arrived synchronously instead) | `active` | none available — deactivation blocked | `tmobile_pit_success_20260721T031833Z.json` | ✅ |
| P2 | callback verification for P1 | P1 | `…7538` | none — DB read only | n/a | n/a | unchanged | n/a | inspector output | ⬜ |
| P3 | `subscriber_inquiry` | contract from T-Mobile | `…7538` | ⛔ unknown | ⛔ unknown | ⛔ unknown | unchanged | n/a | — | ⛔ |
| P4 | `query_network` | contract | `…7538` | ⛔ unknown | ⛔ unknown | ⛔ unknown | unchanged | n/a | — | ⛔ |
| P5 | `query_usage` | contract + date format | `…7538` | ⛔ unknown | ⛔ unknown | ⛔ unknown | unchanged | n/a | — | ⛔ |
| P6 | `activate_subscriber` | lifecycle SIM inactive | lifecycle ICCID | as P1 | `201` `SUCCESS` | account ID | `active` | ⛔ none | bundle | ⬜ |
| P7 | `suspend_subscriber` | P6 `active` | lifecycle ICCID | ⛔ unknown | ⛔ unknown | ⛔ unknown | `suspended` | `restore` (unproven) | — | ⛔ |
| P8 | `restore_subscriber` | P7 `suspended` | lifecycle ICCID | ⛔ unknown | ⛔ unknown | ⛔ unknown | `active` | ⛔ none | — | ⛔ |
| P9 | `change_sim` | P6 + second SIM | lifecycle ICCID | ⛔ unknown | ⛔ unknown | ⛔ unknown | `active` on new ICCID | ⛔ none | — | ⛔ |
| P10 | `deactivate_subscriber` | P6/P8, destructive allowlist | **destructive ICCID only** | ⛔ unknown | ⛔ unknown | ⛔ unknown | `deactivated` (terminal) | **none — terminal** | — | ⛔ |

**P2 is the only live-ready step that is not already done, and it touches no
network.** Everything from P3 down is blocked on §2.

### 3.2 Negative matrix

Mocked unless stated. None of these is sent to T-Mobile.

| # | Case | Mechanism under test | Expected | Where | Status |
|---|---|---|---|---|---|
| N1 | Invalid / malformed ICCID | allowlist regex | refused at parse; nothing sent | `TestAllowlistParsing` | ✅ |
| N2 | Wildcard in an allowlist | wildcard ban | refused | `TestAllowlistParsing` | ✅ |
| N3 | ICCID absent from the tier | tier check | refused, identifier masked | `TestAllowlistHierarchy` | ✅ |
| N4 | Read-only listing used for a lifecycle op | tier hierarchy | refused | `TestAllowlistHierarchy` | ✅ |
| N5 | Lifecycle listing used for destruction | tier hierarchy | refused | `TestAllowlistHierarchy` | ✅ |
| N6 | Destroy the protected ICCID | protected guard | refused without explicit listing **and** `--confirm-protected` | `TestProtectedIccid` | ✅ |
| N7 | Blocked operation, even in preview | provenance gate | refused, questions printed | `TestOperationProvenance` | ✅ |
| N8 | Duplicate activation on an `active` line | state machine | refused | `TestStateMachine` | ✅ |
| N9 | Second request while one is pending | pending guard | refused as duplicate | `TestStateMachine` | ✅ |
| N10 | Any operation on a `deactivated` line | terminal guard | refused | `TestStateMachine` | ✅ |
| N11 | Invalid transition (restore an active line) | state machine | refused, legal set listed | `TestStateMachine` | ✅ |
| N12 | Live call with the env switch off | live switch | refused | `TestLiveCallGates` | ✅ |
| N13 | State change without `--confirm-live` | confirmation gate | refused | `TestCliGateOrdering` | ✅ |
| N14 | Activation with no `call-back-location` | client guard | refused | `TestLiveCallGates` | ✅ |
| N15 | Non-2xx response | error path | one request, no retry, bundle written | `TestLiveCallGates` | ✅ |
| N16 | Replayed callback (stale timestamp) | age guard | promotion refused, archived | `TestReplayProtection` | ✅ |
| N17 | Replayed callback inside the window | — | **accepted — known gap** | `test_GAP_replay_defense_is_a_time_window_not_a_nonce` | ⚠️ gap |
| N18 | Duplicate callback delivery | idempotency | state converges; **second archive row created — gap** | `TestDuplicateDelivery` | ⚠️ gap |
| N19 | Out-of-order callbacks | ordering | **not reordered — gap** | `test_GAP_out_of_order_callbacks_are_not_reordered` | ⚠️ gap |
| N20 | Callback for an unknown subscriber | matching | archived, never promoted; **no quarantine — gap** | `TestUnknownCallbackHandling` | ⚠️ gap |
| N21 | Unauthenticated callback | auth gate | dropped before archiving; 200 returned | `TestRecoverability` | ✅ |
| N22 | Ambiguous subscriber match | ambiguity guard | refused, never guesses | `TestUnknownCallbackHandling` | ✅ |
| N23 | Duplicate `partner-transaction-id` | — | **no detection — gap** (ids are not correlated at all) | `test_GAP_transaction_ids_are_not_extracted_or_correlated` | ⚠️ gap |
| N24 | Expired PoP | crypto | **mocked only.** Do not send live without T-Mobile's explicit go-ahead | — | ⬜ |
| N25 | Body-hash mismatch | crypto | **mocked only.** Same restriction | `test_tmobile_reference_contract.py` | ✅ |

---

## 4. Live execution sequence — **PREPARED, NOT EXECUTED**

Run one step at a time. **Stop after every state-changing step** and get
operator review before continuing. No step may be scripted into a loop.

### Stage 0 — preflight (no network)

```powershell
cd api
python ../scripts/tmobile_pit.py operations          # confirm what is sendable
python ../scripts/tmobile_pit.py allowlists          # confirm the tiers
python ../scripts/tmobile_pit.py state --iccid <SUCCESS_ICCID>
```

### Stage 1 — verify what already exists (no network)

```powershell
# Step 1-2: did a callback ever arrive for the successful activation?
python -m scripts.tmobile_callback_inspect `
    --iccid <SUCCESS_ICCID> `
    --partner-transaction-id true911-pit-d1475fec-981b-40a7-a27c-d867aab8e7f9 `
    --work-flow-id 8a5659f0-16f5-46fb-9a0d-f35bb37fda92_P `
    --service-transaction-id 33f2315c-8da4-9bae-b68e-3178a5c7a620
```

**This is the only step that is ready to run today.** It opens no network
connection and changes nothing.

### Stage 2 — read-only status against the successful ICCID ⛔ BLOCKED

```powershell
# Steps 3-5 — BLOCKED until T-Mobile supplies the SubscriberInquiry contract.
# The harness will refuse; that refusal is correct, not a bug.
python ../scripts/tmobile_pit.py preview subscriber_inquiry --iccid <SUCCESS_ICCID>
```

### Stage 3 — designated lifecycle SIM ⛔ BLOCKED beyond activation

```powershell
# Nominate the lifecycle SIM (Render env, or api/.env locally):
#   TMOBILE_PIT_READONLY_ICCID_ALLOWLIST=<LIFECYCLE_ICCID>
#   TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST=<LIFECYCLE_ICCID>

# Step 4 — activate the lifecycle SIM. Preview first, ALWAYS:
python ../scripts/tmobile_pit.py preview activate_subscriber `
    --iccid <LIFECYCLE_ICCID> --market-zip 30346

# Then exactly one live activation, while T-Mobile is watching:
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "true"
python ../scripts/tmobile_pit.py run activate_subscriber `
    --iccid <LIFECYCLE_ICCID> --market-zip 30346 `
    --confirm-live --operator <you>
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "false"   # close the switch immediately

# ⏸ PAUSE — operator review. Then step 5: verify.
python -m scripts.tmobile_callback_inspect --iccid <LIFECYCLE_ICCID>
python ../scripts/tmobile_pit.py state --iccid <LIFECYCLE_ICCID>
```

```powershell
# Steps 6-9 — suspend / verify / resume / verify. ⛔ BLOCKED (no contract).
python ../scripts/tmobile_pit.py run suspend_subscriber --iccid <LIFECYCLE_ICCID> --confirm-live
# ⏸ PAUSE + verify callback and state before resuming.
python ../scripts/tmobile_pit.py run restore_subscriber --iccid <LIFECYCLE_ICCID> --confirm-live
# ⏸ PAUSE + verify.
```

### Stage 4 — deactivation ⛔ BLOCKED, and destructive

```powershell
# Steps 10-11. Requires ALL of:
#   - T-Mobile's deactivation contract (currently absent)
#   - TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST naming this ICCID
#   - --confirm-live --confirm-destructive --reason "<why>"
#   - --confirm-protected, if targeting the first-activation ICCID
# The MSISDN is expected to be released and the state is TERMINAL. No rollback.
python ../scripts/tmobile_pit.py run deactivate_subscriber `
    --iccid <DESTRUCTIVE_ICCID> --confirm-live --confirm-destructive `
    --reason "PIT certification step 10" --operator <you>
```

**Never target the first successfully activated ICCID here** unless it has been
separately nominated to the destructive allowlist. It is the only end-to-end
evidence the integration works.

### Stage 5 — certification report (step 12)

Collect every evidence bundle plus the state ledger
(`$TMOBILE_PIT_STATE_DIR/<iccid>.json`), fill in the §3 matrix, and record the
outcome in `PROJECT_STATE.md`.

---

## 5. Evidence retention

| Artifact | Where | Retention | Sensitivity |
|---|---|---|---|
| Evidence bundle `.json` / `.txt` | operator temp dir by default; use `--out-dir` for a durable path | Keep for the certification cycle, then delete | Sanitized — safe to send T-Mobile |
| State ledger | `$TMOBILE_PIT_STATE_DIR` (default: temp) | Same | Masked identifiers only |
| Committed fixture | `api/tests/fixtures/` | Permanent | Masked, no credentials |
| Restricted operator record | `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md` | Permanent | **Unmasked — internal only** |

Rules: never commit a raw bundle without re-checking it through the sanitizers;
never paste the restricted record into email; bundles are safe to send T-Mobile
**because** header values are captured by allowlist and bodies are hashed, not
recorded. Delete working bundles once the cycle closes — they are working
artifacts, not records.
