"""Declarative inventory of T-Mobile Wholesale operations, with provenance.

This module answers one question for every operation: **on what evidence do we
believe this endpoint exists in this shape?** Nothing here is added from memory
or inference — each entry records where its path and schema came from, and an
operation may only be sent when that provenance is strong enough.

Why this exists
---------------
The repository contains **no T-Mobile OpenAPI spec, Postman collection, PDF, or
reference implementation**. Every subscriber-family path in ``tmobile_taap.py``
is produced by joining an operation name onto ``TMOBILE_SUBSCRIBER_BASE_PATH``::

    def _subscriber_path(self, op: str) -> str:
        return f"{self.subscriber_base_path}/{op.lstrip('/')}"

That derivation is demonstrably unreliable, and we have proof. The one operation
we can verify — activation — required an explicit
``TMOBILE_ACTIVATION_PATH=/wholesale/v1/subscriber/activation`` override,
because the derived default ``/wholesale/v1/subscriber/activate`` is **wrong**.
If the derivation is wrong for the only endpoint we can check, treating
``/suspend``, ``/restore``, ``/deactivate``, ``/inquiry``, and ``/changesim`` as
real is a guess — and a guess aimed at a carrier's live gateway, where a wrong
path against a real subscriber is not a cheap mistake.

So: operations whose provenance is ``DERIVED`` are **blocked from sending**. They
stay implemented, documented, and mock-tested, and each carries the exact
question T-Mobile must answer to unblock it. Unblocking is a config change plus
a reviewed provenance edit — never a silent default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Classification(str, Enum):
    """Operational risk class, per the certification plan."""

    READ_ONLY = "A"          # cannot change subscriber state
    REVERSIBLE = "B"         # changes state; a documented inverse exists
    DESTRUCTIVE = "C"        # terminal or not cleanly reversible
    UNKNOWN = "D"            # semantics not established — always blocked


class Provenance(str, Enum):
    """How strongly the endpoint's existence and shape are evidenced."""

    # We sent it and T-Mobile answered with a success. The strongest evidence
    # available to a client, and currently true of exactly one operation.
    CONFIRMED_BY_LIVE_RESPONSE = "confirmed_by_live_response"
    # T-Mobile supplied a written contract stored in this repository.
    # No operation currently qualifies — no such artifact exists here.
    TMOBILE_WRITTEN_SPEC = "tmobile_written_spec"
    # The path was produced by our own string derivation. NOT documented.
    DERIVED_UNCONFIRMED = "derived_unconfirmed"


# Provenance strong enough to authorize a live request.
SENDABLE_PROVENANCE = frozenset({
    Provenance.CONFIRMED_BY_LIVE_RESPONSE,
    Provenance.TMOBILE_WRITTEN_SPEC,
})


@dataclass(frozen=True)
class Operation:
    """One T-Mobile Wholesale operation and everything we know about it."""

    name: str
    client_method: str
    http_method: str
    path: str
    path_source: str
    classification: Classification
    provenance: Provenance

    request_schema: str
    response_schema: str
    callback_behavior: str
    required_headers: tuple[str, ...]
    pop_ehts: str
    body_signed: bool
    synchronous: str
    reversibility: str
    prerequisite_state: str
    pit_restrictions: str
    implementation_status: str
    test_status: str

    # Questions T-Mobile must answer before this operation may be sent.
    # Empty for operations that are already sendable.
    blocking_questions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_sendable(self) -> bool:
        """True only when provenance is strong AND the class is understood.

        Both conditions matter: a documented path with unknown lifecycle
        semantics is still not safe to fire at a live subscriber.
        """
        return (
            self.provenance in SENDABLE_PROVENANCE
            and self.classification is not Classification.UNKNOWN
        )

    @property
    def requires_confirm_live(self) -> bool:
        return self.classification is not Classification.READ_ONLY

    @property
    def requires_confirm_destructive(self) -> bool:
        return self.classification is Classification.DESTRUCTIVE


# ── The reference PoP contract, confirmed by the successful activation ──────
# Both the OAuth and resource PoP sign this exact ehts set. Established by
# T-Mobile's supplied PoP Token Builder (PR #170) and confirmed accepted by the
# 2026-07-21 HTTP 201. See docs/tmobile_taap_setup.md § "Authoritative PoP
# contract".
REFERENCE_EHTS = "Content-Type;Authorization;uri;http-method;body"

# Headers the successful activation carried. Recorded as the confirmed set;
# any future operation is expected to carry the same, but that expectation is
# itself unconfirmed for operations T-Mobile has not described.
CONFIRMED_HEADERS = (
    "Authorization", "X-Authorization", "Content-Type", "Accept",
    "X-Correlation-Id", "partner-transaction-id", "partner-id", "sender-id",
)

