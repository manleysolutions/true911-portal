"""
Lightweight async email service for transactional emails (password resets, invites).

Requires SMTP env vars to be configured. When SMTP_HOST is empty (default),
emails are logged instead of sent — safe for dev/demo environments.

Required env vars for production:
    SMTP_HOST=smtp.example.com
    SMTP_PORT=587
    SMTP_USER=apikey            (or your SMTP username)
    SMTP_PASSWORD=your-key
    SMTP_FROM_EMAIL=noreply@true911.com
    SMTP_FROM_NAME=True911+

Works with any SMTP provider: SendGrid, AWS SES, Mailgun, Postmark, etc.
For SendGrid: SMTP_HOST=smtp.sendgrid.net, SMTP_USER=apikey, SMTP_PASSWORD=SG.xxx
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("true911.email")


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    *,
    settings=None,
) -> bool:
    """Send an email via SMTP. Returns True on success, False on failure.

    When SMTP is not configured, logs the email content and returns True
    (no-op for dev/demo environments).
    """
    if settings is None:
        from ..config import settings as _settings
        settings = _settings

    smtp_host = settings.SMTP_HOST.strip()
    if not smtp_host:
        logger.info(
            "SMTP not configured — email would be sent to=%s subject=%s",
            to, subject,
        )
        logger.debug("Email body:\n%s", html_body)
        return True

    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=True,
        )
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except ImportError:
        logger.warning(
            "aiosmtplib not installed — cannot send email. "
            "Install with: pip install aiosmtplib"
        )
        return False
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def build_reset_email(reset_url: str, user_name: str | None = None) -> tuple[str, str]:
    """Return (subject, html_body) for a password reset email."""
    name = user_name or "there"
    subject = "True911+ — Password Reset Request"
    html = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Inter',system-ui,sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);">
    <div style="background:#0f172a;padding:24px 32px;text-align:center;">
      <span style="font-size:22px;font-weight:700;color:#fff;letter-spacing:-.02em;">
        True911<span style="color:#dc2626;">+</span>
      </span>
    </div>
    <div style="padding:32px;">
      <h2 style="margin:0 0 8px;font-size:18px;color:#0f172a;">Reset Your Password</h2>
      <p style="margin:0 0 20px;font-size:14px;color:#64748b;line-height:1.6;">
        Hi {name}, we received a request to reset your password. Click the button below
        to set a new one. This link expires in 30 minutes.
      </p>
      <a href="{reset_url}"
         style="display:inline-block;padding:12px 28px;background:#dc2626;color:#fff;font-size:14px;font-weight:600;text-decoration:none;border-radius:8px;">
        Set New Password
      </a>
      <p style="margin:20px 0 0;font-size:12px;color:#94a3b8;line-height:1.5;">
        If you didn't request this, you can safely ignore this email.
        <br>Link: <a href="{reset_url}" style="color:#94a3b8;word-break:break-all;">{reset_url}</a>
      </p>
    </div>
    <div style="background:#f8fafc;padding:16px 32px;text-align:center;border-top:1px solid #e2e8f0;">
      <span style="font-size:11px;color:#94a3b8;">&copy; 2026 Manley Solutions LLC &middot; Made in USA &middot; NDAA-TAA Compliant</span>
    </div>
  </div>
</body>
</html>"""
    return subject, html
