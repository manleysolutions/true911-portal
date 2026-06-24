"""OTP provider factory — selects an implementation from settings.

``OPS_CENTER_OTP_PROVIDER`` chooses the provider:

  * ``stub``    (default) — no delivery, safe everywhere.
  * ``console``           — logs the code (DEV ONLY).  Refused in production
    app mode (``APP_MODE=production``) and downgraded to ``stub`` (fail
    closed) so a misconfigured production env can never log OTP codes.
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

# Providers that perform real outbound SMS once implemented.  Used by the
# router to gate the destination-override capability until rate-limiting
# exists (stub/console are simulated and never deliver).
SENDING_PROVIDERS = {"twilio", "telnyx"}


def provider_sends_real_sms(settings=None) -> bool:
    """Whether the configured provider would deliver a real SMS.

    False for ``stub`` / ``console`` (simulated, no delivery).  Today even
    the ``twilio`` / ``telnyx`` selections fall back to the stub, but this
    reports the *intent* so abuse-sensitive capabilities (destination
    override) can be gated the moment a real provider is wired.
    """
    if settings is None:
        from app.config import settings as _settings

        settings = _settings
    return (settings.OPS_CENTER_OTP_PROVIDER or "stub").strip().lower() in SENDING_PROVIDERS


def get_otp_provider(settings=None) -> OtpProvider:
    """Return the configured :class:`OtpProvider` instance."""
    if settings is None:
        from app.config import settings as _settings

        settings = _settings

    choice = (settings.OPS_CENTER_OTP_PROVIDER or "stub").strip().lower()
    # Fail closed: default to production if APP_MODE is absent (e.g. a bare
    # settings stub) so the dev-only console provider is never used by accident.
    app_mode = (getattr(settings, "APP_MODE", "production") or "production").strip().lower()

    if choice == "console":
        if app_mode == "production":
            logger.error(
                "OPS_CENTER_OTP_PROVIDER=console is DEV-ONLY and refused in "
                "production app mode; falling back to the stub provider "
                "(no code logged, no SMS sent)."
            )
            return StubOtpProvider()
        return ConsoleOtpProvider()
    if choice in _FUTURE_PROVIDERS:
        logger.warning(
            "OPS_CENTER_OTP_PROVIDER=%s is not yet implemented; "
            "falling back to the stub provider (no real SMS sent).",
            choice,
        )
        return StubOtpProvider()
    return StubOtpProvider()
