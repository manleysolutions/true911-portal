# T-Mobile Wholesale TAAP Integration Setup

## Overview

T-Mobile Wholesale APIs use TAAP (Token-Aware Authentication Protocol) with PoP (Proof of Possession) tokens. This is NOT standard OAuth2 — every request requires a fresh RSA-signed JWT alongside the Bearer token.

## Prerequisites from T-Mobile

Before PIT testing, you need these from your T-Mobile Wholesale account manager:

| Item | Description | Status |
|---|---|---|
| Consumer Key | OAuth2 client ID issued by T-Mobile | Waiting |
| Consumer Secret | OAuth2 client secret | Waiting |
| Partner ID | Your T-Mobile partner identifier | Waiting |
| Sender ID | Your T-Mobile sender identifier | Waiting |
| Account ID | Wholesale account number | Waiting |
| PIT API Access | Whitelisted for PIT environment | Waiting |
| Public Key Registered | Your RSA public key uploaded to T-Mobile portal | Pending |

## 1. Generate RSA Key Pair

T-Mobile requires a 2048-bit RSA key pair. You sign requests with the private key; T-Mobile validates using your public key.

```powershell
# Generate private key
openssl genrsa -out tmobile_private.pem 2048

# Extract public key (send this to T-Mobile)
openssl rsa -in tmobile_private.pem -pubout -out tmobile_public.pem
```

**Send `tmobile_public.pem` to your T-Mobile account manager for registration.**

Keep `tmobile_private.pem` secure — never commit it to git.

> 🔐 **Security guardrails (added 2026-06-13).**
> - `*.pem`, `*.key`, `*.crt`, and related key material are now git-ignored at the
>   repo root and in `api/.gitignore`. A real `tmobile_private.pem` you generate
>   locally will **not** be tracked by git.
> - A tracked **placeholder** lives at `api/tmobile_private.pem.example` showing the
>   expected format. It is NOT a usable key.
> - A private key was previously committed and removed; the key must be treated as
>   compromised and rotated. See `docs/TMOBILE_PRIVATE_KEY_REMEDIATION.md` for the
>   incident record, rotation steps, and the git-history decision.
> - **Production never uses a file.** Provide the PEM via the `TMOBILE_PRIVATE_KEY_PEM`
>   environment variable (Render secret), not `TMOBILE_PRIVATE_KEY_PATH`.

## 2. Configure Environment Variables

Add to your `.env` file (local) or Render environment variables (production):

```bash
# T-Mobile environment: pit or prod
TMOBILE_ENV=pit

# Credentials (from T-Mobile)
TMOBILE_CONSUMER_KEY=your-consumer-key
TMOBILE_CONSUMER_SECRET=your-consumer-secret
TMOBILE_PARTNER_ID=your-partner-id
TMOBILE_SENDER_ID=your-sender-id
TMOBILE_ACCOUNT_ID=your-account-id

# RSA private key — choose ONE method:

# Option A: File path (local development)
TMOBILE_PRIVATE_KEY_PATH=./tmobile_private.pem

# Option B: PEM content directly (Render/Docker/CI)
# Paste the full PEM content with \n for line breaks:
TMOBILE_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----\nMIIE....\n-----END PRIVATE KEY-----"
```

### Override URLs (usually not needed)

```bash
# These default based on TMOBILE_ENV but can be overridden:
TMOBILE_BASE_URL=https://pit-apis.t-mobile.com
TMOBILE_TOKEN_URL=https://pit-oauth.t-mobile.com/oauth2/v2/tokens
```

### Env-driven resource paths

The API resource paths are configurable so a T-Mobile gateway routing change
never requires a code edit. The PIT onboarding **gateway URL list uses
`/wholesale/v1/subscriber`** — NOT the older `/wholesale/subscriber/v2`.

```bash
# Default subscriber base path (all subscriber ops hang off this):
TMOBILE_SUBSCRIBER_BASE_PATH=/wholesale/v1/subscriber

# Activation route. Leave blank to derive {SUBSCRIBER_BASE_PATH}/activate.
# Set explicitly if T-Mobile assigns a route not derivable from the base.
TMOBILE_ACTIVATION_PATH=
```

