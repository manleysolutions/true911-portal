"""Subscriber lifecycle state machine and PIT test-SIM allowlist policy.

Two safety mechanisms live here, both deliberately conservative.

**The state machine** tracks what we believe a line's state to be and refuses
transitions that make no sense. Only ONE state and ONE transition are actually
confirmed by evidence — ``UNKNOWN -> ACTIVATION_REQUESTED -> ACTIVE``, proven by
the 2026-07-21 HTTP 201. Every other state is marked ``confirmed=False``: it is
reachable only through an operation whose contract T-Mobile has not supplied
(see ``tmobile_operations``), so its semantics are our assumption, not their
documentation. The machine models them so the harness can reason and so the
transitions are testable — never as a claim that they are real.

**The allowlist policy** enforces that a live call can only ever target a SIM an
operator deliberately nominated, at the risk tier the operation requires. Three
nested lists, all empty by default, no wildcards. Being on the read-only list
does not authorize suspension; being on the lifecycle list does not authorize
deactivation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.config import settings
from app.integrations.tmobile_evidence import mask_tail
from app.integrations.tmobile_operations import Classification


# ── Lifecycle states ────────────────────────────────────────────────────────

class LifecycleState(str, Enum):
    """States we track for a PIT subscriber line.

    These are OUR tracking states. T-Mobile has not published a state
    vocabulary, so these are named for what we can observe, not for what their
    gateway calls them.
    """

    UNKNOWN = "unknown"
    ACTIVATION_REQUESTED = "activation_requested"
    ACTIVE = "active"
    SUSPENSION_REQUESTED = "suspension_requested"
    SUSPENDED = "suspended"
    RESTORE_REQUESTED = "restore_requested"
    DEACTIVATION_REQUESTED = "deactivation_requested"
    DEACTIVATED = "deactivated"
    FAILED = "failed"


#: States whose meaning is established by observed evidence rather than
#: assumption. Everything else is modelled but unproven.
CONFIRMED_STATES = frozenset({
    LifecycleState.UNKNOWN,
    LifecycleState.ACTIVATION_REQUESTED,
    LifecycleState.ACTIVE,
    LifecycleState.FAILED,
})

#: Terminal states — no transition leaves them.
TERMINAL_STATES = frozenset({LifecycleState.DEACTIVATED})

#: A pending state is one where we have sent a request and not yet reconciled a
#: terminal answer. A second state-changing request while pending is a duplicate.
PENDING_STATES = frozenset({
    LifecycleState.ACTIVATION_REQUESTED,
    LifecycleState.SUSPENSION_REQUESTED,
    LifecycleState.RESTORE_REQUESTED,
    LifecycleState.DEACTIVATION_REQUESTED,
})


@dataclass(frozen=True)
class Transition:
    operation: str
    from_state: LifecycleState
    to_state: LifecycleState
    confirmed: bool


#: The operation -> (allowed source states, requested state, settled state) map.
#: A state-changing operation moves the line into a *_REQUESTED state first; the
#: settled state is reached only when a response or callback reconciles it.
TRANSITIONS: tuple[Transition, ...] = (
    # Confirmed by the 2026-07-21 activation.
    Transition("activate_subscriber", LifecycleState.UNKNOWN,
               LifecycleState.ACTIVATION_REQUESTED, confirmed=True),
    Transition("activate_subscriber", LifecycleState.ACTIVATION_REQUESTED,
               LifecycleState.ACTIVE, confirmed=True),
    Transition("activate_subscriber", LifecycleState.ACTIVATION_REQUESTED,
               LifecycleState.FAILED, confirmed=True),

    # Modelled, NOT confirmed — each depends on a blocked operation.
    Transition("suspend_subscriber", LifecycleState.ACTIVE,
               LifecycleState.SUSPENSION_REQUESTED, confirmed=False),
    Transition("suspend_subscriber", LifecycleState.SUSPENSION_REQUESTED,
               LifecycleState.SUSPENDED, confirmed=False),
    Transition("restore_subscriber", LifecycleState.SUSPENDED,
               LifecycleState.RESTORE_REQUESTED, confirmed=False),
    Transition("restore_subscriber", LifecycleState.RESTORE_REQUESTED,
               LifecycleState.ACTIVE, confirmed=False),
    Transition("deactivate_subscriber", LifecycleState.ACTIVE,
               LifecycleState.DEACTIVATION_REQUESTED, confirmed=False),
    Transition("deactivate_subscriber", LifecycleState.SUSPENDED,
               LifecycleState.DEACTIVATION_REQUESTED, confirmed=False),
    Transition("deactivate_subscriber", LifecycleState.DEACTIVATION_REQUESTED,
               LifecycleState.DEACTIVATED, confirmed=False),
)


class InvalidTransition(RuntimeError):
    """Raised when an operation cannot legally run from the current state."""


def allowed_operations(state: LifecycleState) -> tuple[str, ...]:
    return tuple(sorted({
        t.operation for t in TRANSITIONS if t.from_state is state
    }))


def next_state(operation: str, state: LifecycleState) -> LifecycleState:
    """Resolve the state an operation moves the line into.

    Raises :class:`InvalidTransition` for a terminal state, a duplicate request
    while one is already pending, or any transition not in the table.
    """
    if state in TERMINAL_STATES:
        raise InvalidTransition(
            f"Line is in terminal state '{state.value}'. No operation can move "
            f"it. Refusing '{operation}'."
        )
    if state in PENDING_STATES:
        raise InvalidTransition(
            f"A previous request is still pending (state '{state.value}'). "
            f"Refusing '{operation}' as a probable DUPLICATE — reconcile the "
            "outstanding request first (verify the callback and the observed "
            "state), then retry deliberately."
        )
    for t in TRANSITIONS:
        if t.operation == operation and t.from_state is state:
            return t.to_state
    raise InvalidTransition(
        f"'{operation}' is not a valid transition from '{state.value}'. "
        f"Valid from here: {', '.join(allowed_operations(state)) or 'none'}."
    )


def settle(operation: str, pending: LifecycleState) -> LifecycleState:
    """Resolve the settled state reached from a pending state."""
    for t in TRANSITIONS:
        if (t.operation == operation and t.from_state is pending
                and t.to_state not in PENDING_STATES
                and t.to_state is not LifecycleState.FAILED):
            return t.to_state
    raise InvalidTransition(
        f"No settled state for '{operation}' from '{pending.value}'."
    )


def is_confirmed_state(state: LifecycleState) -> bool:
    return state in CONFIRMED_STATES


# ── PIT test-SIM allowlists ─────────────────────────────────────────────────

#: An ICCID is 19-20 digits. Anything else is a typo or a wildcard attempt.
_ICCID_RE = re.compile(r"^\d{19,20}$")

#: Deactivating the line that proves the integration works would destroy our
#: only end-to-end evidence. It must be nominated to the destructive list
#: deliberately and separately — never inherited from the lifecycle list.
PROTECTED_ICCIDS: frozenset[str] = frozenset({"8901260963132697538"})


class AllowlistError(RuntimeError):
    """Raised for a malformed allowlist or a disallowed target ICCID."""


def parse_allowlist(raw: str, *, name: str) -> tuple[str, ...]:
    """Parse and validate a comma-separated ICCID allowlist.

    Refuses wildcards and malformed entries outright rather than silently
    dropping them — a typo that silently shrinks an allowlist is safe, but a
    typo that silently *matches* nothing hides an operator error.
    """
    entries = [e.strip() for e in (raw or "").split(",") if e.strip()]
    for entry in entries:
        if entry in ("*", "all", "any") or "*" in entry or "?" in entry:
            raise AllowlistError(
                f"{name}: wildcards are not permitted (got {entry!r}). "
                "Every test SIM must be listed explicitly."
            )
        if not _ICCID_RE.match(entry):
            raise AllowlistError(
                f"{name}: {mask_tail(entry)!r} is not a valid ICCID "
                "(expected 19-20 digits)."
            )
    # De-duplicate, preserving order.
    seen: dict[str, None] = {}
    for e in entries:
        seen.setdefault(e, None)
    return tuple(seen)


@dataclass(frozen=True)
class AllowlistPolicy:
    read_only: tuple[str, ...]
    lifecycle: tuple[str, ...]
    destructive: tuple[str, ...]

    @classmethod
    def from_settings(cls) -> "AllowlistPolicy":
        policy = cls(
            read_only=parse_allowlist(
                settings.TMOBILE_PIT_READONLY_ICCID_ALLOWLIST,
                name="TMOBILE_PIT_READONLY_ICCID_ALLOWLIST"),
            lifecycle=parse_allowlist(
                settings.TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST,
                name="TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST"),
            destructive=parse_allowlist(
                settings.TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST,
                name="TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST"),
        )
        policy.validate_hierarchy()
        return policy

    def validate_hierarchy(self) -> None:
        """Each tier must be a subset of the one below it in risk.

        An ICCID you are not permitted to *read* must not be one you are
        permitted to *destroy*. Enforced at parse time so a misconfiguration
        fails at the first operator command, not mid-sequence.
        """
        stray_lifecycle = set(self.lifecycle) - set(self.read_only)
        if stray_lifecycle:
            raise AllowlistError(
                "TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST contains ICCIDs absent "
                "from the read-only list: "
                f"{sorted(mask_tail(i) for i in stray_lifecycle)}. The lifecycle "
                "list must be a subset of the read-only list."
            )
        stray_destructive = set(self.destructive) - set(self.lifecycle)
        if stray_destructive:
            raise AllowlistError(
                "TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST contains ICCIDs absent "
                "from the lifecycle list: "
                f"{sorted(mask_tail(i) for i in stray_destructive)}. The "
                "destructive list must be a subset of the lifecycle list."
            )

    def tier_for(self, classification: Classification) -> tuple[str, ...]:
        if classification is Classification.READ_ONLY:
            return self.read_only
        if classification is Classification.REVERSIBLE:
            return self.lifecycle
        if classification is Classification.DESTRUCTIVE:
            return self.destructive
        # UNKNOWN operations are blocked upstream and have no tier.
        return ()

    def require_allowed(self, iccid: str, classification: Classification) -> None:
        """Fail closed unless this ICCID is nominated at this risk tier."""
        tier_name = {
            Classification.READ_ONLY: "TMOBILE_PIT_READONLY_ICCID_ALLOWLIST",
            Classification.REVERSIBLE: "TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST",
            Classification.DESTRUCTIVE: "TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST",
        }.get(classification, "<no tier>")
        allowed = self.tier_for(classification)

        if not allowed:
            raise AllowlistError(
                f"{tier_name} is empty — nothing was sent. Add the designated "
                "PIT test ICCID explicitly before running this operation."
            )
        if iccid not in allowed:
            raise AllowlistError(
                f"ICCID {mask_tail(iccid)} is not on {tier_name} — nothing was "
                "sent. Being on a lower-risk list does not authorize this "
                "operation."
            )
        if (classification is Classification.DESTRUCTIVE
                and iccid in PROTECTED_ICCIDS):
            # Reaching here means it IS on the destructive list, which is the
            # "separately and explicitly allowlisted" condition. The operator
            # still gets one more deliberate gate at the CLI.
            return
