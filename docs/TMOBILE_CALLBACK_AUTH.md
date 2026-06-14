# T-Mobile Callback Authentication (C2)

> Status: implemented behind `FEATURE_TMOBILE_CALLBACK_AUTH` (default **off**);
> no behavior change until enabled. Closes BACKLOG C2.
> Last updated: 2026-06-14. Related: `docs/TMOBILE_CALLBACK_INGEST_MVP.md`,
> `docs/tmobile_taap_setup.md`, `docs/ARCHITECTURE.md` §6.

## 1. Problem

The T-Mobile PIT callback endpoints (`/tmobile/wholesale/callback/*`) were
unauthenticated at the app layer. With `FEATURE_TMOBILE_CALLBACK_INGEST=true`, a
POST is archived and promoted to `Device.last_network_event`, which the Health
Normalizer reads as carrier liveness. An attacker who could reach the URL could
therefore **inject a forged "fresh" network event and make an offline life-safety
line read CONNECTED** — masking a real outage. The only prior controls were the
Cloudflare WAF (off-platform, bypassable via the `*.onrender.com` origin) and a
*passive* IP-audit that only logged.

## 2. Approach

T-Mobile has **not** published a callback-signing spec, so authentication uses only
what we control:

1. **Shared secret** (`TMOBILE_CALLBACK_TOKEN`) that T-Mobile echoes back on every
   callback — as the `X-True911-Callback-Token` header (**preferred**) or a
   `?token=...` query param embedded in the `call-back-location` URL we register.
   Compared in constant time (`hmac.compare_digest`).
2. **Optional source-IP enforcement** (`TMOBILE_CALLBACK_IP_ENFORCE`) — requires
   `CF-Connecting-IP` to fall inside `TMOBILE_CALLBACK_SOURCE_IPS`, reusing the
   allowlist parser the passive audit already uses (no duplicated logic).

HMAC signature verification is **deferred** until T-Mobile publishes a spec; the
helper (`services/webhook_auth.py::verify_webhook_signature`) is ready when it does.

### The always-200 contract is preserved

The callback endpoints must always return HTTP 200 (the PIT validator and T-Mobile
retry logic must never see a 5xx/4xx). So authentication does **not** reject with
401 — instead it **gates the ingest step only**. On a failed check the request is
logged (`WARNING … DENIED … reason=<…>`) and dropped (no archive, no job enqueue),
and the handler still returns 200. Gating ingest fully addresses the threat because
ingest is the only step that mutates device state.

## 3. Behavior matrix

| `FEATURE_TMOBILE_CALLBACK_INGEST` | `FEATURE_TMOBILE_CALLBACK_AUTH` | Token presented | Result |
|---|---|---|---|
| false | any | any | No ingest (kill-switch). 200. *(unchanged)* |
| true | false | — | Ingest proceeds (pre-C2 behavior). 200. |
| true | true | valid | Ingest proceeds. 200. |
| true | true | missing/wrong | **No ingest.** Warning `reason=token_missing|token_mismatch`. 200. |
| true | true | token unset (misconfig) | **No ingest (fail closed).** Error `reason=token_not_configured`. 200 (never 500). |
| true | true (+IP enforce) | valid token, IP not allowlisted / no CF-IP | **No ingest.** Warning `reason=ip_not_allowlisted|ip_enforce_no_source_ip`. 200. |

GET reachability probes are unaffected (they mutate nothing) and need no token.

## 4. Secret handling

- The token is redacted from logs: headers matching `auth|token|secret|key|cookie|password`
  were already redacted, and C2 adds the **same redaction for query params**
  (`_safe_query`) so a `?token=` value never reaches the log stream.
- Prefer the **header** transport so the secret never appears in a URL (URLs can be
  captured by intermediary/edge logs). Use the query form only if T-Mobile cannot
  send a custom header on callbacks.
- For production the secret lives in Render (`sync:false`), never in git.

## 5. Operator setup (when enabling)

1. Generate a secret: `openssl rand -hex 32`.
2. Set it as a Render secret `TMOBILE_CALLBACK_TOKEN` on every service that serves
   the callback (the API; and the worker only if it ever serves HTTP — it does not
   today). **Watch the env-var-per-service pitfall** (project memory, PR #63).
3. Provide the secret to T-Mobile in whichever form they support:
   - **Header (preferred):** ask T-Mobile to send `X-True911-Callback-Token: <secret>`.
   - **URL token:** register `call-back-location` as
     `…/tmobile/wholesale/callback?token=<secret>` (set `TMOBILE_CALLBACK_LOCATION`).
4. Optionally set `TMOBILE_CALLBACK_IP_ENFORCE=true` and confirm
   `TMOBILE_CALLBACK_SOURCE_IPS` covers T-Mobile's PIT source ranges.
5. Flip `FEATURE_TMOBILE_CALLBACK_AUTH=true`.
6. Send a synthetic callback and confirm: a valid one archives; one with a wrong/no
   token logs `DENIED` and does **not** archive; both return 200.

> **Rollback:** set `FEATURE_TMOBILE_CALLBACK_AUTH=false`. Ingest reverts to the
> pre-C2 behavior immediately (token no longer required). No deploy needed.

## 6. Code map

| File | Role |
|---|---|
| `api/app/config.py` | `FEATURE_TMOBILE_CALLBACK_AUTH`, `TMOBILE_CALLBACK_TOKEN`, `TMOBILE_CALLBACK_IP_ENFORCE` (all default off) |
| `api/app/security/tmobile_callback_auth.py` | `check_callback_auth(request) -> CallbackAuthResult` (never raises) |
| `api/app/routers/tmobile_callback.py` | gates `_maybe_archive`; `_safe_query` redacts the token in logs |
| `api/tests/test_tmobile_callback_auth.py` | full behavior matrix (11 tests) |

## 7. Relationship to other items

- Complements the existing replay-age guard (`TMOBILE_CALLBACK_MAX_AGE_SECONDS`) and
  the passive IP audit (`FEATURE_TMOBILE_CALLBACK_IP_AUDIT`).
- Should be **on** before `FEATURE_TMOBILE_CALLBACK_INGEST` is trusted in any
  internet-exposed environment, and pairs with the C3 pre-production gate (key
  rotation) before any non-PIT exposure.
