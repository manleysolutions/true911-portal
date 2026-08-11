"""Known-issue access + deterministic matching.

Pure functions over the static catalog (no DB, no LLM).  Matching is rules-
based and EXPLAINABLE: every match carries the list of reason codes
(dimensions that matched) and a normalized confidence in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.ops_center.resolution_intelligence.catalog import (
    RESOLUTION_CATALOG,
    KnownIssueSpec,
)

# Per-dimension weights for the confidence score.  issue_category dominates;
# severity is only a tie-breaker.  Sum is normalized over the PROVIDED inputs.
_WEIGHTS = {
    "issue_category": 0.40,
    "carrier": 0.25,
    "vendor": 0.20,
    "hardware_model": 0.10,
    "severity": 0.05,
}
# A match must include at least one of these "strong" dimensions to count —
# a severity-only coincidence is not a real match.
_STRONG = {"issue_category", "carrier", "vendor", "hardware_model"}


@dataclass(frozen=True)
class IssueMatch:
    issue: KnownIssueSpec
    score: float
    reasons: list[str]


def all_known_issues(catalog: Optional[list[KnownIssueSpec]] = None) -> list[KnownIssueSpec]:
    return list(catalog if catalog is not None else RESOLUTION_CATALOG)


def get_known_issue(code: str, catalog: Optional[list[KnownIssueSpec]] = None) -> Optional[KnownIssueSpec]:
    for spec in all_known_issues(catalog):
        if spec.code == code:
            return spec
    return None


def _eqish(a: Optional[str], b: Optional[str]) -> bool:
    """Case-insensitive equality with light substring tolerance (so 'LM150'
    matches 'LM150' and 'StarLink' matches 'NAPCO StarLink')."""
    if not a or not b:
        return False
    aa, bb = a.strip().lower(), b.strip().lower()
    return aa == bb or aa in bb or bb in aa


def _category_match(issue_category: Optional[str], spec: KnownIssueSpec) -> bool:
    if not issue_category:
        return False
    ic = issue_category.strip().lower()
    if ic == (spec.category or "").lower():
        return True
    return ic in {c.lower() for c in spec.ops_issue_categories}


def find_matching_issues(
    *,
    issue_category: Optional[str] = None,
    carrier: Optional[str] = None,
    vendor: Optional[str] = None,
    hardware_model: Optional[str] = None,
    severity: Optional[str] = None,
    catalog: Optional[list[KnownIssueSpec]] = None,
    limit: int = 5,
) -> list[IssueMatch]:
    """Return scored, explainable matches sorted by score (desc), then by the
    catalog's stable order for determinism."""
    provided = {
        "issue_category": issue_category,
        "carrier": carrier,
        "vendor": vendor,
        "hardware_model": hardware_model,
        "severity": severity,
    }
    provided = {k: v for k, v in provided.items() if v}
    provided_weight = sum(_WEIGHTS[k] for k in provided) or 1.0

    matches: list[IssueMatch] = []
    # Catalog specs carry no `active` flag — that column lives on the persisted
    # OpsKnownIssue row, and this engine reads the static catalog, not the DB.
    for spec in all_known_issues(catalog):
        reasons: list[str] = []
        if "issue_category" in provided and _category_match(issue_category, spec):
            reasons.append("issue_category")
        if "carrier" in provided and _eqish(carrier, spec.carrier):
            reasons.append("carrier")
        if "vendor" in provided and _eqish(vendor, spec.vendor):
            reasons.append("vendor")
        if "hardware_model" in provided and _eqish(hardware_model, spec.hardware_model):
            reasons.append("hardware_model")
        if "severity" in provided and severity and severity.lower() == (spec.severity or "").lower():
            reasons.append("severity")

        if not (_STRONG & set(reasons)):
            continue  # severity-only / no match → not a real hit

        matched_weight = sum(_WEIGHTS[r] for r in reasons)
        score = round(matched_weight / provided_weight, 4)
        matches.append(IssueMatch(issue=spec, score=score, reasons=reasons))

    # Stable sort: score desc; ties keep catalog order (Python sort is stable).
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:limit]
