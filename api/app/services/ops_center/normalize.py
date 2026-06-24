"""Identifier normalization + masking helpers for the Operations Center.

Pure functions, no I/O — trivially unit-testable.
"""

from __future__ import annotations

import re

# Identifier types whose values are phone numbers / numeric strings and so
# should be matched on digits only (formatting-insensitive).
PHONE_LIKE_TYPES = {
    "elevator_phone",
    "msisdn",
    "phone_number",
    "did",
}

# Identifier types that are free-text names — matched case-insensitively
# with collapsed whitespace.
NAME_LIKE_TYPES = {
    "site_name",
    "building_name",
    "panel_location",
    "device_label",
    "unit_name",
    "label",
}

# Everything else (iccid, imei, serial_number, starlink_id, napco_radio,
# central_station_account, elevator_number, …) is treated as an opaque
# token: upper-cased, stripped of spaces and common separators.

_NON_DIGITS = re.compile(r"\D+")
_WHITESPACE = re.compile(r"\s+")
_TOKEN_SEPARATORS = re.compile(r"[\s\-_./]+")


def digits_only(value: str) -> str:
    """Return only the digits of *value* (drops +, spaces, dashes, parens)."""
    return _NON_DIGITS.sub("", value or "")


def normalize_phone(value: str) -> str:
    """Normalize a phone-like value to its trailing 10 digits when it looks
    like a NANP number (optionally with a leading country code), else to its
    full digit string.  This lets ``+1 (856) 308-1391`` and ``8563081391``
    and ``18563081391`` all match.
    """
    d = digits_only(value)
    if len(d) == 11 and d.startswith("1"):
        return d[1:]
    return d


def normalize_name(value: str) -> str:
    """Lower-case + collapse internal whitespace for name matching."""
    return _WHITESPACE.sub(" ", (value or "").strip()).lower()


def normalize_token(value: str) -> str:
    """Upper-case + strip separators for opaque identifiers (ICCID, radio #)."""
    return _TOKEN_SEPARATORS.sub("", (value or "").strip()).upper()


def normalize_identifier(identifier_type: str, value: str) -> str:
    """Normalize *value* according to its *identifier_type*."""
    t = (identifier_type or "").strip().lower()
    if t in PHONE_LIKE_TYPES:
        return normalize_phone(value)
    if t in NAME_LIKE_TYPES:
        return normalize_name(value)
    return normalize_token(value)


def mask_phone(value: str | None) -> str:
    """Mask a phone number for display: keep the last 4 digits.

    ``+18563081391`` -> ``•••-•••-1391``.  Empty / very short input is
    returned masked but never raises.
    """
    if not value:
        return ""
    d = digits_only(value)
    if len(d) <= 4:
        return "•" * len(d)
    return f"•••-•••-{d[-4:]}"
