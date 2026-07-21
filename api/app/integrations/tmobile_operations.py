"""Declarative inventory of T-Mobile Wholesale operations, with provenance.

This module answers one question for every operation: **on what evidence do we
believe this endpoint exists in this shape?** Nothing here is added from memory
or inference — each entry records where its path and schema came from, and an
operation may only be sent when that provenance is strong enough.

Why this exists
---------------
Every subscriber-family path here was once produced by joining an operation name
onto a base path::

    def _subscriber_path(self, op: str) -> str:
        return f"{self.subscriber_base_path}/{op.lstrip('/')}"

That derivation was wrong for **every** operation it was applied to. The paths
and methods below have since been reconciled against authorized vendor
documentation reviewed privately, and the corrections were substantial: seven
wrong paths, four wrong HTTP methods, and a wrong request body on every
lifecycle call.

Two rules follow, and both are load-bearing:

1. **Paths and methods are exact literals.** No route builder may reconstruct
   them from a naming convention. The convention has a perfect record of being
   wrong.
2. **Documentation does not authorize sending.** Knowing the contract says what
   to send; it says nothing about whether this client sends it correctly. Every
   reconciled operation stays live-blocked until it has been exercised in PIT
   under the normal gates — see :class:`ReadinessState` and ``is_sendable``.

The vendor source material is confidential and is retained only in the
operator's private evidence store. Nothing here quotes it; the entries below
carry the minimum wire facts needed for the client to function.
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
    # Reconciled against authorized vendor documentation reviewed privately.
    # The contract below is transcribed from that review; the source material
    # itself is confidential and is retained in the operator's private evidence
    # store, never in this repository.
    VENDOR_DOCUMENTED = "vendor_documented"
    # The path was produced by our own string derivation. NOT documented.
    DERIVED_UNCONFIRMED = "derived_unconfirmed"


class ReadinessState(str, Enum):
    """How far an operation has progressed toward being safe to send live.

    Separate from :class:`Provenance` on purpose: knowing the contract is not
    the same as having exercised it. An operation can be fully documented and
    still be nowhere near authorized for a live subscriber.
    """

    DOCUMENTED_UNREVIEWED = "documented_unreviewed"
    DOCUMENTED_REVIEWED = "documented_reviewed"
    IMPLEMENTATION_MISMATCH = "implementation_mismatch"
    IMPLEMENTATION_UPDATED = "implementation_updated"
    MOCK_CERTIFIED = "mock_certified"
    PIT_TEST_PREPARED = "pit_test_prepared"
    PIT_TEST_AUTHORIZED = "pit_test_authorized"
    PIT_TESTED = "pit_tested"
    PRODUCTION_APPROVED = "production_approved"
    BLOCKED = "blocked"


#: Opaque handle for the private reconciliation record. Deliberately carries no
#: document title, version, page, hash, or quotation — those live only in the
#: operator's private evidence store.
CONTRACT_EVIDENCE_REF = "TMO-REST-RECON-001"

#: Readiness states from which a live send may ever be considered. Being
#: documented is explicitly NOT enough.
LIVE_SENDABLE_READINESS = frozenset({ReadinessState.PIT_TESTED,
                                     ReadinessState.PRODUCTION_APPROVED})


# Provenance strong enough to authorize a live request.
SENDABLE_PROVENANCE = frozenset({
    Provenance.CONFIRMED_BY_LIVE_RESPONSE,
    Provenance.VENDOR_DOCUMENTED,
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

    #: How far this operation has progressed toward live authorization.
    readiness: ReadinessState = ReadinessState.BLOCKED

    @property
    def is_sendable(self) -> bool:
        """True only when provenance, risk class, AND readiness all allow it.

        The readiness term is the one that matters most here. Obtaining the
        vendor's contract answered *what* to send; it says nothing about whether
        this client actually sends it correctly, so knowing the contract must
        never by itself unlock a live subscriber call. Every operation whose
        contract was reconciled from documentation therefore stays blocked until
        it has been exercised in PIT under the normal gates.
        """
        return (
            self.provenance in SENDABLE_PROVENANCE
            and self.classification is not Classification.UNKNOWN
            and self.readiness in LIVE_SENDABLE_READINESS
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

# Every path below was corrected against authorized vendor documentation
# reviewed privately (see CONTRACT_EVIDENCE_REF). The previous values were
# produced by joining an operation name onto a base path, and that derivation
# was wrong for EVERY operation it was used on. Treat these as exact literals:
# no route builder may reconstruct them from a naming convention.
_VENDOR_PATH_NOTE = (
    "Exact vendor-confirmed wire path, reconciled against authorized vendor "
    "documentation retained in the operator's private evidence store "
    f"({CONTRACT_EVIDENCE_REF}). Do NOT derive by naming convention — the "
    "previous derived value was wrong."
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
        readiness=ReadinessState.PIT_TESTED,
    ),

    # ── Read-family: contract reconciled; live send still blocked ──────────
    Operation(
        name="subscriber_inquiry",
        client_method="TMobileTAAPClient.subscriber_inquiry",
        http_method="POST",
        path="/wholesale/v1/subscriber/profile",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.READ_ONLY,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="One of msisdn / iccid / imsi is required; any one suffices. Optional pairingId for companion or wearable lines. An account id is NOT a field of this operation.",
        response_schema="status is required, plus subscriber detail; isMultiline optional. Unknown fields are preserved.",
        callback_behavior="No callback. Synchronous only.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous.",
        reversibility="N/A - read-only.",
        prerequisite_state="Must have been previously provisioned; may be in any state, but a SIM still inactive in inventory is not queryable.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Implemented. Corrected: exact path, and the request no longer demands an account id - that requirement was never part of the contract.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
            "Confirm whether an inactive-in-inventory SIM returns an error code or an empty result.",
        ),
    ),
    Operation(
        name="query_network",
        client_method="TMobileTAAPClient.query_network",
        http_method="POST",
        path="/wholesale/v1/subscriber/network-profile",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.READ_ONLY,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="One of msisdn / iccid / imsi is required; any one suffices.",
        response_schema="status is required; optional msisdn, iccid, iccidStatus, imei, imsi, subscriberStatus and simNetworkType. Unknown fields are preserved.",
        callback_behavior="No callback. Synchronous only.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous. Async not applicable.",
        reversibility="N/A - read-only.",
        prerequisite_state="Subscriber must have been previously activated.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Implemented. Corrected: exact path, and iccid/imsi are now accepted as identifiers alongside msisdn.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
        ),
    ),
    Operation(
        name="query_usage",
        client_method="TMobileTAAPClient.query_usage",
        http_method="POST",
        path="/wholesale/v1/subscriber/usage",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.READ_ONLY,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="One of msisdn / iccid / imsi is required; any one suffices. This operation takes NO date range.",
        response_schema="status is required; isMultiline optional; usage detail; simNetworkType optional. Unknown fields are preserved.",
        callback_behavior="No callback. Synchronous only.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous. Async not applicable.",
        reversibility="N/A - read-only.",
        prerequisite_state="Previously activated and provisioned with voice, messaging, wallet or data.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Implemented. Corrected: exact path, identifier choice, and removal of the start/end date fields, which are not part of the contract.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
        ),
    ),

    # ── Lifecycle family: contract reconciled; live send still blocked ─────
    Operation(
        name="suspend_subscriber",
        client_method="TMobileTAAPClient.suspend_subscriber",
        http_method="PUT",
        path="/wholesale/v1/subscriber/suspension",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.REVERSIBLE,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="msisdn and iccid are BOTH required. Optional pairingId. An account id is not a field of this operation.",
        response_schema="status plus result detail. Unknown fields are preserved.",
        callback_behavior="Async response is not applicable to this operation - the synchronous response is the terminal answer.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous only.",
        reversibility="Reversible via restore_subscriber, the documented inverse.",
        prerequisite_state="SIM and MSISDN must both be active.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Implemented. Corrected: exact path, HTTP method (was POST), and the body now sends the required iccid and drops the undocumented account id.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
        ),
    ),
    Operation(
        name="restore_subscriber",
        client_method="TMobileTAAPClient.restore_subscriber",
        http_method="PUT",
        path="/wholesale/v1/subscriber/restoration",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.REVERSIBLE,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="msisdn and iccid are BOTH required. Optional pairingId.",
        response_schema="status plus result detail. Unknown fields are preserved.",
        callback_behavior="Async response follows once basic voice, data and text provisioning completes.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous acceptance, then asynchronous completion.",
        reversibility="Inverse of suspend_subscriber. Restores the same products and plans held before suspension.",
        prerequisite_state="SIM and MSISDN must both be suspended.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Implemented. Corrected: exact path, HTTP method (was POST), and the required iccid added.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
        ),
    ),
    Operation(
        name="change_sim",
        client_method="TMobileTAAPClient.change_sim",
        http_method="PUT",
        path="/wholesale/v1/subscriber/sim-change",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.DESTRUCTIVE,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="msisdn, iccid (the CURRENT sim) and newIccid are required. Optional pairingId. A rollback flag exists but is vendor-internal and is never sent by this client.",
        response_schema="status plus result detail. Unknown fields are preserved.",
        callback_behavior="Async response follows once basic provisioning completes.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous acceptance, then asynchronous completion.",
        reversibility="DESTRUCTIVE. The replaced SIM enters an aging process and no customer-facing inverse is documented. The vendor-internal rollback flag is not a supported customer rollback.",
        prerequisite_state="Current SIM and MSISDN active; the replacement SIM must be available.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Implemented. Corrected: exact path, HTTP method (was POST), and the body now distinguishes the current iccid from newIccid - the previous code sent the replacement SIM in the iccid field.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
            "Confirm whether a replaced ICCID can ever be re-attached, and by which operation.",
        ),
    ),
    Operation(
        name="deactivate_subscriber",
        client_method="TMobileTAAPClient.deactivate_subscriber",
        http_method="PUT",
        path="/wholesale/v1/subscriber/deactivation",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.DESTRUCTIVE,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="msisdn and iccid are BOTH required. A reuse flag exists but is machine-to-machine only and is never sent by this client without confirmation.",
        response_schema="status plus result detail. Unknown fields are preserved.",
        callback_behavior="Async response follows once basic provisioning completes.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous acceptance, then asynchronous completion.",
        reversibility="Classified DESTRUCTIVE. A reactivation operation exists in the vendor contract but is NOT implemented or tested here, and is not assumed to restore the same number or plans. Treat as terminal.",
        prerequisite_state="SIM and MSISDN active or suspended.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Implemented. Corrected: exact path, HTTP method (was POST), and the required iccid added.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
            "Confirm whether reactivation restores the original MSISDN and plans.",
        ),
    ),

    # ── Transaction support: newly reconciled, live send blocked ────────
    Operation(
        name="query_transaction_status",
        client_method="TMobileTAAPClient.query_transaction_status",
        http_method="POST",
        path="/wholesale/v1/transaction",
        path_source=_VENDOR_PATH_NOTE,
        classification=Classification.READ_ONLY,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="transactionId is required - the customer transaction id of a previously submitted request.",
        response_schema="status and action are required; optional msisdn, iccid, imei, marketZip and a result structure. Unknown fields are preserved.",
        callback_behavior="No callback. Synchronous only.",
        required_headers=CONFIRMED_HEADERS,
        pop_ehts=REFERENCE_EHTS,
        body_signed=True,
        synchronous="Synchronous.",
        reversibility="N/A - read-only.",
        prerequisite_state="A previously submitted transaction whose id we still hold.",
        pit_restrictions="Live send blocked; not yet exercised in PIT.",
        implementation_status="Newly implemented from the reconciled contract. This is the vendor-recommended way to inspect a delayed provisioning result instead of resending the request.",
        test_status="Mock-certified against the reconciled contract. Never sent live.",
        readiness=ReadinessState.MOCK_CERTIFIED,
        blocking_questions=(
            "Confirm whether the transactionId to submit is the value this client already sends as its per-request partner transaction id, or a different vendor-assigned identifier.",
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
        "this operation's provenance to VENDOR_DOCUMENTED in "
        "app/integrations/tmobile_operations.py, and add a golden test pinning "
        "the confirmed contract. It is a reviewed code change, never a config "
        "toggle."
    )

class TMobileOperationBlockedError(RuntimeError):
    """Raised when a live send is attempted for an operation not cleared for it.

    Carries everything an operator needs to understand the refusal without
    having to read this module: which operation, which gate stopped it, how far
    the operation has actually progressed, whether its contract is known, and
    the command that explains the rest.
    """

    def __init__(self, operation: str, gate: str, readiness: str,
                 contract_status: str, detail: str = ""):
        self.operation = operation
        self.gate = gate
        self.readiness = readiness
        self.contract_status = contract_status
        lines = [
            f"{operation}: BLOCKED — nothing was sent.",
            f"  blocking gate    : {gate}",
            f"  readiness state  : {readiness}",
            f"  contract status  : {contract_status}",
        ]
        if detail:
            lines.append(f"  detail           : {detail}")
        lines.append(
            f"  for details      : python ../scripts/tmobile_pit.py show {operation}"
        )
        super().__init__("\n".join(lines))


#: Exact wire paths mapped to their operation name. Used by the client boundary
#: to recognise an outbound request no matter which entry point produced it.
PATH_TO_OPERATION: dict[tuple[str, str], str] = {
    (op.http_method.upper(), op.path): op.name for op in OPERATIONS
}


def require_live_sendable(name: str) -> None:
    """Fail closed unless this operation is cleared for live transmission.

    This is the client boundary. It runs before OAuth and before any resource
    request, so a blocked operation costs zero network calls — not a failed one.
    Calling a client method directly must not be a way around the harness gates,
    which is why this lives next to the registry rather than in the CLI.
    """
    try:
        op = get_operation(name)
    except KeyError:
        raise TMobileOperationBlockedError(
            name, "unknown operation", "unknown", "not in the contract registry",
            "An operation absent from the registry has no reviewed contract.",
        ) from None

    if op.is_sendable:
        return

    if op.provenance is Provenance.DERIVED_UNCONFIRMED:
        gate, contract = "provenance", "no reviewed vendor contract"
    elif op.classification is Classification.UNKNOWN:
        gate, contract = "risk classification", "semantics not established"
    else:
        gate = "readiness"
        contract = (
            f"reconciled against authorized vendor documentation "
            f"({CONTRACT_EVIDENCE_REF})"
        )
    raise TMobileOperationBlockedError(
        op.name, gate, op.readiness.value, contract,
        "Knowing the contract is not authorization to send it. This operation "
        "must be exercised in PIT under the operator gates before live use.",
    )


def operation_for_request(http_method: str, path: str) -> str | None:
    """Return the operation name for an outbound request, if it is a known one."""
    return PATH_TO_OPERATION.get((http_method.upper(), path))
