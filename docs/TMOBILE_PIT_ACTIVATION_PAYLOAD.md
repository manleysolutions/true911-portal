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

### Attempted fix (2026-07-07, superseded)

Resource calls added `partner-id` / `sender-id` to the signed **ehts** set and to
the **PoP JWT claims**. This did **not** resolve GENS-0003 — the retest returned
`Empty/Invalid PartnerID/SenderID`. Reverted by the 2026-07-09 finding below.

## 2026-07-09 — Reference-token forensics: identity lives in the access token

T-Mobile supplied a known-good reference request (Bearer + `X-Authorization`).
Decoding both locally established three facts:

1. **The reference PoP signs only `Authorization`.** Its `ehts` is the single
   value `Authorization`, and its `edts` reproduces exactly as
   `base64url(SHA-256("Bearer " + access_token))` — confirmed by hashing the
   paired access token from that same request (the `iat` values match). The
   `"Bearer "` prefix, including its trailing space, is part of the digest input.
   Neither `uri`, `http-method`, `partner-id` nor `sender-id` is signed.

2. **The reference access token carries `senderId` and `channelId` claims.**
   These are minted by T-Mobile's authorization server from the consumer key's
   app registration and cannot be injected by anything we send. (Values withheld
   here — they are in the reference token T-Mobile supplied out of band.)

3. **Our access token has neither claim.** A token decoded from the same
   authorization server for a different `sub` shows no `senderId` and no
   `channelId`.

**Conclusion:** the wholesale gateway reads PartnerID / SenderID from the
**access token claims**, not from our HTTP headers or our PoP. No client-side
change can populate them; T-Mobile must attach the `senderId` / `channelId` (and
partner mapping) attributes to our consumer key's app registration.

### Fix (this change)

Resource calls now sign exactly what T-Mobile's reference signs:

- the signed **ehts** set — `Authorization` (only)
- the **PoP JWT claims** — no `partner-id` / `sender-id`

`partner-id` / `sender-id` remain as HTTP headers (T-Mobile asked for those
explicitly). The now-unused `extra_claims` argument to `generate_pop_token()` is
removed. **The token-endpoint PoP is unchanged** — it still signs exactly
`Content-Type;uri;http-method`, and that call demonstrably succeeds against PIT.
*(Superseded later the same day — see "Token request must carry sender-id"
below, which adds `sender-id` to the token-endpoint PoP.)*

This alignment removes a PoP-validation confound; it is **not** expected to clear
GENS-0003 on its own. That requires the T-Mobile-side registration change above.

Diagnostic logging on a `>= 400` response now also surfaces the response
`work-flow-id` and `service-transaction-id` (alongside method/path/status/
correlation_id/partner_transaction_id and a truncated, auth-redacted body) so a
future PIT failure is self-correlating in our logs — never logging any token,
`X-Authorization`, Basic auth, consumer secret, or private key.

### Retest instructions (for Render, T-Mobile watching logs)

1. **Confirm env** on the API service: `TMOBILE_ENV=pit`,
   `TMOBILE_PARTNER_ID=128`, `TMOBILE_SENDER_ID=128`, `TMOBILE_CALLBACK_LOCATION`
   set, private key present, `TMOBILE_PIT_LIVE_CALLS_ENABLED` still **false**.
2. **Dry-run** (sends nothing) and confirm `pop_signed_ehts` is exactly
   `["Authorization"]`:
   ```powershell
   cd api
   python ../scripts/tmobile_activation_dryrun.py --iccid 8901260963132697538 --market-zip 30346
   ```
3. **One live activation only**, while T-Mobile is watching logs: set
   `TMOBILE_PIT_LIVE_CALLS_ENABLED=true` for the single run, trigger exactly one
   `activate_subscriber`, then set it back to `false`.
4. **Capture** and send to Aman: UTC timestamp, ICCID, endpoint, `work-flow-id`,
   `service-transaction-id`, and the HTTP response.

## 2026-07-09 (later) — Token request must carry sender-id

T-Mobile Engineering (Aman), responding to the reference-token forensics above:

> Please pass the sender-id from your end.
> You can continue to use `https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens`
> as DNS and we handle the backend routing internally.

This closes the gap the forensics opened. The `senderId` / `channelId` claims are
minted by T-Mobile's **authorization server**, which needs the `sender-id` on the
**token request** in order to mint them — we were only ever sending it on the
resource call, where it is too late to influence the access token.

### Fix (this change)

`get_access_token()`, **only when `TMOBILE_SENDER_ID` is set**, sends
`sender-id: <TMOBILE_SENDER_ID>` as an HTTP header on the token request.

> **Correction (2026-07-16, confirmed by Aman in a live working session):**
> **`sender-id` is an unsigned OAuth request HTTP header.** An earlier revision of
> this change also appended `sender-id` to the token-request PoP **ehts** —
> that was wrong and T-Mobile's PoP validator rejects it. The token-request PoP
> ehts is exactly `Content-Type;uri;http-method`, with the `edts` digest input
> `"application/json" + <token-uri-path> + "POST"` — no sender-id. The header
> name is lowercase exactly: `sender-id`.

Unchanged: the **token URL** (T-Mobile routes on the header, internally);
`Authorization: Basic` stays a wire header and is **not** signed; the `cnf` body;
the resource call keeps `ehts="Authorization"` and its `partner-id` / `sender-id`
headers. When `TMOBILE_SENDER_ID` is unset or blank, the header is omitted.

Covered by `api/tests/test_tmobile_token_sender_id.py`.

### Verification after deploy — token-only, no activation

Run **before** any further live activation. This fetches a token and decodes it;
it sends no activation and needs `TMOBILE_PIT_LIVE_CALLS_ENABLED=false`.

```powershell
cd api
python ../scripts/get_tmobile_tokens.py --decode-claims
```

Confirm the Bearer claims now include **`senderId`** and **`channelId`**. If they
are still absent, stop — the T-Mobile-side app registration is still missing the
attributes, and another live activation will fail with GENS-0003 exactly as
before. Report the decoded claim names (never the values, and never the token) to
Aman.

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
