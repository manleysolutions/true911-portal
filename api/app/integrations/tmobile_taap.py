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

# PoP token lifetime (T-Mobile expects short-lived — 2 minutes)
POP_TOKEN_EXPIRY_SECONDS = 120

# Access token cache buffer — refresh 60s before expiry
ACCESS_TOKEN_REFRESH_BUFFER = 60


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


# ── PoP Token Generation ───────────────────────────────────────────────────

def generate_pop_token(
    body: str | bytes | None = None,
    ehts_headers: list[tuple[str, str]] | None = None,
) -> str:
    """Generate a T-Mobile TAAP PoP (Proof of Possession) token.

    T-Mobile TAAP uses the Apigee PoP format (not RFC 9449 DPoP).
    Claims:
      iss  — consumer key
      iat / exp / jti — standard
      ehts — semicolon-separated list of HTTP header names being signed
      edts — base64url(SHA-256(header_value_1 || header_value_2 || ... || body))

    Args:
        body: request body string/bytes (optional)
        ehts_headers: ordered list of (header_name, header_value) tuples
            whose values are concatenated into the edts hash input.
            Header names (not values) appear in the `ehts` claim.

    Returns:
        Signed JWT string for the X-Authorization header.
    """
    private_key_pem = _load_private_key()
    now = int(time.time())

    if ehts_headers is None:
        ehts_headers = []

    ehts = ",".join(name for name, _ in ehts_headers)
    # T-Mobile TAAP: edts is SHA-256 of the request body bytes ONLY.
    # Header values are listed in ehts but are NOT concatenated into
    # the digest input.
    if body is None:
        digest_input = b""
    else:
        digest_input = body if isinstance(body, bytes) else body.encode("utf-8")
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
            headers={"alg": "RS256", "typ": "JWT"},
        )
    except Exception as exc:
        logger.error("Failed to sign PoP token: %s", exc)
        raise RuntimeError(f"PoP token signing failed: {exc}") from exc

    return token


# ── T-Mobile TAAP Client ───────────────────────────────────────────────────

class TMobileTAAPClient:
    """T-Mobile Wholesale API client using TAAP/PoP authentication.

    Usage::

        client = TMobileTAAPClient()
        subs = await client.post_json(
            "/wholesale/subscriber/v2/inquiry",
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

        # Access token cache
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

        # Shared HTTP client
        self._http: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if minimum required credentials are present."""
        return bool(self.consumer_key and self.consumer_secret)

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
        import json as _json
        public_key_pem = _derive_public_key_pem(_load_private_key())
        body_obj = {
            "grant_type": "client_credentials",
            "cnf": public_key_pem,
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
        authorization_value = "Basic " + base64.b64encode(basic_creds).decode("ascii")

        # Finalize the wire headers FIRST, then derive the PoP edts/ehts
        # directly from this same dict. This guarantees the Authorization
        # bytes in the hash input are byte-for-byte identical to what is
        # sent on the wire — no second computation anywhere.
        headers = {
            "Authorization": authorization_value,
            "Content-Type": token_content_type,
            "Accept": "application/json",
        }
        pop = generate_pop_token(
            body=body_str,
            ehts_headers=[
                ("Authorization", headers["Authorization"]),
                ("Content-Type", headers["Content-Type"]),
            ],
        )
        headers["X-Authorization"] = "PoP " + pop
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
            print(f"[TAAP-DEBUG] Body bytes len: {len(body_str.encode('utf-8'))}")
            print(f"[TAAP-DEBUG] Body SHA-256 (hex): {body_hash_hex}")
            print(f"[TAAP-DEBUG] Body JSON (exact wire bytes): {body_str}")
            print(f"[TAAP-DEBUG] X-Authorization prefix: "
                  + ("'PoP ' (with space)" if headers["X-Authorization"].startswith("PoP ")
                     else "(raw JWT, no prefix)"))
            print(f"[TAAP-DEBUG] X-Authorization (first 80): {headers['X-Authorization'][:80]}...")
            print(f"[TAAP-DEBUG] PoP header: {pop_hdr}")
            print(f"[TAAP-DEBUG] PoP claims: {pop_clm}")

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
        if body_str is not None:
            req_content_length = str(len(body_str.encode("utf-8")))
            req_ehts = [
                ("Content-Type", req_content_type),
                ("Content-Length", req_content_length),
            ]
        else:
            req_ehts = []
        pop = generate_pop_token(body=body_str, ehts_headers=req_ehts)

        headers: dict[str, str] = {
            "Authorization": f"Bearer {access_token}",
            "X-Authorization": pop,
            "Content-Type": req_content_type,
            "Accept": "application/json",
            "X-Correlation-Id": str(uuid.uuid4()),
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
        logger.debug("T-Mobile TAAP %s %s", method.upper(), url)

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
            logger.warning(
                "T-Mobile TAAP API error %s %s: %s",
                resp.status_code, path, body,
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

    async def subscriber_inquiry(self, msisdn: str) -> dict[str, Any]:
        """Query subscriber details by MSISDN."""
        return await self.post_json(
            "/wholesale/subscriber/v2/inquiry",
            {"msisdn": msisdn, "accountId": self.account_id},
        )

    async def query_network(self, msisdn: str) -> dict[str, Any]:
        """Query network/device status for a subscriber."""
        return await self.post_json(
            "/wholesale/network/v1/query",
            {"msisdn": msisdn},
        )

    async def query_usage(self, msisdn: str, start_date: str, end_date: str) -> dict[str, Any]:
        """Query subscriber data/voice usage for a date range."""
        return await self.post_json(
            "/wholesale/usage/v1/query",
            {"msisdn": msisdn, "startDate": start_date, "endDate": end_date},
        )

    async def change_sim(self, msisdn: str, new_iccid: str) -> dict[str, Any]:
        """Initiate a SIM swap for a subscriber."""
        return await self.post_json(
            "/wholesale/subscriber/v2/changesim",
            {"msisdn": msisdn, "iccid": new_iccid, "accountId": self.account_id},
        )

    async def activate_subscriber(self, msisdn: str, iccid: str, **kwargs: Any) -> dict[str, Any]:
        """Activate a new subscriber line."""
        payload = {"msisdn": msisdn, "iccid": iccid, "accountId": self.account_id}
        payload.update(kwargs)
        return await self.post_json("/wholesale/subscriber/v2/activate", payload)

    async def suspend_subscriber(self, msisdn: str) -> dict[str, Any]:
        """Suspend a subscriber line."""
        return await self.post_json(
            "/wholesale/subscriber/v2/suspend",
            {"msisdn": msisdn, "accountId": self.account_id},
        )

    async def restore_subscriber(self, msisdn: str) -> dict[str, Any]:
        """Restore (unsuspend) a subscriber line."""
        return await self.post_json(
            "/wholesale/subscriber/v2/restore",
            {"msisdn": msisdn, "accountId": self.account_id},
        )

    async def deactivate_subscriber(self, msisdn: str) -> dict[str, Any]:
        """Deactivate (cancel) a subscriber line."""
        return await self.post_json(
            "/wholesale/subscriber/v2/deactivate",
            {"msisdn": msisdn, "accountId": self.account_id},
        )
