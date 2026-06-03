#!/usr/bin/env python3
"""T-Mobile activation DRY RUN — print the exact payload + headers, send NOTHING.

This command builds the activation request that ``activate_subscriber`` would
POST to T-Mobile and prints it for review. It NEVER contacts T-Mobile: no OAuth
token is fetched, no PoP token is signed, no socket is opened. The two
credential-bearing headers (Authorization / X-Authorization) are shown as
redacted placeholders so the output is safe to paste into a ticket or share.

It does NOT require any T-Mobile credentials or RSA key to run.

PIT onboarding defaults (override with flags or env):
    ICCID          = 8901260963132697538            (one of the 50 PIT ICCIDs)
    marketZip      = 30346                          (TMOBILE_MARKET_ZIP; PIT: 30346/30338)
    language       = ENGL                           (TMOBILE_LANGUAGE)
    baseProductId  = Infatrac Internet Access Plan  (TMOBILE_BASE_PRODUCT_ID)
    wps            = 00011586                        (TMOBILE_WPS)
    product[]      = NOROAM / ADD                    (PIT default sub-product)

Usage:
    cd api
    python ../scripts/tmobile_activation_dryrun.py
    python ../scripts/tmobile_activation_dryrun.py --iccid 8901... --market-zip 30338

This script can never activate anything — there is no flag to make it send.
Use scripts/test_tmobile_taap.py --activate for the live call (requires creds
AND TMOBILE_PIT_LIVE_CALLS_ENABLED=true).
"""

import argparse
import json
import os
import sys

# Add the api/ directory to the path so we can import app modules.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

# Load api/.env so env-driven paths / IDs are honored.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "api", ".env"))

# PIT onboarding test values (see module docstring).
DEFAULT_MARKET_ZIP = "30346"
DEFAULT_ICCID = "8901260963132697538"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the exact T-Mobile activation payload + headers without sending."
    )
    parser.add_argument("--iccid", default=DEFAULT_ICCID, help="SIM ICCID (default: PIT test ICCID)")
    parser.add_argument("--market-zip", default=DEFAULT_MARKET_ZIP, help="5-digit market ZIP (default: 30346; PIT: 30346/30338)")
    parser.add_argument("--language", help="activation language (default: TMOBILE_LANGUAGE / ENGL)")
    parser.add_argument("--base-product-id",
                        help="baseProduct.baseProductId (default: TMOBILE_BASE_PRODUCT_ID / 'Infatrac Internet Access Plan')")
    parser.add_argument("--wps", help="baseProduct.wps (default: TMOBILE_WPS / 00011586)")
    parser.add_argument("--callback-location",
                        help="call-back-location header (default: TMOBILE_CALLBACK_LOCATION env)")
    args = parser.parse_args()

    from app.integrations.tmobile_taap import TMobileTAAPClient

    client = TMobileTAAPClient()
    preview = client.build_activation_preview(
        iccid=args.iccid,
        market_zip=args.market_zip,
        language=args.language,
        base_product_id=args.base_product_id,
        wps=args.wps,
        callback_location=args.callback_location,
    )

    print("=" * 70)
    print("  T-MOBILE ACTIVATION — DRY RUN (nothing sent)")
    print("=" * 70)
    print(f"  env:               {os.environ.get('TMOBILE_ENV', 'pit')}")
    print(f"  {preview['method']} {preview['url']}")
    print(f"  path (env-driven): {preview['path']}")
    print()
    print("  Payload (exact wire body):")
    print(_indent(json.dumps(preview["payload"], indent=2, ensure_ascii=False)))
    print()
    print("  Headers (Authorization / X-Authorization redacted):")
    print(_indent(json.dumps(preview["headers"], indent=2, ensure_ascii=False)))
    print()
    print(f"  PoP-signed ehts at send time: {preview['pop_signed_ehts']}")
    print()
    for note in preview["notes"]:
        print(f"  ⚠  {note}")
    print("=" * 70)
    return 0


def _indent(text: str, pad: str = "    ") -> str:
    return "\n".join(pad + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
