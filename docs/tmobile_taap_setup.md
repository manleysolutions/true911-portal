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
- PoP includes: issuer (consumer key), URI hash, body hash, short expiry (~2 min)
- A **new** PoP token is generated for **every** request (different URI = different PoP)
- Access token is cached and reused until near expiry

## 5. PIT vs Production

| Setting | PIT | Production |
|---|---|---|
| TMOBILE_ENV | `pit` | `prod` |
| Base URL | `https://pit-apis.t-mobile.com` | `https://apis.t-mobile.com` |
| Token URL | `https://pit-oauth.t-mobile.com/oauth2/v2/tokens` | `https://oauth.t-mobile.com/oauth2/v2/tokens` |

PIT is the test environment. All development and integration testing happens there first.

## 6. Available API Methods

Once authenticated, these methods are available on `TMobileTAAPClient`:

| Method | API Path | Description |
|---|---|---|
| `subscriber_inquiry(msisdn)` | `/wholesale/subscriber/v2/inquiry` | Query subscriber details |
| `query_network(msisdn)` | `/wholesale/network/v1/query` | Network/device status |
| `query_usage(msisdn, start, end)` | `/wholesale/usage/v1/query` | Data/voice usage |
| `change_sim(msisdn, iccid)` | `/wholesale/subscriber/v2/changesim` | SIM swap |
| `activate_subscriber(msisdn, iccid)` | `/wholesale/subscriber/v2/activate` | Activate new line |
| `suspend_subscriber(msisdn)` | `/wholesale/subscriber/v2/suspend` | Suspend line |
| `restore_subscriber(msisdn)` | `/wholesale/subscriber/v2/restore` | Restore suspended line |
| `deactivate_subscriber(msisdn)` | `/wholesale/subscriber/v2/deactivate` | Cancel line |

## 7. Checklist Before First PIT Test

- [ ] RSA key pair generated (`openssl genrsa` + `openssl rsa -pubout`)
- [ ] Public key sent to T-Mobile and registered
- [ ] Consumer Key received from T-Mobile
- [ ] Consumer Secret received from T-Mobile
- [ ] Partner ID received
- [ ] Sender ID received
- [ ] Account ID received
- [ ] PIT environment access confirmed by T-Mobile
- [ ] Environment variables set in `.env`
- [ ] `python scripts/test_tmobile_taap.py --dry-run` passes
- [ ] `python scripts/test_tmobile_taap.py` returns access token
- [ ] First `--msisdn` call returns subscriber data
