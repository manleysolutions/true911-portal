"""Narrow, public-safe handling of T-Mobile response codes.

This is deliberately **not** a catalogue. The vendor publishes several hundred
response codes with customer-facing message text, failure reasons and resolution
instructions; that material is confidential and is retained only in the
operator's private evidence store. Bulk-importing it into this public repository
would republish the vendor's documentation, so this module maps only the handful
of codes needed for behaviour we actually implement and test.

Everything else is treated as unknown and routed to manual review. That is the
safe default here: an unrecognised code means we do not know what happened, and
the one thing we must never do on a provisioning call is guess and resend.

Two rules encoded below are worth stating plainly, because both are easy to get
wrong from the vendor data alone:

1. **A vendor "retriable = yes" is not permission to retry automatically.** At
   least one code is marked retriable while its resolution instruction routes
   the operator to vendor support. Retry disposition is therefore derived from
   what the resolution actually requires, never from the retriable flag alone.
2. **Provisioning operations are never automatically retried, full stop** — no
   matter what disposition a code carries. After a successful synchronous
   acceptance the request is already in flight at the vendor; resending it risks
   a duplicate provisioning action. Inspect the transaction instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    UNKNOWN = "unknown"


class Disposition(str, Enum):
    """What an operator must actually do next.

    Derived from the resolution the vendor documents, not from a retriable flag.
    """

    CORRECT_REQUEST_THEN_RESUBMIT = "correct_request_then_resubmit"
    CORRECT_SUBSCRIBER_STATE_THEN_RESUBMIT = "correct_subscriber_state_then_resubmit"
    RETRY_LATER_WITH_OPERATOR_REVIEW = "retry_later_with_operator_review"
    CONTACT_TMOBILE_SUPPORT = "contact_tmobile_support"
    NON_RETRIABLE = "non_retriable"
    WARNING_CONTINUE = "warning_continue"
    UNKNOWN_MANUAL_REVIEW = "unknown_manual_review"


@dataclass(frozen=True)
class ResponseCode:
    """A single mapped code.

    Carries no vendor message, reason, or resolution text by design — only the
    minimum needed to decide what this client does next.
    """

    code: str
    severity: Severity
    disposition: Disposition
    automatic_retry: bool = False
    #: Operation an operator must run first, when the disposition demands a
    #: state correction. Named in True911 terms, not vendor terms.
    prerequisite_operation: str | None = None


#: Operations for which no automatic retry is ever permitted, regardless of the
#: disposition attached to a code. Every state-changing call belongs here.
NEVER_AUTO_RETRY_OPERATIONS = frozenset({
    "activate_subscriber", "suspend_subscriber", "restore_subscriber",
    "change_sim", "deactivate_subscriber",
})

# Only codes required for behaviour we implement and test appear here. Each was
# reviewed individually against the authorized vendor documentation held in the
# operator's private evidence store; none is bulk-imported.
_MAPPED: tuple[ResponseCode, ...] = (
    # Observed against PIT during the activation investigation.
    ResponseCode("GENS-0003", Severity.ERROR,
                 Disposition.CORRECT_REQUEST_THEN_RESUBMIT),
    # Reviewed because it governs the suspend/restore lifecycle we model.
    ResponseCode("GENS-0002", Severity.ERROR,
                 Disposition.CORRECT_SUBSCRIBER_STATE_THEN_RESUBMIT,
                 prerequisite_operation="restore_subscriber"),
    # Reviewed because it is the common identifier-mismatch failure across five
    # of the seven reconciled operations.
    ResponseCode("GENS-0012", Severity.ERROR,
                 Disposition.CORRECT_REQUEST_THEN_RESUBMIT),
    ResponseCode("GENS-0001", Severity.ERROR,
                 Disposition.CORRECT_REQUEST_THEN_RESUBMIT),
    # Vendor-side outage and internal exception: escalation, not retry.
    ResponseCode("GENS-0004", Severity.ERROR, Disposition.CONTACT_TMOBILE_SUPPORT),
    ResponseCode("GENS-0005", Severity.ERROR, Disposition.CONTACT_TMOBILE_SUPPORT),
    # The load-bearing counter-example: the vendor marks this retriable, but the
    # documented resolution routes to support. Retrying it automatically would
    # be wrong, which is why disposition never derives from the flag alone.
    ResponseCode("GENS-0006", Severity.ERROR, Disposition.CONTACT_TMOBILE_SUPPORT),
    # A warning, not a failure. Must not be treated as a terminal error.
    ResponseCode("GENS-0506", Severity.WARNING, Disposition.WARNING_CONTINUE),
)

_BY_CODE: dict[str, ResponseCode] = {rc.code: rc for rc in _MAPPED}


def lookup(code: str | None) -> ResponseCode:
    """Resolve a vendor code, failing closed on anything unrecognised.

    An unmapped code keeps its raw vendor spelling so operational evidence
    records what actually arrived, but always resolves to manual review.
    """
    raw = (code or "").strip()
    if not raw:
        return ResponseCode("", Severity.UNKNOWN, Disposition.UNKNOWN_MANUAL_REVIEW)
    found = _BY_CODE.get(raw)
    if found is not None:
        return found
    return ResponseCode(raw, Severity.UNKNOWN, Disposition.UNKNOWN_MANUAL_REVIEW)


def is_mapped(code: str | None) -> bool:
    return (code or "").strip() in _BY_CODE


def may_auto_retry(code: str | None, operation: str) -> bool:
    """Whether this client may resend automatically. Almost always False.

    Provisioning operations are excluded outright; unknown codes are excluded;
    and no currently mapped disposition authorizes an automatic resend. The
    function exists so the answer is derived in one reviewed place rather than
    inferred at each call site.
    """
    if operation in NEVER_AUTO_RETRY_OPERATIONS:
        return False
    return lookup(code).automatic_retry


def mapped_codes() -> tuple[str, ...]:
    return tuple(sorted(_BY_CODE))
