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
