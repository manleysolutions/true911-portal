"""Normalized T-Mobile subscriber lifecycle: states, transitions, preconditions.

One authoritative state vocabulary, one transition registry, one precondition
policy. Previously these judgements were spread across the client, the operator
CLI, and the callback processor, which is how two of them came to disagree.

The idea that shapes this module is that **a synchronous acceptance is not a
result**. The vendor answers immediately to say a request authenticated and
validated; provisioning finishes later and is reported asynchronously. So every
mutation moves the line into an explicit ``*_pending`` state and only an
asynchronous result settles it. Treating the immediate answer as terminal is the
single most likely way to corrupt our view of a subscriber.

Five different things are tracked separately rather than collapsed into one
string, because they genuinely disagree in normal operation:

* what the carrier last told us (``carrier_status_*``)
* what our own workflow believes (``workflow_state``)
* what we expect an in-flight operation to produce (``expected_state``)
* what we last confirmed (``last_confirmed_state``)
* whether the two need human reconciliation (``reconciliation_*``)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app.integrations.tmobile_operations import (
    Classification,
    get_operation,
)


class LifecycleState(str, Enum):
    """The internal vocabulary. Every state here is reachable by an operation
    this client actually implements — none is included merely because a carrier
    might plausibly have it."""

    UNKNOWN = "unknown"
    ACTIVATION_PENDING = "activation_pending"
    ACTIVE = "active"
    SUSPEND_PENDING = "suspend_pending"
    SUSPENDED = "suspended"
    RESTORE_PENDING = "restore_pending"
    SIM_CHANGE_PENDING = "sim_change_pending"
    DEACTIVATION_PENDING = "deactivation_pending"
    DEACTIVATED = "deactivated"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


#: In-flight states. A second mutation while one of these is outstanding is a
#: duplicate, not a new intent.
PENDING_STATES = frozenset({
    LifecycleState.ACTIVATION_PENDING, LifecycleState.SUSPEND_PENDING,
    LifecycleState.RESTORE_PENDING, LifecycleState.SIM_CHANGE_PENDING,
    LifecycleState.DEACTIVATION_PENDING,
})

#: No operation moves a line out of these.
TERMINAL_STATES = frozenset({LifecycleState.DEACTIVATED})

#: States whose meaning is established by observed evidence rather than
#: assumption. Only the activation path has ever been exercised live.
EVIDENCE_BACKED_STATES = frozenset({
    LifecycleState.UNKNOWN, LifecycleState.ACTIVATION_PENDING,
    LifecycleState.ACTIVE, LifecycleState.FAILED,
})


class TransitionError(RuntimeError):
    """Raised when an operation cannot legally run from the current state."""


@dataclass(frozen=True)
class Transition:
    operation: str
    allowed_source_states: frozenset[LifecycleState]
    pending_state: LifecycleState
    expected_terminal_state: LifecycleState
    failure_state: LifecycleState
    expects_async_completion: bool
    inverse_operation: str | None
    #: True only when the transition has been exercised against the carrier.
    evidence_backed: bool = False


#: Read-only operations are absent by design: they have no transition.
TRANSITIONS: dict[str, Transition] = {
    "activate_subscriber": Transition(
        operation="activate_subscriber",
        allowed_source_states=frozenset({LifecycleState.UNKNOWN,
                                         LifecycleState.FAILED}),
        pending_state=LifecycleState.ACTIVATION_PENDING,
        expected_terminal_state=LifecycleState.ACTIVE,
        failure_state=LifecycleState.FAILED,
        expects_async_completion=True,
        inverse_operation="deactivate_subscriber",
        evidence_backed=True,
    ),
    "suspend_subscriber": Transition(
        operation="suspend_subscriber",
        allowed_source_states=frozenset({LifecycleState.ACTIVE}),
        pending_state=LifecycleState.SUSPEND_PENDING,
        expected_terminal_state=LifecycleState.SUSPENDED,
        failure_state=LifecycleState.FAILED,
        # The contract states an asynchronous response is not applicable here:
        # the synchronous answer is the terminal one for suspension alone.
        expects_async_completion=False,
        inverse_operation="restore_subscriber",
    ),
    "restore_subscriber": Transition(
        operation="restore_subscriber",
        allowed_source_states=frozenset({LifecycleState.SUSPENDED}),
        pending_state=LifecycleState.RESTORE_PENDING,
        expected_terminal_state=LifecycleState.ACTIVE,
        failure_state=LifecycleState.FAILED,
        expects_async_completion=True,
        inverse_operation="suspend_subscriber",
    ),
    "change_sim": Transition(
        operation="change_sim",
        allowed_source_states=frozenset({LifecycleState.ACTIVE}),
        pending_state=LifecycleState.SIM_CHANGE_PENDING,
        # The line stays active; its SIM identity changes.
        expected_terminal_state=LifecycleState.ACTIVE,
        failure_state=LifecycleState.FAILED,
        expects_async_completion=True,
        inverse_operation=None,          # replaced SIM ages out
    ),
    "deactivate_subscriber": Transition(
        operation="deactivate_subscriber",
        allowed_source_states=frozenset({LifecycleState.ACTIVE,
                                         LifecycleState.SUSPENDED}),
        pending_state=LifecycleState.DEACTIVATION_PENDING,
        expected_terminal_state=LifecycleState.DEACTIVATED,
        failure_state=LifecycleState.FAILED,
        expects_async_completion=True,
        inverse_operation=None,          # reactivation not implemented here
    ),
}

READ_ONLY_OPERATIONS = frozenset({
    "subscriber_inquiry", "query_network", "query_usage",
    "query_transaction_status",
})


@dataclass
class TMobileSubscriberState:
    """What we believe about one line, and how confident we are.

    ``carrier_status_raw`` keeps the vendor's own word verbatim for evidence;
    everything else is normalized. The two are never merged, because a
    disagreement between them is exactly the signal reconciliation needs.
    """

    carrier_status_raw: str | None = None
    carrier_status_normalized: LifecycleState = LifecycleState.UNKNOWN
    workflow_state: LifecycleState = LifecycleState.UNKNOWN
    expected_state: LifecycleState | None = None
    last_confirmed_state: LifecycleState | None = None

    pending_operation: str | None = None
    pending_partner_transaction_id: str | None = None
    pending_workflow_id: str | None = None

    state_observed_at: datetime | None = None
    state_confirmed_at: datetime | None = None
    source_operation: str | None = None

    #: "confirmed" when settled by a carrier result, "assumed" while pending,
    #: "unknown" when we have never had an answer.
    confidence: str = "unknown"
    reconciliation_required: bool = False
    reconciliation_reason: str | None = None

    @property
    def has_pending_mutation(self) -> bool:
        return self.workflow_state in PENDING_STATES

    def require_reconciliation(self, reason: str) -> None:
        self.reconciliation_required = True
        self.reconciliation_reason = reason
        self.workflow_state = LifecycleState.MANUAL_REVIEW
        self.confidence = "unknown"


class PreconditionError(RuntimeError):
    """Raised when an operation is not permitted from the current state."""


def check_preconditions(operation: str, state: TMobileSubscriberState) -> None:
    """Central gate for whether an operation may proceed from this state.

    Fails closed on unknown state for every mutation. A read stays permitted
    regardless of lifecycle state — a query is how you *find out* the state, so
    gating it on knowing the state would be circular.
    """
    op = get_operation(operation)

    if operation in READ_ONLY_OPERATIONS:
        # Reads carry a usage restriction rather than a state precondition:
        # on-demand operator investigation only, never bulk or scheduled. That
        # restriction is enforced at the operator boundary, not here.
        return

    transition = TRANSITIONS.get(operation)
    if transition is None:
        raise PreconditionError(
            f"'{operation}' has no registered transition; refusing to mutate."
        )

    current = state.workflow_state

    if current in TERMINAL_STATES:
        raise PreconditionError(
            f"Line is {current.value}; no operation can move it. "
            f"Refusing '{operation}'."
        )

    if state.has_pending_mutation:
        raise PreconditionError(
            f"'{state.pending_operation}' is still pending "
            f"(state {current.value}). Refusing '{operation}' as a probable "
            "DUPLICATE — reconcile the outstanding transaction first."
        )

    if current is LifecycleState.UNKNOWN:
        raise PreconditionError(
            f"Subscriber state is unknown. Refusing the mutating operation "
            f"'{operation}' — establish the state first. Mutations fail closed "
            "on unknown state."
        )

    if current is LifecycleState.MANUAL_REVIEW:
        raise PreconditionError(
            f"Line is flagged for manual review"
            + (f" ({state.reconciliation_reason})" if state.reconciliation_reason else "")
            + f". Refusing '{operation}' until it is resolved."
        )

    if current not in transition.allowed_source_states:
        allowed = ", ".join(sorted(s.value for s in transition.allowed_source_states))
        raise PreconditionError(
            f"'{operation}' requires state in [{allowed}]; the line is "
            f"{current.value}."
        )

    if state.confidence != "confirmed":
        raise PreconditionError(
            f"'{operation}' requires a CONFIRMED state; the current "
            f"{current.value} is '{state.confidence}'. Confirm it before "
            "mutating."
        )

    if op.classification is Classification.DESTRUCTIVE:
        # The operator-confirmation flags live at the CLI boundary; this is the
        # policy record that they are required at all.
        return


def begin_transition(operation: str, state: TMobileSubscriberState,
                     *, partner_transaction_id: str | None = None,
                     workflow_id: str | None = None) -> TMobileSubscriberState:
    """Move a line into its pending state after a synchronous acceptance.

    Explicitly does NOT set a terminal state — acceptance is not completion.
    """
    check_preconditions(operation, state)
    transition = TRANSITIONS[operation]

    state.last_confirmed_state = state.workflow_state
    state.workflow_state = transition.pending_state
    state.expected_state = transition.expected_terminal_state
    state.pending_operation = operation
    state.pending_partner_transaction_id = partner_transaction_id
    state.pending_workflow_id = workflow_id
    state.source_operation = operation
    state.state_observed_at = datetime.now(timezone.utc)
    state.confidence = "assumed"
    return state


def settle_transition(operation: str, state: TMobileSubscriberState,
                      *, succeeded: bool) -> TMobileSubscriberState:
    """Apply an asynchronous result to a pending line."""
    transition = TRANSITIONS.get(operation)
    if transition is None:
        raise TransitionError(f"'{operation}' has no registered transition.")
    if state.workflow_state is not transition.pending_state:
        raise TransitionError(
            f"Cannot settle '{operation}': the line is "
            f"{state.workflow_state.value}, not {transition.pending_state.value}."
        )

    state.workflow_state = (
        transition.expected_terminal_state if succeeded else transition.failure_state
    )
    state.last_confirmed_state = state.workflow_state
    state.expected_state = None
    state.pending_operation = None
    state.pending_partner_transaction_id = None
    state.pending_workflow_id = None
    state.state_confirmed_at = datetime.now(timezone.utc)
    state.confidence = "confirmed"
    return state


def is_evidence_backed(state: LifecycleState) -> bool:
    return state in EVIDENCE_BACKED_STATES
