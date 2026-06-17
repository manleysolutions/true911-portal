"""T-Mobile Wholesale TAAP (Token-Aware Authentication Protocol) client.

Implements the PoP (Proof of Possession) token flow required by T-Mobile
Wholesale APIs. This is NOT standard OAuth2 — it requires RSA-signed PoP
tokens on every request in addition to the OAuth2 access token.

Flow:
1. Generate a PoP token (JWT signed with our RSA private key)
2. Exchange consumer key/secret + PoP for an OAuth2 access token
3. For each API call, generate a fresh PoP token for the request URI
4. Send both Authorization: Bearer <access_token> and X-Authorization: PoP <pop_token>

References:
- T-Mobile TAAP Developer Guide
- T-Mobile Wholesale API Portal (PIT environment)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from jose import jwt as jose_jwt

from app.config import settings

logger = logging.getLogger("true911.integrations.tmobile_taap")

# ── Constants ───────────────────────────────────────────────────────────────

# PIT (Partner Integration Testing) endpoints
PIT_BASE_URL = "https://wholesaleapi-test.t-mobile.com"
PIT_TOKEN_URL = "https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens"

# Production endpoints
PROD_BASE_URL = "https://apis.t-mobile.com"
PROD_TOKEN_URL = "https://oauth.t-mobile.com/oauth2/v2/tokens"

# Default subscriber resource base path. The PIT onboarding gateway URL list
# uses /wholesale/v1/subscriber (NOT the older /wholesale/subscriber/v2).
# Overridable via TMOBILE_SUBSCRIBER_BASE_PATH so a gateway routing change
# never needs a code edit.
DEFAULT_SUBSCRIBER_BASE_PATH = "/wholesale/v1/subscriber"

# PoP token lifetime (T-Mobile expects short-lived — 2 minutes)
POP_TOKEN_EXPIRY_SECONDS = 120

# Access token cache buffer — refresh 60s before expiry
ACCESS_TOKEN_REFRESH_BUFFER = 60

# ── PIT activation payload mapping (T-Mobile-provided 2026-06) ───────────────
# Partner/Sender ID 128, REST. The activation body is NESTED:
#   {iccid, marketZip, language, baseProduct:{baseProductId, wps, product:[...]}}
# These are the PIT-safe defaults from T-Mobile's onboarding packet — every one
# is overridable via the matching TMOBILE_* env var so a value change never needs
# a code edit. Nothing here is a secret (no keys, tokens, or URLs).
PIT_LANGUAGE = "ENGL"
PIT_BASE_PRODUCT_ID = "Infatrac Internet Access Plan"
PIT_WPS = "00011586"
# T-Mobile-confirmed PIT market ZIPs (informational; marketZip is supplied per call).
PIT_MARKET_ZIPS = ("30346", "30338")
# Sub-products carried under baseProduct.product[]. The PIT activation sample
# adds NOROAM (no-roaming) to the base plan.
PIT_DEFAULT_PRODUCTS: tuple[dict[str, Any], ...] = (
    {"ProductID": "NOROAM", "isBaseProduct": False, "action": "ADD"},
)


# ── RSA Key Loading ─────────────────────────────────────────────────────────

def _load_private_key() -> str:
    """Load RSA private key PEM content from file path or env var.

    Returns the PEM string. Raises RuntimeError if neither is configured.
    """
    # Option 1: Direct PEM content in env var (for Render / Docker / CI)
    pem = settings.TMOBILE_PRIVATE_KEY_PEM.strip()
    if pem:
        # Handle escaped newlines from env vars
        if "\\n" in pem:
            pem = pem.replace("\\n", "\n")
        return pem

    # Option 2: File path
    path = settings.TMOBILE_PRIVATE_KEY_PATH.strip()
    if path:
        p = Path(path)
        if not p.exists():
            raise RuntimeError(f"T-Mobile private key file not found: {path}")
        return p.read_text()

    raise RuntimeError(
        "T-Mobile TAAP: No private key configured. "
        "Set TMOBILE_PRIVATE_KEY_PATH or TMOBILE_PRIVATE_KEY_PEM."
    )


def _derive_public_key_pem(private_key_pem: str) -> str:
    """Derive the RSA public key PEM from a private key PEM.

    T-Mobile's token endpoint requires the PoP public key in the request
    body as the `cnf` attribute for proof-of-possession confirmation.
    """
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pub_bytes.decode("utf-8")


def _derive_public_key_jwk(private_key_pem: str) -> dict[str, str]:
    """Derive an RFC 7517 JWK (RSA) from a private key PEM.

    Returns {"kty": "RSA", "n": <base64url(modulus)>, "e": <base64url(exp)>}
    with unpadded base64url per RFC 7518 §6.3.1.
    """
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )
    public_numbers = private_key.public_key().public_numbers()

    def _int_to_b64url(i: int) -> str:
        byte_len = (i.bit_length() + 7) // 8
        raw = i.to_bytes(byte_len, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return {
        "kty": "RSA",
        "n": _int_to_b64url(public_numbers.n),
        "e": _int_to_b64url(public_numbers.e),
    }


# ── PoP Token Generation ───────────────────────────────────────────────────

def generate_pop_token(
    *,
    ehts_headers: list[tuple[str, str]],
) -> str:
    """Generate a T-Mobile TAAP PoP (Proof of Possession) token.

    T-Mobile TAAP uses the Apigee PoP format (not RFC 9449 DPoP).
    Claims:
      iss  — consumer key
      iat / exp / jti — standard
      ehts — the signed keys joined by a SEMICOLON (";").  Each key is a
             header name (e.g. "Content-Type", "Authorization") or a special
             token ("uri", "http-method").
      edts — base64url(SHA-256( value1 + value2 + ... )) over the ehts entry
             VALUES concatenated in order with NO separator, per the T-Mobile
             pop-token-builder reference (e.g. "application/json" +
             "/oauth2/v2/tokens" + "POST" -> "application/json/oauth2/v2/tokensPOST").
             The request body is NOT hashed here.

    Args:
        ehts_headers: ordered list of (ehts_key, value) tuples.  Keys appear
            in the `ehts` claim (";"-joined); the values are concatenated with
            NO separator and SHA-256-hashed into `edts`.

    Returns:
        Signed JWT string for the X-Authorization header.
    """
    private_key_pem = _load_private_key()
    now = int(time.time())

    ehts = ";".join(name for name, _ in ehts_headers)
    # edts = base64url(SHA-256(concatenation of the ehts VALUES in order, with
    # NO separator)).  Matches T-Mobile's PopTokenBuilder; the request body is
    # not included for the flows we sign.
    digest_input_str = "".join(value for _, value in ehts_headers)
    digest_input = digest_input_str.encode("utf-8")
    if os.environ.get("TMOBILE_TAAP_DEBUG", "").lower() in ("1", "true", "yes"):
        # digest_input_str contains the Basic-auth Authorization header
        # value when Authorization is one of the signed headers — that
        # value is Base64-reversible to consumer_key:consumer_secret.
        # Print only the SHA-256 + length + header names for signature
        # debugging; never the raw value itself.
        _digest_sha256 = hashlib.sha256(digest_input).hexdigest()
        print(
            f"[TAAP-DEBUG] edts digest_input: len={len(digest_input)} "
            f"sha256={_digest_sha256[:16]}... "
            f"signed_headers={[name for name, _ in ehts_headers]}"
        )
    edts = (
        base64.urlsafe_b64encode(hashlib.sha256(digest_input).digest())
        .rstrip(b"=")
        .decode("ascii")
    )

    payload: dict[str, Any] = {
        "iss": settings.TMOBILE_CONSUMER_KEY,
        "iat": now,
        "exp": now + POP_TOKEN_EXPIRY_SECONDS,
        "jti": str(uuid.uuid4()),
        "ehts": ehts,
        "edts": edts,
    }

    try:
        token = jose_jwt.encode(
            payload,
            private_key_pem,
            algorithm="RS256",
            headers={"alg": "RS256", "typ": "pop"},
        )
    except Exception as exc:
        logger.error("Failed to sign PoP token: %s", exc)
        raise RuntimeError(f"PoP token signing failed: {exc}") from exc

    return token


# ── Outbound diagnostic logging helpers ─────────────────────────────────────

# Response header names that must never be logged verbatim.
_SENSITIVE_RESPONSE_HEADERS = frozenset({
    "authorization", "x-authorization", "set-cookie", "cookie",
    "proxy-authorization", "www-authenticate",
})

# Response header names T-Mobile may use to carry a partner / transaction id.
_PARTNER_TXN_HEADER_CANDIDATES = (
    "partner-transaction-id", "x-partner-transaction-id",
    "transaction-id", "x-transaction-id",
    "x-correlation-id", "correlation-id",
)


def _redact_response_headers(headers: Any) -> dict[str, str]:
    """Return response headers safe to log — auth/cookie values masked.

    Used only for outbound-call diagnostics; never logs credential material.
    """
    safe: dict[str, str] = {}
    try:
        items = list(headers.items())
    except AttributeError:
        items = list(dict(headers or {}).items())
    for key, value in items:
        if str(key).lower() in _SENSITIVE_RESPONSE_HEADERS:
            safe[str(key)] = "<redacted>"
        else:
            safe[str(key)] = str(value)
    return safe


def _partner_transaction_id(headers: Any) -> str | None:
    """Best-effort extraction of a T-Mobile partner / transaction id header."""
    getter = getattr(headers, "get", None)
    if getter is None:
        getter = dict(headers or {}).get
    for name in _PARTNER_TXN_HEADER_CANDIDATES:
        val = getter(name)
        if val:
            return str(val)
    return None


# ── T-Mobile TAAP Client ───────────────────────────────────────────────────

class TMobileTAAPClient:
    """T-Mobile Wholesale API client using TAAP/PoP authentication.

    Usage::

        client = TMobileTAAPClient()
        subs = await client.post_json(
            client._subscriber_path("inquiry"),  # /wholesale/v1/subscriber/inquiry
            {"msisdn": "12125551234"},
        )
    """

    def __init__(
        self,
        base_url: str | None = None,
        token_url: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        partner_id: str | None = None,
        sender_id: str | None = None,
        account_id: str | None = None,
        subscriber_base_path: str | None = None,
        activation_path: str | None = None,
    ):
        env = settings.TMOBILE_ENV.lower()
        self.base_url = (base_url or settings.TMOBILE_BASE_URL or
                         (PIT_BASE_URL if env == "pit" else PROD_BASE_URL)).rstrip("/")
        self.token_url = (token_url or settings.TMOBILE_TOKEN_URL or
                          (PIT_TOKEN_URL if env == "pit" else PROD_TOKEN_URL))
        self.consumer_key = consumer_key or settings.TMOBILE_CONSUMER_KEY
        self.consumer_secret = consumer_secret or settings.TMOBILE_CONSUMER_SECRET
        self.partner_id = partner_id or settings.TMOBILE_PARTNER_ID
        self.sender_id = sender_id or settings.TMOBILE_SENDER_ID
        self.account_id = account_id or settings.TMOBILE_ACCOUNT_ID

        # Env-driven resource paths (no leading/trailing slash issues — joined
        # by the helpers below). Subscriber base defaults to the PIT gateway's
        # /wholesale/v1/subscriber; activation is kept independently overridable.
        self.subscriber_base_path = (
            subscriber_base_path or settings.TMOBILE_SUBSCRIBER_BASE_PATH
            or DEFAULT_SUBSCRIBER_BASE_PATH
        ).strip().rstrip("/")
        self.activation_path = (
            activation_path
            if activation_path is not None
            else settings.TMOBILE_ACTIVATION_PATH
        ).strip()

        # Access token cache
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

        # Shared HTTP client
        self._http: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if minimum required credentials are present."""
        return bool(self.consumer_key and self.consumer_secret)

    # ── Resource path resolution (env-driven) ───────────────────────────

    def _subscriber_path(self, op: str) -> str:
        """Join the env-driven subscriber base path with an operation name."""
        return f"{self.subscriber_base_path}/{op.lstrip('/')}"

    def activation_endpoint(self) -> str:
        """Resolve the activation route.

        Uses the explicit ``TMOBILE_ACTIVATION_PATH`` override when set, else
        derives ``{subscriber_base_path}/activate``.  Kept env-driven because
        T-Mobile may assign an activation route that is not derivable from the
        subscriber base.
        """
        return self.activation_path or self._subscriber_path("activate")

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    # ── Access Token (OAuth2 + PoP) ─────────────────────────────────────

    async def get_access_token(self) -> str:
        """Get a cached or fresh OAuth2 access token.

        T-Mobile's token endpoint requires:
        - grant_type=client_credentials
        - Basic auth with consumer key:secret
        - X-Authorization: PoP <pop_token> signed for the token URL
        """
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        if not self.consumer_key or not self.consumer_secret:
            raise RuntimeError(
                "T-Mobile TAAP: TMOBILE_CONSUMER_KEY and TMOBILE_CONSUMER_SECRET required"
            )

        # T-Mobile TAAP requires the PoP public key in the token request body
        # as the `cnf` attribute (Security-1018 / Missing Public Key otherwise).
        # JWK form returned Security-1018; T-Mobile's validator wants PEM,
        # but as a single-line string (BEGIN/END markers preserved, all
        # newlines stripped) so JSON-escaped \n sequences don't break parsing.
        import json as _json
        cnf_string = _derive_public_key_pem(_load_private_key()).replace("\n", "")
        body_obj = {
            "grant_type": "client_credentials",
            "cnf": cnf_string,
        }
        body_str = _json.dumps(body_obj)

        # Generate PoP token for the token endpoint. Per T-Mobile TAAP
        # guidance, Authorization is the mandatory header in the signed
        # set (ehts); Content-Type is included but Content-Length is not.
        # The edts digest input is the exact header values (in ehts
        # order) concatenated with the JSON body bytes.
        token_content_type = "application/json"
        # Strip stray whitespace (common when credentials come from a
        # .env file) so the Basic auth bytes — and therefore the single
        # authorization_value used in BOTH the PoP edts digest and the
        # wire Authorization header — exactly match what T-Mobile has
        # registered for this consumer key.
        _ck = self.consumer_key.strip()
        _cs = self.consumer_secret.strip()
        basic_creds = f"{_ck}:{_cs}".encode("utf-8")
        # Standard RFC 4648 base64 (NOT base64url): alphabet [A-Za-z0-9+/]
        # with `=` padding. ASCII output. T-Mobile's header validator
        # rejects base64url substitutions (-/_) and missing padding.
        basic_b64 = base64.b64encode(basic_creds).decode("ascii")
        auth_header = "Basic " + basic_b64
        # SECURITY: do NOT print or log auth_header — it is Base64-
        # reversible to consumer_key:consumer_secret.  The unconditional
        # diagnostic prints that previously lived here were removed in PR
        # security(tmobile): remove unsafe credential logging.  If you
        # need to verify Basic-auth encoding locally, exercise this module
        # in a REPL with throwaway credentials — never re-add prints here.
        # See tests/test_tmobile_taap_no_secret_logging.py for the guard.

        # auth_header is the Basic credential sent on the wire.  Per the
        # T-Mobile reference, the TOKEN request's PoP signs exactly
        # "Content-Type;uri;http-method" (Authorization is NOT part of the
        # PoP signature for this call) — it still travels as a wire header.
        headers = {
            "Authorization": auth_header,
            "Content-Type": token_content_type,
            "Accept": "application/json",
        }
        token_uri_path = urlsplit(self.token_url).path
        pop = generate_pop_token(
            ehts_headers=[
                ("Content-Type", token_content_type),
                ("uri", token_uri_path),
                ("http-method", "POST"),
            ],
        )
        # T-Mobile's TAAP validator parses the entire X-Authorization value
        # as a JWT — adding a "PoP " prefix breaks base64 decoding of the
        # header part and yields JWTDecodeException server-side. Send the
        # raw JWT only.
        headers["X-Authorization"] = pop
        x_auth = pop

        # Opt-in diagnostics for local troubleshooting. Enable with
        # `TMOBILE_TAAP_DEBUG=1` in your shell — never leave on in prod.
        debug = os.environ.get("TMOBILE_TAAP_DEBUG", "").lower() in ("1", "true", "yes")
        if debug:
            body_hash_hex = hashlib.sha256(body_str.encode("utf-8")).hexdigest()
            try:
                pop_hdr = jose_jwt.get_unverified_header(pop)
                pop_clm = jose_jwt.get_unverified_claims(pop)
            except Exception:
                pop_hdr, pop_clm = {}, {}
            print(f"[TAAP-DEBUG] Token URL: {self.token_url}")
            print(f"[TAAP-DEBUG] Token URL repr: {repr(self.token_url)}")
            print(f"[TAAP-DEBUG] Token URL len: {len(self.token_url)}")
            print(f"[TAAP-DEBUG] cnf format: single-line PEM")
            print(f"[TAAP-DEBUG] cnf length: {len(cnf_string)}")
            print(f"[TAAP-DEBUG] Body bytes len: {len(body_str.encode('utf-8'))}")
            print(f"[TAAP-DEBUG] Body SHA-256 (hex): {body_hash_hex}")
            print(f"[TAAP-DEBUG] Body JSON (exact wire bytes): {body_str}")
            print(f"[TAAP-DEBUG] X-Authorization format: "
                  + ("(raw JWT, no prefix)" if not headers["X-Authorization"].startswith("PoP ")
                     else "'PoP ' (with space) — UNEXPECTED, T-Mobile expects raw JWT"))
            # X-Authorization is the signed PoP JWT; even the first 80
            # chars expose the base64-encoded `iss` claim (= consumer_key).
            # Print structure only.
            print(
                f"[TAAP-DEBUG] X-Authorization: <signed JWT, "
                f"segments={headers['X-Authorization'].count('.') + 1}, "
                f"total_len={len(headers['X-Authorization'])}>"
            )
            print(f"[TAAP-DEBUG] PoP header: {pop_hdr}")
            # pop_clm.iss is the consumer_key — redact before printing.
            _safe_pop_clm = (
                {**pop_clm, "iss": "<redacted>"}
                if isinstance(pop_clm, dict) and pop_clm.get("iss")
                else pop_clm
            )
            print(f"[TAAP-DEBUG] PoP claims: {_safe_pop_clm}")

        client = await self._client()
        logger.info("T-Mobile TAAP: requesting access token from %s", self.token_url)

        resp = await client.post(
            self.token_url,
            content=body_str,
            headers=headers,
        )

        if resp.status_code != 200:
            body = resp.text if debug else resp.text[:500]
            if debug:
                print(f"[TAAP-DEBUG] Response status: {resp.status_code}")
                print(f"[TAAP-DEBUG] Response headers: {dict(resp.headers)}")
                print(f"[TAAP-DEBUG] Response body (full): {body}")
            logger.error(
                "T-Mobile TAAP token request failed: %s %s",
                resp.status_code, body,
            )
            raise RuntimeError(
                f"T-Mobile token request failed ({resp.status_code}): {body}"
            )

        token_data = resp.json()
        self._access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self._token_expires_at = now + expires_in - ACCESS_TOKEN_REFRESH_BUFFER

        logger.info(
            "T-Mobile TAAP: access token obtained, expires_in=%ds", expires_in
        )
        return self._access_token

    # ── API Requests ────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request with PoP token.

        Every T-Mobile API call requires:
        - Authorization: Bearer <access_token>
        - X-Authorization: PoP <pop_token>  (signed for this specific URL)
        - X-Sender-Id, X-Partner-Id, X-Account-Id headers
        """
        access_token = await self.get_access_token()
        url = f"{self.base_url}/{path.lstrip('/')}"

        # Serialize body once — the exact same bytes are both hashed and sent.
        import json as _json
        body_str = _json.dumps(json_body) if json_body is not None else None

        req_content_type = "application/json"
        authorization_value = f"Bearer {access_token}"
        # Resource calls sign "Authorization;uri;http-method" (uri = URL path,
        # http-method = the verb). Body is not signed here.
        pop = generate_pop_token(
            ehts_headers=[
                ("Authorization", authorization_value),
                ("uri", urlsplit(url).path),
                ("http-method", method.upper()),
            ],
        )

        # Named so it can be logged + correlated with T-Mobile's server logs.
        # Same value/behavior as before (one uuid4 per request) — just captured.
        correlation_id = str(uuid.uuid4())
        headers: dict[str, str] = {
            "Authorization": authorization_value,
            "X-Authorization": pop,
            "Content-Type": req_content_type,
            "Accept": "application/json",
            "X-Correlation-Id": correlation_id,
        }

        # T-Mobile partner identification headers
        if self.partner_id:
            headers["X-Partner-Id"] = self.partner_id
        if self.sender_id:
            headers["X-Sender-Id"] = self.sender_id
        if self.account_id:
            headers["X-Account-Id"] = self.account_id

        if extra_headers:
            headers.update(extra_headers)

        client = await self._client()
        # Log the correlation id for EVERY outbound request so any later failure
        # (or a T-Mobile log review) can be tied to this exact call. No secrets.
        logger.info(
            "T-Mobile TAAP request: method=%s path=%s correlation_id=%s",
            method.upper(), path, correlation_id,
        )

        try:
            resp = await client.request(
                method.upper(), url,
                content=body_str,
                params=params,
                headers=headers,
            )
        except httpx.TimeoutException:
            raise RuntimeError(f"T-Mobile TAAP: timeout calling {method} {path}")
        except httpx.RequestError as exc:
            raise RuntimeError(f"T-Mobile TAAP: request error: {exc}")

        if resp.status_code >= 400:
            body = resp.text[:500]
            # Diagnostic detail for T-Mobile troubleshooting. Request auth
            # headers are never logged; response headers are redacted of any
            # auth/cookie material; body is truncated to a safe length.
            partner_txn = _partner_transaction_id(resp.headers)
            logger.warning(
                "T-Mobile TAAP API error: method=%s path=%s status=%s "
                "correlation_id=%s partner_transaction_id=%s "
                "response_headers=%s body=%s",
                method.upper(), path, resp.status_code, correlation_id,
                partner_txn, _redact_response_headers(resp.headers), body,
            )
            raise RuntimeError(
                f"T-Mobile API error ({resp.status_code}): {body}"
            )

        if resp.status_code == 204:
            return {}
        return resp.json()

    async def post_json(self, path: str, body: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return await self._request("POST", path, json_body=body, **kwargs)

    async def get_json(self, path: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return await self._request("GET", path, params=params, **kwargs)

    # ── Wholesale API Methods (ready for PIT testing) ───────────────────

    @staticmethod
    def _callback_headers(callback_location: str | None) -> dict[str, str]:
        """Resolve the async ``call-back-location`` header, or ``{}`` if unset.

        Async-capable calls pass the callback URL so T-Mobile can return the
        asynchronous response to our ingest endpoint (per T-Mobile guidance:
        "asynchronous responses can be validated by passing the callback
        location").  Resolution mirrors ``activate_subscriber`` exactly:
        explicit ``callback_location`` arg first, then the
        ``TMOBILE_CALLBACK_LOCATION`` env, attached as the HTTP header
        ``call-back-location``.

        Unlike activation — where the callback is MANDATORY because the
        generated account ID is returned only there — these query/change calls
        also work synchronously, so a missing callback is NOT an error: the
        header is simply omitted and the existing request is unchanged byte for
        byte.  No body field is added.
        """
        resolved = (
            callback_location or settings.TMOBILE_CALLBACK_LOCATION or ""
        ).strip()
        return {"call-back-location": resolved} if resolved else {}

    async def subscriber_inquiry(
        self,
        msisdn: str,
        *,
        account_id: str | None = None,
        callback_location: str | None = None,
    ) -> dict[str, Any]:
        """Query subscriber details by MSISDN.

        Requires an account ID.  Per T-Mobile, the account ID is GENERATED by
        activation and returned asynchronously via the callback.

        ``account_id`` may be passed explicitly — the activation-first flow
        stores a PER-SUBSCRIBER account ID on ``sims.meta`` (captured from the
        callback), and ``app.services.tmobile_subscriber.query_subscriber_by_iccid``
        resolves it and passes it here.  When omitted, falls back to the global
        ``TMOBILE_ACCOUNT_ID`` env (single-account setups).  Disabled (raises)
        when neither is available.
        """
        account_id = account_id or self.account_id
        if not account_id:
            raise RuntimeError(
                "SubscriberInquiry is disabled until an account ID exists. "
                "The account ID is generated by activation and returned via the "
                "callback; pass account_id (resolved per-ICCID from sims.meta) or "
                "set TMOBILE_ACCOUNT_ID once it is known."
            )
        return await self.post_json(
            self._subscriber_path("inquiry"),
            {"msisdn": msisdn, "accountId": account_id},
            extra_headers=self._callback_headers(callback_location),
        )

    async def query_network(
        self, msisdn: str, *, callback_location: str | None = None
    ) -> dict[str, Any]:
        """Query network/device status for a subscriber.

        When a callback location is configured (arg or TMOBILE_CALLBACK_LOCATION)
        the ``call-back-location`` header is attached so T-Mobile can return the
        status asynchronously to our ingest endpoint; otherwise the call is the
        plain synchronous query, unchanged.
        """
        return await self.post_json(
            "/wholesale/network/v1/query",
            {"msisdn": msisdn},
            extra_headers=self._callback_headers(callback_location),
        )

    async def query_usage(self, msisdn: str, start_date: str, end_date: str) -> dict[str, Any]:
        """Query subscriber data/voice usage for a date range."""
        return await self.post_json(
            "/wholesale/usage/v1/query",
            {"msisdn": msisdn, "startDate": start_date, "endDate": end_date},
        )

    async def change_sim(
        self, msisdn: str, new_iccid: str, *, callback_location: str | None = None
    ) -> dict[str, Any]:
        """Initiate a SIM swap for a subscriber.

        SIM swap completes asynchronously; when a callback location is
        configured (arg or TMOBILE_CALLBACK_LOCATION) the ``call-back-location``
        header is attached so T-Mobile can return the result to our ingest
        endpoint.  The request body is unchanged.
        """
        return await self.post_json(
            self._subscriber_path("changesim"),
            {"msisdn": msisdn, "iccid": new_iccid, "accountId": self.account_id},
            extra_headers=self._callback_headers(callback_location),
        )

    @staticmethod
    def live_calls_enabled() -> bool:
        """True only when TMOBILE_PIT_LIVE_CALLS_ENABLED is explicitly truthy.

        This is the hard switch that authorizes a REAL activation POST. The
        dry-run preview never consults it.
        """
        return str(settings.TMOBILE_PIT_LIVE_CALLS_ENABLED).strip().lower() in (
            "1", "true", "yes", "on",
        )

    def _require_live_calls_enabled(self) -> None:
        """Fail closed unless live PIT calls are explicitly authorized."""
        if not self.live_calls_enabled():
            raise RuntimeError(
                "Live T-Mobile PIT activation is DISABLED — no request was sent. "
                "Set TMOBILE_PIT_LIVE_CALLS_ENABLED=true to authorize real PIT "
                "activation calls. Use build_activation_preview() or the dry-run "
                "script to inspect the exact payload without sending."
            )

    async def activate_subscriber(
        self,
        iccid: str,
        *,
        market_zip: str | None = None,
        language: str | None = None,
        base_product_id: str | None = None,
        wps: str | None = None,
        products: list[dict[str, Any]] | None = None,
        callback_location: str | None = None,
    ) -> dict[str, Any]:
        """Activate a new subscriber line (IoT / Infatrac) — LIVE PIT call.

        Per T-Mobile guidance, activation does NOT take an ``accountId`` or an
        ``msisdn`` — the account ID is GENERATED by activation and returned
        asynchronously to the ``call-back-location``.  The request carries the
        nested ``{iccid, marketZip, language, baseProduct{...}}`` body.

        Inputs fall back to env / PIT constants when not passed (see
        ``_build_activation_payload``).  ``callback_location`` ->
        TMOBILE_CALLBACK_LOCATION.  The partner / sender headers
        (X-Partner-Id / X-Sender-Id) are applied by ``_request`` from
        TMOBILE_PARTNER_ID / TMOBILE_SENDER_ID (both 128 for Infatrac).

        Two fail-closed guards before anything is sent:
          1. TMOBILE_PIT_LIVE_CALLS_ENABLED must be "true" — otherwise this
             raises ``RuntimeError`` and sends nothing.
          2. A ``call-back-location`` is REQUIRED — the generated account ID is
             returned only to that callback, so a missing one raises
             ``ValueError`` rather than send an activation we can't reconcile.
        """
        # Guard 1: refuse to send unless live calls are explicitly authorized.
        self._require_live_calls_enabled()

        payload = self._build_activation_payload(
            iccid, market_zip=market_zip, language=language,
            base_product_id=base_product_id, wps=wps, products=products,
        )
        callback_location = (
            callback_location or settings.TMOBILE_CALLBACK_LOCATION or ""
        ).strip()
        # Guard 2: the account ID is GENERATED by activation and returned ONLY to
        # this callback.  A live activation without call-back-location would
        # succeed at T-Mobile but strand the generated account ID with no way for
        # us to capture it — so require it rather than silently omit.
        if not callback_location:
            raise ValueError(
                "activate_subscriber requires a call-back-location (pass "
                "callback_location or set TMOBILE_CALLBACK_LOCATION). The account "
                "ID is generated by activation and returned only via this "
                "callback; without it the activation result cannot be captured."
            )
        return await self.post_json(
            self.activation_endpoint(),
            payload,
            extra_headers={"call-back-location": callback_location},
        )

    def _build_activation_payload(
        self,
        iccid: str,
        *,
        market_zip: str | None = None,
        language: str | None = None,
        base_product_id: str | None = None,
        wps: str | None = None,
        products: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build + validate the nested activation request body.

        Field mapping (env override -> PIT constant fallback):
          marketZip                  <- market_zip / TMOBILE_MARKET_ZIP
          language                   <- language / TMOBILE_LANGUAGE / PIT_LANGUAGE
          baseProduct.baseProductId  <- base_product_id / TMOBILE_BASE_PRODUCT_ID / PIT_BASE_PRODUCT_ID
          baseProduct.wps            <- wps / TMOBILE_WPS / PIT_WPS
          baseProduct.product[]      <- products / PIT_DEFAULT_PRODUCTS (NOROAM ADD)

        Shared by ``activate_subscriber`` (live) and
        ``build_activation_preview`` (dry run) so both produce identical bytes.
        """
        market_zip = market_zip or settings.TMOBILE_MARKET_ZIP
        language = language or settings.TMOBILE_LANGUAGE or PIT_LANGUAGE
        base_product_id = (
            base_product_id or settings.TMOBILE_BASE_PRODUCT_ID or PIT_BASE_PRODUCT_ID
        )
        wps = wps or settings.TMOBILE_WPS or PIT_WPS
        if products is None:
            # Deep-copy the constant so callers can never mutate the default.
            products = [dict(p) for p in PIT_DEFAULT_PRODUCTS]

        if not iccid:
            raise ValueError("activate_subscriber requires an ICCID")
        if not market_zip:
            raise ValueError(
                "activate_subscriber requires a marketZip (pass market_zip or set "
                "TMOBILE_MARKET_ZIP, e.g. 30346/30338 for PIT)"
            )
        if not base_product_id:
            raise ValueError(
                "activate_subscriber requires a baseProductId (pass base_product_id "
                "or set TMOBILE_BASE_PRODUCT_ID)"
            )
        if not wps:
            raise ValueError(
                "activate_subscriber requires a wps (pass wps or set TMOBILE_WPS)"
            )

        return {
            "iccid": iccid,
            "marketZip": market_zip,
            "language": language,
            "baseProduct": {
                "baseProductId": base_product_id,
                "wps": wps,
                "product": products,
            },
        }

    def build_activation_preview(
        self,
        iccid: str,
        *,
        market_zip: str | None = None,
        language: str | None = None,
        base_product_id: str | None = None,
        wps: str | None = None,
        products: list[dict[str, Any]] | None = None,
        callback_location: str | None = None,
    ) -> dict[str, Any]:
        """Build the EXACT activation request as a printable descriptor — WITHOUT
        sending it or contacting T-Mobile (no network, no OAuth, no signing).

        This is the dry-run path and NEVER consults TMOBILE_PIT_LIVE_CALLS_ENABLED
        — it only ever returns the generated payload + headers for review.

        The two credential-bearing headers added by ``_request`` at send time
        (``Authorization: Bearer <token>`` and ``X-Authorization: <PoP JWT>``)
        are shown as redacted placeholders so the output is safe to print/share.
        Every other header and the full payload are the real values that would
        go on the wire.  Use this for the dry-run activation command.
        """
        payload = self._build_activation_payload(
            iccid, market_zip=market_zip, language=language,
            base_product_id=base_product_id, wps=wps, products=products,
        )
        callback_location = (
            callback_location or settings.TMOBILE_CALLBACK_LOCATION or ""
        ).strip()
        path = self.activation_endpoint()
        url = f"{self.base_url}/{path.lstrip('/')}"

        # Mirror the non-sensitive headers _request() attaches. The two secret
        # headers are placeholders — never the real Bearer token or PoP JWT.
        headers: dict[str, str] = {
            "Authorization": "<redacted: OAuth access token — added at send time>",
            "X-Authorization": "<redacted: PoP JWT — RS256-signed per request at send time>",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Correlation-Id": "<generated per request>",
        }
        if self.partner_id:
            headers["X-Partner-Id"] = self.partner_id
        if self.sender_id:
            headers["X-Sender-Id"] = self.sender_id
        if self.account_id:
            headers["X-Account-Id"] = self.account_id
        # Always SHOW call-back-location so a dry-run surfaces a missing callback
        # (the live activate_subscriber refuses to send without it).  A real
        # value is displayed verbatim; when unset, an explicit marker makes the
        # gap obvious instead of silently dropping the header.
        if callback_location:
            headers["call-back-location"] = callback_location
        else:
            headers["call-back-location"] = (
                "<NOT SET — set TMOBILE_CALLBACK_LOCATION; live activation will refuse to send>"
            )

        live_enabled = self.live_calls_enabled()
        notes = [
            "DRY RUN — nothing was sent to T-Mobile.",
            "Authorization/X-Authorization are redacted placeholders.",
            f"Live PIT calls are {'ENABLED' if live_enabled else 'DISABLED'} "
            f"(TMOBILE_PIT_LIVE_CALLS_ENABLED).",
        ]
        if not live_enabled:
            notes.append(
                "activate_subscriber() will refuse to send until "
                "TMOBILE_PIT_LIVE_CALLS_ENABLED=true."
            )
        if not callback_location:
            notes.append(
                "call-back-location is NOT configured — the account ID is "
                "returned only via this callback; live activation will refuse "
                "to send until TMOBILE_CALLBACK_LOCATION is set."
            )

        return {
            "method": "POST",
            "path": path,
            "url": url,
            "payload": payload,
            "headers": headers,
            "callback_location_configured": bool(callback_location),
            "live_calls_enabled": live_enabled,
            # ehts entries the PoP token signs for a resource call (see _request).
            "pop_signed_ehts": ["Authorization", "uri", "http-method"],
            "would_send": False,
            "notes": notes,
        }

    async def suspend_subscriber(self, msisdn: str) -> dict[str, Any]:
        """Suspend a subscriber line."""
        return await self.post_json(
            self._subscriber_path("suspend"),
            {"msisdn": msisdn, "accountId": self.account_id},
        )

    async def restore_subscriber(self, msisdn: str) -> dict[str, Any]:
        """Restore (unsuspend) a subscriber line."""
        return await self.post_json(
            self._subscriber_path("restore"),
            {"msisdn": msisdn, "accountId": self.account_id},
        )

    async def deactivate_subscriber(self, msisdn: str) -> dict[str, Any]:
        """Deactivate (cancel) a subscriber line."""
        return await self.post_json(
            self._subscriber_path("deactivate"),
            {"msisdn": msisdn, "accountId": self.account_id},
        )
