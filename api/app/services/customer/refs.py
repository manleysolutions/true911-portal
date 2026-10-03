"""Opaque, authenticated, versioned customer-facing reference tokens (CG-1).

A ``*_ref`` replaces a raw internal id (db pk / site_id / unit_id / a connection
key that may contain a telephone number) in customer responses.  Version 2 is
deterministic AUTHENTICATED ENCRYPTION (AES-SIV) - not a signed plaintext - so:

  * nothing inside the token is recoverable by inspecting it in a browser (no
    db id, no telephone number, no canonical key);
  * a forged, edited, truncated, wrong-kind or wrong-version token is rejected
    (decode returns None - fail closed, never raises);
  * it is still resolvable server-side, and the same id always yields the same
    ref (stable URLs / React keys).

Token shape: ``<kind>_2<k><base64url ciphertext>`` - ``2`` is the format
version, ``<k>`` names the key that made it (``k`` = the dedicated
``CUSTOMER_REF_SECRET``, ``t`` = transitional).  The kind and version are
authenticated as associated data, so a ``loc`` ref can never be replayed as a
``svc`` ref.

KEYS.  ``CUSTOMER_REF_SECRET`` (>= 32 chars, e.g. ``python -c "import secrets;
print(secrets.token_urlsafe(48))"``) is the durable key.  Until it is set, refs
use a TRANSITIONAL key derived from the app secret so the existing customer API
keeps working; the canonical customer read model refuses to run on it
(``dedicated_secret_configured()``).  Refs are never persisted, so setting or
ROTATING the secret only invalidates refs a browser already holds (old links /
bookmarks 404 and the UI reloads fresh refs) - no data migration.

Cross-tenant safety does NOT rely on opacity - every resolver still filters by
the caller's tenant_id, so a valid ref of another tenant's object yields 404.
"""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

REF_VERSION = "2"
MIN_SECRET_LEN = 32
_DEDICATED, _TRANSITIONAL = "k", "t"
_cache: dict = {}


def dedicated_secret_configured() -> bool:
    """True when the durable CUSTOMER_REF_SECRET is set (canonical customer
    mode requires it and fails closed without it)."""
    return len((settings.CUSTOMER_REF_SECRET or "").strip()) >= MIN_SECRET_LEN


def _material() -> tuple[bytes, str]:
    if dedicated_secret_configured():
        return settings.CUSTOMER_REF_SECRET.strip().encode("utf-8"), _DEDICATED
    return (settings.JWT_SECRET or "true911-customer-ref").encode("utf-8"), _TRANSITIONAL


def _aead(material: bytes, key_id: str) -> AESSIV:
    hit = _cache.get((material, key_id))
    if hit is None:
        key = HKDF(algorithm=hashes.SHA256(), length=64, salt=b"true911-customer-ref",
                   info=("customer-ref:v%s:%s" % (REF_VERSION, key_id)).encode()).derive(material)
        hit = _cache[(material, key_id)] = AESSIV(key)
    return hit


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _ad(kind: str) -> list[bytes]:
    return [kind.encode("utf-8"), REF_VERSION.encode("ascii")]


def encode_ref(kind: str, raw_id) -> str:
    """Opaque ref for ``raw_id`` of ``kind``, e.g. ``loc_2k3q0W…``."""
    material, key_id = _material()
    ct = _aead(material, key_id).encrypt(str(raw_id).encode("utf-8"), _ad(kind))
    return "%s_%s%s%s" % (kind, REF_VERSION, key_id, _b64(ct))


def decode_ref(kind: str, ref: str) -> str | None:
    """The raw id string of a valid ``kind`` ref made with the current key, else
    None (wrong kind / version / key, malformed or tampered).  Never raises."""
    try:
        prefix, rest = str(ref).split("_", 1)
        material, key_id = _material()
        if prefix != kind or len(rest) < 3 or rest[0] != REF_VERSION or rest[1] != key_id:
            return None
        return _aead(material, key_id).decrypt(_unb64(rest[2:]), _ad(kind)).decode("utf-8")
    except (ValueError, TypeError, UnicodeDecodeError, InvalidTag):
        return None
