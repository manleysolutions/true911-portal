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

> **Update 2026-07-21.** Requests are now validated as typed models before OAuth,
> so a malformed command fails locally with identifiers masked. The refusal you
> see may now come from request validation, the lifecycle precondition policy, or
> the operation registry — all three fail closed and all say *nothing was sent*.

> **Update 2026-09-30.** At T-Mobile Engineering's request the Network Profile
> read was re-tested once and returned HTTP 200 / `SUCCESS`; `query_network` is
> now `PIT_TESTED` and still needs a one-shot grant per run. Only
> `subscriber-inquiry` and `query-network` may reconcile the ledger (D-026).
> Record: `TMOBILE_PIT_CERTIFICATION_20260930.md`.

> **Update 2026-09-01.** The Network Profile read was attempted once and the
> carrier returned HTTP 500 / `GENS-0005`; it is **not** certified and
> `query_network` stays `MOCK_CERTIFIED`. Two things follow for operators:
> §2c on nominating the PIT ICCID without depending on a shell-local variable,
> and §4's new "if the carrier answers with an error" procedure. Record:
> `TMOBILE_PIT_CERTIFICATION_20260901.md`.

> **Update 2026-08-28.** Two things changed after the first activation +
> readback run (`TMOBILE_PIT_CERTIFICATION_20260828.md`).
>
> 1. **`state --iccid` now prints an evidence ledger, not one boolean.** A
>    synchronous carrier acceptance leaves the line `activation_requested` on
>    class-**B** evidence and settles nothing; running `subscriber-inquiry`
>    against the same ICCID is what moves it to `active` on class-**C**
>    evidence. **You do not need a callback for this.** If `carrier-attested`
>    reads `False`, run the inquiry before acting on the state.
> 2. **The callback inspector is invoked by path, not as a module.** `python -m
>    scripts.tmobile_callback_inspect` fails from `api/` — there is a second,
>    unrelated `api/scripts` package that wins the import there. Every command
>    below uses the path form.

## 1. The rules

**Preview everything. Send nothing you have not previewed.** `preview` opens no
network connection and runs the same gates a live send would, so it is a real
rehearsal rather than a formality.

**Certification maturity is not send authorization.** `operations` prints them
as two separate columns because they are two separate questions:

| Column | Question |
|---|---|
| MATURITY | how far has this been certified? |
| GENERAL SEND | may it be transmitted with no explicit grant? |
| 1-SHOT GRANT | may a controlled single-run authorization be issued? |

`pit_tested` means **live PIT certified** — successfully exercised against the
carrier PIT gateway with evidence retained. It does **not** mean production
authorized, and it does **not** permit an unauthorized send. `subscriber_inquiry`
is live PIT certified and is exactly as un-sendable as it was before. Advancing
an operation's maturity never changes what you may send.

---

## 2. Commands

### Informational — always safe, never touch the network

```powershell
cd api
python ../scripts/tmobile_pit.py operations              # maturity vs authorization, side by side
python ../scripts/tmobile_pit.py show suspend_subscriber # full record + what T-Mobile must answer
python ../scripts/tmobile_pit.py allowlists              # configured test SIMs (masked)
python ../scripts/tmobile_pit.py state --iccid <ICCID>   # state AND the evidence for it
```

### Reconcile — settle the ledger from a read that already happened

```powershell
python ../scripts/tmobile_pit.py reconcile --iccid <ICCID> `
    --evidence <path-to-evidence-bundle>.json --operator <you>
```

Opens no socket. Use it when the ledger and the carrier evidence were recorded
separately — for example when a read was captured by a build of this harness
that had no way to reconcile it. **Re-running a live inquiry purely to rebuild a
local file spends a real carrier request to learn something already observed and
written down; this is how you avoid that.**

It is a replay, not an attestation: it parses the carrier's own recorded
response out of the bundle and runs it through the same reconciler a live run
uses. You cannot type a status in. It refuses:

- an activation bundle (that is class-B evidence and settles nothing);
- a bundle recording a request that did not succeed;
- a bundle about a different subscriber;
- a truncated or unparseable response body;
- a bundle with no exchange matching the operation's exact wire path.

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
python ../scripts/tmobile_callback_inspect.py --iccid <ICCID> `
    --partner-transaction-id <ptx> --work-flow-id <wf>

# Subscriber status against the live gateway (currently BLOCKED — no contract):
python ../scripts/tmobile_subscriber_status.py `
    --msisdn <MSISDN> --account-id <ACCOUNT_ID> --confirm-read-only
```

---


## 2a. Read-only subscriber inquiry (PIT certification)

**Preview is the default.** The command below opens no connection:

```powershell
cd api
python ../scripts/tmobile_pit.py subscriber-inquiry --iccid <PIT_ICCID>
```

It prints the environment, the explicit endpoint and method, the masked
selector, the request body with identifiers masked, the header names with values
omitted, the response model, the readiness state, and the send policy.

To send **exactly one** request, every gate below must pass:

```powershell
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "true"
python ../scripts/tmobile_pit.py subscriber-inquiry `
    --iccid <PIT_ICCID> --execute --confirm-live `
    --confirm-subscriber-approved --operator <you>
$env:TMOBILE_PIT_LIVE_CALLS_ENABLED = "false"
```

