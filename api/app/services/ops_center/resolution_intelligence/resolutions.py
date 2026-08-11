"""Resolution-workflow access over the catalog (pure, no DB / no LLM)."""

from __future__ import annotations

from typing import Optional

from app.services.ops_center.resolution_intelligence.catalog import (
    KnownIssueSpec,
    ResolutionSpec,
)
from app.services.ops_center.resolution_intelligence.known_issues import get_known_issue


def resolution_for_issue(
    issue_code: str, catalog: Optional[list[KnownIssueSpec]] = None
) -> Optional[ResolutionSpec]:
    spec = get_known_issue(issue_code, catalog)
    return spec.resolution if spec else None


def resolution_to_dict(res: ResolutionSpec) -> dict:
    return {
        "code": res.code,
        "title": res.title,
        "resolution_steps": res.resolution_steps,
        "estimated_time_minutes": res.estimated_time_minutes,
        "escalation_trigger": res.escalation_trigger,
        "success_criteria": res.success_criteria,
    }
