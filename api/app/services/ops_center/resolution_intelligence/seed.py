"""Idempotent DB seeder for the Resolution-Intelligence catalog.

Loads the static catalog (``catalog.RESOLUTION_CATALOG``) into the
``ops_known_issues`` / ``ops_diagnostic_workflows`` / ``ops_resolution_workflows``
tables.  Idempotent by ``code`` (insert-if-absent), so it is safe to re-run.

This is NOT wired into any startup/deploy command — it is a manual/CLI action
an operator runs once the feature is being prepared.  It writes only to the new
Phase-1.6 tables and never touches existing tables.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops_center_resolution import (
    OpsDiagnosticWorkflow,
    OpsKnownIssue,
    OpsResolutionWorkflow,
)
from app.services.ops_center.resolution_intelligence.catalog import (
    RESOLUTION_CATALOG,
    KnownIssueSpec,
)


async def _existing_codes(db: AsyncSession, model) -> set[str]:
    rows = (await db.execute(select(model.code))).scalars().all()
    return set(rows)


async def seed_resolution_intelligence(
    db: AsyncSession, *, catalog: Optional[list[KnownIssueSpec]] = None, commit: bool = True
) -> dict:
    """Insert any catalog entries not already present (by ``code``).

    Returns counts of rows inserted per table.  Caller may pass ``commit=False``
    to manage the transaction externally (e.g. in tests).
    """
    specs = list(catalog if catalog is not None else RESOLUTION_CATALOG)

    have_issues = await _existing_codes(db, OpsKnownIssue)
    have_diag = await _existing_codes(db, OpsDiagnosticWorkflow)
    have_res = await _existing_codes(db, OpsResolutionWorkflow)

    inserted = {"known_issues": 0, "diagnostic_workflows": 0, "resolution_workflows": 0}

    for spec in specs:
        if spec.code not in have_issues:
            db.add(
                OpsKnownIssue(
                    code=spec.code,
                    title=spec.title,
                    category=spec.category,
                    severity=spec.severity,
                    description=spec.description,
                    symptoms=list(spec.symptoms),
                    probable_causes=list(spec.probable_causes),
                    vendor=spec.vendor,
                    carrier=spec.carrier,
                    hardware_model=spec.hardware_model,
                    escalation_queue=spec.escalation_queue,
                    active=True,
                )
            )
            inserted["known_issues"] += 1

        diag = spec.diagnostic
        if diag and diag.code not in have_diag:
            db.add(
                OpsDiagnosticWorkflow(
                    code=diag.code,
                    title=diag.title,
                    issue_code=spec.code,
                    category=spec.category,
                    ordered_steps=list(diag.ordered_steps),
                    expected_results=list(diag.expected_results),
                    failure_paths=list(diag.failure_paths),
                    escalation_queue=diag.escalation_queue,
                    active=True,
                )
            )
            inserted["diagnostic_workflows"] += 1

        res = spec.resolution
        if res and res.code not in have_res:
            db.add(
                OpsResolutionWorkflow(
                    code=res.code,
                    title=res.title,
                    issue_code=spec.code,
                    resolution_steps=list(res.resolution_steps),
                    estimated_time_minutes=res.estimated_time_minutes,
                    escalation_trigger=res.escalation_trigger,
                    success_criteria=list(res.success_criteria),
                    active=True,
                )
            )
            inserted["resolution_workflows"] += 1

    if commit:
        await db.commit()
    return inserted
