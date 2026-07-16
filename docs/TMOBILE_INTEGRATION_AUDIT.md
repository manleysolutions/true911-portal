# T-Mobile Integration Audit

**Status:** Audit only — no code changes, no PR. Awaiting plan approval before implementation.
**Branch:** `main` (commit `2bb9296`)
**Date:** 2026-05-25
**Companion docs:** `docs/HEALTH_STATUS_AUDIT.md` (root-cause architecture audit), `docs/HEALTH_NORMALIZER_MVP.md` (Phase 1 health normalizer — the system T-Mobile would feed), `docs/tmobile_taap_setup.md` (existing TAAP setup notes).

---

## Bottom line

T-Mobile is in an asymmetric state: **outbound TAAP signing is fully implemented and production-ready, but no part of the codebase ever calls it. Inbound callbacks are wired to seven URLs that log and discard the payload — no DB write, no SIM/device lookup, no carrier liveness signal, no health-normalizer evidence.** From the Health Normalizer's point of view, T-Mobile does not exist. Verizon's pattern of writing `Device.last_network_event` is the template; T-Mobile needs to mirror it before it can become a real evidence source.

There is also one **medium-severity secret-leak** (`tmobile_taap.py:304, 310-311` `print` the Base64-encoded Authorization header unconditionally) and zero **inbound signature verification**, both of which should be addressed before flipping any production flag.

---

## 1. Current architecture

### File inventory (16 files reference T-Mobile / TAAP / Wholesale)

| File | Role | State |
|---|---|---|
| `api/app/routers/tmobile_callback.py` | 7 PIT callback endpoints (6 event-specific + 1 legacy generic, both GET+POST = 14 routes) | **Stub — logging only, zero DB writes** |
| `api/app/routers/webhooks.py:109-111` | Generic `POST /api/webhooks/tmobile` ingress (archives → enqueues `webhook.tmobile` job) | Archives raw payload; **handler is a stub** |
| `api/app/integrations/tmobile_taap.py` | Outbound TAAP client — OAuth2 + Apigee PoP + 9 wholesale API methods | **Fully implemented; NEVER called from anywhere** |
| `api/app/integrations/tmobile.py` | Legacy IoT (non-Wholesale) SIM client, API-key auth | Disabled — `is_configured` hard-coded `False` |
| `api/app/services/carrier_provider/tmobile.py` | Carrier-provider interface impl | Stub — `is_configured` returns `False`, all methods raise |
| `api/app/services/carrier_adapter.py:78-90` | `TMobileAdapter` — normalizes carrier payload → `CarrierTelemetry` | Class exists; **never invoked** |
| `api/app/services/sim_service.py:148-165` | `handle_webhook()` — the `webhook.tmobile` worker handler | Marks payload `processed=True`, **discards data** |
| `api/worker.py:26` | Worker registry — `webhook.tmobile` → `sim_service:handle_webhook` | Wired to the stub |
| `api/app/config.py:116-126` | 10 `TMOBILE_*` env-var declarations (env, base/token URLs, consumer key/secret, partner/sender/account IDs, private key path/PEM) | All defaults are empty string |
| `api/app/models/sim.py:27,59` | `Sim.carrier` accepts `"tmobile"`; `inferred_location_source` accepts `"tmobile_api"` | Generic — no T-Mobile-specific column |
| `api/app/models/device.py:46-51` | `Device.carrier`, `network_status`, `last_network_event` are generic | Same — fields exist, just not written by T-Mobile path |
| `api/app/models/integration_payload.py:17` | `IntegrationPayload.source` accepts `"tmobile"` | Works — generic webhook archive |
| `api/tests/test_tmobile_callback_events.py` (131 lines, 8 tests) | All 200-response shape tests + log redaction | Tests current stub behavior |
| `api/tests/test_tmobile_taap.py` (354 lines, 15 tests) | PoP signing, canonicalization, OAuth2 flow, header structure | Comprehensive — all mocked, no real API calls |
| `render.yaml` | Production deployment config | **Zero `TMOBILE_*` env vars set** |
| `docs/tmobile_taap_setup.md` | Existing operator notes | (predates this audit) |

### Routes deployed

**Mounted at `/tmobile/wholesale` prefix** (`api/app/main.py:189`):

| Route | Method | Handler (`tmobile_callback.py:`) | What it does | Returns |
|---|---|---|---|---|
| `/callback` | POST | `tmobile_wholesale_callback` (95) | Logs body, no parse | `{"success":true,"message":"callback received"}` |
| `/callback` | GET | `tmobile_wholesale_callback_probe` (115) | Logs only | `{"success":true}` |
| `/callback/provisioning` | GET+POST | `cb_provisioning_get/post` (143/149) | Logs + ack | `{"status":"ok","provider":"t-mobile","event":"provisioning",...}` |
| `/callback/usage` | GET+POST | `cb_usage_get/post` (155/161) | Logs + ack | same shape, event=`usage` |
| `/callback/device-change` | GET+POST | `cb_device_change_get/post` (167/173) | Logs + ack | event=`device_change` |
| `/callback/subscriber-status` | GET+POST | `cb_subscriber_status_get/post` (179/185) | Logs + ack | event=`subscriber_status` |
| `/callback/static-ip` | GET+POST | `cb_static_ip_get/post` (191/197) | Logs + ack | event=`static_ip` |
| `/callback/cim` | GET+POST | `cb_cim_get/post` (203/209) | Logs + ack | event=`cim` |

