"""Pluggable SMS OTP provider abstraction (Operations Center Phase 3).

The verification workflow depends only on the :class:`OtpProvider`
interface, never on a concrete provider.  A real Twilio / Telnyx provider
can be dropped in later by implementing ``send()`` and registering it in
``factory.get_otp_provider``; no workflow/router change is required.

Default provider is the no-send ``StubOtpProvider`` so dev and CI never
emit a real message and never need credentials.
"""

from app.services.ops_center.otp.base import OtpProvider, OtpSendResult
from app.services.ops_center.otp.factory import get_otp_provider, provider_sends_real_sms

__all__ = ["OtpProvider", "OtpSendResult", "get_otp_provider", "provider_sends_real_sms"]
