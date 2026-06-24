"""OTP provider interface + result type."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class OtpSendResult:
    """Outcome of an attempt to deliver an OTP code."""

    ok: bool
    provider: str
    # Provider-side message id when available (Twilio SID, Telnyx id, …).
    message_id: Optional[str] = None
    # Human-readable error when ``ok`` is False.  Never contains the code.
    error: Optional[str] = None
    # True when no real message was sent (stub/console) — surfaced so the
    # router can flag a non-production delivery in the audit trail.
    simulated: bool = False


class OtpProvider(abc.ABC):
    """A one-time-passcode delivery channel.

    Implementations MUST NOT log or persist the plaintext ``code`` except a
    console/dev provider that is explicitly opt-in.  The caller is
    responsible for generating, hashing, and expiring the code; the
    provider only delivers it.
    """

    name: str = "base"

    @abc.abstractmethod
    async def send(
        self,
        *,
        destination: str,
        code: str,
        session_ref: str,
        context: Optional[dict] = None,
    ) -> OtpSendResult:
        """Deliver *code* to *destination* (E.164 phone).  Async."""
        raise NotImplementedError
