"""T-Mobile PIT certification harness — the single operator entry point.

One tool for every PIT API call, with the safety gates in one place instead of
scattered across ad hoc scripts.

    python ../scripts/tmobile_pit.py operations
    python ../scripts/tmobile_pit.py show <operation>
    python ../scripts/tmobile_pit.py allowlists
    python ../scripts/tmobile_pit.py state --iccid <ICCID>
    python ../scripts/tmobile_pit.py reconcile --iccid <ICCID> --evidence <bundle.json>
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
9. **Certification blockers.** An operation with an unresolved carrier question
   about what to put on the wire cannot be single-run authorized at all — see
   ``Operation.certification_blockers``.

Exactly one request per invocation. Nothing here retries a state-changing call.

State and evidence are recorded SEPARATELY
------------------------------------------
The ledger keeps what we believe about a line apart from why we believe it, and
``state --iccid`` prints both. A synchronous carrier answer settles nothing on
its own: it is the carrier replying to *our request*, not describing *its own
record*. What settles a line is an independent read — ``subscriber-inquiry`` —
whose ``subscriberStatus`` reconciles the ledger through
``reconcile_from_carrier_read``. That path, not a callback, is what moves an
activation from ``activation_requested`` to ``active``.

``reconcile`` replays a read that already happened, parsing the carrier's own
recorded response out of its evidence bundle and through the same reconciler. It
opens no socket. It exists so that rebuilding a local file never costs a real
carrier request — and it refuses anything that is not an independent read.
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

from app.config import settings  # noqa: E402
from app.integrations.tmobile_contracts import (  # noqa: E402
    NormalizedStatus,
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
    CarrierEvidence,
    InvalidTransition,
    LifecycleState,
    ReconciliationError,
    is_carrier_attested,
    is_confirmed_state,
    next_state,
    reconcile_from_carrier_read,
)
from app.integrations.tmobile_contracts import (  # noqa: E402
    QueryNetworkRequest,
    QuerySubscriberUsageRequest,
    QueryTransactionStatusRequest,
    SubscriberInquiryRequest,
    TMobileRequestError,
)
from app.integrations.tmobile_pit_authorization import (  # noqa: E402
    TRANSACTION_SELECTOR,
    AuthorizationError,
    clear_authorization,
    grant_single_run,
)
from app.integrations.tmobile_operations import (  # noqa: E402
    OPERATIONS,
    Classification,
    OperationBlocked,
    blocked_operations,
    certification_blockers,
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
    if op.certification_blockers:
        print("\n  BLOCKED PENDING A T-MOBILE ANSWER — not sendable even once,")
        print("  and not single-run authorizable, until these are resolved:")
        for i, q in enumerate(op.certification_blockers, 1):
            print(f"    {i}. {q}")
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
    """Report the last known lifecycle state for an ICCID, and how it is known.

    Read-only and offline: this reflects what the harness recorded, not a live
    query. Two separate things are printed on purpose. The *state* is what we
    believe; the *evidence* is why. A state recorded on our own request's
    say-so and the same state confirmed by an independent carrier read are not
    the same claim, and an operator deciding whether to act needs to see which
    one they have.
    """
    doc = _load_ledger(args.iccid)
    state = _load_state(args.iccid)
    evidence = _load_evidence(args.iccid)
    ledger = doc["evidence_ledger"]

    print(f"ICCID {mask_tail(args.iccid)}")
    print(f"  last known state : {state.value}")
    print(f"  state modelled   : {is_confirmed_state(state)}")
    print(f"  evidence class   : {evidence.value}")
    print(f"  carrier-attested : {is_carrier_attested(evidence)}")
    if not is_confirmed_state(state):
        print("  NOTE: this state is reachable only via an operation whose "
              "contract\n        T-Mobile has not supplied. Treat it as an "
              "assumption.")
    if not is_carrier_attested(evidence):
        print("  NOTE: no independent carrier read backs this state. Run "
              "subscriber-inquiry\n        to verify it against T-Mobile's own "
              "record.")
    print()
    print("  EVIDENCE LEDGER  (each line is a separate observation)")
    for label, key in (
        ("A request submitted   ", "request_submitted_at"),
        ("B carrier sync ack    ", "carrier_sync_ack_at"),
        ("  sync status / code  ", "carrier_sync_status_raw"),
        ("C carrier verified    ", "carrier_verified_at"),
        ("  verified status raw ", "carrier_verified_status_raw"),
        ("  verified by         ", "carrier_verified_by_operation"),
        ("  verified from       ", "carrier_verified_source"),
        ("D callback received   ", "callback_received_at"),
        ("E callback authentic  ", "callback_authenticity_verified"),
        ("F callback correlated ", "callback_correlated"),
        ("G callback agrees     ", "callback_agrees"),
    ):
        value = ledger.get(key)
        print(f"    {label} {'—' if value is None else value}")
    if ledger.get("carrier_sync_vendor_code"):
        print(f"    vendor result code    {ledger['carrier_sync_vendor_code']}")
    if ledger.get("reconciliation_required"):
        print()
        print("  *** RECONCILIATION REQUIRED ***")
        print(f"      {ledger.get('reconciliation_reason')}")
    print()
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


def _blank_evidence_ledger() -> dict:
    """The observations that establish a state, kept apart from one another.

    Seven things can be separately true about an activation, and squashing them
    into one flag is how a ledger ends up claiming more (or less) than it knows.
    Each key here is one observation, absent until it actually happens.
    """
    return {
        # A — we sent something.
        "request_submitted_at": None,
        # B — the carrier answered the request itself, synchronously.
        "carrier_sync_ack_at": None,
        "carrier_sync_status_raw": None,
        "carrier_sync_vendor_code": None,
        # C — we asked the carrier separately and it described its own record.
        "carrier_verified_at": None,
        "carrier_verified_status_raw": None,
        "carrier_verified_by_operation": None,
        "carrier_verified_source": None,
        # D/E/F/G — the callback, in the four stages it can reach.
        "callback_received_at": None,
        "callback_authenticity_verified": None,
        "callback_correlated": None,
        "callback_agrees": None,
        # Set when two observations disagree. Never cleared automatically.
        "reconciliation_required": False,
        "reconciliation_reason": None,
    }


def _load_ledger(iccid: str) -> dict:
    """Read the certification ledger, filling in anything an older file lacks."""
    try:
        with open(_state_path(iccid), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    doc.setdefault("iccid_masked", mask_tail(iccid))
    doc.setdefault("history", [])
    doc.setdefault("state", LifecycleState.UNKNOWN.value)
    doc.setdefault("evidence", CarrierEvidence.NONE.value)
    ledger = _blank_evidence_ledger()
    ledger.update(doc.get("evidence_ledger") or {})
    doc["evidence_ledger"] = ledger
    return doc


def _load_state(iccid: str) -> LifecycleState:
    try:
        return LifecycleState(_load_ledger(iccid)["state"])
    except ValueError:
        return LifecycleState.UNKNOWN


def _load_evidence(iccid: str) -> CarrierEvidence:
    try:
        return CarrierEvidence(_load_ledger(iccid)["evidence"])
    except ValueError:
        return CarrierEvidence.NONE


def _record_state(iccid: str, state: LifecycleState, entry: dict, *,
                  evidence: CarrierEvidence | None = None,
                  evidence_updates: dict | None = None) -> None:
    """Append one certification record and update the current state.

    ``state`` and ``evidence`` are written separately and neither implies the
    other: an unchanged state with stronger evidence is a real and useful
    outcome (it is what an independent confirmation produces), and so is a
    changed state whose evidence class stays where it was.

    Identifiers are masked on the way in — the ledger is a working artifact that
    may be attached to a report.
    """
    os.makedirs(_state_dir(), exist_ok=True)
    doc = _load_ledger(iccid)
    doc["state"] = state.value
    if evidence is not None:
        doc["evidence"] = evidence.value
    doc["evidence_ledger"].update(evidence_updates or {})
    doc["history"].append(entry)
    with open(_state_path(iccid), "w", encoding="utf-8") as fh:
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
    evidence = CarrierEvidence.REQUEST_SUBMITTED
    evidence_updates = {"request_submitted_at": utc_now_iso()}
    envelope = None
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
        # A 2xx is not a success. ``_request`` raises only on HTTP >= 400, so a
        # body carrying status=FAILURE, or no status at all, reaches here
        # looking exactly like the 201 that worked. Classify it before anything
        # is written down: an apparent success we cannot read must fail closed,
        # because a ledger that records an unreadable answer as an activation is
        # worse than one that records a failure.
        envelope = TMobileResponseEnvelope.from_payload(
            result, operation=op.name, kind=ResponseKind.SYNCHRONOUS,
            http_status=201,
        )
        if not envelope.accepted:
            raise RuntimeError(
                f"{op.name}: the carrier returned a 2xx whose body does not "
                f"read as an acceptance (status="
                f"{envelope.normalized_status.value}, result code="
                f"{envelope.vendor_code or 'absent'}). Treating it as a "
                "FAILURE. Nothing is claimed about the line; classify the "
                "response before doing anything else."
            )
        result_text = _redact_body_text(json.dumps(result))
        bundle["ok"] = True
        bundle["result"] = result_text
        bundle["normalized_status"] = envelope.normalized_status.value
        bundle["vendor_code"] = envelope.vendor_code
        # The line moves to its *_requested state and no further. The carrier
        # answered our request; it has not yet told us about its own record.
        # That is evidence class B, and B is not C.
        observed = expected
        if envelope.normalized_status is NormalizedStatus.SUCCESS:
            evidence = CarrierEvidence.CARRIER_SYNC_ACK
            evidence_updates["carrier_sync_ack_at"] = utc_now_iso()
        evidence_updates["carrier_sync_status_raw"] = (
            envelope.normalized_status.value)
        evidence_updates["carrier_sync_vendor_code"] = envelope.vendor_code
    except Exception as exc:
        bundle["ok"] = False
        bundle["error"] = _redact_body_text(str(exc))
        observed = LifecycleState.FAILED
        evidence = CarrierEvidence.REQUEST_SUBMITTED
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
    entry["evidence_class"] = evidence.value
    _record_state(args.iccid, observed, entry, evidence=evidence,
                  evidence_updates=evidence_updates)

    print(f"\nEvidence written:\n  {json_path}\n  {txt_path}")
    print(f"State recorded:\n  {_state_path(args.iccid)}")
    print(f"  state            : {observed.value}")
    print(f"  evidence class   : {evidence.value}")
    if envelope is not None and bundle.get("ok"):
        print(f"  carrier answered : status="
              f"{envelope.normalized_status.value} "
              f"result={envelope.vendor_code or 'absent'}")
        print("  NOTE: that is the carrier answering OUR REQUEST. It is not "
              "yet the carrier\n        describing its own record. Verify "
              "independently before relying on it.")
    print(
        "\nNEXT: establish the carrier's own view before any further state "
        "change.\n"
        "  1. Independent read (this is what settles the state):\n"
        f"       python {_callback_inspect_sibling('tmobile_pit.py')} "
        f"subscriber-inquiry --iccid {args.iccid}\n"
        "  2. Callback arrival, authenticity and correlation:\n"
        f"       python {_callback_inspect_command()} --iccid {args.iccid}"
    )
    return 0 if bundle.get("ok") else 1




def _callback_inspect_sibling(script: str) -> str:
    """Path to a sibling operator script, as invoked from the runbook's cwd.

    The runbook runs these from ``api/``, and ``python -m scripts.<name>``
    resolves ``scripts`` to ``api/scripts`` from there — a DIFFERENT package
    that does not contain the T-Mobile tooling, so the module form fails with
    ModuleNotFoundError. Emit the path form, which is what every other command
    in this harness already documents.
    """
    return f"../scripts/{script}"


def _callback_inspect_command() -> str:
    return _callback_inspect_sibling("tmobile_callback_inspect.py")


# ── Read-only certification operations ─────────────────────────────────────
# One entry per operation the certification sprint covers. Each carries its own
# request model and client method, so a command for one operation can never
# construct or send another — and each needs its own single-run grant.

READ_ONLY_OPERATIONS = {
    "subscriber_inquiry": {
        "command": "subscriber-inquiry",
        "request_model": SubscriberInquiryRequest,
        "client_method": "subscriber_inquiry",
        "selector_kind": "subscriber",
    },
    "query_network": {
        "command": "query-network",
        "request_model": QueryNetworkRequest,
        "client_method": "query_network",
        "selector_kind": "subscriber",
    },
    "query_usage": {
        "command": "query-usage",
        "request_model": QuerySubscriberUsageRequest,
        "client_method": "query_usage",
        "selector_kind": "subscriber",
    },
    "query_transaction_status": {
        "command": "query-transaction-status",
        "request_model": QueryTransactionStatusRequest,
        "client_method": "query_transaction_status",
        "selector_kind": "transaction",
    },
}

#: The order the certification plan requires. Each step needs the previous one
#: reconciled before it runs — the tool does not enforce ordering across
#: separate invocations, so this exists to be quoted in the runbook.
CERTIFICATION_ORDER = ("subscriber_inquiry", "query_network",
                       "query_usage", "query_transaction_status")

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



def _reconcile_ledger_from_read(
    operation: str, envelope, *, iccid: str | None, operator: str,
    source: str = "live",
) -> dict | None:
    """Settle the certification ledger from an INDEPENDENT carrier read.

    This is the answer to "why is the ledger still activation_requested after a
    successful activation": nothing here ever ran. A read is not a transition,
    so it does not go through ``next_state``; it is the carrier describing its
    own record, which is stronger evidence than our inference about our own
    request and is what lets an activation settle **without** a callback.

    Returns None when the response gives nothing to reconcile against — a usage
    query carries no subscriberStatus, and silence is not evidence.
    """
    status_raw = envelope.subscriber_status_raw
    if not iccid or not status_raw:
        return None

    previous = _load_state(iccid)
    try:
        result = reconcile_from_carrier_read(status_raw, current=previous)
    except ReconciliationError as exc:
        print(f"\nLEDGER NOT RECONCILED — {exc}")
        return {"reconciled": False, "reason": str(exc),
                "carrier_status_raw": status_raw}

    now = utc_now_iso()
    updates = {
        "carrier_verified_at": now,
        "carrier_verified_status_raw": result.carrier_status_raw,
        "carrier_verified_by_operation": operation,
        # Whether we watched the answer arrive or replayed one we had already
        # captured. The observation is the same; where it came from is not, and
        # a ledger that hides the difference is harder to audit later.
        "carrier_verified_source": source,
    }
    if result.conflict:
        updates["reconciliation_required"] = True
        updates["reconciliation_reason"] = result.reason

    _record_state(
        iccid, result.observed_state,
        {
            "operation": operation,
            "iccid_masked": mask_tail(iccid),
            "kind": "carrier_read_reconciliation",
            "previous_state": result.previous_state.value,
            "observed_state": result.observed_state.value,
            "carrier_status_raw": result.carrier_status_raw,
            "evidence_class": result.evidence.value,
            "conflict": result.conflict,
            "reason": result.reason,
            "verification_timestamp_utc": now,
            "source": source,
            "operator": operator,
        },
        evidence=result.evidence, evidence_updates=updates,
    )

    print("\nLEDGER RECONCILED FROM AN INDEPENDENT CARRIER READ")
    print(f"  source           : {source}")
    print(f"  previous state   : {result.previous_state.value}")
    print(f"  observed state   : {result.observed_state.value}")
    print(f"  evidence class   : {result.evidence.value}")
    print(f"  {result.reason}")
    if result.conflict:
        print("  *** CONFLICT — the recorded state was NOT overwritten. "
              "Resolve by hand. ***")
    print(f"  ledger           : {_state_path(iccid)}")

    return {
        "reconciled": True,
        "source": source,
        "previous_state": result.previous_state.value,
        "observed_state": result.observed_state.value,
        "evidence_class": result.evidence.value,
        "conflict": result.conflict,
        "carrier_status_raw": result.carrier_status_raw,
    }


async def cmd_read_only(args: argparse.Namespace, operation: str) -> int:
    """Preview by default; send exactly one request when fully authorized.

    Shared by all four read-only certification operations. The operation is
    fixed by the subcommand, so a grant or a request for one can never be
    spent on another.
    """
    spec = READ_ONLY_OPERATIONS[operation]
    op = get_operation(operation)

    if spec["selector_kind"] == "transaction":
        selector_type = TRANSACTION_SELECTOR
        selector = (getattr(args, "transaction_id", None) or "").strip()
        if not selector:
            raise SystemExit(
                "--transaction-id is required and must be a transaction id you "
                "already hold. There is no 'latest transaction' lookup."
            )
        model_kwargs = {"transaction_id": selector}
    else:
        selector_type, selector = _selector_from(args)
        model_kwargs = {selector_type: selector}

    # Validate the typed request FIRST — a malformed request must fail as a
    # local object, before anything touches OAuth.
    try:
        request = spec["request_model"](**model_kwargs)
    except TMobileRequestError as exc:
        print(f"\nREFUSED — request validation failed. Nothing was sent.\n\n{exc}")
        return 2

    masked = mask_tail(selector)
    body = request.to_wire()
    masked_body = {k: (mask_tail(v) if k in ("iccid", "msisdn", "imsi",
                                             "transactionId") else v)
                   for k, v in body.items()}

    def report(authorized: bool, audit_ref: str = "") -> None:
        print("=" * 72)
        print(f"ENVIRONMENT     {settings.TMOBILE_ENV} (must be PIT)")
        print(f"OPERATION       {operation}  [class {op.classification.value} "
              f"{op.classification.name}]")
        print(f"ENDPOINT        {op.http_method} {op.path}   (explicit; never derived)")
        print(f"SELECTOR        {selector_type} = {masked}")
        print(f"REQUEST BODY    {masked_body}")
        print("HEADERS         Authorization / X-Authorization present, values "
              "omitted;")
        print("                partner-id, sender-id, partner-transaction-id, "
              "X-Correlation-Id")
        print("RESPONSE MODEL  TMobileResponseEnvelope (synchronous)")
        print(f"READINESS       {op.readiness.value}")
        print(f"SEND POLICY     {'TEMPORARILY AUTHORIZED (single run)' if authorized else 'BLOCKED'}")
        if audit_ref:
            print(f"AUTHORIZATION   {audit_ref} (single run, consumed on use)")
        print(f"EVIDENCE        {args.out_dir}  (+ private evidence store)")
        for i, question in enumerate(certification_blockers(operation), 1):
            print(f"CARRIER BLOCKER {i}. {question}"
                  if i == 1 else f"                {i}. {question}")
        print("-" * 72)

    if not args.execute:
        report(authorized=False)
        print("\nPREVIEW ONLY — no OAuth request and no API call were made.")
        print("To execute one real request, re-run with:")
        print("  --execute --confirm-live --operator <you> "
              "--confirm-subscriber-approved")
        return 0

    # ── live path: every gate, in order ────────────────────────────────────
    if not args.confirm_live:
        raise SystemExit("--confirm-live is required to execute. Nothing was sent.")
    if not args.confirm_subscriber_approved:
        raise SystemExit(
            "--confirm-subscriber-approved is required: the operator must "
            "affirm this target is approved for read-only testing. Nothing was sent."
        )
    if not (args.operator or "").strip():
        raise SystemExit("--operator is required for the audit record. Nothing was sent.")

    if selector_type == "iccid":
        AllowlistPolicy.from_settings().require_allowed(
            selector, Classification.READ_ONLY)

    if not TMobileTAAPClient.live_calls_enabled():
        raise SystemExit(
            "TMOBILE_PIT_LIVE_CALLS_ENABLED is not true. Nothing was sent.")

    client = TMobileTAAPClient()
    if not client.is_configured:
        raise SystemExit(
            "T-Mobile credentials are not configured in this environment, so a "
            "live request is impossible. Nothing was sent."
        )

    auth = grant_single_run(
        operation=operation, selector_type=selector_type, selector=selector,
        operator=args.operator, confirmed=True,
    )
    report(authorized=True, audit_ref=auth.audit_ref)

    bundle = _bundle_skeleton(client, f"certify:{operation}")
    bundle["operation"] = operation
    bundle["selector_type"] = selector_type
    bundle["selector_masked"] = masked
    bundle["operator"] = args.operator
    bundle["authorization"] = auth.audit_record()
    recorder = EvidenceRecorder(env=client.base_url)
    recorder.attach(client)

    started = utc_now_iso()
    try:
        # Exactly one call. No retry wrapper anywhere on this path.
        result = await getattr(client, spec["client_method"])(**model_kwargs)
        envelope = TMobileResponseEnvelope.from_payload(
            result, operation=operation, kind=ResponseKind.SYNCHRONOUS,
            http_status=200,
        )
        bundle["ok"] = True
        bundle["normalized_status"] = envelope.normalized_status.value
        bundle["vendor_code"] = envelope.vendor_code
        bundle["sim_network_type_present"] = envelope.sim_network_type is not None
        bundle["unknown_response_fields"] = sorted(envelope.raw_extra_fields)
        # The field the ledger reconciles on, lifted to the top of the bundle so
        # a later offline replay does not have to re-derive it from the captured
        # exchange. A status word, not an identifier — nothing to mask.
        bundle["subscriber_status_raw"] = envelope.subscriber_status_raw
        # Guarded separately: a problem writing the local ledger must not be
        # reported as a failure of the carrier request, which already
        # succeeded and whose evidence bundle is the thing being certified.
        try:
            reconciliation = _reconcile_ledger_from_read(
                operation, envelope,
                iccid=(selector if selector_type == "iccid" else envelope.iccid),
                operator=args.operator,
            )
        except Exception as exc:            # noqa: BLE001 - reported, not raised
            reconciliation = {"reconciled": False,
                              "reason": _redact_body_text(str(exc))}
            print(f"\nLEDGER NOT UPDATED — {exc}\n"
                  "The carrier request itself succeeded; only the local record "
                  "failed to write.")
        if reconciliation:
            bundle["ledger_reconciliation"] = reconciliation
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
        f"Exactly one {operation} request was sent. Read-only: no subscriber "
        "state was changed. No retry, no follow-up query, no polling."
    )
    print(render_text_report(bundle))
    json_path, txt_path = write_evidence(bundle, args.out_dir)
    print(f"\nEvidence written:\n  {json_path}\n  {txt_path}")
    print("Authorization consumed and cleared.")
    if not bundle.get("ok"):
        print("\nSTOP — this operation did not succeed. Do NOT retry and do NOT "
              "advance to the next operation. Classify the failure first.")
    return 0 if bundle.get("ok") else 1


# ── Offline reconciliation from an already-captured response ───────────────

class EvidenceReplayError(RuntimeError):
    """Raised when an evidence bundle cannot be replayed into the ledger."""


def _replayable_response_body(bundle: dict, op) -> dict:
    """Pull the carrier's own recorded answer out of an evidence bundle.

    Matched by the operation's **exact** wire path, never by position or by a
    naming convention — a bundle contains the OAuth exchange too, and every path
    in this integration that was ever derived turned out to be wrong.
    """
    for exchange in bundle.get("exchanges") or []:
        request = exchange.get("request") or {}
        response = exchange.get("response") or {}
        if (str(request.get("method") or "").upper() != op.http_method.upper()
                or str(request.get("path") or "") != op.path):
            continue
        raw = response.get("body")
        if not raw:
            raise EvidenceReplayError(
                "The captured exchange for this operation has no response body. "
                "Nothing was reconciled."
            )
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise EvidenceReplayError(
                "The captured response body is not parseable JSON — it may have "
                "been truncated by the evidence recorder's size limit. Nothing "
                f"was reconciled, and nothing was guessed. ({exc})"
            ) from exc
    raise EvidenceReplayError(
        f"No captured exchange in this bundle targets {op.http_method} "
        f"{op.path}. Nothing was reconciled."
    )


def cmd_reconcile(args: argparse.Namespace) -> int:
    """Settle the ledger from a read that ALREADY happened. Opens no socket.

    Exists because the ledger and the carrier evidence can be recorded on
    different days, or by a build of this harness that had no way to reconcile
    them. Re-running a live inquiry purely to rebuild a local file would spend a
    real carrier request to learn something we already observed and wrote down.

    This is a replay, not an attestation: it parses the carrier's own recorded
    response through the same envelope and the same
    ``reconcile_from_carrier_read`` a live run uses. An operator cannot type a
    status in. If the bundle does not contain the answer, this refuses.
    """
    try:
        with open(args.evidence, encoding="utf-8") as fh:
            bundle = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"\nREFUSED — cannot read the evidence bundle. Nothing was "
              f"reconciled.\n\n{exc}")
        return 2

    operation = bundle.get("operation") or ""
    if operation not in READ_ONLY_OPERATIONS:
        print(
            f"\nREFUSED — this bundle records '{operation or '<none>'}', which "
            "is not a read-only operation. Nothing was reconciled.\n\n"
            "Only an INDEPENDENT carrier read may settle a line. An activation "
            "bundle records the carrier answering our own request, which is "
            "evidence class B and settles nothing — replaying one here would "
            "reintroduce exactly the confusion this ledger exists to prevent."
        )
        return 2
    if bundle.get("ok") is not True:
        print("\nREFUSED — this bundle records a request that did not succeed. "
              "Nothing was reconciled.")
        return 2

    op = get_operation(operation)
    masked = mask_tail(args.iccid)
    recorded_selector = bundle.get("selector_masked")
    if recorded_selector and recorded_selector != masked:
        print(
            f"\nREFUSED — this bundle is about {recorded_selector}, not "
            f"{masked}. Nothing was reconciled.\n\n"
            "A ledger entry for one subscriber must never be written from "
            "another subscriber's evidence."
        )
        return 2

    try:
        body = _replayable_response_body(bundle, op)
    except EvidenceReplayError as exc:
        print(f"\nREFUSED — {exc}")
        return 2

    envelope = TMobileResponseEnvelope.from_payload(
        body, operation=operation, kind=ResponseKind.SYNCHRONOUS,
        http_status=200,
    )
    if envelope.iccid and envelope.iccid != args.iccid:
        print(f"\nREFUSED — the recorded response names SIM "
              f"{mask_tail(envelope.iccid)}, not {masked}. Nothing was "
              "reconciled.")
        return 2

    print("=" * 72)
    print("OFFLINE RECONCILIATION — no network connection will be opened")
    print(f"  source operation : {operation}")
    print(f"  evidence bundle  : {args.evidence}")
    print(f"  captured at      : {bundle.get('generated_at_utc', 'unknown')}")
    print(f"  target ICCID     : {masked}")
    print("-" * 72)

    result = _reconcile_ledger_from_read(
        operation, envelope, iccid=args.iccid, operator=args.operator,
        source=f"replayed:{args.evidence}",
    )
    if result is None:
        print("\nNOTHING TO RECONCILE — the recorded response carries no "
              "subscriberStatus. Silence is not evidence, so the ledger is "
              "unchanged.")
        return 1
    if not result.get("reconciled"):
        return 1
    return 0


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

    for _op, _spec in READ_ONLY_OPERATIONS.items():
        if _spec["command"] == "subscriber-inquiry":
            continue          # already registered above
        _c = sub.add_parser(
            _spec["command"],
            help=f"Read-only {_op}. PREVIEW by default.")
        if _spec["selector_kind"] == "transaction":
            _c.add_argument("--transaction-id",
                            help="An exact transaction id you already hold.")
        else:
            _c.add_argument("--iccid")
            _c.add_argument("--msisdn")
            _c.add_argument("--imsi")
        _c.add_argument("--preview", action="store_true",
                        help="Explicit preview (the default behaviour).")
        _c.add_argument("--execute", action="store_true",
                        help="Send exactly ONE request. Requires every gate.")
        _c.add_argument("--confirm-live", action="store_true")
        _c.add_argument("--confirm-subscriber-approved", action="store_true")
        _c.add_argument("--operator", default="")
        _c.add_argument("--out-dir", default=tempfile.gettempdir())

    state = sub.add_parser("state", help="Last known lifecycle state for an ICCID.")
    state.add_argument("--iccid", required=True)

    rec = sub.add_parser(
        "reconcile",
        help="Settle the ledger from an ALREADY-CAPTURED read. Opens no socket.")
    rec.add_argument("--iccid", required=True)
    rec.add_argument("--evidence", required=True,
                     help="Path to the evidence bundle JSON from a previous "
                          "read-only run.")
    rec.add_argument("--operator", default=os.environ.get("USER") or
                     os.environ.get("USERNAME") or "unknown")

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
        if args.command == "reconcile":
            return cmd_reconcile(args)
        for _op, _spec in READ_ONLY_OPERATIONS.items():
            if args.command == _spec["command"]:
                return asyncio.run(cmd_read_only(args, _op))
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
