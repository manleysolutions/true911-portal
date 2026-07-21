"""T-Mobile PIT certification harness — the single operator entry point.

One tool for every PIT API call, with the safety gates in one place instead of
scattered across ad hoc scripts.

    python ../scripts/tmobile_pit.py operations
    python ../scripts/tmobile_pit.py show <operation>
    python ../scripts/tmobile_pit.py allowlists
    python ../scripts/tmobile_pit.py state --iccid <ICCID>
    python ../scripts/tmobile_pit.py preview <operation> --iccid <ICCID> [...]
    python ../scripts/tmobile_pit.py run <operation> --iccid <ICCID> --confirm-live [...]

Safety model — every gate must pass, and each is independent:

1. **Preview is the default.** ``preview`` never opens a socket. ``run`` is the
   only subcommand that can send, and it is never the default.
2. **Provenance.** An operation whose path T-Mobile never supplied is BLOCKED,
   in preview and in run alike (see ``tmobile_operations``). Most operations are
   currently blocked; ``operations`` shows exactly which and why.
3. **Live switch.** ``TMOBILE_PIT_LIVE_CALLS_ENABLED=true`` is required to send.
4. **--confirm-live** for any state-changing operation.
5. **--confirm-destructive** *and* an operator ``--reason`` for destructive ones.
6. **--confirm-protected** additionally, for the first-activation ICCID.
7. **Allowlist tier.** The ICCID must be nominated at the operation's risk tier.
8. **State machine.** The transition must be legal from the last known state,
   and a pending request blocks a duplicate.

Exactly one request per invocation. Nothing here retries a state-changing call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "api", ".env"))

from app.integrations.tmobile_contracts import (  # noqa: E402
    ResponseKind,
    TMobileResponseEnvelope,
)
from app.integrations.tmobile_evidence import (  # noqa: E402
    EvidenceRecorder,
    _bundle_skeleton,
    _redact_body_text,
    mask_tail,
    render_text_report,
    utc_now_iso,
    write_evidence,
)
from app.integrations.tmobile_lifecycle import (  # noqa: E402
    PROTECTED_ICCIDS,
    AllowlistError,
    AllowlistPolicy,
    InvalidTransition,
    LifecycleState,
    is_confirmed_state,
    next_state,
)
from app.integrations.tmobile_contracts import (  # noqa: E402
    SubscriberInquiryRequest,
    TMobileRequestError,
)
from app.integrations.tmobile_pit_authorization import (  # noqa: E402
    AuthorizationError,
    clear_authorization,
    grant_single_run,
)
from app.integrations.tmobile_operations import (  # noqa: E402
    OPERATIONS,
    Classification,
    OperationBlocked,
    blocked_operations,
    get_operation,
    require_sendable,
    sendable_operations,
)
from app.integrations.tmobile_taap import TMobileTAAPClient  # noqa: E402


# ── Informational subcommands (never touch the network) ─────────────────────

def cmd_operations(args: argparse.Namespace) -> int:
    print("T-MOBILE PIT OPERATION INVENTORY")
    print("=" * 72)
    print(f"{'OPERATION':<24}{'CLASS':<6}{'SENDABLE':<10}PROVENANCE")
    print("-" * 72)
    for op in OPERATIONS:
        mark = "YES" if op.is_sendable else "BLOCKED"
        print(f"{op.name:<24}{op.classification.value:<6}{mark:<10}"
              f"{op.provenance.value}")
    print()
    print(f"Sendable: {len(sendable_operations())} · "
          f"Blocked: {len(blocked_operations())} of {len(OPERATIONS)}")
    print()
    print("Class A=read-only  B=reversible  C=destructive  D=unknown")
    print("A BLOCKED operation has no T-Mobile-supplied contract in this "
          "repository.\nRun `show <operation>` for the exact questions T-Mobile "
          "must answer.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    op = get_operation(args.operation)
    print(f"OPERATION: {op.name}")
    print("=" * 72)
    fields = [
        ("client method", op.client_method),
        ("method / path", f"{op.http_method} {op.path}"),
        ("path source", op.path_source),
        ("classification", f"{op.classification.name} ({op.classification.value})"),
        ("provenance", op.provenance.value),
        ("SENDABLE", "yes" if op.is_sendable else "NO — BLOCKED"),
        ("request schema", op.request_schema),
        ("response schema", op.response_schema),
        ("callback behavior", op.callback_behavior),
        ("required headers", ", ".join(op.required_headers)),
        ("PoP ehts", op.pop_ehts),
        ("body signed", str(op.body_signed)),
        ("sync/async", op.synchronous),
        ("reversibility", op.reversibility),
        ("prerequisite state", op.prerequisite_state),
        ("PIT restrictions", op.pit_restrictions),
        ("implementation", op.implementation_status),
        ("test status", op.test_status),
    ]
    for label, value in fields:
        print(f"  {label:<20} {value}")
    if op.blocking_questions:
        print("\n  REQUIRED FROM T-MOBILE BEFORE THIS CAN BE SENT:")
        for i, q in enumerate(op.blocking_questions, 1):
            print(f"    {i}. {q}")
    return 0


def cmd_allowlists(args: argparse.Namespace) -> int:
    try:
        policy = AllowlistPolicy.from_settings()
    except AllowlistError as exc:
        print(f"ALLOWLIST CONFIGURATION ERROR:\n  {exc}")
        return 1
    print("PIT DESIGNATED TEST-SIM ALLOWLISTS (masked)")
    print("=" * 72)
    for label, values in (
        ("read-only", policy.read_only),
        ("lifecycle", policy.lifecycle),
        ("destructive", policy.destructive),
    ):
        shown = ", ".join(mask_tail(v) for v in values) or "<empty — refuses all>"
        print(f"  {label:<14} {shown}")
    print()
    print("  protected     " + ", ".join(mask_tail(i) for i in sorted(PROTECTED_ICCIDS)))
    print("                (needs explicit destructive listing "
          "AND --confirm-protected)")
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    """Report the last known lifecycle state for an ICCID.

    Read-only and offline: this reflects what the harness recorded, not a live
    query. A live status check needs `run subscriber_inquiry`, which is
    currently BLOCKED pending T-Mobile's contract.
    """
    state = _load_state(args.iccid)
    print(f"ICCID {mask_tail(args.iccid)}")
    print(f"  last known state : {state.value}")
    print(f"  state confirmed  : {is_confirmed_state(state)}")
    if not is_confirmed_state(state):
        print("  NOTE: this state is reachable only via an operation whose "
              "contract\n        T-Mobile has not supplied. Treat it as an "
              "assumption.")
    print(f"  source           : {_state_path(args.iccid)}")
    return 0


# ── Minimal local state persistence ─────────────────────────────────────────
# Deliberately a file, not a database row: the harness must work from an
# operator workstation with no application database, and the certification
# record has to survive independently of app state.

def _state_dir() -> str:
    return os.environ.get(
        "TMOBILE_PIT_STATE_DIR",
        os.path.join(tempfile.gettempdir(), "tmobile-pit-state"),
    )


def _state_path(iccid: str) -> str:
    return os.path.join(_state_dir(), f"{iccid}.json")


def _load_state(iccid: str) -> LifecycleState:
    try:
        with open(_state_path(iccid), encoding="utf-8") as fh:
            return LifecycleState(json.load(fh)["state"])
    except (OSError, KeyError, ValueError):
        return LifecycleState.UNKNOWN


def _record_state(iccid: str, state: LifecycleState, entry: dict) -> None:
    """Append one certification record and update the current state.

    Identifiers are masked on the way in — the ledger is a working artifact that
    may be attached to a report.
    """
    os.makedirs(_state_dir(), exist_ok=True)
    path = _state_path(iccid)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {"iccid_masked": mask_tail(iccid), "history": []}
    doc["state"] = state.value
    doc["history"].append(entry)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)


def _ledger_entry(
    *, op_name, iccid, msisdn, account_id, previous, expected, observed,
    bundle, operator, reason, result,
) -> dict:
    """The Phase-3 certification record for one operation."""
    trace = {}
    for exchange in (bundle or {}).get("exchanges", []):
        response = exchange.get("response") or {}
        request = exchange.get("request") or {}
        safe = (request.get("headers") or {}).get("safe_values", {})
        if response:
            trace = {
                "partner_transaction_id": (
                    response.get("partner_transaction_id")
                    or safe.get("partner-transaction-id")
                ),
                "correlation_id": safe.get("X-Correlation-Id"),
                "work_flow_id": response.get("work_flow_id"),
                "service_transaction_id": response.get("service_transaction_id"),
            }
    return {
        "operation": op_name,
        "iccid_masked": mask_tail(iccid),
        "msisdn_masked": mask_tail(msisdn),
        "account_id_masked": mask_tail(account_id),
        "previous_state": previous.value,
        "expected_state": expected.value if expected else None,
        "observed_state": observed.value if observed else None,
        "trace": trace,
        "request_timestamp_utc": (bundle or {}).get("generated_at_utc"),
        "callback_timestamp_utc": None,   # filled by tmobile_callback_inspect
        "verification_timestamp_utc": None,
        "operator": operator,
        "reason": reason,
        "result": result,
    }


# ── Gate evaluation, shared by preview and run ──────────────────────────────

def _evaluate_gates(args: argparse.Namespace, op, *, live: bool) -> list[str]:
    """Return the ordered gate report. Raises on the first hard failure.

    Runs identically for preview and run so a preview genuinely rehearses the
    decision, rather than passing checks the real call would fail.
    """
    report: list[str] = []

    # Gate 1 — provenance. Applies even in preview: previewing a guessed path
    # would render a request we must never send, which invites sending it.
    require_sendable(op)
    report.append(f"provenance      OK ({op.provenance.value})")

    # Gate 2 — allowlist tier.
    policy = AllowlistPolicy.from_settings()
    policy.require_allowed(args.iccid, op.classification)
    report.append(
        f"allowlist       OK ({op.classification.name} tier, "
        f"{mask_tail(args.iccid)})"
    )

    # Gate 3 — state machine.
    previous = _load_state(args.iccid)
    expected = next_state(op.name, previous)
    report.append(f"transition      OK ({previous.value} -> {expected.value})")
    if not is_confirmed_state(expected):
        report.append(
            "                WARNING: target state is NOT confirmed by evidence"
        )

    if not live:
        report.append("mode            PREVIEW — nothing will be sent")
        return report

    # Gate 4 — operator confirmations, in increasing severity.
    if op.requires_confirm_live and not args.confirm_live:
        raise SystemExit(
            f"'{op.name}' changes subscriber state and requires --confirm-live. "
            "Nothing was sent."
        )
    if op.requires_confirm_destructive:
        if not args.confirm_destructive:
            raise SystemExit(
                f"'{op.name}' is DESTRUCTIVE ({op.reversibility}) and requires "
                "--confirm-destructive. Nothing was sent."
            )
        if not (args.reason or "").strip():
            raise SystemExit(
                "A destructive operation requires --reason '<why>'. "
                "Nothing was sent."
            )
        if args.iccid in PROTECTED_ICCIDS and not args.confirm_protected:
            raise SystemExit(
                f"ICCID {mask_tail(args.iccid)} is the first successfully "
                "activated line — the only end-to-end evidence the integration "
                "works. Destroying it additionally requires --confirm-protected. "
                "Nothing was sent."
            )
    report.append("confirmations   OK")

    # Gate 5 — the hard live switch, checked last so a misconfigured run still
    # surfaces every other problem first.
    if not TMobileTAAPClient.live_calls_enabled():
        raise SystemExit(
            "TMOBILE_PIT_LIVE_CALLS_ENABLED is not true. Nothing was sent."
        )
    report.append("live switch     OK")
    return report


def _print_preflight(op, args, report: list[str], previous: LifecycleState) -> None:
    print("=" * 72)
    print(f"OPERATION       {op.name}  [class {op.classification.value} "
          f"{op.classification.name}]")
    print(f"REQUEST         {op.http_method} {op.path}")
    print(f"TARGET ICCID    {mask_tail(args.iccid)}")
    print(f"KNOWN STATE     {previous.value} "
          f"(confirmed={is_confirmed_state(previous)})")
    print("-" * 72)
    for line in report:
        print(f"  {line}")
    print("=" * 72)


# ── preview / run ───────────────────────────────────────────────────────────

async def cmd_preview(args: argparse.Namespace) -> int:
    op = get_operation(args.operation)
    previous = _load_state(args.iccid)
    report = _evaluate_gates(args, op, live=False)
    _print_preflight(op, args, report, previous)

    if op.name == "activate_subscriber":
        # The only operation with a real preview builder — it is the only one
        # whose request shape is confirmed.
        from app.integrations.tmobile_evidence import run_activation_preview
        bundle = await run_activation_preview(
            TMobileTAAPClient(), iccid=args.iccid, market_zip=args.market_zip)
        print(render_text_report(bundle))
    print("\nPREVIEW ONLY — no network connection was opened.")
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    op = get_operation(args.operation)
    previous = _load_state(args.iccid)
    report = _evaluate_gates(args, op, live=True)
    _print_preflight(op, args, report, previous)

    expected = next_state(op.name, previous)
    client = TMobileTAAPClient()
    bundle = _bundle_skeleton(client, f"certify:{op.name}")
    bundle["operation"] = op.name
    bundle["iccid_masked"] = mask_tail(args.iccid)
    bundle["operator"] = args.operator
    bundle["reason"] = args.reason
    recorder = EvidenceRecorder(env=client.base_url)
    recorder.attach(client)

    observed, result_text = None, None
    try:
        # Exactly one call. No retry wrapper anywhere in this path.
        if op.name == "activate_subscriber":
            result = await client.activate_subscriber(
                args.iccid, market_zip=args.market_zip)
        else:  # pragma: no cover - unreachable while every other op is blocked
            raise OperationBlocked(
                f"'{op.name}' passed the gates but has no dispatch entry. "
                "Wiring it is a deliberate change made only once T-Mobile "
                "supplies its contract."
            )
        result_text = _redact_body_text(json.dumps(result))
        bundle["ok"] = True
        bundle["result"] = result_text
        observed = expected
    except Exception as exc:
        bundle["ok"] = False
        bundle["error"] = _redact_body_text(str(exc))
        observed = LifecycleState.FAILED
    finally:
        bundle["exchanges"] = recorder.finalize()
        await client.close()

    bundle["notes"].append(
        f"Exactly one '{op.name}' request was sent. No automatic retry."
    )
    print(render_text_report(bundle))
    json_path, txt_path = write_evidence(bundle, args.out_dir)

    entry = _ledger_entry(
        op_name=op.name, iccid=args.iccid,
        msisdn=args.msisdn, account_id=args.account_id,
        previous=previous, expected=expected, observed=observed,
        bundle=bundle, operator=args.operator, reason=args.reason,
        result="ok" if bundle.get("ok") else "failed",
    )
    entry["evidence_json"] = json_path
    _record_state(args.iccid, observed, entry)

    print(f"\nEvidence written:\n  {json_path}\n  {txt_path}")
    print(f"State recorded:\n  {_state_path(args.iccid)}")
    print(
        "\nNEXT: verify the callback before any further state change —\n"
        f"  python -m scripts.tmobile_callback_inspect --iccid {args.iccid}"
    )
    return 0 if bundle.get("ok") else 1



# ── subscriber-inquiry: the read-only certification command ─────────────────

def _selector_from(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve exactly one nominated selector. Never guesses."""
    supplied = [(t, getattr(args, t)) for t in ("iccid", "msisdn", "imsi")
                if getattr(args, t, None)]
    if not supplied:
        raise SystemExit(
            "A subscriber must be explicitly nominated: pass exactly one of "
            "--iccid / --msisdn / --imsi. There is no default and no 'latest' "
            "subscriber."
        )
    if len(supplied) > 1:
        raise SystemExit(
            f"Exactly one selector is allowed; got {len(supplied)}. Nothing was sent."
        )
    return supplied[0]


