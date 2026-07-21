"""Shadow evaluation of the typed callback rules against live ingest.

The typed rules in ``app.integrations.tmobile_transactions`` decide whether a
callback may change subscriber state: exact correlation to a transaction we
initiated, duplicate and replay refusal, quarantine on anything ambiguous. They
were built and tested in isolation. This module runs them **alongside** the
deployed processor so their decisions can be observed on real traffic before any
of them is allowed to matter.

Why shadow rather than authoritative
------------------------------------
Two things are missing for the typed rules to be correct as the authority:

1. **Nothing creates lifecycle transactions.** There is no persistence for them
   and every lifecycle mutation is blocked, so the correlation set is always
   empty and every callback would resolve to ``quarantined_no_correlation``.
2. **Today's callbacks are not mutation results.** What actually arrives is
   network/provisioning liveness, which the deployed processor promotes to
   ``Device.last_network_event``. Correlating those to an originating
   transaction is a category error — there is no originating transaction.

Making the rules authoritative now would therefore stop liveness promotion on a
path that feeds the health surfaces. So this module observes and records; it
changes nothing. When lifecycle transactions exist and are persisted, the
recorded agreement/disagreement is the evidence for promoting it to authority.

Guarantees
----------
* **Off by default** — gated on ``FEATURE_TMOBILE_CALLBACK_TYPED_SHADOW``.
* **Cannot mutate.** It evaluates against a throwaway state object that is
  discarded; no session, no ORM object, and no live state is ever passed in.
* **Cannot break ingest.** Every failure is swallowed and reported as a
  ``shadow:error`` observation, never raised.
* **Masked.** Identifiers are masked before they reach a log line.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings
from app.integrations.tmobile_contracts import (
    ResponseKind,
    TMobileResponseEnvelope,
)
from app.integrations.tmobile_evidence import mask_tail
from app.integrations.tmobile_state import TMobileSubscriberState
from app.integrations.tmobile_transactions import (
    CallbackDecision,
    LifecycleTransaction,
    apply_callback,
    callback_idempotency_key,
)

logger = logging.getLogger("true911.tmobile_callback_shadow")

#: Deployed statuses that mean the live path DID change state.
_LIVE_APPLIED_PREFIXES = ("promoted",)


def shadow_enabled() -> bool:
    """Flag check, tolerant of env-var whitespace like the sibling flags."""
    return str(
        getattr(settings, "FEATURE_TMOBILE_CALLBACK_TYPED_SHADOW", "false")
    ).strip().lower() == "true"


@dataclass(frozen=True)
class ShadowObservation:
    """What the typed rules would have decided, and whether that agrees.

    ``agrees`` compares only the coarse question both layers can answer: did
    state change or not. A finer comparison would be misleading while the typed
    layer has no transactions to correlate against.
    """

    decision: str
    reason: str
    would_change_state: bool
    live_changed_state: bool
    agrees: bool
    idempotency_key: Optional[str] = None
    correlated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "would_change_state": self.would_change_state,
            "live_changed_state": self.live_changed_state,
            "agrees": self.agrees,
            "correlated": self.correlated,
            "idempotency_key": self.idempotency_key,
        }


def _candidate_transactions() -> list[LifecycleTransaction]:
    """Transactions a callback could correlate against.

    Always empty today: lifecycle transactions have no persistence and no
    mutation runs to create one. Isolated here so that when a transaction store
    lands, this is the single place that changes.
    """
    return []


def build_envelope(
    body: dict[str, Any] | None,
    headers: dict[str, Any] | None,
    *,
    operation: str,
) -> TMobileResponseEnvelope:
    """Build a typed envelope from an archived callback payload."""
    safe_headers = {str(k): str(v) for k, v in (headers or {}).items()}
    return TMobileResponseEnvelope.from_payload(
        body if isinstance(body, dict) else {},
        operation=operation,
        # A callback is by definition the asynchronous side of an exchange.
        kind=ResponseKind.ASYNCHRONOUS,
        headers=safe_headers,
    )


def evaluate(
    *,
    body: dict[str, Any] | None,
    headers: dict[str, Any] | None,
    operation: str,
    payload_id: str,
    live_status: str,
) -> Optional[ShadowObservation]:
    """Run the typed rules for observation only. Never raises, never mutates.

    Returns ``None`` when the shadow is disabled, so the caller can treat
    "not evaluated" and "evaluated to nothing" as distinct.
    """
    if not shadow_enabled():
        return None

    live_changed = live_status.startswith(_LIVE_APPLIED_PREFIXES)

    try:
        envelope = build_envelope(body, headers, operation=operation)
        # A THROWAWAY state object: the typed rules mutate what they are given,
        # so they are given something with no connection to anything real. This
        # is what makes shadow mode structurally incapable of side effects.
        scratch_state = TMobileSubscriberState()
        outcome = apply_callback(envelope, _candidate_transactions(), scratch_state)

        observation = ShadowObservation(
            decision=outcome.decision.value,
            reason=outcome.reason,
            would_change_state=outcome.state_changed,
            live_changed_state=live_changed,
            agrees=(outcome.state_changed == live_changed),
            idempotency_key=callback_idempotency_key(envelope),
            correlated=outcome.decision is not CallbackDecision.QUARANTINED_NO_CORRELATION,
        )
    except Exception as exc:  # noqa: BLE001 — the shadow must never break ingest
        logger.warning(
            "T-Mobile callback %s: shadow evaluation failed (%s: %s) — "
            "ingest is unaffected",
            payload_id, type(exc).__name__, exc,
        )
        return ShadowObservation(
            decision="shadow:error", reason=type(exc).__name__,
            would_change_state=False, live_changed_state=live_changed,
            agrees=False,
        )

    logger.info(
        "T-Mobile callback %s shadow: decision=%s would_change=%s live_changed=%s "
        "agrees=%s correlated=%s iccid=%s",
        payload_id, observation.decision, observation.would_change_state,
        observation.live_changed_state, observation.agrees, observation.correlated,
        mask_tail(envelope.iccid) if observation.decision != "shadow:error" else "<none>",
    )
    return observation
