#!/usr/bin/env python3
"""T-Mobile TAAP authentication test script.

Validates:
1. RSA key loading
2. PoP token generation and structure
3. Access token retrieval (if credentials are configured)
4. First proof API call (SubscriberInquiry) if a test MSISDN is provided

Usage:
    # Validate key + PoP generation only (no T-Mobile credentials needed):
    python scripts/test_tmobile_taap.py --dry-run

    # Full test with credentials:
    python scripts/test_tmobile_taap.py

    # Full test + subscriber inquiry:
    python scripts/test_tmobile_taap.py --msisdn 12125551234

Environment variables required (set in .env or shell):
    TMOBILE_CONSUMER_KEY
    TMOBILE_CONSUMER_SECRET
    TMOBILE_PRIVATE_KEY_PATH  (or TMOBILE_PRIVATE_KEY_PEM)
    TMOBILE_PARTNER_ID
    TMOBILE_SENDER_ID
    TMOBILE_ACCOUNT_ID
    TMOBILE_ENV=pit           (default)
"""

import argparse
import asyncio
import json
import os
import sys
import time

# Add the api/ directory to Python path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

# Load .env file
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "api", ".env"))


def step(msg: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}")


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


async def main():
    parser = argparse.ArgumentParser(description="T-Mobile TAAP test")
    parser.add_argument("--dry-run", action="store_true", help="Only test key loading and PoP generation")
    parser.add_argument("--msisdn", help="Test MSISDN for SubscriberInquiry call")
    parser.add_argument("--activate", action="store_true", help="Test Activation API (requires --iccid, --market-zip, --product-id)")
    parser.add_argument("--iccid", help="SIM ICCID for activation test")
    parser.add_argument("--market-zip", help="5-digit market ZIP for activation")
    parser.add_argument("--product-id", help="T-Mobile product ID for activation")
    args = parser.parse_args()

    from app.config import settings

    # ── Step 1: Check configuration ────────────────────────────────────
    step("Step 1: Configuration Check")

    env = settings.TMOBILE_ENV
    info(f"Environment: {env}")
    info(f"Consumer Key: {'***' + settings.TMOBILE_CONSUMER_KEY[-4:] if len(settings.TMOBILE_CONSUMER_KEY) > 4 else '(not set)' if not settings.TMOBILE_CONSUMER_KEY else '(short)'}")
    info(f"Consumer Secret: {'***' + settings.TMOBILE_CONSUMER_SECRET[-4:] if len(settings.TMOBILE_CONSUMER_SECRET) > 4 else '(not set)' if not settings.TMOBILE_CONSUMER_SECRET else '(short)'}")
    info(f"Partner ID: {settings.TMOBILE_PARTNER_ID or '(not set)'}")
    info(f"Sender ID: {settings.TMOBILE_SENDER_ID or '(not set)'}")
    info(f"Account ID: {settings.TMOBILE_ACCOUNT_ID or '(not set)'}")
    info(f"Private Key Path: {settings.TMOBILE_PRIVATE_KEY_PATH or '(not set)'}")
    info(f"Private Key PEM: {'(set, {0} chars)'.format(len(settings.TMOBILE_PRIVATE_KEY_PEM)) if settings.TMOBILE_PRIVATE_KEY_PEM else '(not set)'}")

    has_creds = bool(settings.TMOBILE_CONSUMER_KEY and settings.TMOBILE_CONSUMER_SECRET)
    has_key = bool(settings.TMOBILE_PRIVATE_KEY_PATH or settings.TMOBILE_PRIVATE_KEY_PEM)

    if has_creds:
        ok("Consumer credentials configured")
    else:
        info("Consumer credentials not yet configured (waiting for T-Mobile)")

    if has_key:
        ok("Private key configured")
    else:
        info("Private key not configured")

    # ── Step 2: RSA Key Loading ────────────────────────────────────────
    step("Step 2: RSA Key Loading")

    if not has_key:
        info("Skipping — no private key configured.")
        info("Generate one with:")
        info("  openssl genrsa -out tmobile_private.pem 2048")
        info("  openssl rsa -in tmobile_private.pem -pubout -out tmobile_public.pem")
        if args.dry_run:
            # Generate a temporary key for dry-run testing
            info("Generating temporary RSA key for dry-run test...")
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            os.environ["TMOBILE_PRIVATE_KEY_PEM"] = pem.decode()
            # Force settings reload
            settings.__dict__.pop("TMOBILE_PRIVATE_KEY_PEM", None)
            object.__setattr__(settings, "TMOBILE_PRIVATE_KEY_PEM", pem.decode())
            ok("Temporary key generated for dry-run")
    else:
        try:
            from app.integrations.tmobile_taap import _load_private_key
            pem = _load_private_key()
            ok(f"Private key loaded ({len(pem)} bytes)")
            if "BEGIN RSA PRIVATE KEY" in pem or "BEGIN PRIVATE KEY" in pem:
                ok("Key format looks valid (PEM)")
            else:
                fail("Key doesn't look like a PEM private key")
        except Exception as exc:
            fail(f"Key loading error: {exc}")
            return

    # ── Step 3: PoP Token Generation ───────────────────────────────────
    step("Step 3: PoP Token Generation")

    try:
        from app.integrations.tmobile_taap import (
            generate_pop_token,
            PIT_TOKEN_URL,
            PROD_TOKEN_URL,
        )

        _env = settings.TMOBILE_ENV.lower()
        test_uri = settings.TMOBILE_TOKEN_URL or (PIT_TOKEN_URL if _env == "pit" else PROD_TOKEN_URL)
        info(f"PoP test URI: {test_uri}")
        pop = generate_pop_token(
            ehts_headers=[("Content-Type", "application/json")],
        )

        ok(f"PoP token generated ({len(pop)} chars)")

        # Decode and inspect (without verification — we just want structure)
        from jose import jwt as jose_jwt
        header = jose_jwt.get_unverified_header(pop)
        claims = jose_jwt.get_unverified_claims(pop)

        ok(f"Header: alg={header.get('alg')}, typ={header.get('typ')}")
        ok(f"Claims: iss={claims.get('iss', '(none)')[:20]}...")
        ok(f"  iat={claims.get('iat')}, exp={claims.get('exp')}")
        ok(f"  jti={claims.get('jti')}")
        ok(f"  ehts={claims.get('ehts')}")
        if claims.get("edts"):
            ok(f"  edts={claims['edts'][:24]}... (ehts header-pairs hash, base64url)")
        ok("PoP token structure is valid")

    except Exception as exc:
        fail(f"PoP generation error: {exc}")
        import traceback
        traceback.print_exc()
        return

    if args.dry_run:
        step("Dry Run Complete")
        ok("Key loading and PoP generation work correctly.")
        ok("Set TMOBILE_CONSUMER_KEY, TMOBILE_CONSUMER_SECRET, and configure")
        ok("your real RSA key to proceed with live PIT testing.")
        return

    # ── Step 4: Access Token ───────────────────────────────────────────
    step("Step 4: Access Token Retrieval")

    if not has_creds:
        info("Skipping — consumer credentials not configured.")
        return

    try:
        from app.integrations.tmobile_taap import TMobileTAAPClient
        client = TMobileTAAPClient()

        info(f"Token URL: {client.token_url}")
        info(f"Base URL: {client.base_url}")

        token = await client.get_access_token()
        ok(f"Access token obtained ({len(token)} chars)")
        ok(f"  Preview: {token[:30]}...")

    except Exception as exc:
        fail(f"Token retrieval failed: {exc}")
        info("This is expected if T-Mobile hasn't issued your credentials yet,")
        info("or if your public key hasn't been registered with T-Mobile.")
        import traceback
        traceback.print_exc()
        return

    # ── Step 5: Proof API Call ─────────────────────────────────────────
    CALLBACK_URL = "https://pit-api.manleysolutions.com/tmobile/wholesale/callback"

    if args.activate:
        if not args.iccid or not args.market_zip or not args.product_id:
            fail("--activate requires --iccid, --market-zip, and --product-id")
            return
        step(f"Step 5: Activation for iccid={args.iccid} marketZIP={args.market_zip} productId={args.product_id}")
        info(f"call-back-location: {CALLBACK_URL}")
        try:
            payload = {
                "marketZIP": args.market_zip,
                "ICCID": args.iccid,
                "productId": args.product_id,
            }
            result = await client.post_json(
                "/wholesale/subscriber/v2/activate",
                payload,
                extra_headers={"call-back-location": CALLBACK_URL},
            )
            ok("Activation request accepted.")
            print(json.dumps(result, indent=2, default=str)[:2000])
        except Exception as exc:
            fail(f"Activation failed: {exc}")
            import traceback
            traceback.print_exc()
    elif args.msisdn:
        step(f"Step 5: SubscriberInquiry for {args.msisdn}")
        try:
            result = await client.subscriber_inquiry(args.msisdn)
            ok("SubscriberInquiry succeeded!")
            print(json.dumps(result, indent=2, default=str)[:1000])
        except Exception as exc:
            fail(f"SubscriberInquiry failed: {exc}")
            import traceback
            traceback.print_exc()
    else:
        step("Step 5: Proof API Call")
        info("Skipped — pass --msisdn <number> to test a live API call.")

    # Cleanup
    try:
        await client.close()
    except Exception:
        pass

    step("Test Complete")
    ok("T-Mobile TAAP integration is ready for PIT testing.")


if __name__ == "__main__":
    asyncio.run(main())