_ACTIVATION_HEADERS = CONFIRMED_HEADERS + ("call-back-location",)

_DERIVED_PATH_NOTE = (
    "Derived by tmobile_taap._subscriber_path() joining the operation name onto "
    "TMOBILE_SUBSCRIBER_BASE_PATH. NOT supplied by T-Mobile. The same derivation "
    "produces the WRONG activation path (/activate vs the working /activation), "
    "so it is not trustworthy evidence."
)

_STANDARD_BLOCKING_QUESTIONS = (
    "Exact HTTP method and path for this operation in the Wholesale PIT gateway.",
    "Exact request body schema, including which identifier keys it expects "
    "(msisdn, iccid, accountId) and which are required.",
    "Exact synchronous response schema, including the result-code vocabulary.",
    "Whether the operation is synchronous, asynchronous via call-back-location, "
    "or both — and which callback event type it emits.",
    "Whether the PoP ehts set differs from the reference "
    f"'{REFERENCE_EHTS}'.",
    "Prerequisite subscriber state, and the exact state the line is left in.",
    "Whether the operation is reversible, and by which inverse operation.",
    "Any PIT-environment restrictions or rate limits.",
)


OPERATIONS: tuple[Operation, ...] = (
    # ── The one confirmed operation ─────────────────────────────────────────
    Operation(
        name="activate_subscriber",
        client_method="TMobileTAAPClient.activate_subscriber",
        http_method="POST",
        path="/wholesale/v1/subscriber/activation",
        path_source=(
            "CONFIRMED: returned HTTP 201 status=SUCCESS result=100 at "
            "2026-07-21T03:18:33.694749Z on deployed commit 1766f51. Set "
            "explicitly via TMOBILE_ACTIVATION_PATH — the derived default "
            "(/wholesale/v1/subscriber/activate) is wrong."
        ),
        classification=Classification.REVERSIBLE,
        provenance=Provenance.CONFIRMED_BY_LIVE_RESPONSE,
        request_schema=(
            "{iccid, marketZip, language, baseProduct:{baseProductId, wps, "
            "product:[{ProductID, isBaseProduct, action}]}} — compact-serialized. "
            "Pinned by test_tmobile_activation.py::"
            "TestActivationPayloadMatchesTMobileSample."
        ),
        response_schema=(
            "{status, msisdn, iccid, accountId, result:[{result, status}]} — "
            "observed on the 201. Only result code '100' (SUCCESS) has been seen; "
            "the full result-code vocabulary is NOT documented."
        ),
        callback_behavior=(
            "call-back-location is MANDATORY (activate_subscriber raises without "
            "one). T-Mobile documented the account ID as returned asynchronously "
            "via callback, but on the 2026-07-21 success it arrived in the "
            "SYNCHRONOUS 201 body. No callback has been confirmed for that "
            "activation — see TMOBILE_PIT_ACTIVATION_PAYLOAD.md."
        ),
        required_headers=_ACTIVATION_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Both — 201 body observed; async callback documented, unconfirmed.",
        reversibility=(
            "Reversible in principle by deactivation, but deactivation is itself "
            "BLOCKED (undocumented path). Treat an activation as effectively "
            "irreversible until T-Mobile confirms the deactivation contract."
        ),
        prerequisite_state="ICCID not already active.",
        pit_restrictions=(
            "marketZip must be a PIT market (30346 / 30338). baseProductId and "
            "wps are the Infatrac PIT values."
        ),
        implementation_status="Implemented and proven live.",
        test_status=(
            "Mock-tested (payload golden + 201 parsing) and LIVE-tested once."
        ),
    ),

    # ── Read-family: implemented, path derived, therefore blocked ───────────
    Operation(
        name="subscriber_inquiry",
        client_method="TMobileTAAPClient.subscriber_inquiry",
        http_method="POST",
        path="/wholesale/v1/subscriber/inquiry",
        path_source=_DERIVED_PATH_NOTE,
        classification=Classification.READ_ONLY,
        provenance=Provenance.DERIVED_UNCONFIRMED,
        request_schema="{msisdn, accountId} — our construction, not documented.",
        response_schema="UNKNOWN — never observed.",
        callback_behavior=(
            "Attaches call-back-location when TMOBILE_CALLBACK_LOCATION is set. "
            "Whether T-Mobile actually emits a callback for a read is unknown."
        ),
        required_headers=CONFIRMED_HEADERS + ("call-back-location (optional)",),
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Assumed synchronous. Unconfirmed.",
        reversibility="N/A — read-only.",
        prerequisite_state="An activated line with a known accountId.",
        pit_restrictions="UNKNOWN.",
        implementation_status=(
            "Implemented; wired to app.services.tmobile_subscriber."
            "query_subscriber_by_iccid, which resolves the per-ICCID account ID."
        ),
        test_status="Mock-tested only. Never sent live.",
        blocking_questions=_STANDARD_BLOCKING_QUESTIONS,
    ),
    Operation(
        name="query_network",
        client_method="TMobileTAAPClient.query_network",
        http_method="POST",
        path="/wholesale/network/v1/query",
        path_source=(
            "Hard-coded literal in tmobile_taap.py. No repository artifact "
            "attributes it to T-Mobile; it predates the documented contract work."
        ),
        classification=Classification.READ_ONLY,
        provenance=Provenance.DERIVED_UNCONFIRMED,
        request_schema="{msisdn} — our construction, not documented.",
        response_schema="UNKNOWN — never observed.",
        callback_behavior="Attaches call-back-location when configured. Unconfirmed.",
        required_headers=CONFIRMED_HEADERS + ("call-back-location (optional)",),
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Assumed synchronous. Unconfirmed.",
        reversibility="N/A — read-only.",
        prerequisite_state="An activated line.",
        pit_restrictions="UNKNOWN.",
        implementation_status="Implemented; not called by any service.",
        test_status="Mock-tested only. Never sent live.",
        blocking_questions=_STANDARD_BLOCKING_QUESTIONS,
    ),
    Operation(
        name="query_usage",
        client_method="TMobileTAAPClient.query_usage",
        http_method="POST",
        path="/wholesale/usage/v1/query",
        path_source=(
            "Hard-coded literal in tmobile_taap.py. No repository artifact "
            "attributes it to T-Mobile."
        ),
        classification=Classification.READ_ONLY,
        provenance=Provenance.DERIVED_UNCONFIRMED,
        request_schema="{msisdn, startDate, endDate} — date FORMAT is unspecified.",
        response_schema="UNKNOWN — never observed.",
        callback_behavior="No callback header attached. Unconfirmed.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Assumed synchronous. Unconfirmed.",
        reversibility="N/A — read-only.",
        prerequisite_state="An activated line with usage history.",
        pit_restrictions="UNKNOWN — PIT lines may have no usage data at all.",
        implementation_status="Implemented; not called by any service.",
        test_status="Mock-tested only. Never sent live.",
        blocking_questions=_STANDARD_BLOCKING_QUESTIONS + (
            "Required date format for startDate / endDate (ISO-8601? YYYYMMDD?).",
        ),
    ),

    # ── Lifecycle-family: implemented, path derived, therefore blocked ──────
    Operation(
        name="suspend_subscriber",
        client_method="TMobileTAAPClient.suspend_subscriber",
        http_method="POST",
        path="/wholesale/v1/subscriber/suspend",
        path_source=_DERIVED_PATH_NOTE,
        classification=Classification.REVERSIBLE,
        provenance=Provenance.DERIVED_UNCONFIRMED,
        request_schema="{msisdn, accountId} — our construction, not documented.",
        response_schema="UNKNOWN — never observed.",
        callback_behavior="No callback header attached by the client. Unconfirmed.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="UNKNOWN.",
        reversibility="Assumed reversible by restore_subscriber. UNCONFIRMED.",
        prerequisite_state="Active line.",
        pit_restrictions="UNKNOWN.",
        implementation_status=(
            "Implemented, and NOT fail-closed: unlike activate_subscriber it has "
            "no live-calls guard of its own. The harness supplies the gate."
        ),
        test_status="Mock-tested only. Never sent live.",
        blocking_questions=_STANDARD_BLOCKING_QUESTIONS + (
            "Does suspension bill differently, or have a maximum duration after "
            "which the line is auto-deactivated?",
        ),
    ),
    Operation(
        name="restore_subscriber",
        client_method="TMobileTAAPClient.restore_subscriber",
        http_method="POST",
        path="/wholesale/v1/subscriber/restore",
        path_source=_DERIVED_PATH_NOTE,
        classification=Classification.REVERSIBLE,
        provenance=Provenance.DERIVED_UNCONFIRMED,
        request_schema="{msisdn, accountId} — our construction, not documented.",
        response_schema="UNKNOWN — never observed.",
        callback_behavior="No callback header attached by the client. Unconfirmed.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="UNKNOWN.",
        reversibility="Inverse of suspend. UNCONFIRMED.",
        prerequisite_state="Suspended line.",
        pit_restrictions="UNKNOWN.",
        implementation_status="Implemented, not fail-closed (see suspend).",
        test_status="Mock-tested only. Never sent live.",
        blocking_questions=_STANDARD_BLOCKING_QUESTIONS + (
            "Does restore return the ORIGINAL MSISDN, or may it assign a new one?",
        ),
    ),
    Operation(
        name="change_sim",
        client_method="TMobileTAAPClient.change_sim",
        http_method="POST",
        path="/wholesale/v1/subscriber/changesim",
        path_source=_DERIVED_PATH_NOTE,
        classification=Classification.DESTRUCTIVE,
        provenance=Provenance.DERIVED_UNCONFIRMED,
        request_schema="{msisdn, iccid, accountId} — our construction.",
        response_schema="UNKNOWN — never observed.",
        callback_behavior=(
            "Attaches call-back-location when configured; the client's docstring "
            "states the swap completes asynchronously. UNCONFIRMED."
        ),
        required_headers=CONFIRMED_HEADERS + ("call-back-location (optional)",),
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Documented by us as async. Unconfirmed.",
        reversibility=(
            "Classified DESTRUCTIVE: a swap detaches the original ICCID, and no "
            "documented operation restores it. Swapping back requires the old SIM "
            "to still be assignable — unproven."
        ),
        prerequisite_state="Active line, plus a second unassigned ICCID.",
        pit_restrictions="UNKNOWN. Requires a second PIT SIM we may not have.",
        implementation_status="Implemented, not fail-closed.",
        test_status="Mock-tested only. Never sent live.",
        blocking_questions=_STANDARD_BLOCKING_QUESTIONS + (
            "Can a swapped-out ICCID be re-attached, and by what operation?",
        ),
    ),
    Operation(
        name="deactivate_subscriber",
        client_method="TMobileTAAPClient.deactivate_subscriber",
        http_method="POST",
        path="/wholesale/v1/subscriber/deactivate",
        path_source=_DERIVED_PATH_NOTE,
        classification=Classification.DESTRUCTIVE,
        provenance=Provenance.DERIVED_UNCONFIRMED,
        request_schema="{msisdn, accountId} — our construction, not documented.",
        response_schema="UNKNOWN — never observed.",
        callback_behavior="No callback header attached by the client. Unconfirmed.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="UNKNOWN.",
        reversibility=(
            "TERMINAL. No documented operation reactivates a deactivated line, "
            "and the MSISDN is expected to return to T-Mobile's pool."
        ),
        prerequisite_state="Active or suspended line.",
        pit_restrictions="UNKNOWN.",
        implementation_status="Implemented, not fail-closed (see suspend).",
        test_status="Mock-tested only. Never sent live.",
        blocking_questions=_STANDARD_BLOCKING_QUESTIONS + (
            "Is deactivation reversible in PIT, and is the MSISDN released?",
            "Is there a grace period during which the line can be recovered?",
        ),
    ),
)

