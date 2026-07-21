# T-Mobile PIT operator runbook

> The single entry point for every T-Mobile PIT API call is
> `scripts/tmobile_pit.py`. If you are about to run a different script or a
> `curl`, stop — the gates live in the harness, not in the client.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-07-21 |
| **Related** | `TMOBILE_API_INVENTORY.md` · `TMOBILE_PIT_CERTIFICATION_PLAN.md` · `TMOBILE_PIT_TEST_SIM_POLICY.md` |

---

## 1. The rule

**Preview everything. Send nothing you have not previewed.** `preview` opens no
network connection and runs the same gates a live send would, so it is a real
rehearsal rather than a formality.

---

## 2. Commands

### Informational — always safe, never touch the network

```powershell
cd api
python ../scripts/tmobile_pit.py operations              # what is sendable, and what is blocked
python ../scripts/tmobile_pit.py show suspend_subscriber # full record + what T-Mobile must answer
python ../scripts/tmobile_pit.py allowlists              # configured test SIMs (masked)
python ../scripts/tmobile_pit.py state --iccid <ICCID>   # last known lifecycle state
```

### Preview — rehearse without sending

```powershell
python ../scripts/tmobile_pit.py preview activate_subscriber `
    --iccid <ICCID> --market-zip 30346
```

### Run — exactly one live request

```powershell
# Reversible (class B):
python ../scripts/tmobile_pit.py run activate_subscriber `
    --iccid <ICCID> --market-zip 30346 --confirm-live --operator <you>

# Destructive (class C) — every flag is required:
python ../scripts/tmobile_pit.py run deactivate_subscriber `
    --iccid <ICCID> --confirm-live --confirm-destructive `
    --reason "PIT certification step 10" --operator <you>
```

### Read-only diagnostics

```powershell
# Callbacks for a request — pure SELECT, no network call:
python -m scripts.tmobile_callback_inspect --iccid <ICCID> `
    --partner-transaction-id <ptx> --work-flow-id <wf>

# Subscriber status against the live gateway (currently BLOCKED — no contract):
python ../scripts/tmobile_subscriber_status.py `
    --msisdn <MSISDN> --account-id <ACCOUNT_ID> --confirm-read-only
```

---

## 3. The gates, in order

A live send passes all eight. Each is independent; any one refuses on its own.

| # | Gate | Refusal looks like |
|---|---|---|
| 1 | **Provenance** — T-Mobile must have supplied the contract | `'<op>' is BLOCKED` + the questions T-Mobile must answer |
| 2 | **Allowlist tier** — ICCID nominated at this risk tier | `is not on TMOBILE_PIT_*_ALLOWLIST` |
| 3 | **State machine** — transition legal, nothing pending | `not a valid transition` / `probable DUPLICATE` |
| 4 | `--confirm-live` for any state change | `requires --confirm-live` |
| 5 | `--confirm-destructive` + `--reason` for class C | `requires --confirm-destructive` |
| 6 | `--confirm-protected` for the first-activation ICCID | `only end-to-end evidence the integration works` |
| 7 | `TMOBILE_PIT_LIVE_CALLS_ENABLED=true` | `is not true. Nothing was sent.` |
| 8 | Client-side guards (e.g. `call-back-location` required) | `requires a call-back-location` |

Gates 1–3 run in preview too. Every refusal message ends with *nothing was sent*
— if you do not see that phrase, read the output again before assuming nothing
happened.

---

## 4. Standard live-call procedure

1. **Preview.** Read the preflight block: operation, class, target ICCID (masked), known state, and each gate's verdict.
2. **Confirm the ICCID.** The preview masks it — check the last four against `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md` or your SIM record.
3. **Open the switch:** `$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "true"`.
4. **Run exactly one command.** Never re-run on a timeout or an unclear result — investigate first. A retry is a second activation.
5. **Close the switch immediately:** `$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "false"`. This is what makes an accidental second invocation harmless.
6. **Capture** the evidence bundle paths the tool prints.
7. **Verify** the callback before any further state change: `python -m scripts.tmobile_callback_inspect --iccid <ICCID>`.
8. **Pause for review.** Do not chain state-changing operations.

### If a request times out or the outcome is unclear

**Do not retry.** The request may have succeeded at T-Mobile. Instead:

1. Check the evidence bundle — it is written even on failure, with every correlation id.
2. Run the callback inspector.
3. Send T-Mobile the `partner-transaction-id` and `work-flow-id` and ask what they saw.
4. Only after establishing the real state, decide deliberately.

The harness records the line as `failed` on error, which does **not** unlock a
duplicate — a pending or unclear state blocks the next state-changing request by
design.

---

## 5. Evidence handling

- Bundles are **sanitized by allowlist**: unknown header values are redacted by default, credential headers are presence-only, and bodies are hashed rather than recorded. The `.txt` is designed to be pasted into an email to T-Mobile.
- **Never** send `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md` outside the team — it holds unmasked identifiers.
- Retention and sensitivity: `TMOBILE_PIT_CERTIFICATION_PLAN.md` §5.

---

## 6. Troubleshooting refusals

| Message | Meaning | Do this |
|---|---|---|
| `is BLOCKED` | No T-Mobile contract for this operation | Get the answers from `show <op>`; do **not** work around it |
| `ALLOWLIST … is empty` | No SIM nominated at that tier | Add the designated test ICCID — see the SIM policy |
| `must be a subset of` | Tier hierarchy violated | An ICCID you cannot read must not be one you can destroy |
| `probable DUPLICATE` | A previous request is unreconciled | Verify the callback and observed state first |
| `terminal state` | Line is deactivated | Nothing can be done to it; use a different SIM |
| `TMOBILE_PIT_LIVE_CALLS_ENABLED is not true` | Switch closed | Open it only for the single intended call |

**A refusal is the harness working.** The correct response is to satisfy the
gate or get the missing documentation — never to bypass it. Every past shortcut
in this integration (PRs #165, #167, #168) was plausible, and every one was
wrong and cost a live PIT cycle.
