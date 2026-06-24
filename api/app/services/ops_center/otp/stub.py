"""Stub + console OTP providers (no real delivery).

``StubOtpProvider`` is the safe default for dev/CI/production-until-wired:
it reports a successful "send" without contacting any network service and
WITHOUT logging the code.  ``ConsoleOtpProvider`` additionally logs the
code at INFO for local manual testing — it must never be enabled in an
internet-exposed environment.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.services.ops_center.normalize import mask_phone
from app.services.ops_center.otp.base import OtpProvider, OtpSendResult

logger = logging.getLogger("true911.ops_center.otp")


class StubOtpProvider(OtpProvider):
    """Records a simulated send; never transmits, never logs the code."""

    name = "stub"

    async def send(
        self,
        *,
        destination: str,
        code: str,  # noqa: ARG002 — intentionally unused / never logged
        session_ref: str,
        context: Optional[dict] = None,
    ) -> OtpSendResult:
        logger.info(
            "ops_center OTP (stub, NOT sent) session=%s dest=%s",
            session_ref,
            mask_phone(destination),
        )
        return OtpSendResult(
            ok=True,
            provider=self.name,
            message_id=f"stub-{session_ref}",
            simulated=True,
        )


class ConsoleOtpProvider(OtpProvider):
    """Dev-only: logs the OTP code so a developer can complete the flow."""

    name = "console"

    async def send(
        self,
        *,
        destination: str,
        code: str,
        session_ref: str,
        context: Optional[dict] = None,
    ) -> OtpSendResult:
        logger.warning(
            "ops_center OTP (console DEV ONLY) session=%s dest=%s code=%s",
            session_ref,
            mask_phone(destination),
            code,
        )
        return OtpSendResult(
            ok=True,
            provider=self.name,
            message_id=f"console-{session_ref}",
            simulated=True,
        )
