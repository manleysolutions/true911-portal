"""Regenerate the committed T-Mobile PIT success fixture.

The successful 2026-07-21 PIT activation wrote its raw evidence bundle to the
operator's temp directory. That bundle is **not** committed — this script
distills it into the sanitized, masked artifact under
``api/tests/fixtures/`` that the repository keeps as the durable record.

Every identifier that could identify a line is masked to its last four
characters by ``tmobile_evidence.mask_tail``, and the response body is passed
through the same ``_redact_body_text`` used for live captures. No redaction
logic is reimplemented here — this script only supplies the inputs.

The unmasked MSISDN / account ID are deliberately NOT baked into this file;
they live only in ``docs/TMOBILE_PIT_ACTIVATED_SUBSCRIBER_RESTRICTED.md`` and
must be passed on the command line::

    python scripts/tmobile_build_success_fixture.py \
        --iccid <ICCID> --msisdn <MSISDN> --account-id <ACCOUNT_ID>

Re-running with the same inputs is byte-identical — the fixture test fails if
this script and the committed fixture ever drift apart.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from app.integrations.tmobile_evidence import build_success_record  # noqa: E402

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "api", "tests", "fixtures",
    "tmobile_pit_success_20260721T031833Z.json",
)

# Facts reported by the operator from the successful runner invocation.
ACTIVATED_AT_UTC = "2026-07-21T03:18:33.694749Z"
DEPLOYMENT_COMMIT = "1766f51161908d163ba2d3c4a96d1f774782cbfd"
ENDPOINT = "POST /wholesale/v1/subscriber/activation"
HTTP_STATUS = 201
PARTNER_TRANSACTION_ID = "true911-pit-d1475fec-981b-40a7-a27c-d867aab8e7f9"
CORRELATION_ID = "ee790876-7b0a-472e-823e-4b30fbefa88d"
WORK_FLOW_ID = "8a5659f0-16f5-46fb-9a0d-f35bb37fda92_P"
SERVICE_TRANSACTION_ID = "33f2315c-8da4-9bae-b68e-3178a5c7a620"
OAUTH_SERVICE_TRANSACTION_ID = "62f5fd11-7756-953b-b032-e71a14ac118d"

# A value we did not observe is never invented. The callback location was
# configured (activate_subscriber refuses to send without one) but its exact
# value is not reproduced here.
CALLBACK_LOCATION_PLACEHOLDER = "<configured; value not reproduced in this record>"

NOTES = [
    "HTTP 201 with body status=SUCCESS and result code 100.",
    "No Partner Foundation header was configured or transmitted on this request.",
    "partner-id and sender-id were both 128, as on every prior attempt.",
    "The immediately preceding attempts on this same deployed client contract "
    "returned HTTP 400 GENS-0003 Invalid partnerID. T-Mobile Engineering "
    "recreated the gateway configuration shortly before this request.",
    "Root cause inside T-Mobile is not independently observable from the client; "
    "this record asserts only what the client observed.",
    "X-Auth-Originator presence is not reproduced here — it is emitted only when "
    "the OAuth response returned an id_token. Consult the operator's raw bundle.",
    "Exactly one activation was sent. The runner never retries.",
]


def build(iccid: str, msisdn: str, account_id: str) -> dict:
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "<presence only — never recorded>",
        "X-Authorization": "<presence only — never recorded>",
        "X-Correlation-Id": CORRELATION_ID,
        "partner-transaction-id": PARTNER_TRANSACTION_ID,
        "partner-id": "128",
        "sender-id": "128",
        "call-back-location": CALLBACK_LOCATION_PLACEHOLDER,
    }
    return build_success_record(
        activated_at_utc=ACTIVATED_AT_UTC,
        endpoint=ENDPOINT,
        http_status=HTTP_STATUS,
        response_body={
            "status": "SUCCESS",
            "msisdn": msisdn,
            "iccid": iccid,
            "accountId": account_id,
            "result": [{"result": "100", "status": "SUCCESS"}],
        },
        iccid=iccid,
        partner_transaction_id=PARTNER_TRANSACTION_ID,
        correlation_id=CORRELATION_ID,
        work_flow_id=WORK_FLOW_ID,
        service_transaction_id=SERVICE_TRANSACTION_ID,
        oauth_service_transaction_id=OAUTH_SERVICE_TRANSACTION_ID,
        deployment_commit=DEPLOYMENT_COMMIT,
        request_headers=request_headers,
        partner_foundation_header_sent=False,
        notes=NOTES,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iccid", required=True)
    parser.add_argument("--msisdn", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--out", default=FIXTURE_PATH)
    args = parser.parse_args()

    record = build(args.iccid, args.msisdn, args.account_id)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
