"""Diagnostic-workflow access over the catalog (pure, no DB / no LLM)."""

from __future__ import annotations

from typing import Optional

from app.services.ops_center.resolution_intelligence.catalog import (
    DiagnosticSpec,
    KnownIssueSpec,
)
from app.services.ops_center.resolution_intelligence.known_issues import get_known_issue


def diagnostic_for_issue(
    issue_code: str, catalog: Optional[list[KnownIssueSpec]] = None
) -> Optional[DiagnosticSpec]:
    spec = get_known_issue(issue_code, catalog)
    return spec.diagnostic if spec else None


def diagnostic_to_dict(diag: DiagnosticSpec) -> dict:
    return {
        "code": diag.code,
        "title": diag.title,
        "ordered_steps": diag.ordered_steps,
        "expected_results": diag.expected_results,
        "failure_paths": diag.failure_paths,
        "escalation_queue": diag.escalation_queue,
    }
