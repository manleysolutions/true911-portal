"""Escalation service — deduplication, Zoho Desk ticket creation, local persistence.

Flow:
  1. Gather session context (diagnostics, transcript, AI summary)
  2. Compute dedupe key from tenant/site/device/category
  3. Check for existing recent escalation matching dedupe key
  4. If match → link to existing, skip Zoho ticket creation
  5. If new → create Zoho Desk ticket (or store pending if API fails)
  6. Always persist escalation record locally

Subscribers see only calm confirmation regardless of Zoho outcome.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.support import (
    SupportEscalation, SupportSession, SupportMessage,
    SupportDiagnostic, SupportAISummary,
)
from . import zoho_desk_service

logger = logging.getLogger("true911.support.escalation")

# Dedupe windows by escalation level
DEDUPE_WINDOWS = {
    "urgent": timedelta(minutes=30),
    "recommend": timedelta(hours=4),
    "offer": timedelta(hours=4),
    "none": timedelta(hours=24),
}


async def create_escalation(
    db: AsyncSession,
    session_id: UUID,
    tenant_id: str,
    user_id: UUID,
    reason: str,
    probable_cause: str | None = None,
    additional_notes: str | None = None,
) -> SupportEscalation:
    """Create an escalation with deduplication and Zoho Desk integration."""

    # 1. Gather context
    session = await _get_session(db, session_id)
    diagnostics = await _get_diagnostics(db, session_id)
    messages = await _get_messages(db, session_id)
    ai_summary = await _get_ai_summary(db, session_id)

    site_id = session.site_id if session else None
    device_id = session.device_id if session else None
    issue_category = ai_summary.issue_category if ai_summary else (session.issue_category if session else None)

    # Determine escalation level from policy context
    escalation_level = _determine_escalation_level(diagnostics, ai_summary)

    # 2. Compute dedupe key
    dedupe_key = _compute_dedupe_key(tenant_id, site_id, device_id, issue_category)

    # 3. Check for existing recent escalation
    existing = await _find_recent_escalation(db, dedupe_key, escalation_level)

    # 4. Build context for ticket/record
    diagnostics_checked = _build_diagnostics_dict(diagnostics)
    transcript_excerpt = _build_transcript_excerpt(messages)
    recommended_followup = _recommend_followup(diagnostics_checked, probable_cause)

    if existing:
        # ── Deduplicated: link to existing escalation ──
        handoff = _build_handoff_summary(
            tenant_id=tenant_id, site_id=site_id, device_id=device_id,
            reason=reason, probable_cause=probable_cause,
            issue_category=issue_category,
            diagnostics_checked=diagnostics_checked,
            transcript_excerpt=transcript_excerpt,
            additional_notes=additional_notes,
        )

        escalation = SupportEscalation(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            site_id=site_id,
            device_id=device_id,
            reason=reason,
            probable_cause=probable_cause,
            issue_category=issue_category,
            escalation_level=escalation_level,
            diagnostics_checked=diagnostics_checked,
            recommended_followup=recommended_followup,
            handoff_summary=handoff,
            dedupe_key=dedupe_key,
            was_deduplicated=True,
            linked_escalation_id=existing.id,
            zoho_ticket_id=existing.zoho_ticket_id,
            zoho_ticket_number=existing.zoho_ticket_number,
            zoho_ticket_url=existing.zoho_ticket_url,
            zoho_status=existing.zoho_status,
            status="linked",
        )
        db.add(escalation)

        if session:
            session.status = "escalated"
            session.escalated = True

        await db.commit()
        await db.refresh(escalation)

        logger.info(
            "Escalation deduplicated for session %s — linked to existing escalation %s (ticket %s)",
            session_id, existing.id, existing.zoho_ticket_id or "N/A",
        )
        return escalation

    # ── New escalation: create ticket ──

    # Build structured ticket content
    ticket_subject = _build_ticket_subject(issue_category, tenant_id, site_id, device_id)
    handoff = _build_handoff_summary(
        tenant_id=tenant_id, site_id=site_id, device_id=device_id,
        reason=reason, probable_cause=probable_cause,
        issue_category=issue_category,
        diagnostics_checked=diagnostics_checked,
        transcript_excerpt=transcript_excerpt,
        additional_notes=additional_notes,
    )

    # Priority mapping
    priority = "Urgent" if escalation_level == "urgent" else "High"

    # Create escalation record first (always persisted even if Zoho fails)
    escalation = SupportEscalation(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        site_id=site_id,
        device_id=device_id,
        reason=reason,
        probable_cause=probable_cause,
        issue_category=issue_category,
        escalation_level=escalation_level,
        diagnostics_checked=diagnostics_checked,
        recommended_followup=recommended_followup,
        handoff_summary=handoff,
        dedupe_key=dedupe_key,
        was_deduplicated=False,
        status="pending",
    )
    db.add(escalation)

    if session:
        session.status = "escalated"
        session.escalated = True

    # Attempt Zoho Desk ticket creation
    zoho_result = await zoho_desk_service.create_ticket(
        subject=ticket_subject,
        description=handoff,
        priority=priority,
        category=_zoho_category(issue_category),
        custom_fields={"cf_tenant_id": tenant_id},
    )

    if zoho_result["status"] == "created":
        escalation.zoho_ticket_id = zoho_result["ticket_id"]
        escalation.zoho_ticket_number = zoho_result.get("ticket_number")
        escalation.zoho_ticket_url = zoho_result.get("ticket_url")
        escalation.zoho_status = zoho_result.get("zoho_status", "Open")
        escalation.status = "created"
        escalation.synced_at = datetime.now(timezone.utc)
    elif zoho_result["status"] == "failed":
        escalation.status = "failed"
        escalation.sync_error = zoho_result.get("error", "Unknown Zoho API error")
        logger.warning("Zoho ticket creation failed — escalation stored locally: %s", escalation.sync_error)
    else:
        # Stub mode
        escalation.status = "pending"

    await db.commit()
    await db.refresh(escalation)

    logger.info(
        "Escalation created for session %s tenant %s — status=%s zoho_ticket=%s",
        session_id, tenant_id, escalation.status,
        escalation.zoho_ticket_id or "NOT_CREATED",
    )

    return escalation


# ═══════════════════════════════════════════════════════════════════
# Deduplication
# ═══════════════════════════════════════════════════════════════════

def _compute_dedupe_key(
    tenant_id: str,
    site_id: int | None,
    device_id: int | None,
    issue_category: str | None,
) -> str:
    """Build a stable dedupe key from escalation context."""
    parts = [
        tenant_id,
        str(site_id or "any"),
        str(device_id or "any"),
        (issue_category or "general").lower(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def _find_recent_escalation(
    db: AsyncSession,
    dedupe_key: str,
    escalation_level: str,
) -> SupportEscalation | None:
    """Find an existing recent escalation with the same dedupe key."""
    window = DEDUPE_WINDOWS.get(escalation_level, timedelta(hours=4))
    cutoff = datetime.now(timezone.utc) - window

    result = await db.execute(
        select(SupportEscalation)
        .where(and_(
            SupportEscalation.dedupe_key == dedupe_key,
            SupportEscalation.was_deduplicated == False,  # noqa: E712 — only match originals
            SupportEscalation.status.in_(["created", "pending"]),
            SupportEscalation.created_at >= cutoff,
        ))
        .order_by(SupportEscalation.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════
# Context gathering
# ═══════════════════════════════════════════════════════════════════

async def _get_session(db: AsyncSession, session_id: UUID) -> SupportSession | None:
    result = await db.execute(select(SupportSession).where(SupportSession.id == session_id))
    return result.scalar_one_or_none()


async def _get_diagnostics(db: AsyncSession, session_id: UUID) -> list:
    result = await db.execute(
        select(SupportDiagnostic).where(SupportDiagnostic.session_id == session_id)
    )
    return result.scalars().all()


async def _get_messages(db: AsyncSession, session_id: UUID) -> list:
    result = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.session_id == session_id)
        .order_by(SupportMessage.created_at.desc())
        .limit(20)
    )
    return list(reversed(result.scalars().all()))


async def _get_ai_summary(db: AsyncSession, session_id: UUID) -> SupportAISummary | None:
    result = await db.execute(
        select(SupportAISummary).where(SupportAISummary.session_id == session_id)
    )
    return result.scalar_one_or_none()


def _build_diagnostics_dict(diagnostics: list) -> dict:
    out = {}
    for d in diagnostics:
        out[d.check_type] = {
            "status": d.status,
            "severity": d.severity,
            "summary": d.internal_summary,
        }
    return out


def _build_transcript_excerpt(messages: list) -> str:
    return "\n".join(f"[{m.role.upper()}] {m.content[:200]}" for m in messages[-10:])


def _determine_escalation_level(diagnostics: list, ai_summary) -> str:
    has_critical = any(d.severity == "critical" for d in diagnostics)
    if has_critical:
        return "urgent"
    if ai_summary and ai_summary.escalated:
        return "recommend"
    has_warning = any(d.severity == "warning" for d in diagnostics)
    if has_warning:
        return "offer"
    return "offer"


# ═══════════════════════════════════════════════════════════════════
# Ticket content builders
# ═══════════════════════════════════════════════════════════════════

def _build_ticket_subject(
    issue_category: str | None,
    tenant_id: str,
    site_id: int | None,
    device_id: int | None,
) -> str:
    """Format: True911 | {issue_class} | {site} | {device}"""
    issue_label = {
        "device_offline": "Device Offline",
        "voice_quality": "Voice Service",
        "connectivity": "Connectivity",
        "compliance": "E911 Compliance",
        "escalation_request": "Customer Request",
        "general": "Support Request",
    }.get(issue_category or "general", "Support Request")

    parts = ["True911", issue_label]
    if site_id:
        parts.append(f"Site {site_id}")
    if device_id:
        parts.append(f"Device {device_id}")
    if not site_id and not device_id:
        parts.append(f"Tenant {tenant_id}")

    return " | ".join(parts)


def _build_handoff_summary(
    tenant_id: str,
    site_id: int | None,
    device_id: int | None,
    reason: str,
    probable_cause: str | None,
    issue_category: str | None,
    diagnostics_checked: dict,
    transcript_excerpt: str,
    additional_notes: str | None,
) -> str:
    """Build a structured, human-readable ticket description."""
    sections = []

    # 1. Summary
    sections.append("=== SUMMARY ===")
    sections.append(f"Reason: {reason}")
    sections.append("")

    # 2. Service Context
    sections.append("=== SERVICE CONTEXT ===")
    sections.append(f"Tenant: {tenant_id}")
    if site_id:
        sections.append(f"Site ID: {site_id}")
    if device_id:
        sections.append(f"Device ID: {device_id}")
    if issue_category:
        sections.append(f"Issue Category: {issue_category}")
    sections.append("")

    # 3. AI / System Assessment
    sections.append("=== SYSTEM ASSESSMENT ===")
    if probable_cause:
        sections.append(f"Probable Cause: {probable_cause}")
    if issue_category:
        sections.append(f"Issue Category: {issue_category}")
    sections.append("")

    # 4. Checks Already Completed
    if diagnostics_checked:
        sections.append("=== CHECKS COMPLETED ===")
        for check, result in diagnostics_checked.items():
            label = {
                "heartbeat": "Device Responsiveness",
                "device_status": "Device Status",
                "sip_registration": "Voice Service",
                "telemetry": "System Data",
                "ata_reachability": "Device Reachability",
                "incidents": "Active Issues",
                "e911": "E911 Compliance",
            }.get(check, check)
            status = result["status"].upper()
            severity = result["severity"]
            summary = result.get("summary", "")[:150]
            sections.append(f"  [{status}] {label} ({severity}) — {summary}")
        sections.append("")

    # 5. Conversation Excerpt
    if transcript_excerpt:
        sections.append("=== CONVERSATION ===")
        sections.append(transcript_excerpt)
        sections.append("")

    # 6. Recommended Next Step
    sections.append("=== RECOMMENDED NEXT STEP ===")
    sections.append(_recommend_followup(diagnostics_checked, probable_cause))

    if additional_notes:
        sections.append("")
        sections.append(f"Additional Notes: {additional_notes}")

    return "\n".join(sections)


def _recommend_followup(diagnostics_checked: dict, probable_cause: str | None) -> str:
    actions = []
    if not diagnostics_checked:
        actions.append("Run full diagnostic suite on the affected site/device.")

    for check, result in diagnostics_checked.items():
        if result["status"] in ("critical", "warning"):
            recs = {
                "heartbeat": "Verify device power and network connectivity on-site.",
                "device_status": "Check device provisioning status and firmware version.",
                "sip_registration": "Check SIP credentials and registrar connectivity.",
                "e911": "Update missing E911 address records.",
                "incidents": "Review open incidents and prioritize resolution.",
                "ata_reachability": "Verify ATA device is powered and network-reachable.",
            }
            if check in recs:
                actions.append(recs[check])

    if not actions:
        actions.append("Review customer conversation and follow up as needed.")

    return "\n".join(f"- {a}" for a in actions)


def _zoho_category(issue_category: str | None) -> str:
    return {
        "device_offline": "Device Issue",
        "voice_quality": "Voice Issue",
        "connectivity": "Connectivity",
        "compliance": "E911/Compliance",
    }.get(issue_category or "", "Support Escalation")
