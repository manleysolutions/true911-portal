"""READ-ONLY T-Mobile subscriber status query for an already-activated line.

Uses the two read-only operations the TAAP client already supports:

  * ``subscriber_inquiry(msisdn, account_id=...)`` -> ``{subscriber_base}/inquiry``
  * ``query_network(msisdn)``                     -> ``/wholesale/network/v1/query``

**No subscriber state is changed.** This script cannot activate, suspend,
restore, deactivate, or SIM-swap — those methods are not imported here. It sends
only the inquiry/query POSTs above and writes a sanitized evidence bundle using
the same capture pipeline as the activation runner.

Both identifiers must be supplied explicitly; nothing is inferred from env, so
the script cannot be pointed at the wrong line by a stale variable::

    python ../scripts/tmobile_subscriber_status.py \
        --msisdn <MSISDN> --account-id <ACCOUNT_ID> --confirm-read-only

``--confirm-read-only`` is a deliberate speed bump: these calls DO reach
T-Mobile's live PIT gateway. It is not run automatically anywhere.

Note on the ``call-back-location`` header: ``subscriber_inquiry`` and
``query_network`` attach it whenever ``TMOBILE_CALLBACK_LOCATION`` is set, so
the response may ALSO arrive asynchronously at the callback endpoint. There is
no flag to suppress it — the client resolves an empty argument back to the env
var — so unset ``TMOBILE_CALLBACK_LOCATION`` for the run if you need the plain
synchronous form.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "api", ".env"))

from app.integrations.tmobile_evidence import (  # noqa: E402
    EvidenceRecorder,
    _bundle_skeleton,
    _redact_body_text,
    mask_tail,
    render_text_report,
    write_evidence,
)
from app.integrations.tmobile_taap import TMobileTAAPClient  # noqa: E402

import json  # noqa: E402


async def query_status(
    client: TMobileTAAPClient,
    *,
    msisdn: str,
    account_id: str,
    include_network: bool,
    callback_location: str | None,
) -> dict:
    """Run the read-only queries and return a sanitized bundle."""
    bundle = _bundle_skeleton(client, "subscriber-status-readonly")
    bundle["msisdn_masked"] = mask_tail(msisdn)
    bundle["account_id_masked"] = mask_tail(account_id)
    recorder = EvidenceRecorder(env=client.base_url)
    recorder.attach(client)

    results: dict[str, str] = {}
    try:
        inquiry = await client.subscriber_inquiry(
            msisdn, account_id=account_id, callback_location=callback_location
        )
        results["subscriber_inquiry"] = _redact_body_text(json.dumps(inquiry))
        if include_network:
            network = await client.query_network(
                msisdn, callback_location=callback_location
            )
            results["query_network"] = _redact_body_text(json.dumps(network))
        bundle["ok"] = True
    except Exception as exc:
        bundle["ok"] = False
        bundle["error"] = _redact_body_text(str(exc))
    finally:
        bundle["exchanges"] = recorder.finalize()
        await client.close()

    bundle["results"] = results
    bundle["notes"].append(
        "READ-ONLY: only SubscriberInquiry"
        + (" and NetworkQuery" if include_network else "")
        + " were called. No activation, suspension, restoration, deactivation, "
          "or SIM swap was sent."
    )
    return bundle


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--msisdn", required=True,
                   help="Assigned MSISDN. Required explicitly — never inferred.")
    p.add_argument("--account-id", required=True,
                   help="Account ID returned by activation. Required explicitly.")
    p.add_argument("--confirm-read-only", action="store_true",
                   help="Required. Acknowledges these queries reach the live gateway.")
    p.add_argument("--skip-network-query", action="store_true",
                   help="Run SubscriberInquiry only.")
    p.add_argument("--out-dir", default=tempfile.gettempdir())
    return p


async def run(args: argparse.Namespace) -> int:
    if not args.confirm_read_only:
        raise SystemExit(
            "Refusing to send: --confirm-read-only was not passed. "
            "No request was made."
        )

    bundle = await query_status(
        TMobileTAAPClient(),
        msisdn=args.msisdn,
        account_id=args.account_id,
        include_network=not args.skip_network_query,
        callback_location=None,  # resolved from TMOBILE_CALLBACK_LOCATION
    )

    print(render_text_report(bundle))
    for name, body in (bundle.get("results") or {}).items():
        print(f"\n{name}: {body}")
    json_path, txt_path = write_evidence(bundle, args.out_dir)
    print(f"\nEvidence written:\n  {json_path}\n  {txt_path}")
    return 0 if bundle.get("ok") else 1


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
