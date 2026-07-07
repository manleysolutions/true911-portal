# T-Mobile Wholesale PIT — Activation Payload Mapping

Backend-only configuration for the T-Mobile Wholesale PIT (Partner Integration
Testing) `ActivateSubscriber` call. Sender/Partner ID **128**, API type **REST**.

## Required payload (T-Mobile-provided)

`activate_subscriber()` / the dry-run preview generate this **exact** nested body
from an ICCID:

```json
{
  "iccid": "<PIT_ICCID>",
  "marketZip": "30346",
  "language": "ENGL",
  "baseProduct": {
    "baseProductId": "Infatrac Internet Access Plan",
    "wps": "00011586",
    "product": [
      { "ProductID": "NOROAM", "isBaseProduct": false, "action": "ADD" }
    ]
  }
}
```

## 2026-07-07 — PIT retest failure: sender-id absent from PoP auth claims

T-Mobile Engineering (Aman) reviewed a **live** PIT activation and found the
**sender-id was not present in the auth claims** — the implementation sent
`partner-id` / `sender-id` only as HTTP headers, not inside the PoP token.

**Live PIT failure (as reported by T-Mobile):**

| Field | Value |
| --- | --- |
| UTC | `2026-07-07T14:59:50Z` |
| Endpoint | `POST /wholesale/v1/subscriber/activation` |
| ICCID | `8901260963132697538` |
| partner-id | `128` |
| sender-id | `128` |
| HTTP status | `400` |
| Code | `GENS-0003` |
| Message | `Invalid partnerID` |
| work-flow-id | `99a2b4f7-cdd3-499f-951b-915d98efe819_P` |
| service-transaction-id | `9b8f65ad-48ac-973f-9687-cd5ed75ad991` |

> T-Mobile note: *"I investigated the auth and don't see sender id was passed in
> the claims. Please check the solution to see if it's being sent or not. Also,
> the data/identifier sent has no logs."*

### Fix (this change)

For **resource calls** (`_request`), when `partner-id` / `sender-id` are
configured they are now included in **both**:

- the signed **ehts** set — `Authorization;uri;http-method;partner-id;sender-id`
- the **PoP JWT claims** — `partner-id` / `sender-id`

in addition to the existing HTTP headers (unchanged). `generate_pop_token()`
gained an optional `extra_claims` argument to carry these; omitting it reproduces
the previous token byte-for-byte. **The token-endpoint PoP is unchanged** — it
still signs exactly `Content-Type;uri;http-method` with no partner/sender claims.

Diagnostic logging on a `>= 400` response now also surfaces the response
`work-flow-id` and `service-transaction-id` (alongside method/path/status/
correlation_id/partner_transaction_id and a truncated, auth-redacted body) so a
future PIT failure is self-correlating in our logs — never logging any token,
`X-Authorization`, Basic auth, consumer secret, or private key.

### Retest instructions (for Render, T-Mobile watching logs)

1. **Confirm env** on the API service: `TMOBILE_ENV=pit`,
   `TMOBILE_PARTNER_ID=128`, `TMOBILE_SENDER_ID=128`, `TMOBILE_CALLBACK_LOCATION`
   set, private key present, `TMOBILE_PIT_LIVE_CALLS_ENABLED` still **false**.
2. **Dry-run** (sends nothing) and confirm `pop_signed_ehts` now lists
   `partner-id` / `sender-id`:
   ```powershell
   cd api
   python ../scripts/tmobile_activation_dryrun.py --iccid 8901260963132697538 --market-zip 30346
   ```
3. **One live activation only**, while T-Mobile is watching logs: set
   `TMOBILE_PIT_LIVE_CALLS_ENABLED=true` for the single run, trigger exactly one
   `activate_subscriber`, then set it back to `false`.
4. **Capture** and send to Aman: UTC timestamp, ICCID, endpoint, `work-flow-id`,
   `service-transaction-id`, and the HTTP response.

## Field mapping (env override → PIT-safe constant fallback)

