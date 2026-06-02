"""Redact secrets from inbound Zoho payloads before persisting them — pure, no I/O.

The full (unsanitized) webhook body already lives on
``integration_events.payload_json``.  This module produces a SECRET-FREE copy for
the ``zoho_payload_observations`` / ``zoho_subscription_records.raw_json`` staging
columns, which are read by the admin review surface.  Business field NAMES and
shapes are preserved so the real Zoho contract can be learned from production;
only values under sensitive key names are replaced with ``"<redacted>"``.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "<redacted>"

# Substring patterns: any key whose normalized name CONTAINS one of these has its
# value redacted.  Chosen to catch credentials without nuking business fields.
_SENSITIVE_SUBSTRINGS = (
    "secret",
    "password",
    "passwd",
    "token",
    "authorization",
    "apikey",      # matches api_key / apiKey after normalization
    "signature",
    "credential",
)
# Exact normalized names that are sensitive on their own (kept narrow so values
# like "Subscription_Mgmt_Key" are NOT redacted — only a bare "key"/"auth").
_SENSITIVE_EXACT = {"key", "auth", "pwd", "sig"}

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize_key(key: str) -> str:
    return _NON_ALNUM.sub("", str(key).lower())


def _is_sensitive_key(key: str) -> bool:
    norm = _normalize_key(key)
    if norm in _SENSITIVE_EXACT:
        return True
    return any(sub in norm for sub in _SENSITIVE_SUBSTRINGS)


def sanitize(value: Any, _depth: int = 0) -> Any:
    """Recursively copy ``value``, redacting values under sensitive key names.

    Dicts and lists are walked (bounded depth as a guard against pathological
    nesting).  Scalars pass through unchanged.  The structure — including all
    business key names — is preserved.
    """
    if _depth > 12:
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _is_sensitive_key(k):
                out[k] = REDACTED
            else:
                out[k] = sanitize(v, _depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize(item, _depth + 1) for item in value]
    return value


def top_level_keys(payload: Any) -> list[str]:
    """Return the sorted top-level key names of a dict payload (else empty list)."""
    if isinstance(payload, dict):
        return sorted(str(k) for k in payload.keys())
    return []