**Plus a second, separate entry point** at `/api/webhooks/tmobile` (`webhooks.py:109-111`) — this one DOES archive to `IntegrationPayload` and enqueue a `webhook.tmobile` job, but the job handler is a stub.

### Tests that exist

| File | Tests | What's asserted |
|---|---|---|
| `test_tmobile_callback_events.py` | 8 | GET/POST → 200, valid/invalid/empty JSON → 200, sensitive header redaction in logs, legacy `/callback` still 200. **No assertion that anything is parsed or stored.** |
| `test_tmobile_taap.py` | 15 | Private-key load (file + env), PoP token structure / canonicalization / RS256 / unique edts per call, client config detection, PIT default URLs, OAuth2 token caching + failure handling, full subscriber_inquiry round-trip (mocked) with header verification. |

### Env vars / config settings (all declared in `api/app/config.py:116-126`)

| Var | Default | Read where | Set in `render.yaml`? |
|---|---|---|---|
| `TMOBILE_ENV` | `"pit"` | `tmobile_taap.py:220` | ❌ |
| `TMOBILE_BASE_URL` | `""` | `tmobile_taap.py:221` (overrides PIT/PROD defaults) | ❌ |
| `TMOBILE_TOKEN_URL` | `""` | `tmobile_taap.py:223` (overrides PIT/PROD defaults) | ❌ |
| `TMOBILE_CONSUMER_KEY` | `""` | `tmobile_taap.py:225`, `174`, `297` | ❌ |
| `TMOBILE_CONSUMER_SECRET` | `""` | `tmobile_taap.py:226`, `298` | ❌ |
| `TMOBILE_PARTNER_ID` | `""` | `tmobile_taap.py:228` | ❌ |
| `TMOBILE_SENDER_ID` | `""` | `tmobile_taap.py:229` | ❌ |
| `TMOBILE_ACCOUNT_ID` | `""` | `tmobile_taap.py:230` | ❌ |
| `TMOBILE_PRIVATE_KEY_PATH` | `""` | `tmobile_taap.py:71` | ❌ |
| `TMOBILE_PRIVATE_KEY_PEM` | `""` | `tmobile_taap.py:62` | ❌ |

**`ANTHROPIC_API_KEY`-style pattern** (secret in Render dashboard, not `render.yaml`) is appropriate for these — but **nothing** is set today.

### Code deployed but unused

- **`api/app/integrations/tmobile_taap.py`** — entire 532-line TAAP client (token exchange, PoP signing, 9 wholesale API methods). Imported by tests; **not imported by any router, service, or worker handler in production code**.
- **`api/app/services/carrier_adapter.py:78-90`** — `TMobileAdapter` class normalizes raw carrier payload into `CarrierTelemetry`. **Never instantiated.** Verizon's adapter pattern (lines 139-234) DOES flow through `process_telemetry()` → updates `Device.network_status` + writes `CommandTelemetry`; T-Mobile has no caller for the equivalent path.
- **`api/app/services/carrier_provider/tmobile.py`** — `TMobileProvider` class with `is_configured` hard-coded to `False`. Every method raises `CarrierProviderError`.
- **`api/app/integrations/tmobile.py`** — Legacy IoT (`api.t-mobile.com/iot/v1`) client. Disabled.

### What's stubbed, incomplete, or PIT-only

| Component | State |
|---|---|
| `tmobile_callback.py` handlers (14 routes) | **Logging-only stub**, intentionally so per the file's docstring (lines 7-10) until T-Mobile provides callback signing requirements |
| `sim_service.py:handle_webhook` (the `webhook.tmobile` worker job) | **Stub** — marks payload processed, discards event data |
| `TMobileAdapter` in carrier_adapter | **Class exists, never called** |
| `TMobileProvider` in carrier_provider | **Hard-coded disabled** |
| `TMobileTAAPClient` (outbound API) | **Fully working, never called** |
| `tmobile_callback.py:304,310-311` (in `tmobile_taap.py`) `print()` of Auth header | **Active code path, leaks Base64(key:secret) unconditionally** — see §6 |
| Inbound callback signature verification | **Missing** — see §2 |

---

## 2. Callback readiness

### URLs currently deployed

7 unique callback URLs are LIVE on `https://true911-api.onrender.com` (and `https://pit-api.manleysolutions.com` per the docstring):

- `/tmobile/wholesale/callback` (legacy generic)
- `/tmobile/wholesale/callback/provisioning`
- `/tmobile/wholesale/callback/usage`
- `/tmobile/wholesale/callback/device-change`
- `/tmobile/wholesale/callback/subscriber-status`
- `/tmobile/wholesale/callback/static-ip`
- `/tmobile/wholesale/callback/cim`