| Payload field                | Source (in order)                                              |
| ---------------------------- | ------------------------------------------------------------- |
| `iccid`                      | per-call argument (required)                                   |
| `marketZip`                  | `market_zip` arg / `TMOBILE_MARKET_ZIP` (PIT: `30346`/`30338`) |
| `language`                   | `TMOBILE_LANGUAGE` / `PIT_LANGUAGE` (`ENGL`)                   |
| `baseProduct.baseProductId`  | `TMOBILE_BASE_PRODUCT_ID` / `PIT_BASE_PRODUCT_ID`              |
| `baseProduct.wps`            | `TMOBILE_WPS` / `PIT_WPS` (`00011586`)                         |
| `baseProduct.product[]`      | `PIT_DEFAULT_PRODUCTS` (`NOROAM` / `ADD`)                      |

PIT-safe constants live in `api/app/integrations/tmobile_taap.py`; every one is
overridable via the matching `TMOBILE_*` env var so a value change never needs a
code edit. No secrets are baked in — consumer key/secret, private key, and base
URL come **only** from env (`TMOBILE_CONSUMER_KEY`, `TMOBILE_CONSUMER_SECRET`,
`TMOBILE_PRIVATE_KEY_PATH`/`_PEM`, `TMOBILE_BASE_URL`).

## Safety: dry-run by default, live behind a flag

- **Dry run (no network):** `TMobileTAAPClient.build_activation_preview(iccid=...)`
  or `python scripts/tmobile_activation_dryrun.py` — returns the generated payload
  + headers (secrets redacted) and sends nothing. Never consults the live flag.
- **Live PIT call:** `activate_subscriber()` fails closed unless
  **`TMOBILE_PIT_LIVE_CALLS_ENABLED=true`** (raises `RuntimeError`, sends nothing
  otherwise) and still requires a `call-back-location` (the generated account ID
  returns only via that callback).

Nothing here triggers a real activation automatically.

## Tests

`api/tests/test_tmobile_activation.py` —
`TestActivationPayloadMatchesTMobileSample` pins the generated body (builder, PIT
constants, and the actual wire bytes) to the sample above;
`test_disabled_by_default_refuses_to_send` proves the live flag gates sending.

## Lifecycle gaps closed (follow-up)

Two gaps were found in the activation → callback → account-ID lifecycle and
fixed in a backend-only follow-up. The generated account ID is now persisted to
the correct ICCID regardless of how the callback matched, and QuerySubscriber
uses it automatically.

### Gap #1 — QuerySubscriber uses the per-ICCID account ID

`app/services/tmobile_subscriber.py` →
`query_subscriber_by_iccid(db, iccid)` resolves the **stored per-ICCID** account
ID (`sims.meta.tmobile_account_id`, falling back to the `tmobile_activation`
record) and the MSISDN, then calls
`TMobileTAAPClient.subscriber_inquiry(msisdn, account_id=…)`. The low-level
`subscriber_inquiry` now accepts an explicit `account_id` (falls back to the
global `TMOBILE_ACCOUNT_ID` env). The live call is gated behind
`TMOBILE_PIT_LIVE_CALLS_ENABLED`.

### Gap #2 — account ID captured even on the Device-fallback path

`app/services/tmobile_callback_processor.py` →
`capture_activation_via_device(db, device, signal)` runs when an
activation/provisioning callback carries a generated account ID but matched only
a Device (no Sim row). It **find-or-creates a single Sim keyed on the
globally-unique ICCID** so the account ID always lands on `sims.meta`:

- existing Sim for that ICCID → reused (meta updated, device linked if unset) —
  **never duplicated**;
- no Sim → one minimal Sim created (`carrier=tmobile`,
  `data_source=device_discovered`, linked to the device);
- no usable ICCID, or an **ambiguous** device match → capture skipped, **no Sim
  written**.

`jobs.result.tmobile_account_capture` (`created_sim` / `updated_sim` /
`skipped:no_iccid` / `null`) surfaces the outcome for operators.

### Tests

`api/tests/test_tmobile_subscriber_resolver.py` (Gap #1) and
`api/tests/test_tmobile_account_capture.py` (Gap #2 — create, no-duplicate,
ambiguous-safe, end-to-end promote+capture).
