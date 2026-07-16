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
import hashlib
import json
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
    create_api_pop_token,
)

ACTIVATE_PATH = "/wholesale/v1/subscriber/activate"

# Claims whose VALUES are the identifiers we are verifying with T-Mobile.
# These are opaque partner identifiers (e.g. 128), not credentials.
_SAFE_TO_PRINT = ("senderId", "channelId")


# The authoritative OAuth signed set, per T-Mobile's supplied PoP Token Builder.
EXPECTED_OAUTH_EHTS = "Content-Type;Authorization;uri;http-method;body"


def _report_token_request(
    request: "httpx.Request | None", id_token_present: bool
) -> None:
    """Report the OUTBOUND token request against the reference contract.

    Observes the request actually sent (captured via an httpx event hook) rather
    than re-deriving it, so this cannot silently agree with a broken client.

    Prints NO credential material. The body carries the cnf public key, so only
    its byte length and SHA-256 are shown; the Basic Authorization value, the PoP
    JWT, and the ID token are never printed. sender-id / grant-type are opaque
    non-secret routing values and are shown verbatim.
    """
    print("\n=== OAUTH REQUEST CONTRACT ===")
    if request is None:
        print("  <token request not captured — nothing to report>")
        return

    body = request.content or b""
    print(f"  body bytes: {len(body)}")
    print(f"  body SHA-256: {hashlib.sha256(body).hexdigest()}")
    try:
        body_keys = sorted(json.loads(body.decode() or "{}"))
    except ValueError:
        body_keys = ["<unparseable>"]
    print(f"  body properties: {body_keys}  (expected ['cnf'])")

    # grant type must be an unsigned wire header, not a body property.
    grant_type = request.headers.get("grant-type")
    print(f"  grant-type present: {grant_type is not None}")
    if grant_type:
        print(f"  grant-type value: {grant_type!r}")

    # sender-id must travel as an unsigned HTTP header (Aman, confirmed).
    sender_present = "sender-id" in request.headers
    print(f"  sender-id present: {sender_present}")
    if sender_present:
        print(f"  sender-id value: {request.headers['sender-id']!r}")

    print(f"  id_token returned: {id_token_present}")

    pop = request.headers.get("X-Authorization")
    if not pop:
        print("  WARNING: no X-Authorization PoP on the token request")
        return

    ehts = jose_jwt.get_unverified_claims(pop).get("ehts", "")
    signed = [name for name in ehts.split(";") if name]
    print(f"  OAuth EHTS: {ehts}")
    print(f"  signed_headers={signed}")
    print(f"  EHTS matches reference: {ehts == EXPECTED_OAUTH_EHTS}")
    print(f"  sender-id unsigned: {'sender-id' not in signed}")

    if ehts != EXPECTED_OAUTH_EHTS:
        print(f"  WARNING: expected {EXPECTED_OAUTH_EHTS!r}")
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


def _print_tokens(
    access_token: str, oauth_pop: str | None, body_str: str | None
) -> int:
    """Operator-only: print the live header values for a hand-run request.

    Explicitly separates the three distinct values so they cannot be confused at
    the point of use. The Basic Authorization value and the private key are never
    printed by any mode.
    """
    authorization = f"Bearer {access_token}"

    print("\n=== T-MOBILE PIT TOKENS — LIVE CREDENTIALS, DO NOT SHARE ===")
    print("Environment: PIT")
    print("HTTP Method: POST")
    print(f"Request Path: {ACTIVATE_PATH}")
    print("PoP lifetime: 60s, single-use — regenerate if it expires.")

    print("\n--- [1] Resource Authorization (Bearer access token) ---")
    print(authorization)

    print("\n--- [2] OAuth X-Authorization (PoP that fetched the token above) ---")
    print("Already spent on the token request; shown for reference only.")
    print(oauth_pop if oauth_pop else "<not captured>")

    print("\n--- [3] Resource X-Authorization (PoP for the activation POST) ---")
    if body_str is None:
        # The resource PoP signs the exact body, so one cannot be produced
        # without knowing it. Emitting a PoP over a guessed body would be worse
        # than emitting none: it would look usable and fail at the gateway.
        print(
            "SKIPPED — the resource PoP signs the exact request body, so it is\n"
            "only valid for one specific payload. Re-run with --iccid <ICCID> to\n"
            "generate a PoP bound to that activation body."
        )
        return 0

    resource_pop = create_api_pop_token(
        content_type="application/json",
        authorization=authorization,
        uri=ACTIVATE_PATH,
        http_method="POST",
        body=body_str,
    )
    print(f"Signs: {EXPECTED_OAUTH_EHTS}")
    print("Valid ONLY for the exact body it was generated against — if the body")
    print("changes by even one byte of whitespace, the signature is invalid.")
    print(f"Bound body SHA-256: {hashlib.sha256(body_str.encode()).hexdigest()}")
    print(resource_pop)
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
        help="Operator-only: print raw Authorization / X-Authorization values",
    )
    parser.add_argument(
        "--iccid",
        help="With --print-tokens: bind the resource PoP to this ICCID's "
             "activation body (the PoP signs the exact body).",
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
        token_req = captured.get("token")
        oauth_pop = token_req.headers.get("X-Authorization") if token_req else None

        if args.print_tokens:
            body_str = None
            if args.iccid:
                # Serialize exactly as the client does, so the PoP this prints
                # matches the bytes an activation would actually send.
                body_str = json.dumps(
                    client._build_activation_payload(args.iccid),
                    separators=(",", ":"),
                )
            return _print_tokens(access_token, oauth_pop, body_str)

        _report_token_request(token_req, id_token_present=bool(client._id_token))
        return _report_claims(access_token)
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