All 7 accept both GET (callback-validator probe) and POST. **Yes — unique callback URLs per event type are implemented.**

### GET + POST handlers — both implemented?

✅ Yes. Every event has both. Each returns a fixed JSON ack:

```json
{"status": "ok", "provider": "t-mobile", "event": "<event_name>", "message": "Callback endpoint reachable"}
```

### Do they archive incoming payloads?

❌ **No.** The 7 event-specific endpoints in `tmobile_callback.py` only call `_log_callback()` (line 78) and `_ack()` (line 68). Neither persists anything.

A separate, less-discoverable endpoint at `POST /api/webhooks/tmobile` (`webhooks.py:109-111`) **does** archive — it persists to `IntegrationPayload` and enqueues a `webhook.tmobile` job. But T-Mobile's PIT validator is configured to hit `/tmobile/wholesale/callback/*`, not `/api/webhooks/tmobile`, so the archiving path is effectively unused for T-Mobile traffic.

### Signature/token validation?

❌ **None.** `tmobile_callback.py:8-11` is explicit:

> "These endpoints are intentionally unauthenticated for now — they exist so T-Mobile's callback validator can confirm DNS/TLS/routing reach the target paths. Signature/IP validation will be added once T-Mobile provides their final callback signing requirements."

Compare to Telnyx, which **does** verify Ed25519 signatures on every webhook (`telnyx_service.py:58-99`, config-gated by `TELNYX_PUBLIC_KEY`). T-Mobile has nothing equivalent.

### Response format T-Mobile expects?

Partially confirmed. The 200 status code + JSON body is sufficient for the callback-validator probe stage (DNS/TLS/routing check). Whether T-Mobile's production callback validator requires a specific response **schema** (e.g., echoing back a token from the request) is unconfirmed — `docs/tmobile_taap_setup.md` should be checked or T-Mobile contact should be re-confirmed before promotion.

---

## 3. OAuth / PoP token status

> **⚠️ This section described the implementation as of the original audit. Several
> of its "✅ correct" verdicts were wrong** — they judged our reconstruction
> against itself rather than against T-Mobile's contract. T-Mobile Engineering
> supplied the authoritative PoP Token Builder reference on 2026-07-16; it now
> governs. See `tmobile_taap_setup.md` § "Authoritative PoP contract".
>
> Corrections to what this section claimed:
>
> | Audit claimed ✅ | Actually |
> |---|---|
> | `grant_type` in the JSON body | unsigned `grant-type` **header**; body is `{"cnf":"..."}` only |
> | `typ="pop"` | `typ="JWT"` |
> | `iss` = consumer_key | **no `iss`** — it leaked the consumer key into a decodable JWT |
> | ehts is comma-separated | **semicolon**-separated |
> | edts joins values with `\n` | values concatenated with **no separator** |
> | "Body is NEVER included (also correct for TAAP)" | body **is** signed, as exact wire bytes |
> | `X-Authorization: PoP <jwt>` | raw JWT, no `PoP ` prefix |
>
> The lesson worth keeping: an audit that reads only our own code can confirm
> internal consistency, never conformance to someone else's wire contract.
>
> **2026-07-16 follow-up:** the reference contract is now deployed (`1766f51`) and
> the PIT activation **still returns `GENS-0003 Invalid partnerID`** — so the PoP
> was never the cause. Blocked on T-Mobile's "Partner Foundation ID" contract; see
> `TMOBILE_PIT_ACTIVATION_PAYLOAD.md`. Conformance is now checked by an evidence
> runner that captures what was **actually sent**
> (`scripts/tmobile_pit_evidence.py`) rather than by reading our own code — which
> is the only way this section's original mistake gets caught early.

### Token exchange implemented?

✅ **Yes — fully.** `get_access_token()` implements the client-credentials flow:

- POST to `TMOBILE_TOKEN_URL` with a compact `{"cnf":"..."}` body
- `Authorization: Basic base64(consumer_key:consumer_secret)` header
- `grant-type: client_credentials` and `sender-id` unsigned headers
- `X-Authorization: <jwt>` PoP signing `Content-Type;Authorization;uri;http-method;body`
- Caches the access token (and any `id_token`) with `expires_in - 60s` margin
- Raises `RuntimeError` with status code on failure

### PoP / Apigee-style signing?

✅ **Yes** — the Apigee PoP family (NOT RFC 9449 DPoP), per T-Mobile's supplied builder.

`generate_pop_token()`:
- RS256 JWT with header `{"alg":"RS256","typ":"JWT"}`
- Claims exactly: `iat`, `exp` (= iat + 60), `ehts`, `edts`, `jti`, `v="1"` — no `iss`

### Canonicalization?

```python
ehts = ";".join(name for name, _ in ehts_headers)
digest_input = "".join(value for _, value in ehts_headers).encode("utf-8")
edts = base64.urlsafe_b64encode(hashlib.sha256(digest_input).digest()).rstrip(b"=").decode("ascii")
```