| Variable | Default | Resolves to |
|---|---|---|
| `TMOBILE_SUBSCRIBER_BASE_PATH` | `/wholesale/v1/subscriber` | base for inquiry/activate/changesim/suspend/restore/deactivate |
| `TMOBILE_ACTIVATION_PATH` | *(blank)* | `{base}/activate`, or the literal override when set |

## 3. Test Locally

### Dry run (no T-Mobile credentials needed)

```powershell
cd api
python ../scripts/test_tmobile_taap.py --dry-run
```

This validates:
- RSA key generation/loading
- PoP token structure (JWT with RS256, correct claims)
- No network calls made

### Full test (requires credentials)

```powershell
cd api
python ../scripts/test_tmobile_taap.py
```

### Test with a live API call

```powershell
cd api
python ../scripts/test_tmobile_taap.py --msisdn 12125551234
```

### Dry-run activation (prints payload + headers, sends NOTHING)

Before any live activation, review the exact request with the dry-run command.
It builds the request `activate_subscriber` would POST and prints it — **no
OAuth token is fetched, no PoP is signed, no socket is opened**. The two
credential-bearing headers (`Authorization`, `X-Authorization`) are shown as
redacted placeholders, so output is safe to paste into a ticket. It needs no
credentials or RSA key, and there is **no flag that makes it send**.

```powershell
cd api
# Uses the PIT onboarding defaults below:
python ../scripts/tmobile_activation_dryrun.py

# Or override any field:
python ../scripts/tmobile_activation_dryrun.py `
  --iccid 8901260963132697538 --market-zip 30346 --product-id wps-00011586
```

PIT onboarding test values (from the onboarding attachments):

| Field | Value | Source |
|---|---|---|
| `marketZIP` | `30346` | onboarding packet |
| `ICCID` | `8901260963132697538` | one of the 50 PIT ICCIDs (`infatrac - 50 ICCIDs.txt`) |
| `productId` | `wps-00011586` | **PLACEHOLDER** — price-plan code, confirm with T-Mobile |

> ⚠️ **Product ID must still be confirmed by T-Mobile.** See
> [§ Product ID must be confirmed by T-Mobile](#product-id-must-be-confirmed-by-t-mobile).

> ⚠️ **`call-back-location` is REQUIRED.** The account ID is generated by
> activation and returned **only** to this callback, so `activate_subscriber`
> refuses to send without it. Set `TMOBILE_CALLBACK_LOCATION` (PIT:
> `https://pit-api.manleysolutions.com/tmobile/wholesale/callback`). The dry-run
> shows `call-back-location: <NOT SET …>` and a warning when it is unconfigured —
> verify it is present before any live activation.

The live activation path (`scripts/test_tmobile_taap.py --activate`) is **never
run automatically** — it requires explicit flags and valid credentials.

## 4. How TAAP/PoP Works

```
┌──────────┐                         ┌──────────────┐
│ True911  │                         │  T-Mobile    │
│ Backend  │                         │  API Gateway │
└────┬─────┘                         └──────┬───────┘
     │                                      │
     │  1. Generate PoP JWT (signed RS256)  │
     │  2. POST /oauth2/v2/tokens           │
     │     Basic Auth: key:secret           │
     │     X-Authorization: PoP <jwt>       │
     │─────────────────────────────────────>│
     │                                      │
     │  3. { access_token, expires_in }     │
     │<─────────────────────────────────────│
     │                                      │
     │  4. Generate new PoP JWT for API URL │
     │  5. POST /wholesale/subscriber/...   │
     │     Authorization: Bearer <token>    │
     │     X-Authorization: PoP <jwt>       │
     │     X-Partner-Id, X-Sender-Id, etc.  │
     │─────────────────────────────────────>│
     │                                      │
     │  6. { subscriber data }              │
     │<─────────────────────────────────────│
```

Key details:
- PoP token is a JWT signed with RS256 (your private key)
- A **new** PoP token is generated for **every** request; it is **single-use**
  with a **60-second** lifetime
