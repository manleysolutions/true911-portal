"""Single-run PIT authorization for one operation against one subscriber.

The operation registry blocks every non-activation operation, and that block is
what makes the integration safe to work on. Certifying a read-only operation
needs a way through it exactly once — without turning the block into something
an operator can wave away.

So this is deliberately the narrowest possible exception:

* **one operation**, named explicitly, and only from a read-only allowlist;
* **one subscriber**, pinned by the exact selector the operator nominated;
* **one request** — the grant is consumed the moment the client boundary uses
  it, so a second call in the same process finds nothing;
* **PIT only**, refused outright if the environment is not PIT;
* **time-boxed**, so a forgotten grant expires rather than lingering;
* **auditable**, carrying operator identity and an audit reference.

It does **not** weaken the global guard. ``require_live_sendable`` still refuses
everything; this simply gives it one narrowly-matching key to check, and the key
destroys itself on use. Nothing here can authorize a mutation: the allowlist
below is read-only operations, and a grant for anything else raises.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.integrations.tmobile_evidence import mask_tail

#: Operations a single-run grant may ever cover. Read-only by construction —
#: a lifecycle mutation must never be reachable through this path.
AUTHORIZABLE_OPERATIONS = frozenset({
    "subscriber_inquiry", "query_network", "query_usage",
    "query_transaction_status",
})

#: A grant left lying around is a standing permission. Keep the window short
#: enough that forgetting to consume one is harmless.
DEFAULT_TTL = timedelta(minutes=15)

SELECTOR_TYPES = frozenset({"iccid", "msisdn", "imsi"})

#: QueryTransactionStatus does not target a subscriber — it targets one
#: previously submitted transaction. Its grant binds to that transaction id
#: instead, so a grant for transaction A cannot be spent on transaction B.
TRANSACTION_SELECTOR = "transaction_id"
ALL_SELECTOR_TYPES = SELECTOR_TYPES | {TRANSACTION_SELECTOR}


class AuthorizationError(RuntimeError):
    """Raised when a grant cannot be issued, or does not apply."""


def _fingerprint(value: str) -> str:
    """Stable, non-reversible handle for a selector.

    The grant must be able to prove it is about *this* subscriber without
    holding the identifier in a form that can be logged or serialized.
    """
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:16]


@dataclass
class PitSingleRunAuthorization:
    operation: str
    selector_type: str
    selector_fingerprint: str
    selector_masked: str
    operator: str
    audit_ref: str
    granted_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    consumed_for: str | None = None

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or datetime.now(timezone.utc)) >= self.expires_at

    def is_valid_for(self, operation: str, *, now: datetime | None = None) -> bool:
        return (
            not self.is_consumed
            and not self.is_expired(now=now)
            and operation == self.operation
        )

    def matches_selector(self, selector: str) -> bool:
        return _fingerprint(selector) == self.selector_fingerprint

    def consume(self, operation: str) -> None:
        if self.is_consumed:
            raise AuthorizationError(
                f"This PIT authorization was already consumed at "
                f"{self.consumed_at:%Y-%m-%dT%H:%M:%SZ}. It authorizes exactly "
                "one request; issue a new one deliberately."
            )
        if self.is_expired():
            raise AuthorizationError(
                "This PIT authorization has expired. Nothing was sent."
            )
        if operation != self.operation:
            raise AuthorizationError(
                f"This PIT authorization covers '{self.operation}', not "
                f"'{operation}'. Nothing was sent."
            )
        self.consumed_at = datetime.now(timezone.utc)
        self.consumed_for = operation

    def audit_record(self) -> dict[str, str | None]:
        """Auditable summary. Carries no reversible identifier."""
        return {
            "audit_ref": self.audit_ref,
            "operation": self.operation,
            "selector_type": self.selector_type,
            "selector_masked": self.selector_masked,
            "selector_fingerprint": self.selector_fingerprint,
            "operator": self.operator,
            "environment": "pit",
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
            "consumed_for": self.consumed_for,
        }


#: Process-scoped. Deliberately not persisted: a grant must not survive the
#: command that created it.
_ACTIVE: PitSingleRunAuthorization | None = None


def _environment_is_pit() -> bool:
    return str(settings.TMOBILE_ENV or "").strip().lower() == "pit"


def grant_single_run(
    *,
    operation: str,
    selector_type: str,
    selector: str,
    operator: str,
    confirmed: bool,
    ttl: timedelta = DEFAULT_TTL,
) -> PitSingleRunAuthorization:
    """Issue a single-run grant, or refuse with the reason."""
    global _ACTIVE

    if not _environment_is_pit():
        raise AuthorizationError(
            f"Environment is '{settings.TMOBILE_ENV}', not PIT. A single-run "
            "authorization may only be issued in PIT. Nothing was granted."
        )
    if operation not in AUTHORIZABLE_OPERATIONS:
        raise AuthorizationError(
            f"'{operation}' may not be single-run authorized. Only read-only "
            f"operations qualify: {', '.join(sorted(AUTHORIZABLE_OPERATIONS))}. "
            "Lifecycle mutations are never reachable through this path."
        )
    if selector_type not in ALL_SELECTOR_TYPES:
        raise AuthorizationError(
            f"selector_type must be one of {sorted(ALL_SELECTOR_TYPES)}."
        )
    if operation == "query_transaction_status" and selector_type != TRANSACTION_SELECTOR:
        raise AuthorizationError(
            "query_transaction_status binds to an exact transaction id, not a "
            f"subscriber selector (got '{selector_type}'). There is no "
            "'latest transaction' lookup."
        )
    if selector_type == TRANSACTION_SELECTOR and operation != "query_transaction_status":
        raise AuthorizationError(
            f"a transaction-id grant only covers query_transaction_status, "
            f"not '{operation}'."
        )
    if not (selector or "").strip():
        raise AuthorizationError(
            "A subscriber must be explicitly nominated. There is no 'latest' "
            "or default subscriber."
        )
    if not (operator or "").strip():
        raise AuthorizationError("An operator identity is required for the audit record.")
    if not confirmed:
        raise AuthorizationError(
            "Operator confirmation is required. Nothing was granted."
        )

    now = datetime.now(timezone.utc)
    _ACTIVE = PitSingleRunAuthorization(
        operation=operation,
        selector_type=selector_type,
        selector_fingerprint=_fingerprint(selector),
        selector_masked=mask_tail(selector) or "",
        operator=operator.strip(),
        audit_ref=f"TMO-PIT-{uuid.uuid4().hex[:12]}",
        granted_at=now,
        expires_at=now + ttl,
    )
    return _ACTIVE


def active_authorization() -> PitSingleRunAuthorization | None:
    return _ACTIVE


def clear_authorization() -> None:
    """Drop any active grant. Called after a run, and in test teardown."""
    global _ACTIVE
    _ACTIVE = None


def consume_if_authorized(operation: str) -> PitSingleRunAuthorization | None:
    """Consume a matching grant, or return None.

    Called from the client boundary. Returning None means "no exception
    applies" — the caller then refuses exactly as it would have anyway, so a
    missing or mismatched grant can never widen access.
    """
    auth = _ACTIVE
    if auth is None or not _environment_is_pit():
        return None
    if not auth.is_valid_for(operation):
        return None
    auth.consume(operation)
    return auth
