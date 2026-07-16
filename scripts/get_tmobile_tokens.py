"""Fetch a T-Mobile access token and inspect it — no activation is sent.

Two modes:

  --decode-claims  (default)  Fetch a token, decode its claims, and report
                              whether ``senderId`` / ``channelId`` are present.
                              Also reports the OUTBOUND token request: that the
                              unsigned ``sender-id`` header was sent, and which
                              headers the token-request PoP signed.  Prints NO
                              token material.  This is the check to run after
                              deploying the token-request sender-id fix, BEFORE
                              any further live PIT activation.

  --print-tokens              Print the raw ``Authorization`` /
                              ``X-Authorization`` header values, for handing a
                              reproducible request to T-Mobile out of band.
                              These are live credentials — do not paste them
                              into a ticket, chat, or commit.

Neither mode sends an activation; ``TMOBILE_PIT_LIVE_CALLS_ENABLED`` is never
consulted.
"""

import argparse
import asyncio
import os
import sys
from urllib.parse import urlsplit

# Add the api/ directory to the path so we can import app modules.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

# Load api/.env so env-driven credentials / IDs are honored.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "api", ".env"))

import httpx  # noqa: E402
from jose import jwt as jose_jwt  # noqa: E402

from app.integrations.tmobile_taap import (  # noqa: E402
    TMobileTAAPClient,
    generate_pop_token,
)

ACTIVATE_PATH = "/wholesale/v1/subscriber/activate"

# Claims whose VALUES are the identifiers we are verifying with T-Mobile.
# These are opaque partner identifiers (e.g. 128), not credentials.
_SAFE_TO_PRINT = ("senderId", "channelId")


def _report_token_request(request: "httpx.Request | None") -> None:
    """Report the OUTBOUND token request — sender-id header + signed PoP set.

    Observes the request actually sent (captured via an httpx event hook) rather
    than re-deriving it, so this cannot silently agree with a broken client.
    Prints no credential material: the sender-id value is an opaque partner
    identifier (128 for Infatrac) and only the PoP's signed header NAMES are
    shown — never the PoP itself or the Basic auth header.
    """
    print("\n=== OUTBOUND TOKEN REQUEST ===")
    if request is None:
        print("  <token request not captured — nothing to report>")
        return

    # sender-id must travel as an unsigned HTTP header (Aman, 2026-07-16).
    present = "sender-id" in request.headers
    print(f"  sender-id present: {present}")
    if present:
        print(f"  sender-id value: {request.headers['sender-id']!r}")

    # The token-request PoP must sign exactly Content-Type;uri;http-method —
    # sender-id must NOT be in the signed set.
    pop = request.headers.get("X-Authorization")
    if pop:
        ehts = jose_jwt.get_unverified_claims(pop).get("ehts", "")
        signed = [name for name in ehts.split(";") if name]
        print(f"  signed_headers={signed}")
        if "sender-id" in signed:
            print(
                "  WARNING: sender-id is in the signed PoP ehts — it must be "
                "UNSIGNED. T-Mobile's PoP validator will reject this request."
            )


def _report_claims(access_token: str) -> int:
    """Print a credential-free summary of the access token's claims.

    Returns a process exit code: 0 when both senderId and channelId are
    present, 1 otherwise.
    """
    claims = jose_jwt.get_unverified_claims(access_token)

    print("\n=== ACCESS TOKEN CLAIMS (values redacted unless safe) ===")
    for name in sorted(claims):
        if name in _SAFE_TO_PRINT:
            print(f"  {name}: {claims[name]}")
        else:
            print(f"  {name}: <redacted>")

    missing = [name for name in _SAFE_TO_PRINT if not claims.get(name)]
    print()
    if missing:
        print(f"MISSING: {', '.join(missing)}")
        print(
            "The authorization server did not mint these claims. Do NOT run a "
            "live activation — it will fail with GENS-0003. Report the missing "
            "claim NAMES (not the token) to T-Mobile."
        )
        return 1

    print("OK: senderId and channelId are present. Cleared for live activation.")
    return 0


def _print_tokens(access_token: str) -> int:
    authorization = f"Bearer {access_token}"
    x_authorization = generate_pop_token(
        ehts_headers=[("Authorization", authorization)]
    )

    print("\n=== T-MOBILE PIT TOKENS — LIVE CREDENTIALS, DO NOT SHARE ===")
    print("Environment: PIT")
    print("HTTP Method: POST")
    print(f"Request Path: {ACTIVATE_PATH}")
    print("\nAuthorization:")
    print(authorization)
    print("\nX-Authorization:")
    print(x_authorization)
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--decode-claims", action="store_true",
        help="Decode the access token and check for senderId / channelId (default)",
    )
    group.add_argument(
        "--print-tokens", action="store_true",
        help="Print raw Authorization / X-Authorization header values",
    )
    args = parser.parse_args()

    client = TMobileTAAPClient()

    # Capture the real outbound token request so --decode-claims can report the
    # sender-id header and the signed PoP set as actually sent. Pre-seeding the
    # client's HTTP client is the only injection point; TMobileTAAPClient._client()
    # reuses an already-open instance rather than building its own.
    token_path = urlsplit(client.token_url).path
    captured: dict[str, httpx.Request] = {}

    async def _capture(request: httpx.Request) -> None:
        if request.url.path == token_path:
            captured["token"] = request

    client._http = httpx.AsyncClient(
        timeout=30.0, event_hooks={"request": [_capture]}
    )

    try:
        access_token = await client.get_access_token()
        if args.print_tokens:
            return _print_tokens(access_token)
        _report_token_request(captured.get("token"))
        return _report_claims(access_token)
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
