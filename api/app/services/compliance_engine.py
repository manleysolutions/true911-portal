"""Elevator communications compliance evaluation engine.

IMPORTANT DISCLAIMER:
This module provides operational guidance states for tracking compliance
readiness. It does NOT constitute legal advice or a legal determination
of code compliance. Actual compliance depends on the Authority Having
Jurisdiction (AHJ), the specific code edition adopted, local amendments,
and the interpretation of the AHJ inspector.

True911 provides compliance tracking tools — not legal compliance certification.

The engine evaluates service units against known code requirements and
produces one of:
    compliant           — all known requirements appear met
    partially_compliant — some requirements met, others missing
    review_required     — insufficient data to make a determination
    non_compliant       — known requirements are clearly not met
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("true911.compliance")


@dataclass
class ComplianceCheck:
    """Result of a single compliance check."""
    rule: str
    passed: bool
    severity: str = "warning"  # info | warning | critical
    message: str = ""


@dataclass
class ComplianceResult:
    """Aggregated compliance evaluation for a service unit."""
    status: str  # compliant | partially_compliant | review_required | non_compliant
    checks: list[ComplianceCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)


def evaluate_service_unit(unit) -> ComplianceResult:
    """Evaluate a service unit's compliance based on its capabilities and configuration.

    This is operational guidance, not a legal determination.
    """
    checks: list[ComplianceCheck] = []
    warnings: list[str] = []

    # ── Voice is always baseline ────────────────────────────────
    checks.append(ComplianceCheck(
        rule="voice_communication",
        passed=unit.voice_supported,
        severity="critical",
        message="Voice communication is required for all elevator emergency phones" if not unit.voice_supported else "Voice communication supported",
    ))

    # ── Backup power ────────────────────────────────────────────
    if unit.unit_type == "elevator_phone":
        checks.append(ComplianceCheck(
            rule="backup_power",
            passed=unit.backup_power_supported,
            severity="warning",
            message="Backup power not confirmed" if not unit.backup_power_supported else "Backup power supported",
        ))

    # ── Monitoring station ──────────────────────────────────────
    if unit.unit_type in ("elevator_phone", "fire_alarm"):
        has_monitoring = bool(unit.monitoring_station_type)
        checks.append(ComplianceCheck(
            rule="monitoring_station",
            passed=has_monitoring,
            severity="warning",
            message="No monitoring station type configured" if not has_monitoring else f"Monitoring: {unit.monitoring_station_type}",
        ))

    # ── Video/text — jurisdiction-dependent ─────────────────────
    # Video and text are NOT universally required. Requirements depend on:
    #   - jurisdiction (state/city code adoption)
    #   - code edition (ASME A17.1-2019+ for video in some jurisdictions)
    #   - install type (new installs vs existing)
    # We flag missing video/text as "review needed" when no jurisdiction is set.
    if unit.unit_type == "elevator_phone":
        if not unit.jurisdiction_code:
            warnings.append("Jurisdiction/code review needed — cannot determine video/text requirements")
        elif not unit.governing_code_edition:
            warnings.append("Governing code edition not set — video/text requirements may apply")
        else:
            # If jurisdiction IS set, check if video/text gaps exist
            if not unit.video_supported and not unit.text_supported:
                warnings.append(
                    "Video and text messaging not enabled — may be required depending on "
                    f"jurisdiction ({unit.jurisdiction_code}) and code edition ({unit.governing_code_edition})"
                )

    # ── E911 linkage ────────────────────────────────────────────
    # Service units should be traceable to an E911 address via their site.
    # We don't check it here (site-level concern) but we flag if the unit
    # has no line or device to connect it to the emergency system.
    if not unit.line_id and not unit.device_id:
        warnings.append("No device or line linked — emergency routing cannot be verified")

    # ── Compliance review freshness ─────────────────────────────
    if not unit.compliance_last_reviewed_at:
        warnings.append("Compliance has never been reviewed")

    # ── Camera vs video_supported mismatch ──────────────────────
    if unit.camera_present and not unit.video_supported:
        warnings.append("Camera installed but video capability not enabled in configuration")
    if unit.video_supported and not unit.camera_present:
        warnings.append("Video capability marked as supported but no camera present")

    # ── Determine overall status ────────────────────────────────
    critical_failures = [c for c in checks if not c.passed and c.severity == "critical"]
    warning_failures = [c for c in checks if not c.passed and c.severity == "warning"]

    if critical_failures:
        status = "non_compliant"
    elif warning_failures or len(warnings) > 2:
        status = "partially_compliant"
    elif warnings:
        status = "review_required"
    elif all(c.passed for c in checks):
        status = "compliant"
    else:
        status = "review_required"

    return ComplianceResult(status=status, checks=checks, warnings=warnings)


def evaluate_site_compliance(units: list) -> dict:
    """Evaluate compliance across all service units at a site.

    Returns an aggregate summary suitable for dashboard display.
    """
    if not units:
        return {
            "status": "no_units",
            "summary": "No service units configured at this site",
            "unit_count": 0,
            "compliant": 0,
            "partially_compliant": 0,
            "review_required": 0,
            "non_compliant": 0,
            "warnings": [],
        }

    results = [evaluate_service_unit(u) for u in units]

    counts = {
        "compliant": sum(1 for r in results if r.status == "compliant"),
        "partially_compliant": sum(1 for r in results if r.status == "partially_compliant"),
        "review_required": sum(1 for r in results if r.status == "review_required"),
        "non_compliant": sum(1 for r in results if r.status == "non_compliant"),
    }

    all_warnings = []
    for r in results:
        all_warnings.extend(r.warnings)

    # Overall site status is the worst of any unit
    if counts["non_compliant"] > 0:
        overall = "non_compliant"
    elif counts["partially_compliant"] > 0:
        overall = "partially_compliant"
    elif counts["review_required"] > 0:
        overall = "review_required"
    else:
        overall = "compliant"

    return {
        "status": overall,
        "summary": f"{len(units)} service unit(s) evaluated",
        "unit_count": len(units),
        **counts,
        "warnings": all_warnings[:10],  # cap at 10 for UI
    }
