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
