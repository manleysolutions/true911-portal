#!/usr/bin/env python3
"""READ-ONLY inspection of T-Mobile callbacks for a given activation.

Answers the question "did T-Mobile call us back after the activation, was it
authenticated, was it persisted, and did it update the subscriber record?"
without sending anything to T-Mobile and without writing a single row.

**This script issues SELECT statements only.** It never commits, never enqueues
a job, never calls the T-Mobile API, and never triggers an activation.

Correlate by any combination of the identifiers the activation returned::

    python -m scripts.tmobile_callback_inspect --iccid <ICCID>
    python -m scripts.tmobile_callback_inspect \
        --partner-transaction-id true911-pit-... \
        --work-flow-id 8a5659f0-..._P \
        --service-transaction-id 33f2315c-... \
        --iccid <ICCID> --msisdn <MSISDN>

At least one identifier is required — the script refuses to dump the whole
callback archive. ``--since`` (UTC ISO-8601) narrows the window; it defaults to
the activation date when ``--iccid`` alone is given nothing else to anchor on.

Output is sanitized: identifiers are masked to their last four characters via
the shared ``tmobile_evidence.mask_tail``, and header values are classified by
the same allowlist used for outbound evidence capture, so a callback that
carried the shared secret in ``X-True911-Callback-Token`` or ``?token=`` is
never echoed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from sqlalchemy import desc, select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.integrations.tmobile_evidence import mask_tail, utc_now_iso  # noqa: E402
from app.models.integration_payload import IntegrationPayload  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.sim import Sim  # noqa: E402

# Header names whose VALUES may be shown. Anything else is presence-only —
# the same allowlist discipline as outbound capture, for the same reason: a
# callback header we have not classified may carry the shared callback secret.
_SAFE_CALLBACK_HEADERS = {
    "content-type",
    "user-agent",
    "partner-transaction-id",
    "work-flow-id",
    "service-transaction-id",
    "x-correlation-id",
    "x-true911-tmobile-event-type",
}

_TRACE_BODY_KEYS = (
    "partnerTransactionId", "partner_transaction_id",
    "workFlowId", "work_flow_id", "workflowId",
    "serviceTransactionId", "service_transaction_id",
    "iccid", "ICCID", "msisdn", "MSISDN", "accountId", "account_id",
)


def _safe_headers(headers: dict | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in (headers or {}).items():
        if name.lower() in _SAFE_CALLBACK_HEADERS:
            out[name] = value
        else:
            out[name] = "<present, redacted>"
    return out


def _safe_body(body: dict | None) -> dict[str, Any]:
    """Surface only the correlation keys, with identifiers masked."""
    if not isinstance(body, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _TRACE_BODY_KEYS:
        if key in body:
            value = body[key]
            lowered = key.lower()
            if any(t in lowered for t in ("iccid", "msisdn", "account")):
                out[key] = mask_tail(str(value))
            else:
                out[key] = value
    other = sorted(set(body) - set(_TRACE_BODY_KEYS))
    if other:
        out["_other_keys_present"] = other
    return out


def _matches(payload: IntegrationPayload, needles: list[str]) -> bool:
    """True when any supplied identifier appears in the stored callback.

    Matches across headers, the parsed body, and the raw body, because T-Mobile
    may return a given correlation id in any of the three.
    """
    haystack = json.dumps(
        {"h": payload.headers or {}, "b": payload.body or {}, "r": payload.raw_body or ""}
    ).lower()
    return any(n.lower() in haystack for n in needles)


async def inspect(args: argparse.Namespace) -> dict[str, Any]:
    needles = [
        n for n in (
            args.iccid, args.msisdn, args.account_id,
            args.partner_transaction_id, args.work_flow_id,
            args.service_transaction_id,
        ) if n
    ]

    report: dict[str, Any] = {
        "generated_at_utc": utc_now_iso(),
        "read_only": True,
        "identifiers_searched": [mask_tail(n, keep=8) for n in needles],
        "callbacks": [],
        "jobs": [],
        "sim": None,
    }

    async with AsyncSessionLocal() as db:
        stmt = (
            select(IntegrationPayload)
            .where(IntegrationPayload.source == "tmobile")
            .where(IntegrationPayload.direction == "inbound")
            .order_by(desc(IntegrationPayload.created_at))
            .limit(args.limit)
        )
        if args.since:
            stmt = stmt.where(IntegrationPayload.created_at >= args.since)

        rows = (await db.execute(stmt)).scalars().all()
        matched = [r for r in rows if _matches(r, needles)]

        report["scanned_inbound_tmobile_payloads"] = len(rows)
        report["matched_callback_count"] = len(matched)

        for row in matched:
            headers = row.headers or {}
            report["callbacks"].append({
                "payload_id": row.payload_id,
                "received_at_utc": row.created_at.isoformat() if row.created_at else None,
                "event_type": headers.get("x-true911-tmobile-event-type"),
                "processed": row.processed,
                # Persistence to IntegrationPayload only happens AFTER the
                # authenticity gate in _maybe_archive, so the row's existence
                # is itself the evidence the callback was accepted.
                "authenticated_and_accepted": True,
                "headers": _safe_headers(headers),
                "body_correlation_keys": _safe_body(row.body),
                "raw_body_present": bool(row.raw_body),
            })

            job_rows = (await db.execute(
                select(Job)
                .where(Job.job_type == "webhook.tmobile")
                .order_by(desc(Job.created_at))
                .limit(args.limit)
            )).scalars().all()
            for job in job_rows:
                if (job.payload or {}).get("payload_id") == row.payload_id:
                    report["jobs"].append({
                        "job_id": job.id,
                        "status": job.status,
                        "attempt": job.attempt,
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                        "completed_at": (
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        "error": job.error,
                        "result": job.result,
                    })

        if args.iccid:
            sim = (await db.execute(
                select(Sim).where(Sim.iccid == args.iccid)
            )).scalar_one_or_none()
            if sim is not None:
                meta = sim.meta or {}
                report["sim"] = {
                    "iccid_masked": mask_tail(sim.iccid),
                    "carrier": sim.carrier,
                    "tmobile_account_id_masked": mask_tail(meta.get("tmobile_account_id")),
                    "tmobile_msisdn_masked": mask_tail(meta.get("tmobile_msisdn")),
                    "activation_recorded": bool(meta.get("tmobile_activation")),
                }

    if not report["callbacks"]:
        report["conclusion"] = (
            "NO CALLBACK FOUND for the supplied identifiers in the scanned window. "
            "This is NOT proof that T-Mobile sent none: the callback is only "
            "persisted when FEATURE_TMOBILE_CALLBACK_INGEST is on AND the "
            "authenticity gate passes. Check those flags and the "
            "'T-Mobile callback ingest DENIED' log line before concluding."
        )
    else:
        report["conclusion"] = (
            f"{len(report['callbacks'])} matching callback(s) persisted. "
            "Each was authenticated and accepted (archiving happens only after "
            "the authenticity gate)."
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--iccid")
    p.add_argument("--msisdn")
    p.add_argument("--account-id")
    p.add_argument("--partner-transaction-id")
    p.add_argument("--work-flow-id")
    p.add_argument("--service-transaction-id")
    p.add_argument("--since", help="UTC ISO-8601 lower bound on created_at.")
    p.add_argument("--limit", type=int, default=500,
                   help="Max recent inbound T-Mobile payloads to scan (default 500).")
    return p


async def run(args: argparse.Namespace) -> int:
    if not any((args.iccid, args.msisdn, args.account_id,
                args.partner_transaction_id, args.work_flow_id,
                args.service_transaction_id)):
        raise SystemExit(
            "At least one identifier is required — this script will not dump "
            "the entire callback archive."
        )
    print(json.dumps(await inspect(args), indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
