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

import hashlib
import logging
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
PIT_BASE_URL = "https://pit-apis.t-mobile.com"
PIT_TOKEN_URL = "https://pit-oauth.t-mobile.com/oauth2/v2/tokens"

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


# ── PoP Token Generation ───────────────────────────────────────────────────

def generate_pop_token(
    uri: str,
    http_method: str = "POST",
    body: str | bytes | None = None,
) -> str:
    """Generate a T-Mobile PoP (Proof of Possession) token.

    The PoP token is a JWT signed with our RSA private key that proves
    we possess the key pair. T-Mobile validates the signature using our
    registered public key.

    Args:
        uri: The full request URI (e.g. https://pit-apis.t-mobile.com/...)
        http_method: GET, POST, PUT, DELETE
        body: Request body bytes for body hash (optional)

    Returns:
        Signed JWT string for the X-Authorization header.
    """
    private_key_pem = _load_private_key()
    now = int(time.time())

    # Build the PoP token payload per T-Mobile TAAP spec
    payload: dict[str, Any] = {
        "iss": settings.TMOBILE_CONSUMER_KEY,
        "iat": now,
        "exp": now + POP_TOKEN_EXPIRY_SECONDS,
        "jti": str(uuid.uuid4()),
        "at": {
            "htm": http_method.upper(),
            "htu": uri,
        },
    }

    # If there's a request body, include its SHA-256 hash
    if body:
        body_bytes = body if isinstance(body, bytes) else body.encode("utf-8")
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        payload["at"]["ath"] = body_hash

    # Sign with RS256 using our private key
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

        # Generate PoP token for the token endpoint
        pop = generate_pop_token(
            uri=self.token_url,
            http_method="POST",
            body="grant_type=client_credentials",
        )

        client = await self._client()
        logger.info("T-Mobile TAAP: requesting access token from %s", self.token_url)

        resp = await client.post(
            self.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.consumer_key, self.consumer_secret),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Authorization": f"PoP {pop}",
            },
        )

        if resp.status_code != 200:
            body = resp.text[:500]
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

        # Serialize body for PoP hash
        import json as _json
        body_str = _json.dumps(json_body) if json_body else None

        # Generate PoP token for this specific request
        pop = generate_pop_token(
            uri=url,
            http_method=method.upper(),
            body=body_str,
        )

        headers: dict[str, str] = {
            "Authorization": f"Bearer {access_token}",
            "X-Authorization": f"PoP {pop}",
            "Content-Type": "application/json",
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
                json=json_body,
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
