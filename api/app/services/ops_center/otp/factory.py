"""OTP provider factory — selects an implementation from settings.

``OPS_CENTER_OTP_PROVIDER`` chooses the provider:

  * ``stub``    (default) — no delivery, safe everywhere.
  * ``console``           — logs the code (dev only).
  * ``twilio`` / ``telnyx`` — reserved for Phase 3+; not yet implemented,
    so they fall back to the stub with a warning rather than failing the
    workflow (the verification path still works end-to-end in tests).
"""

from __future__ import annotations

import logging

from app.services.ops_center.otp.base import OtpProvider
from app.services.ops_center.otp.stub import ConsoleOtpProvider, StubOtpProvider

logger = logging.getLogger("true911.ops_center.otp")

# Providers reserved for a future phase; selecting one today degrades to the
# stub so nothing breaks before the real integration lands.
_FUTURE_PROVIDERS = {"twilio", "telnyx"}


def get_otp_provider(settings=None) -> OtpProvider:
    """Return the configured :class:`OtpProvider` instance."""
    if settings is None:
        from app.config import settings as _settings

        settings = _settings

    choice = (settings.OPS_CENTER_OTP_PROVIDER or "stub").strip().lower()

    if choice == "console":
        return ConsoleOtpProvider()
    if choice in _FUTURE_PROVIDERS:
        logger.warning(
            "OPS_CENTER_OTP_PROVIDER=%s is not yet implemented; "
            "falling back to the stub provider (no real SMS sent).",
            choice,
        )
        return StubOtpProvider()
    return StubOtpProvider()
