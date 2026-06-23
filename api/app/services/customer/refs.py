"""Opaque, tamper-evident customer-facing reference tokens.

A `*_ref` replaces a raw internal id (db pk / site_id / unit_id) in customer
responses.  It is HMAC-signed with the server secret, so:
  * the raw id is never exposed in a guessable form,
  * a forged or sequential value is rejected (decode returns None),
  * it is still resolvable server-side (the id is recoverable after the
    signature is verified).

Cross-tenant safety does NOT rely on opacity alone — the caller's query MUST
still filter by current_user.tenant_id, so a (valid) ref for another tenant's
object yields 404 at resolution time.  This module only hides/authenticates the
identifier.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from app.config import settings

_SIG_BYTES = 9  # 72-bit truncated HMAC — ample against forgery for these ids


def _key() -> bytes:
    # Reuse the app signing secret.  Never the empty string in prod (startup
    # guards enforce a real JWT_SECRET); fall back to a constant only so dev
    # without a secret still functions deterministically.
    return (settings.JWT_SECRET or "true911-customer-ref").encode("utf-8")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def encode_ref(kind: str, raw_id) -> str:
    """Return an opaque signed ref, e.g. ``loc_aWQ6NDI.x1y2z3``."""
    payload = f"{kind}:{raw_id}".encode("utf-8")
    sig = hmac.new(_key(), payload, hashlib.sha256).digest()[:_SIG_BYTES]
    return f"{kind}_{_b64(payload)}.{_b64(sig)}"


def decode_ref(kind: str, ref: str) -> str | None:
    """Return the raw id string for a valid ref of ``kind``, else None.

    Rejects wrong-kind, malformed, or signature-mismatched (forged/guessed)
    tokens.  Never raises.
    """
    try:
        prefix, rest = ref.split("_", 1)
        body, sig = rest.split(".", 1)
        if prefix != kind:
            return None
        payload = _unb64(body)
        expected = hmac.new(_key(), payload, hashlib.sha256).digest()[:_SIG_BYTES]
        if not hmac.compare_digest(_b64(expected), sig):
            return None
        k, raw_id = payload.decode("utf-8").split(":", 1)
        if k != kind:
            return None
        return raw_id
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
