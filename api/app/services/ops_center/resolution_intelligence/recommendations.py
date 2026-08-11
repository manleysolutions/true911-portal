"""Deterministic, rules-based recommendation engine.

Input:  issue category, carrier, vendor, hardware model, severity.
Output: matching known issues + diagnostic workflow + resolution workflow +
        escalation queue + an EXPLAINABLE confidence score.

NO LLM.  Pure rules over the static catalog (``CONSTITUTION.md`` §4.4
deterministic-before-AI; §5 explainable).  The ``confidence`` is an INTERNAL
(tech/NOC) signal — it is NOT a customer-facing readiness score (§7.1) and no
customer surface reads it.
"""

from __future__ import annotations

from typing import Optional

from app.services.ops_center.resolution_intelligence.catalog import KnownIssueSpec
from app.services.ops_center.resolution_intelligence.known_issues import find_matching_issues


def recommend(
    *,
    issue_category: Optional[str] = None,
    carrier: Optional[str] = None,
    vendor: Optional[str] = None,
    hardware_model: Optional[str] = None,
    severity: Optional[str] = None,
    catalog: Optional[list[KnownIssueSpec]] = None,
    limit: int = 5,
) -> dict:
    """Return a structured recommendation.

    Shape (extra ``matched_issues`` / ``note`` are additive explainability):
        {
          "probable_causes": [...],
          "recommended_diagnostics": [...steps...],
          "recommended_resolutions": [...steps...],
          "recommended_escalation_queue": "NOC" | None,
          "confidence": 0.0,
          "matched_issues": [{"code","title","score","reasons"}],
          "note": "..."
        }
    """
    matches = find_matching_issues(
        issue_category=issue_category,
        carrier=carrier,
        vendor=vendor,
        hardware_model=hardware_model,
        severity=severity,
        catalog=catalog,
        limit=limit,
    )

    matched_issues = [
        {"code": m.issue.code, "title": m.issue.title, "score": m.score, "reasons": m.reasons}
        for m in matches
    ]

    if not matches:
        return {
            "probable_causes": [],
            "recommended_diagnostics": [],
            "recommended_resolutions": [],
            "recommended_escalation_queue": None,
            "confidence": 0.0,
            "matched_issues": [],
            "note": "No matching known issue — gather more detail and route to a human queue.",
        }

    best = matches[0].issue
    escalation_queue = best.escalation_queue or (best.diagnostic.escalation_queue if best.diagnostic else None)

    return {
        "probable_causes": list(best.probable_causes),
        "recommended_diagnostics": list(best.diagnostic.ordered_steps) if best.diagnostic else [],
        "recommended_resolutions": list(best.resolution.resolution_steps) if best.resolution else [],
        "recommended_escalation_queue": escalation_queue,
        "confidence": matches[0].score,
        "matched_issues": matched_issues,
        "note": (
            f"Best match '{best.code}' on {', '.join(matches[0].reasons)}. "
            "Deterministic, internal-only; not a customer-facing status."
        ),
    }
