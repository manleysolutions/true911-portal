# 🔒 RESTRICTED — T-Mobile PIT activated subscriber (operator record)

> **Scope: internal operators only.** This is the single place in the repository
> that carries the **unmasked** identifiers for the line activated during PIT
> testing on 2026-07-21. Every other document, fixture, test, and PR body masks
> them to the last four characters.
>
> **Do not paste this page into email, tickets, screenshots, or customer-facing
> material.** When corresponding with T-Mobile, send the sanitized evidence
> bundle produced by `scripts/tmobile_pit_evidence.py` instead.
>
> These are **PIT (Partner Integration Testing) lab identifiers**, not a
> production customer line. They are recorded because the account ID is required
> to make any subsequent read-only `SubscriberInquiry` call, and it is returned
> exactly once.

| Metadata | |
|---|---|
| **Authority Level** | 3 — Execution (operator reference) |
| **Environment** | T-Mobile Wholesale **PIT** |
| **Created** | 2026-07-21 |
| **Related** | `TMOBILE_PIT_ACTIVATION_PAYLOAD.md`, `TMOBILE_PRODUCTION_READINESS.md` |

---

## 1. The activated subscriber

| Field | Value |
|---|---|
| Activated (UTC) | `2026-07-21T03:18:33.694749Z` |
| Deployment commit | `1766f51161908d163ba2d3c4a96d1f774782cbfd` |
| Endpoint | `POST /wholesale/v1/subscriber/activation` |
| HTTP status | `201` |
| Body status | `SUCCESS` |
| Result code | `100` (`SUCCESS`) |
| **ICCID** | `8901260963132697538` |
| **Assigned MSISDN** | `4102406851` |
| **Generated account ID** | `10410763214` |
| Market ZIP | `30346` |
| Base product | `Infatrac Internet Access Plan` / WPS `00011586` |

### Trace identifiers (safe to share with T-Mobile)

| Field | Value |
|---|---|
| `partner-transaction-id` | `true911-pit-d1475fec-981b-40a7-a27c-d867aab8e7f9` |
| `X-Correlation-Id` | `ee790876-7b0a-472e-823e-4b30fbefa88d` |
| `work-flow-id` | `8a5659f0-16f5-46fb-9a0d-f35bb37fda92_P` |
| `service-transaction-id` | `33f2315c-8da4-9bae-b68e-3178a5c7a620` |
| OAuth `service-transaction-id` | `62f5fd11-7756-953b-b032-e71a14ac118d` |

The sanitized, masked version of this record is committed at
`api/tests/fixtures/tmobile_pit_success_20260721T031833Z.json` and pinned by
`api/tests/test_tmobile_pit_success_closeout.py`.

---

## 2. ⛔ Do not re-activate or modify this line

This subscriber is the **only** evidence that the integration works end to end.
Until the closeout items in `TMOBILE_PRODUCTION_READINESS.md` are complete:

- **Do not** run `tmobile_pit_evidence.py --activate` against this ICCID again.
  A second activation on an already-active ICCID is an untested path and would
  destroy the clean single-activation record.
- **Do not** call `suspend_subscriber`, `restore_subscriber`,
  `deactivate_subscriber`, or `change_sim` for this MSISDN.
- Keep `TMOBILE_PIT_LIVE_CALLS_ENABLED=false` in the deployed environment
  between deliberate, supervised runs.

Only the read-only paths in §3 are approved for this line.

---

## 3. Approved read-only operations

Both scripts below make **no** change to subscriber state.

### Callback inspection — no network call at all

Pure SELECT against our own database; sends nothing to T-Mobile:

```powershell
python -m scripts.tmobile_callback_inspect `
    --iccid 8901260963132697538 `
    --partner-transaction-id true911-pit-d1475fec-981b-40a7-a27c-d867aab8e7f9 `
    --work-flow-id 8a5659f0-16f5-46fb-9a0d-f35bb37fda92_P `
    --service-transaction-id 33f2315c-8da4-9bae-b68e-3178a5c7a620
```

### Subscriber status — reaches the live PIT gateway, read-only

`SubscriberInquiry` + `NetworkQuery` only. Writes a sanitized evidence bundle:

```powershell
cd api
python ../scripts/tmobile_subscriber_status.py `
    --msisdn 4102406851 --account-id 10410763214 --confirm-read-only
```

`--confirm-read-only` is required; without it nothing is sent. Note that both
operations attach `call-back-location` when `TMOBILE_CALLBACK_LOCATION` is set,
so a response may also arrive asynchronously at the callback endpoint.

**As of this document's creation, neither script has been run against this
line.** Callback state and subscriber status are therefore **UNVERIFIED** — see
`TMOBILE_PRODUCTION_READINESS.md` §2.
