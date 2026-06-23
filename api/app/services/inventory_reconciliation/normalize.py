"""Normalization + similarity helpers for matching (customer-agnostic).

No customer- or vendor-specific tokens are hardcoded — these are generic string
operations so the same logic serves RH, R&R, Benson, Integrity, USPS, etc.
"""

from __future__ import annotations

import re
from typing import Optional


def norm_iccid(v) -> Optional[str]:
    """Digits-only ICCID; None if empty/non-numeric."""
    if not v:
        return None
    digits = re.sub(r"\D", "", str(v))
    return digits or None


def norm_radio(v) -> Optional[str]:
    """Whitespace-stripped radio id, leading zeros removed for stable compare."""
    if not v:
        return None
    s = re.sub(r"\s+", "", str(v))
    if not s:
        return None
    return s.lstrip("0") or s


def norm_name(v) -> Optional[str]:
    """Lowercase, alphanumeric-only, single-spaced. Generic — no stopword list."""
    if not v:
        return None
    s = re.sub(r"[^a-z0-9 ]", " ", str(v).lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def tokens(v) -> set:
    n = norm_name(v)
    return set(n.split()) if n else set()


def site_similarity(a, b) -> float:
    """Jaccard token overlap in [0, 1] — used as the weakest (REVIEW) signal."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0