_BY_NAME = {op.name: op for op in OPERATIONS}


def get_operation(name: str) -> Operation:
    """Look up an operation by name, or raise with the valid set listed."""
    try:
        return _BY_NAME[name]
    except KeyError:
        raise KeyError(
            f"Unknown operation {name!r}. Known operations: "
            f"{', '.join(sorted(_BY_NAME))}"
        ) from None


def sendable_operations() -> tuple[Operation, ...]:
    return tuple(op for op in OPERATIONS if op.is_sendable)


def blocked_operations() -> tuple[Operation, ...]:
    return tuple(op for op in OPERATIONS if not op.is_sendable)


def operations_by_classification(c: Classification) -> tuple[Operation, ...]:
    return tuple(op for op in OPERATIONS if op.classification is c)


class OperationBlocked(RuntimeError):
    """Raised when a live send is attempted for an unconfirmed operation."""


def require_sendable(op: Operation) -> None:
    """Fail closed unless the operation's provenance authorizes a live send."""
    if op.is_sendable:
        return
    questions = "\n".join(f"  {i}. {q}" for i, q in
                          enumerate(op.blocking_questions, 1))
    raise OperationBlocked(
        f"'{op.name}' is BLOCKED — nothing was sent.\n\n"
        f"Provenance: {op.provenance.value}\n"
        f"Path source: {op.path_source}\n\n"
        "This path was never supplied by T-Mobile. Sending it would be a guess "
        "aimed at a live carrier gateway.\n\n"
        f"Required from T-Mobile before this can be unblocked:\n{questions}\n\n"
        "To unblock: record T-Mobile's written answer in the repository, update "
        "this operation's provenance to TMOBILE_WRITTEN_SPEC in "
        "app/integrations/tmobile_operations.py, and add a golden test pinning "
        "the confirmed contract. It is a reviewed code change, never a config "
        "toggle."
    )
