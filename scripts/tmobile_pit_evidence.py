"""T-Mobile PIT evidence runner — sanitized bundles for T-Mobile Engineering.

Produces a JSON + text evidence bundle that is safe to paste into an email to
Aman while carrying everything needed to diagnose a wire-contract mismatch.
No tokens, keys, Basic credentials, or body content ever enter the output.

Modes (exactly one):

  --token-only          One OAuth token request. NO activation, no resource call.
  --activation-preview  Builds the exact compact activation body, header summary,
                        body hash, and expected PoP claims. Sends NOTHING.
  --activate            Sends EXACTLY ONE activation. Never retries. Requires
                        BOTH --confirm-live AND TMOBILE_PIT_LIVE_CALLS_ENABLED=true.

Examples::

    # Token-only contract check (safe, no activation):
    python ../scripts/tmobile_pit_evidence.py --token-only

    # Dry run — build the activation without sending it:
    python ../scripts/tmobile_pit_evidence.py --activation-preview \
        --iccid <ICCID> --market-zip 30346

    # One-shot live activation, only while T-Mobile is watching:
    python ../scripts/tmobile_pit_evidence.py --activate --confirm-live \
        --iccid <ICCID> --market-zip 30346

Exits non-zero when the exchange failed — the bundle is still written, with every
correlation id preserved (that is the deliverable for a 400).
"""

import argparse
import asyncio
import os
import sys
import tempfile

# Add the api/ directory to the path so we can import app modules.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "api", ".env"))

from app.integrations.tmobile_evidence import (  # noqa: E402
    render_text_report,
    run_activation,
    run_activation_preview,
    run_token_only,
    write_evidence,
)
from app.integrations.tmobile_taap import TMobileTAAPClient  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--token-only", action="store_true",
                      help="One OAuth token request; no activation.")
    mode.add_argument("--activation-preview", action="store_true",
                      help="Build the activation request without sending it.")
    mode.add_argument("--activate", action="store_true",
                      help="Send exactly one live activation (requires --confirm-live).")

    parser.add_argument("--confirm-live", action="store_true",
                        help="Required by --activate. Without it, nothing is sent.")
    parser.add_argument("--iccid", help="ICCID (required by --activation-preview/--activate).")
    parser.add_argument("--market-zip", help="PIT market ZIP, e.g. 30346 or 30338.")
    parser.add_argument(
        "--out-dir", default=tempfile.gettempdir(),
        help="Directory for the evidence bundle (default: system temp dir).",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    if (args.activation_preview or args.activate) and not args.iccid:
        raise SystemExit("--iccid is required for --activation-preview and --activate")
    if args.activate and not args.market_zip:
        raise SystemExit("--market-zip is required for --activate")

    client = TMobileTAAPClient()

    if args.token_only:
        bundle = await run_token_only(client)
    elif args.activation_preview:
        bundle = await run_activation_preview(
            client, iccid=args.iccid, market_zip=args.market_zip
        )
    else:
        bundle = await run_activation(
            client, iccid=args.iccid, market_zip=args.market_zip,
            confirm_live=args.confirm_live,
        )

    print(render_text_report(bundle))
    json_path, txt_path = write_evidence(bundle, args.out_dir)
    print(f"\nEvidence written:\n  {json_path}\n  {txt_path}")
    # Non-zero on failure — but only AFTER the bundle is safely on disk.
    return 0 if bundle.get("ok") else 1


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