- Access token is cached and reused until near expiry

### Authoritative PoP contract (supplied by T-Mobile Engineering)

This is T-Mobile's own PoP Token Builder contract. It supersedes every earlier
reconstruction in this repo (see "Superseded decisions" below).

JWT header — note `typ` is **`JWT`**, not `pop`:

```json
{"alg": "RS256", "typ": "JWT"}
```

JWT payload — exactly these six claims, and **no `iss`**:

```json
{"iat": 1700000000, "exp": 1700000060, "ehts": "...", "edts": "...",
 "jti": "<uuid>", "v": "1"}
```

`edts` rules:
- preserve the ehts key **insertion order**
- concatenate the corresponding values **directly, with no separator**
- hash the concatenated UTF-8 bytes **once** with SHA-256
- base64url-encode, strip `=` padding
- the body is **not** separately hashed first — its value is the **exact
  request-body string sent on the wire**

**Both** the OAuth PoP and the resource PoP sign the same key set, in this order:

```
Content-Type;Authorization;uri;http-method;body
```

| ehts key | OAuth PoP value | Resource PoP value |
|---|---|---|
| `Content-Type` | `application/json` | `application/json` |
| `Authorization` | the **Basic** header value | `Bearer <access_token>` |
| `uri` | token URL **path only** | resource URL **path only** (no query) |
| `http-method` | `POST` | uppercase verb |
| `body` | exact compact `{"cnf":"..."}` | exact compact JSON sent |

**Exact-byte rule:** the body is serialized **once** with
`json.dumps(..., separators=(',', ':'))` and that same string is both signed and
transmitted. A whitespace difference between the signed and sent body invalidates
the signature server-side.

### OAuth token request

Body — compact, `cnf` only, **no `grant_type` property**:

```json
{"cnf":"<single-line public key PEM>"}
```

Headers:

| Header | Value | Signed? |
|---|---|---|
| `Content-Type` | `application/json` | ✅ |
| `Authorization` | `Basic <base64(key:secret)>` | ✅ |
| `X-Authorization` | the OAuth PoP JWT | — |
| `grant-type` | `client_credentials` | ❌ unsigned |
| `sender-id` | `<TMOBILE_SENDER_ID>` (e.g. `128`) | ❌ unsigned |

**`sender-id` is an unsigned OAuth request HTTP header** (Aman, confirmed),
spelled lowercase exactly. It must **not** appear in the PoP ehts — signing it
makes T-Mobile's validator reject the request. It is what lets the authorization
server mint the `senderId` / `channelId` claims into the access token; Channel ID
needs no attribute of its own. The token **URL is unchanged** — T-Mobile routes on
the header internally. With `TMOBILE_SENDER_ID` unset, the header is omitted.

### Resource calls

`partner-id` / `sender-id` travel as **unsigned** HTTP headers — do not add them
to the resource PoP claims or ehts without new explicit instruction from T-Mobile.
If the OAuth response returns an `id_token`, it is cached paired with the access
token and replayed as the `X-Auth-Originator` header; when PIT returns none, the
header is omitted. The ID token is credential material and is never logged.

### Verify after deploy

```powershell
cd api
python ../scripts/get_tmobile_tokens.py --decode-claims
```

```
OAuth EHTS: Content-Type;Authorization;uri;http-method;body
sender-id present: True
sender-id value: '128'
sender-id unsigned: True
grant-type value: 'client_credentials'
body properties: ['cnf']
```

### Superseded decisions (PRs #165–#168)

These were reconstructed from partial evidence during GENS-0003 debugging and are
**wrong**. They are recorded so the reasoning is not repeated:

| Superseded claim | Authoritative contract |
|---|---|
| OAuth PoP signs `Content-Type;uri;http-method` | signs all five keys incl. `Authorization` + `body` |
| Resource PoP signs `Authorization` only | signs all five keys |
| Body is never part of ehts | body **is** signed, exact bytes |
| `typ="pop"` | `typ="JWT"` |
| 120-second lifetime | **60** seconds, single-use |
| PoP carries `iss` (consumer key) | no `iss`; adds `v="1"` |