def _print_preflight_report(args, selector_type, selector, request, authorized):
    """Show everything about the request except the things that must stay secret."""
    op = get_operation("subscriber_inquiry")
    body = request.to_wire()
    masked_body = {k: (mask_tail(v) if k in ("iccid", "msisdn", "imsi") else v)
                   for k, v in body.items()}
    print("=" * 72)
    print(f"ENVIRONMENT     {os.environ.get('TMOBILE_ENV', 'pit')} (must be PIT)")
    print(f"OPERATION       subscriber_inquiry  [class {op.classification.value} "
          f"{op.classification.name}]")
    print(f"ENDPOINT        {op.http_method} {op.path}   (explicit; never derived)")
    print(f"SELECTOR        {selector_type} = {mask_tail(selector)}")
    print(f"REQUEST BODY    {masked_body}")
    print(f"HEADERS         Authorization / X-Authorization present, values omitted;")
    print(f"                partner-id, sender-id, partner-transaction-id, "
          f"X-Correlation-Id")
    print(f"RESPONSE MODEL  TMobileResponseEnvelope (synchronous)")
    print(f"READINESS       {op.readiness.value}")
    print(f"SEND POLICY     {'TEMPORARILY AUTHORIZED (single run)' if authorized else 'BLOCKED'}")
    print(f"AUDIT           {_state_dir()}  (+ private evidence store)")
    print("-" * 72)


