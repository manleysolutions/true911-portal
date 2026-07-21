# T-Mobile PIT designated test-SIM policy

> Which SIMs a live PIT call may target, and at what risk tier. Enforced in
> `api/app/integrations/tmobile_lifecycle.py`; every rule below is pinned by a
> test in `api/tests/test_tmobile_pit_certification.py`.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution |
| **Created** | 2026-07-21 |
| **Related** | `TMOBILE_PIT_OPERATOR_RUNBOOK.md` · `TMOBILE_API_INVENTORY.md` |

---

## 1. Three nested tiers

| Env var | Authorizes | Class |
|---|---|---|
| `TMOBILE_PIT_READONLY_ICCID_ALLOWLIST` | queries that cannot change state | A |
| `TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST` | reversible state changes (activate, suspend, restore) | B |
| `TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST` | terminal changes (deactivate, SIM swap) | C |

**All three are empty by default, and empty means refuse everything** — not
"allow everything". A missing configuration can only ever make the harness more
restrictive.

## 2. Rules

1. **Comma-separated, 19–20 digits each.** Anything else raises at parse time. A malformed entry is a hard error, never a silent drop: a typo that silently shrinks an allowlist looks identical to a working one.
2. **No wildcards.** `*`, `all`, `any`, or any entry containing `*`/`?` is refused. There is no syntax for "every SIM".
3. **Strict subset hierarchy:** `destructive ⊆ lifecycle ⊆ read-only`. An ICCID you are not permitted to *read* must never be one you are permitted to *destroy*. Violations raise on the first command, not mid-sequence.
4. **Lower tiers never inherit upward.** Nominating a SIM for suspension does not nominate it for deletion.
5. **Masked in every log and error.** Refusal messages show `***…7538`, never the full value.
6. **No production ICCIDs, ever.** These lists are for PIT lab SIMs only.

## 3. The protected ICCID

`PROTECTED_ICCIDS` currently holds the **first successfully activated line**
(`***************7538`, activated 2026-07-21).

That line is the only end-to-end evidence the integration works. Deactivating or
swapping it would destroy the proof and cannot be undone — no documented
operation reactivates a deactivated line.

**It must never automatically become the destructive test ICCID.** To target it
destructively, both of these are required, deliberately and separately:

1. Its ICCID explicitly listed in `TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST` — inheriting from the lifecycle list is not enough.
2. `--confirm-protected` on the command line, on top of `--confirm-live`, `--confirm-destructive`, and `--reason`.

**Recommended: designate a different SIM for lifecycle and destructive testing.**
The certification plan assumes a separate lifecycle ICCID precisely so the
proven line is never at risk.

## 4. Configuration

Set on the Render service (or `api/.env` locally). Note the subset requirement —
a lifecycle SIM must also appear in the read-only list:

```bash
TMOBILE_PIT_READONLY_ICCID_ALLOWLIST=8901260963132697538,<LIFECYCLE_ICCID>
TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST=<LIFECYCLE_ICCID>
TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST=
```

Leave the destructive list **empty** until a deactivation test is actually
authorized, then populate it for that single run and clear it afterwards — the
same discipline as `TMOBILE_PIT_LIVE_CALLS_ENABLED`.

Verify what is loaded (masked, no network):

```powershell
cd api
python ../scripts/tmobile_pit.py allowlists
```

## 5. Adding a SIM

1. Confirm with T-Mobile that the ICCID is a PIT test SIM.
2. Record it in `TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md` with its purpose.
3. Add it to the read-only list first, and to a higher tier only when a specific authorized test needs it.
4. Run `allowlists` and confirm the masked tail matches.
5. Remove it from the destructive list as soon as that test completes.