Values only (not names), **concatenated with no separator**, SHA-256 once,
base64url, strip `=`. The body participates as its exact wire bytes and is not
pre-hashed. Pinned by golden tests in `tests/test_tmobile_reference_contract.py`.

### Client credentials configured?

✅ Code is ready (`tmobile_taap.py:225-226`); ❌ values are empty in production (`render.yaml` has no `TMOBILE_*` vars, Render dashboard contents unknown to this audit).

### PIT and production environments separated?

✅ **Yes.** `tmobile_taap.py:39-45,220-224`:

```python
PIT_BASE_URL   = "https://wholesaleapi-test.t-mobile.com"
PIT_TOKEN_URL  = "https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens"
PROD_BASE_URL  = "https://apis.t-mobile.com"
PROD_TOKEN_URL = "https://oauth.t-mobile.com/oauth2/v2/tokens"

env = settings.TMOBILE_ENV.lower()
self.base_url  = (base_url or settings.TMOBILE_BASE_URL or (PIT_BASE_URL if env=="pit" else PROD_BASE_URL)).rstrip("/")
self.token_url = (token_url or settings.TMOBILE_TOKEN_URL or (PIT_TOKEN_URL if env=="pit" else PROD_TOKEN_URL))
```

⚠️ Default is `"pit"` — good for safety. But there's no equivalent of `LLLM_ALLOW_EXTERNAL` to gate ANY outbound traffic; the only safety today is "nobody calls the client."

### Secrets handled safely?

⚠️ **Medium-severity finding.** `tmobile_taap.py:304,310-311`:

```python
auth_header = "Basic " + basic_b64
print("AUTH HEADER EXACT:", repr(auth_header))           # ← leaks Base64(key:secret)
print("AUTH BASIC B64 VALID:", b64_valid)
print("AUTH BASIC ROUNDTRIP OK:", roundtrip_ok)
```

These three `print()` calls execute on **every** token request, not gated by `TMOBILE_TAAP_DEBUG`. The Authorization header is `Basic ` + Base64(consumer_key:consumer_secret) — trivially reversible.

The debug-guarded prints further down (`lines 336-372` inside `if debug:`) are safe. **Recommend: remove or gate lines 304, 310-311 before any production credentials land in env vars.**

### What's missing before a real PIT token request can succeed?