async def cmd_subscriber_inquiry(args: argparse.Namespace) -> int:
    """Preview by default; send exactly one request only when fully authorized."""
    selector_type, selector = _selector_from(args)

    # Build and validate the typed request FIRST. A malformed request must fail
    # here, as a local object, before anything touches OAuth.
    try:
        request = SubscriberInquiryRequest(**{selector_type: selector})
    except TMobileRequestError as exc:
        print(f"\nREFUSED — request validation failed. Nothing was sent.\n\n{exc}")
        return 2

    if not args.execute:
        _print_preflight_report(args, selector_type, selector, request, authorized=False)
        print("\nPREVIEW ONLY — no OAuth request and no API call were made.")
        print("To execute one real request, re-run with:")
        print(f"  --execute --confirm-live --operator <you> "
              f"--confirm-subscriber-approved")
        return 0

    # ── live path: every gate, in order ────────────────────────────────────
    if not args.confirm_live:
        raise SystemExit("--confirm-live is required to execute. Nothing was sent.")
    if not args.confirm_subscriber_approved:
        raise SystemExit(
            "--confirm-subscriber-approved is required: the operator must "
            "affirm this subscriber is approved for read-only inquiry. "
            "Nothing was sent."
        )
    if not (args.operator or "").strip():
        raise SystemExit("--operator is required for the audit record. Nothing was sent.")

    policy = AllowlistPolicy.from_settings()
    policy.require_allowed(selector, Classification.READ_ONLY) if selector_type == "iccid" \
        else None

    if not TMobileTAAPClient.live_calls_enabled():
        raise SystemExit(
            "TMOBILE_PIT_LIVE_CALLS_ENABLED is not true. Nothing was sent."
        )

    client = TMobileTAAPClient()
    if not client.is_configured:
        raise SystemExit(
            "T-Mobile credentials are not configured in this environment, so a "
            "live request is impossible. Nothing was sent."
        )

    auth = grant_single_run(
        operation="subscriber_inquiry", selector_type=selector_type,
        selector=selector, operator=args.operator, confirmed=True,
    )
    _print_preflight_report(args, selector_type, selector, request, authorized=True)
    print(f"AUTHORIZATION   {auth.audit_ref} (single run, consumed on use)")

    bundle = _bundle_skeleton(client, "certify:subscriber_inquiry")
    bundle["operation"] = "subscriber_inquiry"
    bundle["selector_type"] = selector_type
    bundle["selector_masked"] = mask_tail(selector)
    bundle["operator"] = args.operator
    bundle["authorization"] = auth.audit_record()
    recorder = EvidenceRecorder(env=client.base_url)
    recorder.attach(client)

    started = utc_now_iso()
    try:
        # Exactly one call. No retry wrapper anywhere on this path.
        result = await client.subscriber_inquiry(**{selector_type: selector})
        envelope = TMobileResponseEnvelope.from_payload(
            result, operation="subscriber_inquiry",
            kind=ResponseKind.SYNCHRONOUS, http_status=200,
        )
        bundle["ok"] = True
        bundle["normalized_status"] = envelope.normalized_status.value
        bundle["vendor_code"] = envelope.vendor_code
        bundle["sim_network_type_present"] = envelope.sim_network_type is not None
        bundle["unknown_response_fields"] = sorted(envelope.raw_extra_fields)
        bundle["subscriber_status_normalized"] = envelope.normalized_status.value
    except Exception as exc:
        bundle["ok"] = False
        bundle["error"] = _redact_body_text(str(exc))
    finally:
        bundle["exchanges"] = recorder.finalize()
        bundle["started_at_utc"] = started
        bundle["finished_at_utc"] = utc_now_iso()
        await client.close()
        clear_authorization()

    bundle["notes"].append(
        "Exactly one SubscriberInquiry was sent. Read-only: no subscriber "
        "state was changed. No retry, no follow-up query, no polling."
    )
    print(render_text_report(bundle))
    json_path, txt_path = write_evidence(bundle, args.out_dir)
    print(f"\nEvidence written:\n  {json_path}\n  {txt_path}")
    print("Authorization consumed and cleared.")
    return 0 if bundle.get("ok") else 1


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("operations", help="List every operation and whether it is sendable.")

    show = sub.add_parser("show", help="Full inventory record for one operation.")
    show.add_argument("operation")

    sub.add_parser("allowlists", help="Show the configured test-SIM allowlists (masked).")

    inq = sub.add_parser(
        "subscriber-inquiry",
        help="Read-only subscriber inquiry. PREVIEW by default.")
    inq.add_argument("--iccid")
    inq.add_argument("--msisdn")
    inq.add_argument("--imsi")
    inq.add_argument("--preview", action="store_true",
                     help="Explicit preview (the default behaviour).")
    inq.add_argument("--execute", action="store_true",
                     help="Send exactly ONE request. Requires every gate below.")
    inq.add_argument("--confirm-live", action="store_true")
    inq.add_argument("--confirm-subscriber-approved", action="store_true",
                     help="Affirm this subscriber is approved for read-only inquiry.")
    inq.add_argument("--operator", default="",
                     help="Audit identity. Required to execute.")
    inq.add_argument("--expected-state", help="Optional: known expected state.")
    inq.add_argument("--out-dir", default=tempfile.gettempdir())

    state = sub.add_parser("state", help="Last known lifecycle state for an ICCID.")
    state.add_argument("--iccid", required=True)

    for name, help_text in (
        ("preview", "Rehearse an operation. Opens no network connection."),
        ("run", "Send exactly one live request. Requires every gate to pass."),
    ):
        c = sub.add_parser(name, help=help_text)
        c.add_argument("operation")
        c.add_argument("--iccid", required=True)
        c.add_argument("--msisdn", help="Recorded in the ledger; not sent unless "
                                        "the operation's schema requires it.")
        c.add_argument("--account-id")
        c.add_argument("--market-zip", help="Required by activate_subscriber.")
        c.add_argument("--operator", default=os.environ.get("USER") or
                       os.environ.get("USERNAME") or "unknown")
        c.add_argument("--reason", help="Required for destructive operations.")
        c.add_argument("--confirm-live", action="store_true")
        c.add_argument("--confirm-destructive", action="store_true")
        c.add_argument("--confirm-protected", action="store_true")
        c.add_argument("--out-dir", default=tempfile.gettempdir())
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "operations":
            return cmd_operations(args)
        if args.command == "show":
            return cmd_show(args)
        if args.command == "allowlists":
            return cmd_allowlists(args)
        if args.command == "state":
            return cmd_state(args)
        if args.command == "subscriber-inquiry":
            return asyncio.run(cmd_subscriber_inquiry(args))
        if args.command == "preview":
            return asyncio.run(cmd_preview(args))
        if args.command == "run":
            if args.operation == "activate_subscriber" and not args.market_zip:
                raise SystemExit("--market-zip is required for activate_subscriber.")
            return asyncio.run(cmd_run(args))
    except (OperationBlocked, AllowlistError, InvalidTransition) as exc:
        print(f"\nREFUSED — nothing was sent.\n\n{exc}")
        return 2
    except KeyError as exc:
        print(f"\nREFUSED — {exc}")
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
