"""Lifecycle transactions, callback application rules, and idempotency.

A *lifecycle transaction* is one attempt to change a subscriber, from the moment
we send it to the moment a carrier result settles it. It is the record a
callback must correlate against before it is allowed to touch state.

The rule that shapes everything here: **a callback may only be applied by exact
correlation.** No timestamp proximity, no "the most recent pending transaction",
no matching on ICCID alone. Those fallbacks all look reasonable and all fail the
same way — under concurrency or replay they attribute a result to the wrong
attempt, and a wrong lifecycle result is materially worse than an unapplied one.
Anything that cannot be correlated exactly is quarantined with its evidence
intact and left for a human.

Persistence note: these are typed, persistence-ready structures, not ORM models.
A durable table is deliberately deferred — see the PR description — because the
repository's migration chain is currently branched and adding a revision here
would entangle this work with an unrelated in-flight migration.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.integrations.tmobile_contracts import (
    NormalizedStatus,
    ResponseKind,
    TMobileResponseEnvelope,
)
from app.integrations.tmobile_evidence import mask_tail
from app.integrations.tmobile_state import (
    TMobileSubscriberState,
    TransitionError,
    settle_transition,
)


class TransactionStatus(str, Enum):
    INITIATED = "initiated"
    SYNC_ACCEPTED = "sync_accepted"
    SYNC_REJECTED = "sync_rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    MANUAL_REVIEW = "manual_review"


class CallbackDecision(str, Enum):
    """What happened to an inbound callback. Every value is auditable."""

    APPLIED = "applied"
    DUPLICATE_IGNORED = "duplicate_ignored"
    REPLAY_AFTER_COMPLETION = "replay_after_completion"
    STALE_IGNORED = "stale_ignored"
    QUARANTINED_UNKNOWN_TRANSACTION = "quarantined_unknown_transaction"
    QUARANTINED_CONFLICTING_IDENTIFIER = "quarantined_conflicting_identifier"
    QUARANTINED_CONFLICTING_OPERATION = "quarantined_conflicting_operation"
    QUARANTINED_AMBIGUOUS = "quarantined_ambiguous"
    QUARANTINED_NO_CORRELATION = "quarantined_no_correlation"
    QUARANTINED_INVALID_TRANSITION = "quarantined_invalid_transition"
    QUARANTINED_UNKNOWN_RESULT = "quarantined_unknown_result"


#: Decisions that leave subscriber state untouched.
NON_MUTATING_DECISIONS = frozenset(
    d for d in CallbackDecision if d is not CallbackDecision.APPLIED
)


@dataclass
class LifecycleTransaction:
    """One attempt to mutate a subscriber, with its full evidence trail."""

    operation: str
    tenant_id: str
    subscriber_ref: str | None = None

    # Identifiers are stored masked. The full values live on the subscriber
    # record; a transaction log is read far more often than it is acted on.
    iccid_masked: str | None = None
    msisdn_masked: str | None = None

    partner_transaction_id: str | None = None
    workflow_id: str | None = None
    service_transaction_id: str | None = None

    source_state: str | None = None
    pending_state: str | None = None
    expected_state: str | None = None
    actual_terminal_state: str | None = None

    status: TransactionStatus = TransactionStatus.INITIATED
    sync_vendor_code: str | None = None
    async_vendor_code: str | None = None
    internal_disposition: str | None = None

    initiated_by: str | None = None
    initiated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))
    sync_response_at: datetime | None = None
    async_response_at: datetime | None = None
    completed_at: datetime | None = None

    evidence_ref: str | None = None
    supersedes_transaction: str | None = None
    superseded_by: str | None = None
    manual_review_reason: str | None = None

    #: Idempotency keys of callbacks already applied to this transaction.
    applied_callback_keys: set[str] = field(default_factory=set)

    @property
    def is_settled(self) -> bool:
        return self.status in (TransactionStatus.COMPLETED,
                               TransactionStatus.FAILED,
                               TransactionStatus.SUPERSEDED)

    def correlation_ids(self) -> set[str]:
        return {v for v in (self.partner_transaction_id, self.workflow_id,
                            self.service_transaction_id) if v}


def callback_idempotency_key(envelope: TMobileResponseEnvelope) -> str:
    """A stable key for one delivered callback.

    Built from the correlation ids, operation and outcome — deliberately NOT
    from arrival time, so the same callback delivered twice (or replayed after a
    process restart) produces the same key.
    """
    material = "|".join([
        envelope.operation,
        envelope.partner_transaction_id or "",
        envelope.workflow_id or "",
        envelope.service_transaction_id or "",
        envelope.normalized_status.value,
        envelope.vendor_code or "",
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


@dataclass
class CallbackOutcome:
    decision: CallbackDecision
    transaction: LifecycleTransaction | None = None
    reason: str = ""
    state_changed: bool = False

    @property
    def quarantined(self) -> bool:
        return self.decision.name.startswith("QUARANTINED")


def correlate(
    envelope: TMobileResponseEnvelope,
    candidates: list[LifecycleTransaction],
) -> tuple[LifecycleTransaction | None, CallbackDecision | None, str]:
    """Find the one transaction this callback belongs to, or refuse.

    Correlation is by exact identifier match only, in documented precedence:
    partner transaction id, then workflow id, then service transaction id. If
    none of those is present, or more than one transaction matches, the callback
    is quarantined — never guessed at.
    """
    for attr, label in (("partner_transaction_id", "partner-transaction-id"),
                        ("workflow_id", "workflow-id"),
                        ("service_transaction_id", "service-transaction-id")):
        value = getattr(envelope, attr)
        if not value:
            continue
        matches = [t for t in candidates if getattr(t, attr) == value]
        if len(matches) == 1:
            return matches[0], None, f"matched on {label}"
        if len(matches) > 1:
            return None, CallbackDecision.QUARANTINED_AMBIGUOUS, (
                f"{len(matches)} transactions share the same {label}"
            )

    return None, CallbackDecision.QUARANTINED_NO_CORRELATION, (
        "callback carried no usable correlation identifier; there is no "
        "latest-pending or timestamp fallback by design"
    )


def apply_callback(
    envelope: TMobileResponseEnvelope,
    candidates: list[LifecycleTransaction],
    state: TMobileSubscriberState,
    *,
    expected_iccid: str | None = None,
) -> CallbackOutcome:
    """Decide whether a callback may change subscriber state, and apply it.

    Every refusal path preserves the callback's evidence and leaves state
    untouched. The function never mutates on a path it is not certain about.
    """
    transaction, refusal, reason = correlate(envelope, candidates)
    if refusal is not None:
        return CallbackOutcome(refusal, None, reason)
    assert transaction is not None

    if transaction.operation != envelope.operation:
        return CallbackOutcome(
            CallbackDecision.QUARANTINED_CONFLICTING_OPERATION, transaction,
            f"callback is for '{envelope.operation}' but the correlated "
            f"transaction is '{transaction.operation}'",
        )

    if expected_iccid and envelope.iccid and envelope.iccid != expected_iccid:
        return CallbackOutcome(
            CallbackDecision.QUARANTINED_CONFLICTING_IDENTIFIER, transaction,
            f"callback names SIM {mask_tail(envelope.iccid)}, the transaction "
            f"targets {mask_tail(expected_iccid)}",
        )

    key = callback_idempotency_key(envelope)
    if key in transaction.applied_callback_keys:
        return CallbackOutcome(
            CallbackDecision.DUPLICATE_IGNORED, transaction,
            "identical callback already applied to this transaction",
        )

    if transaction.status is TransactionStatus.SUPERSEDED:
        return CallbackOutcome(
            CallbackDecision.STALE_IGNORED, transaction,
            "transaction was superseded by a newer lifecycle transaction",
        )

    if transaction.is_settled:
        # A terminal result already stands. A later contradicting result is not
        # applied silently — it is surfaced, because one of the two is wrong.
        return CallbackOutcome(
            CallbackDecision.REPLAY_AFTER_COMPLETION, transaction,
            f"transaction already {transaction.status.value}; a later callback "
            "cannot overwrite a settled terminal result",
        )

    if envelope.normalized_status is NormalizedStatus.UNKNOWN:
        transaction.status = TransactionStatus.MANUAL_REVIEW
        transaction.manual_review_reason = "unrecognised result status"
        state.require_reconciliation("callback carried an unrecognised status")
        return CallbackOutcome(
            CallbackDecision.QUARANTINED_UNKNOWN_RESULT, transaction,
            "result status not understood; routed to manual review",
        )

    succeeded = envelope.normalized_status is NormalizedStatus.SUCCESS
    try:
        settle_transition(transaction.operation, state, succeeded=succeeded)
    except TransitionError as exc:
        transaction.status = TransactionStatus.MANUAL_REVIEW
        transaction.manual_review_reason = str(exc)
        state.require_reconciliation(str(exc))
        return CallbackOutcome(
            CallbackDecision.QUARANTINED_INVALID_TRANSITION, transaction,
            str(exc),
        )

    transaction.applied_callback_keys.add(key)
    transaction.async_vendor_code = envelope.vendor_code
    transaction.async_response_at = envelope.received_at
    transaction.internal_disposition = envelope.disposition
    if succeeded:
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = envelope.received_at
    else:
        transaction.status = TransactionStatus.FAILED
    transaction.actual_terminal_state = state.workflow_state.value

    return CallbackOutcome(CallbackDecision.APPLIED, transaction,
                           reason, state_changed=True)


def record_sync_response(
    transaction: LifecycleTransaction, envelope: TMobileResponseEnvelope
) -> LifecycleTransaction:
    """Record the immediate answer. Never marks the transaction complete.

    Acceptance means authenticated and validated. For every mutation except
    suspension, completion arrives later and separately.
    """
    transaction.sync_response_at = envelope.received_at
    transaction.sync_vendor_code = envelope.vendor_code
    transaction.partner_transaction_id = (
        envelope.partner_transaction_id or transaction.partner_transaction_id)
    transaction.workflow_id = envelope.workflow_id or transaction.workflow_id
    transaction.service_transaction_id = (
        envelope.service_transaction_id or transaction.service_transaction_id)
    transaction.status = (
        TransactionStatus.SYNC_ACCEPTED if envelope.accepted
        else TransactionStatus.SYNC_REJECTED
    )
    return transaction