Constant across all of them, and still true: **`sender-id` is unsigned.**

## 5. PIT vs Production

| Setting | PIT | Production |
|---|---|---|
| TMOBILE_ENV | `pit` | `prod` |
| Base URL | `https://pit-apis.t-mobile.com` | `https://apis.t-mobile.com` |
| Token URL | `https://pit-oauth.t-mobile.com/oauth2/v2/tokens` | `https://oauth.t-mobile.com/oauth2/v2/tokens` |

PIT is the test environment. All development and integration testing happens there first.

## 6. Available API Methods

Once authenticated, these methods are available on `TMobileTAAPClient`:

Subscriber-family paths are built from `TMOBILE_SUBSCRIBER_BASE_PATH`
(default `/wholesale/v1/subscriber`); the table shows the resolved default.

| Method | API Path (default) | Description |
|---|---|---|
| `subscriber_inquiry(msisdn)` | `/wholesale/v1/subscriber/inquiry` | Query subscriber details |
| `query_network(msisdn)` | `/wholesale/network/v1/query` | Network/device status |
| `query_usage(msisdn, start, end)` | `/wholesale/usage/v1/query` | Data/voice usage |
| `change_sim(msisdn, iccid)` | `/wholesale/v1/subscriber/changesim` | SIM swap |
| `activate_subscriber(iccid, ...)` | `/wholesale/v1/subscriber/activate` † | Activate new line |
| `suspend_subscriber(msisdn)` | `/wholesale/v1/subscriber/suspend` | Suspend line |
| `restore_subscriber(msisdn)` | `/wholesale/v1/subscriber/restore` | Restore suspended line |
| `deactivate_subscriber(msisdn)` | `/wholesale/v1/subscriber/deactivate` | Cancel line |

† or the literal `TMOBILE_ACTIVATION_PATH` when set.

## Product ID must be confirmed by T-Mobile

The activation request requires a `productId`. The onboarding packet lists a
catalog candidate:

- **Product/Plan Name:** Infatrac Internet Access Plan
- **Price Plan:** `wps - 00011586`
- **Optional static IP / APN SLO:** ISP1 / `iot.tmowholesale.static`

We use `wps-00011586` as a **placeholder** (`TMOBILE_PRODUCT_ID` /
`--product-id`). **This is the price-plan code, not a confirmed activation
`productId`.** Before running a live activation:

1. Ask your T-Mobile Wholesale account manager to confirm the exact `productId`
   string the **activation** API expects for the Infatrac Internet Access Plan
   (it may differ from the price-plan code, and formatting — `wps-00011586` vs
   `wps - 00011586` vs `00011586` — matters).
2. Confirm whether the static IP / APN SLO (`ISP1` / `iot.tmowholesale.static`)
   is selected via `productId`, a separate field, or account configuration.
3. Set the confirmed value in `TMOBILE_PRODUCT_ID` and re-run the dry-run to
   review the payload before sending.

Until T-Mobile confirms, treat any activation built with the placeholder as
**unvalidated** — the dry-run output flags this with a `productId is
UNCONFIRMED` note.

## 7. Checklist Before First PIT Test

- [ ] RSA key pair generated (`openssl genrsa` + `openssl rsa -pubout`)
- [ ] Public key sent to T-Mobile and registered
- [ ] Consumer Key received from T-Mobile
- [ ] Consumer Secret received from T-Mobile
- [ ] Partner ID received
- [ ] Sender ID received
- [ ] Account ID received
- [ ] PIT environment access confirmed by T-Mobile
- [ ] Environment variables set in `.env` (incl. `TMOBILE_SUBSCRIBER_BASE_PATH`)
- [ ] `python scripts/test_tmobile_taap.py --dry-run` passes
- [ ] `python scripts/tmobile_activation_dryrun.py` payload + paths reviewed
- [ ] **`productId` confirmed by T-Mobile** (placeholder `wps-00011586` replaced)
- [ ] `python scripts/test_tmobile_taap.py` returns access token
- [ ] First `--msisdn` call returns subscriber data