Gates, in order: exactly one selector supplied · typed request validates ·
`--confirm-live` · `--confirm-subscriber-approved` · `--operator` ·
read-only ICCID allowlist · live-call switch · credentials configured ·
single-run authorization granted.

The authorization covers **one operation, one subscriber, one request**, is
PIT-only, expires after 15 minutes, and is consumed the moment the client
boundary spends it. A second invocation finds nothing and is refused. It cannot
be issued for any lifecycle mutation — the allowlist is read-only operations by
construction.

## 2b. The other three read-only operations

Same shape as §2a, one grant each, preview by default:

```powershell
python ../scripts/tmobile_pit.py query-network            --iccid <PIT_ICCID>
python ../scripts/tmobile_pit.py query-usage              --iccid <PIT_ICCID>
python ../scripts/tmobile_pit.py query-transaction-status --transaction-id <TXN>
```

Add `--execute --confirm-live --confirm-subscriber-approved --operator <you>` to
send exactly one. **Each operation needs its own authorization** — an inquiry
grant does not authorize a network query, and a transaction-status grant binds
to one exact transaction id. Run them in the order above and reconcile each
before advancing.

## 2c. Nominating the designated PIT ICCID without a shell-session trap

**The selector stays explicit.** There is no default subscriber, no "latest",
and no implicit selection — that is not up for negotiation and none of this
changes it. What changed is *where the operator gets the value from*.

On 2026-09-01 a preview using `$PIT_ICCID` succeeded, and two later copied
command blocks reached the explicit-subscriber gate with **no nominated
selector** because that shell-local value was no longer set in their context:

```
A subscriber must be explicitly nominated: pass exactly one of
--iccid / --msisdn / --imsi. There is no default and no 'latest' subscriber.
```

Nothing was sent — the gate did its job. But a variable that has to survive
across copied blocks is a session-state dependency, and the environment already
holds the authoritative answer. Derive it inline instead, from the same
allowlist the gate checks against:

```powershell
cd api
# Fails loudly if the allowlist is empty or holds more than one ICCID.
$PitIccids = @($env:TMOBILE_PIT_READONLY_ICCID_ALLOWLIST -split ',' |
    ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique)
if ($PitIccids.Count -ne 1) {
    throw "Expected exactly one read-only PIT ICCID; got $($PitIccids.Count). Nominate it by hand."
}
$PitIccid = $PitIccids[0]
python ../scripts/tmobile_pit.py query-network --iccid $PitIccid
```

Bash equivalent:

```bash
cd api
PIT_ICCID="$(printf '%s' "$TMOBILE_PIT_READONLY_ICCID_ALLOWLIST" | tr -d '[:space:]')"
case "$PIT_ICCID" in ""|*,*) echo "Nominate the ICCID by hand." >&2; exit 1;; esac
python ../scripts/tmobile_pit.py query-network --iccid "$PIT_ICCID"
```

Why this is safe rather than a loosening:

- the ICCID is still passed on the command line as an explicit selector;
- it is still checked against the read-only allowlist by the harness;
- it still appears **masked in the preflight block** the operator reads before
  confirming — check the last four before opening the live switch;
- the derivation refuses an empty or multi-valued allowlist instead of
  choosing, so it can never silently pick a subscriber.

Do the same derivation in the preview and in the live command, in the **same**
shell invocation, so the value the operator rehearsed is the value that gets
sent.

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
7. **Verify** the carrier's own view before any further state change:
   - `python ../scripts/tmobile_pit.py subscriber-inquiry --iccid <ICCID>` —
     this is what settles the ledger;
   - `python ../scripts/tmobile_callback_inspect.py --iccid <ICCID>` — callback
     arrival, authenticity and correlation. A `NO CALLBACK FOUND` result is not
     proof none was sent; it is the absence of a persisted one.
8. **Pause for review.** Do not chain state-changing operations.

### If the carrier answers with an error (a read included)

A structured carrier error is a *classified* outcome, not an unclear one — but
it is still a full stop.

1. **Do not retry.** The same request against unchanged state produces the same
   uninterpretable result.
2. **Do not advance to the next operation.** The harness prints
   `STOP — this operation did not succeed…` for exactly this reason; running the
   next step turns one unexplained result into two.
3. **Capture the evidence bundle** — it is written on failure too, with the
   carrier's own trace identifiers, and the one-shot authorization has already
   been consumed and cleared.
4. **Classify how far the evidence actually reaches.** A resource error after a
   successful OAuth is a carrier/resource failure, *not* an authentication
   failure — and a generic vendor code (e.g. an "unexpected exception") does not
   establish that the fault is the carrier's. Say what is known and no more.
5. **Ask T-Mobile**, quoting the correlation, work-flow, service-transaction and
   partner-transaction ids from the private evidence store. Add the question to
   `TMOBILE_CARRIER_QUESTIONS_OPEN.md`.
6. **Do not promote the operation's maturity.** A failed live attempt is not PIT
   certification; record the attempt in the operation's `test_status`, leave
   `readiness` alone.

Worked example: `TMOBILE_PIT_CERTIFICATION_20260901.md`.

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
