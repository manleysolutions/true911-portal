"""Compare our sanitized T-Mobile evidence against a known-good reference.

Answers: **where does our request differ from T-Mobile's?**

Inputs are sanitized evidence JSON files — the bundles written by
``tmobile_pit_evidence.py``. No secrets or tokens are read or printed: the
comparison works on header names, allowlisted header values, ehts order, PoP
structure, and body digests.

Usage::

    # Compare our OAuth request against a reference T-Mobile supplies later:
    python compare_tmobile_request_contract.py \
        --ours /tmp/tmobile-pit-evidence-<UTC>.json \
        --reference /tmp/tmobile-reference.json

    # Without a reference, check our own bundle against the known contract:
    python compare_tmobile_request_contract.py --ours /tmp/tmobile-pit-evidence-<UTC>.json

The reference file may be either a full evidence bundle or a single sanitized
request capture. Ask T-Mobile for a SANITIZED capture — never a real token.

Exits non-zero when differences are found.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from app.integrations.tmobile_contract_compare import (  # noqa: E402
    compare_requests,
    render_report,
)

# The contract T-Mobile supplied on 2026-07-16. Used when no reference file is
# given, so the tool is useful before Aman sends a capture.
EXPECTED_EHTS_NAMES = ["Content-Type", "Authorization", "uri", "http-method", "body"]
EXPECTED_JWT_HEADER = {"alg": "RS256", "typ": "JWT"}


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _extract_request(doc: dict, *, index: int) -> dict:
    """Accept either a full evidence bundle or a bare request capture."""
    if "exchanges" in doc:
        exchanges = doc.get("exchanges") or []
        if not exchanges:
            raise SystemExit("evidence bundle contains no exchanges")
        if index >= len(exchanges):
            raise SystemExit(
                f"--index {index} out of range: bundle has {len(exchanges)} exchange(s)"
            )
        return exchanges[index].get("request") or {}
    if "request" in doc:
        return doc["request"]
    return doc


def _synthetic_reference(ours: dict) -> dict:
    """Build a reference from the known contract when no file is supplied.

    Only the fields the contract actually pins are populated — the rest are
    copied from ours so they do not show up as spurious differences. Fields the
    contract does not cover are reported as `assumption`, never invented.
    """
    return {
        "method": ours.get("method"),
        "path": ours.get("path"),
        "url": ours.get("url"),
        "headers": ours.get("headers"),
        "body": ours.get("body"),
        "pop": {
            "present": True,
            "jwt_header": EXPECTED_JWT_HEADER,
            "ehts_names": EXPECTED_EHTS_NAMES,
            "claims": {k: None for k in ("iat", "exp", "ehts", "edts", "jti", "v")},
            "lifetime_seconds": 60,
            "edts": None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ours", required=True, help="Our sanitized evidence JSON.")
    parser.add_argument(
        "--reference",
        help="T-Mobile's sanitized reference JSON. Omit to check against the "
             "known 2026-07-16 contract instead.",
    )
    parser.add_argument("--index", type=int, default=0,
                        help="Which exchange to compare (default: 0, the first).")
    args = parser.parse_args()

    ours = _extract_request(_load(args.ours), index=args.index)

    if args.reference:
        reference = _extract_request(_load(args.reference), index=0)
        source = args.reference
    else:
        reference = _synthetic_reference(ours)
        source = "built-in 2026-07-16 contract (PoP shape only)"
        print(
            "NOTE: no --reference given. Comparing the PoP shape against the\n"
            "      known contract only. Headers/body are NOT independently\n"
            "      verified — supply a sanitized T-Mobile capture for that.\n"
        )

    print(f"ours:      {args.ours}")
    print(f"reference: {source}\n")

    diffs = compare_requests(ours, reference)
    print(render_report(diffs))
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