| Gap | Severity | Effort |
|---|---|---|
| Set `TMOBILE_CONSUMER_KEY` + `TMOBILE_CONSUMER_SECRET` in Render dashboard (not `render.yaml`) | trivial | minutes |
| Set `TMOBILE_PARTNER_ID` + `TMOBILE_SENDER_ID` + `TMOBILE_ACCOUNT_ID` | trivial | minutes |
| Set `TMOBILE_PRIVATE_KEY_PEM` (multi-line PEM in env var, or `_PATH` if mounting a file) | trivial | minutes |
| Confirm T-Mobile registered our public key (the partner side of the keypair handshake) | medium | days — coordinate with T-Mobile |
| Remove or debug-gate the `print()` leak on lines 304, 310-311 | **trivial — should fix before flipping config** | minutes |
| Decide PIT vs PROD (set `TMOBILE_ENV=pit` explicitly even though it's the default) | trivial | minutes |
| Identify any caller / use case for outbound TAAP API — currently no router or service uses the client | **high — no consumer** | days (Phase 2+) |

**Tokens could succeed today if creds are set; nothing in production code would consume the token. Outbound TAAP integration requires both credentials AND a use case.**

---

## 4. Data flow trace — what happens when a T-Mobile event arrives

### Path A: `POST /tmobile/wholesale/callback/<event>` (the T-Mobile PIT-validator path)

```
T-Mobile sends POST /tmobile/wholesale/callback/usage
  ↓
FastAPI routes to cb_usage_post (tmobile_callback.py:161)
  ↓
_log_callback(request, "usage", include_body=True)
  ├─ reads body via _safe_body_preview() — attempts JSON decode, falls back to UTF-8 string
  ├─ redacts sensitive headers via _safe_headers()
  └─ logger.info("T-Mobile callback | method=... | event=usage | ... | body=...")
  ↓
_ack("usage") → returns {"status":"ok","provider":"t-mobile","event":"usage","message":"Callback endpoint reachable"}
  ↓
HTTP 200

Database writes:           NONE
Job enqueued:              NONE
SIM/device lookup:         NONE
last_network_event update: NONE
CommandTelemetry write:    NONE
IntegrationPayload write:  NONE
```

**The event data is logged to stdout and then permanently lost.**

### Path B: `POST /api/webhooks/tmobile` (the generic webhook ingress)

```
POST /api/webhooks/tmobile
  ↓
webhooks.tmobile_webhook (webhooks.py:109-111)
  ↓
_ingest_webhook("tmobile", request, db) (webhooks.py:28-69)
  ├─ payload_id = "wh-<uuid12>"
  ├─ raw = await request.body()
  ├─ body_json = json.loads(...) or None
  ├─ db.add(IntegrationPayload(
  │    payload_id=..., source="tmobile", direction="inbound",
  │    headers=..., body=..., raw_body=..., processed=False))
  ├─ job = await job_service.create_and_enqueue(
  │    db, job_type="webhook.tmobile", queue="default",
  │    payload={"payload_id": payload_id, "source": "tmobile"})
  └─ await db.commit()
  ↓
HTTP 202 + {"payload_id": "wh-...", "job_id": <int>}
  ↓
RQ worker picks up the job
  ↓
sim_service.handle_webhook(db, job) (sim_service.py:148-165)
  ├─ payload_id = job.payload["payload_id"]
  ├─ ip = SELECT * FROM integration_payloads WHERE payload_id = ?
  ├─ ip.processed = True
  └─ return {"payload_id": ..., "processed": True}

Database writes:           IntegrationPayload row written, then marked processed
Job enqueued:              webhook.tmobile (succeeds, runs the stub)
SIM/device lookup:         NONE
last_network_event update: NONE
CommandTelemetry write:    NONE
Tenant linkage:            NONE (payload is tenant-less)
Customer/site/device link: NONE
```

**Raw payload is preserved on disk; no operational state derived from it.**

### Is it linked to ICCID / MSISDN / SIM / Device / Customer / Site / Tenant?

❌ **No.** `IntegrationPayload` carries no FK to any of these. The body sits as a JSONB blob with no extraction.

### Does it affect Command Center / Map / Sites / Devices / AI Health Summary / Health Normalizer?

❌ **No, none of these.** Neither `Site.status` nor `Device.last_network_event` nor `Device.network_status` nor `Sim.status` nor `CommandTelemetry` is written from any T-Mobile path. T-Mobile is invisible to every health surface.

---

## 5. Health Normalizer gap analysis

The Health Normalizer (`api/app/services/health/`) reads `Device.last_network_event` as the `last_carrier_event_at` channel of `HealthSignals` (verified at `api/app/services/health/signals_loader.py:91`). When `compute_device_state` runs, a device with a fresh `last_carrier_event_at` returns `CONNECTED` even with no heartbeat — this is exactly the Scenario A bug-fix from `HEALTH_STATUS_AUDIT.md` §5.

**Verizon already feeds this channel** via `carrier_adapter.py:158-162` (`device.last_network_event = now`). T-Mobile has the equivalent adapter (`TMobileAdapter`) and the equivalent target column (`Device.last_network_event`) — what's missing is the wire from a T-Mobile callback into that adapter's `process_telemetry()` call.

### Answers to the user's specific questions

| Question | Recommendation |
|---|---|
| Should T-Mobile callbacks produce `last_carrier_event_at` evidence? | **Yes.** Match the Verizon pattern: callback → SIM lookup → Device → `last_network_event = now`. Zero schema change. Zero HealthSignals change. The normalizer immediately picks it up. |
| Should T-Mobile SIM status update carrier liveness? | **Yes — subscriber-status, device-change, and provisioning events all imply liveness.** Static-ip and cim are less clear; defer those. |
| Should signal/network data translate into HealthSignals? | **Yes — `network_status` field, written via `TMobileAdapter.normalize()`** which already maps `registration_status`/`network_status` from the payload to the normalized `network_status` string. The normalizer reads this for ATTENTION classification. |
| What `sources_used` tag should appear? | **Reuse the existing tag** `devices:tenant=X.last_network_event (carrier liveness)` so the audit trail is consistent across Verizon + T-Mobile + future carriers. Add `webhook.tmobile:<event_type>` as a sub-source on the `IntegrationPayload`-level evidence if granularity becomes useful. Avoid `tmobile:tenant=X:carrier_liveness` as its own primary tag — that would split the same logical channel by vendor and complicate operator reading. |

### What changes in the HealthSignals dataclass?

**Nothing.** The existing `last_carrier_event_at` field is the right home. The signals_loader already reads `Device.last_network_event`. The normalizer already treats it as a CONNECTED-qualifying signal.

### What changes in the normalizer algorithm?

**Nothing.** The algorithm is signal-agnostic.

### What changes in `sources_used`?

Nothing initially. After T-Mobile starts feeding `Device.last_network_event`, the existing `(carrier liveness)` source label covers it. If, after soak, operators want per-vendor accountability, add a `(carrier liveness:tmobile)` qualifier on rows where the latest event came from a T-Mobile source — that requires tracking which carrier wrote the most recent event, but it's an additive change.

---

## 6. Risks

### Critical (block any production flag flip)

1. **Spoofing** — No signature verification on `/tmobile/wholesale/callback/*`. Anyone can POST a forged payload that would, in the MVP design below, mark a device as CONNECTED. **Mitigation:** require T-Mobile's callback signing spec before promoting; until then, gate the new ingestion path with `FEATURE_TMOBILE_CALLBACK_INGEST=false` AND scope IP allowlist via Render or Cloudflare to T-Mobile's source CIDRs.

2. **Secret leak in `tmobile_taap.py:304,310-311`** — `print()` the Base64-encoded Authorization header on every token request. Trivially reversible to consumer_key:consumer_secret. **Fix before setting credentials in any environment.**

3. **Wrong-tenant cross-update** — An ICCID may exist in `Sim` rows under multiple tenants (manual entry, migrations, demo data). Callback-to-SIM lookup MUST scope by tenant or refuse ambiguity. **Mitigation:** `Sim.tenant_id` filter + reject if multiple rows match; log + alert on ambiguity rather than guessing.

### High (must address in design)

4. **ICCID/MSISDN mapping ambiguity** — Some T-Mobile callbacks may include MSISDN only; others ICCID only. `Sim.iccid` and `Sim.msisdn` are both nullable. **Mitigation:** try `iccid` first, fall back to `msisdn`, drop the callback (still archive) if neither matches a tenant-scoped SIM.

5. **Duplicate callback handling** — T-Mobile may retry. Same event arriving twice should not double-update `Device.last_network_event` to misleading values nor write duplicate CommandTelemetry. **Mitigation:** `IntegrationPayload.payload_id` is unique; check `(source, event_type, x_request_id)` or `(source, hash(body))` for idempotency before promotion to Device.

6. **Replay events** — Old payloads replayed (deliberately or accidentally) could mark long-offline devices as CONNECTED. **Mitigation:** parse event timestamp from payload, reject if older than `CALLBACK_MAX_AGE_SECONDS` (e.g., 600s).

### Medium

7. **PII exposure in `IntegrationPayload.body`** — Full callback bodies stored as JSONB include MSISDN, ICCID, and potentially subscriber metadata. **Mitigation:** existing pattern (raw payload archived for audit) is fine; ensure access to `integration_payloads` is RBAC-gated; consider retention policy (e.g., 90-day TTL). No new exposure beyond what Telnyx CDRs already create.

8. **PIT vs prod confusion** — Default `TMOBILE_ENV=pit`; if creds for prod accidentally land with PIT env (or vice versa) the token endpoint will silently fail. **Mitigation:** log token endpoint URL on first request; reject if creds look like prod (different prefix) but env is `pit`.

9. **Rate limits** — Not specified in code. T-Mobile may rate-limit outbound calls. **Mitigation:** N/A for MVP (no outbound). Future Phase 2.

10. **Wrong site marked connected** — If a SIM is associated with the wrong site or has been physically moved, a T-Mobile callback would mark a stale site as connected. **Mitigation:** same as Verizon today — accept that `Device.site_id` is operator-managed; surface a `verification_status` flag in audit.

### Low

11. **Latency-sensitive callbacks** — If T-Mobile expects a 200 within N ms and our handler tries to do a DB lookup synchronously, retries pile up. **Mitigation:** keep the synchronous handler thin (write `IntegrationPayload` + enqueue job), do all matching async. This is the existing webhook pattern.

---

## 7. Recommended MVP

### Scope — smallest production-safe slice

A new `FEATURE_TMOBILE_CALLBACK_INGEST=false`-gated path that:

1. **Receives** T-Mobile callback at `/tmobile/wholesale/callback/<event>` (no URL change)
2. **Archives** raw payload to `IntegrationPayload(source="tmobile", body=..., metadata={event_type, payload_id})` — same shape Telnyx/VOLA already use
3. **Enqueues** a `webhook.tmobile` job (or a new `tmobile.callback.process` if we want a separate handler)
4. **Worker** extracts ICCID/MSISDN/timestamp/event_type from the body using a new `TMobileCallbackAdapter.normalize()` method (mirror of the existing `TMobileAdapter`)
5. **Matches** to a `Sim` row scoped by `tenant_id` (rejecting ambiguous matches)
6. **Records normalized carrier evidence** by writing `Device.last_network_event = now`, optionally `Device.network_status` if the event implies it
7. **Health Normalizer** automatically picks this up via the existing `last_carrier_event_at` channel — no normalizer change needed
8. **AI Health Summary** automatically reflects T-Mobile in `connected_sites` / `stale_devices` counts when `FEATURE_HEALTH_NORMALIZER=true`
9. **No customer-facing change** — internal-only surface unchanged
10. **No provisioning writes** — never creates SIM rows, never creates Device rows, never modifies Customer / Site / Line records
11. **No E911 / call-routing / emergency-behavior changes**
12. **No signature verification yet** — keep the current "PIT validator can reach the URL" guarantee, but document this as a known gap

When `FEATURE_TMOBILE_CALLBACK_INGEST=false` (default), the callback endpoints continue to ack with 200 and discard the body — byte-identical to today.

### Out of scope for MVP

- ❌ Outbound TAAP API calls (`subscriber_inquiry`, `query_network`, `query_usage`, `change_sim`, lifecycle methods) — defer to Phase 2 with `FEATURE_TMOBILE_OUTBOUND=false` and `TMOBILE_ALLOW_EXTERNAL=false` flags mirroring the LLLM model
- ❌ Inbound signature verification — defer until T-Mobile provides spec; document as known gap with timeline
- ❌ Static-IP and CIM event handlers — log/archive only; no operational promotion (these don't carry liveness signal)
- ❌ Provisioning writes (auto-creating SIMs from a subscriber-status callback) — defer to a separate governance decision
- ❌ Per-tenant rollout — MVP is platform-wide (matches the Verizon pattern)

---

## 8. Implementation plan

### Files to touch

**Modify (additive only):**

| File | Change |
|---|---|
| `api/app/config.py` | Add `FEATURE_TMOBILE_CALLBACK_INGEST: str = "false"`; add `TMOBILE_CALLBACK_MAX_AGE_SECONDS: int = 600`; remove/gate the `print()` leaks in `tmobile_taap.py:304,310-311` as a separate hygiene commit |
| `api/app/routers/tmobile_callback.py` | Per event handler: when flag is on, also call `_ingest_for_tmobile(event_type, request, db)` (new helper that wraps `_ingest_webhook` for the tmobile source); when flag is off, current logging-only path runs unchanged |
| `api/app/services/sim_service.py:handle_webhook` | When flag is on AND `source=="tmobile"`, delegate to a new `tmobile_callback_processor.process_event(db, payload_id)`; when flag is off, current stub runs unchanged |
| `api/app/services/health/signals_loader.py` | **No change.** The existing `last_carrier_event_at` channel already reads `Device.last_network_event`, which the new processor will write |
| `api/app/services/llm/context.py` | **No change.** Sources string is unchanged |
| `api/tests/test_tmobile_callback_events.py` | Add flag-on assertions: payload archived, job enqueued, no DB write when flag off |

**New files:**

| File | Purpose |
|---|---|
| `api/app/services/tmobile_callback_processor.py` | `process_event(db, payload_id)` — extract ICCID/MSISDN/event_type/timestamp, tenant-scoped SIM lookup, idempotency check, replay-age check, then call into `carrier_adapter.process_telemetry()` for the actual `Device.last_network_event` write — same path Verizon already uses |
| `api/tests/test_tmobile_callback_processor.py` | Unit tests for extraction + matching + idempotency + replay-rejection + ambiguity handling |
| `api/tests/test_tmobile_callback_integration.py` | End-to-end flag on/off tests; surface-containment guard (only `tmobile_callback.py` and `sim_service.py` reference the new flag) |

**Total: ~3 files modified, ~3 files added, ~50 lines of net behavior change behind the flag.**

### Database changes

❌ **None.** No new column, no migration. Uses:
- existing `IntegrationPayload` for raw archive
- existing `Device.last_network_event` / `Device.network_status` / `Device.telemetry_source` for promoted evidence
- existing `Sim.iccid` / `Sim.msisdn` / `Sim.tenant_id` for matching
- existing `CommandTelemetry` writes from `carrier_adapter.process_telemetry()` reused

### Feature flag strategy

```yaml
FEATURE_TMOBILE_CALLBACK_INGEST: "false"   # default — current logging-only behavior preserved
```

Mirrors the `FEATURE_HEALTH_NORMALIZER` pattern. When false: zero behavior change. When true: callbacks archived + matched + Device updated. Surface containment enforced by a static test (`test_only_*_files_reference_the_flag`).

A separate flag controls outbound (Phase 2):
```yaml
FEATURE_TMOBILE_OUTBOUND: "false"           # Phase 2 only
TMOBILE_ALLOW_EXTERNAL: "false"             # mirrors LLLM_ALLOW_EXTERNAL semantics
```

### Tests required

| Layer | Coverage |
|---|---|
| Unit (extraction) | parse event body for each of provisioning / usage / device-change / subscriber-status; extract ICCID + MSISDN + event timestamp |
| Unit (matching) | tenant-scoped SIM lookup; ambiguous match → log + skip; no match → log + skip; ICCID-first then MSISDN-fallback |
| Unit (idempotency) | same payload_id twice → second call no-op |
| Unit (replay) | event older than `TMOBILE_CALLBACK_MAX_AGE_SECONDS` → archive but skip promotion |
| Unit (adapter) | `TMobileAdapter.normalize` produces correct `CarrierTelemetry` (already covered) |
| Integration | flag off → current 200-only behavior preserved (existing 8 tests stay green); flag on → IntegrationPayload row + Device.last_network_event updated; surface-containment guard |
| RBAC | not applicable — endpoints are unauthenticated by design (T-Mobile PIT validator) |

### Rollout plan

| Phase | Action |
|---|---|
| **MVP (this PR)** | Merge flag-off. No-op deploy. Run smoke (callback endpoints still 200). |
| **Phase 1a soak** | Set `FEATURE_TMOBILE_CALLBACK_INGEST=true` on `true911-api` via ops PR. Use Render Blueprint sync (same gotcha as PR #55 and #57). Verify a synthetic POST → `IntegrationPayload` row + `Device.last_network_event` updated. |
| **Phase 1b** | Observe `integration_payloads.source='tmobile'` row rate; spot-check a few `Device.telemetry_source='t-mobile_carrier'` updates. After 1 week, no rollback signal → leave on. |
| **Hygiene PR (parallel)** | Remove the `print()` leak in `tmobile_taap.py:304,310-311`. Independent of the MVP. |
| **Phase 2 (separate audit + PR)** | Outbound TAAP — pick a use case (verification probe?), gate behind `FEATURE_TMOBILE_OUTBOUND=true` + `TMOBILE_ALLOW_EXTERNAL=true`, mirror LLLM cost-control patterns |
| **Phase 3** | Inbound signature verification once T-Mobile publishes spec |

### Rollback plan

| Tier | Action | Effect |
|---|---|---|
| **1 (instant)** | Set `FEATURE_TMOBILE_CALLBACK_INGEST=false` on `true911-api` and restart | Callbacks revert to logging-only. `IntegrationPayload` rows already written remain (audit value). No `Device` row reset. |
| **2 (revert)** | `git revert <merge-commit>` | Same as Tier 1 plus removes the new code. Tables unchanged (no schema mod). |
| **3 (data scrub)** | Manual SQL: `DELETE FROM integration_payloads WHERE source='tmobile' AND created_at > <merge_ts>` if needed | Permanent. Lose audit trail for the soak period. |

---

## 9. Constraints honored

- ✅ No code changes (this is audit only)
- ✅ No production behavior modified
- ✅ No E911, provisioning, call routing, customer records, or emergency behavior touched
- ✅ MVP recommendation is additive: new flag (default off), new processor module, no schema change, no migration, no outbound API call
- ✅ MVP keeps signature verification deferred per existing scope (`tmobile_callback.py` docstring) and explicitly notes the gap
- ✅ MVP touches no surface other than the AI Health Summary's evidence trail (transitively via `Device.last_network_event` reuse)
- ✅ No Phase 2 outbound TAAP integration in this audit's MVP

---

## 10. Decisions required before any implementation

1. **Is the MVP scope right?** Specifically: should the MVP modify `tmobile_callback.py:cb_*_post` handlers to dual-write (log + archive) when the flag is on, OR introduce a new prefix (`/api/webhooks/tmobile/<event>`) that T-Mobile would need to be reconfigured to use? Recommendation: modify existing handlers — zero T-Mobile-side reconfiguration, single source of truth.
2. **Idempotency key.** Recommendation: hash of `(source, event_type, body)` stored on `IntegrationPayload` as a unique index — but that's a schema change. Acceptable alternative: idempotency check via a SELECT before promotion (slower but no migration). MVP picks the SELECT path; Phase 1c adds an index if rate justifies it.
3. **Hygiene fix timing.** Remove the `print()` leak in `tmobile_taap.py:304,310-311` BEFORE setting any T-Mobile credentials, even as a one-line PR landed ahead of the MVP. Recommendation: ship as a tiny independent commit on `main` immediately.
4. **PIT-validator response shape.** Confirm with T-Mobile whether they require any specific JSON shape beyond HTTP 200. If yes, encode it in `_ack()` to avoid validator regressions on promotion.

---

## Appendix A — File:line citations used in this audit

- `api/app/routers/tmobile_callback.py:7-11,68-90,95-211` — handler stubs, logging helpers, intentional non-validation
- `api/app/routers/webhooks.py:28-69,109-111` — generic webhook archive path
- `api/app/integrations/tmobile_taap.py:39-45,56-80,83-99,130-193,210-389,393-468,470-531` — OAuth/PoP/canonicalization/API methods
- `api/app/integrations/tmobile_taap.py:304,310-311` — **unconditional `print()` of Authorization header** (secret-leak finding)
- `api/app/integrations/tmobile.py:1-39` — legacy IoT stub
- `api/app/services/carrier_provider/tmobile.py:1-33` — disabled provider
- `api/app/services/carrier_adapter.py:78-90,139-234` — `TMobileAdapter` + the Verizon-flow promotion path T-Mobile should mirror
- `api/app/services/sim_service.py:148-165` — stub worker handler
- `api/app/services/health/signals_loader.py:91` — reads `Device.last_network_event` as `last_carrier_event_at`
- `api/worker.py:19-32` — `webhook.tmobile` → stub registry entry
- `api/app/models/sim.py:27,59`, `device.py:46-51`, `integration_payload.py:17` — generic models; T-Mobile uses them, no T-Mobile-specific columns
- `api/app/config.py:116-126` — 10 declared env vars, all empty default
- `api/tests/test_tmobile_callback_events.py:43-130` — 8 stub-behavior tests
- `api/tests/test_tmobile_taap.py:56-353` — 15 signing / OAuth tests
- `api/app/services/telnyx_service.py:58-99` — Telnyx Ed25519 verification, the pattern T-Mobile should mirror eventually
- `render.yaml` — no T-Mobile env vars present
- `docs/tmobile_taap_setup.md` — existing operator notes (not re-audited)

---

*End of audit. No code changes proposed. Awaiting approval before any implementation work.*
