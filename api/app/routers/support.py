"""Support AI assistant — API endpoints.

Endpoints:
    POST   /api/support/sessions                        — Create new support session
    POST   /api/support/sessions/{session_id}/message    — Send a message
    GET    /api/support/sessions/{session_id}            — Get session detail + transcript
    POST   /api/support/diagnostics/run                  — Run system diagnostics
    POST   /api/support/escalate                         — Escalate to human support
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.dependencies import get_current_user
from app.models.user import User
from app.models.support import SupportSession, SupportMessage, SupportDiagnostic, SupportEscalation, SupportRemediationAction
from app.schemas.support import (
    SupportSessionCreate, SupportSessionOut, SupportSessionUpdate,
    SupportMessageSend, SupportMessageOut,
    SupportSessionDetail, SupportDiagnosticOut,
    DiagnosticRunRequest, DiagnosticResult,
    EscalationRequest, SupportEscalationOut, SupportEscalationCustomerOut,
    RemediationRunRequest, RemediationActionOut,
)

logger = logging.getLogger("true911.support")
router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _is_admin(user: User) -> bool:
    return user.role in ("Admin", "SuperAdmin")


# ── List Sessions (Admin) ───────────────────────────────────────

@router.get("/sessions", response_model=list[SupportSessionOut])
async def list_sessions(
    status_filter: str | None = Query(None, alias="status"),
    escalated: bool | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List support sessions. SuperAdmins see all tenants; others see own tenant only."""
    if not _is_admin(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")

    q = select(SupportSession)

    # Tenant scoping
    if current_user.role == "SuperAdmin" and tenant_id:
        q = q.where(SupportSession.tenant_id == tenant_id)
    elif current_user.role != "SuperAdmin":
        q = q.where(SupportSession.tenant_id == current_user.tenant_id)

    if status_filter:
        q = q.where(SupportSession.status == status_filter)
    if escalated is not None:
        q = q.where(SupportSession.escalated == escalated)

    q = q.order_by(desc(SupportSession.updated_at)).limit(limit)
    result = await db.execute(q)
    return [SupportSessionOut.model_validate(s) for s in result.scalars().all()]


# ── Update Session (Admin) ─────────────────────────────────────

@router.patch("/sessions/{session_id}", response_model=SupportSessionOut)
async def update_session(
    session_id: UUID,
    body: SupportSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update session status (e.g. mark resolved). Admin only."""
    if not _is_admin(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")

    session = await _get_session_or_404(db, session_id, current_user)

    if body.status is not None:
        session.status = body.status
    if body.resolution_summary is not None:
        session.resolution_summary = body.resolution_summary

    await db.commit()
    await db.refresh(session)
    return SupportSessionOut.model_validate(session)


# ── Create Session ──────────────────────────────────────────────

@router.post("/sessions", response_model=SupportSessionOut, status_code=201)
async def create_session(
    body: SupportSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new support session."""
    from app.services.support.orchestrator import create_session as svc_create

    session, _ = await svc_create(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        site_id=body.site_id,
        device_id=body.device_id,
        initial_message=body.initial_message,
    )
    return SupportSessionOut.model_validate(session)


# ── Send Message ────────────────────────────────────────────────

@router.post("/sessions/{session_id}/message", response_model=SupportMessageOut)
async def send_message(
    session_id: UUID,
    body: SupportMessageSend,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message in a support session and get an AI response."""
    session = await _get_session_or_404(db, session_id, current_user)

    if session.status != "active":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Session is {session.status} — cannot send messages.",
        )

    from app.services.support.orchestrator import process_message

    assistant_msg = await process_message(db, session, body.content)
    await db.commit()
    await db.refresh(assistant_msg)

    out = SupportMessageOut.model_validate(assistant_msg)

    # Strip internal-only fields from structured_response for non-admins
    if not _is_admin(current_user) and out.structured_response:
        out.structured_response = _sanitize_structured(out.structured_response)

    return out


# ── Get Session Detail ──────────────────────────────────────────

@router.get("/sessions/{session_id}", response_model=SupportSessionDetail)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full session detail including messages and diagnostics."""
    session = await _get_session_or_404(db, session_id, current_user)

    # Messages
    msg_result = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.session_id == session_id)
        .order_by(SupportMessage.created_at.asc())
    )
    messages = msg_result.scalars().all()

    # Diagnostics
    diag_result = await db.execute(
        select(SupportDiagnostic)
        .where(SupportDiagnostic.session_id == session_id)
        .order_by(SupportDiagnostic.created_at.desc())
    )
    diagnostics = diag_result.scalars().all()

    is_admin = _is_admin(current_user)

    # Sanitize for non-admin users
    msg_out = []
    for m in messages:
        out = SupportMessageOut.model_validate(m)
        if not is_admin and out.structured_response:
            out.structured_response = _sanitize_structured(out.structured_response)
        msg_out.append(out)

    diag_out = []
    for d in diagnostics:
        out = SupportDiagnosticOut.model_validate(d)
        if not is_admin:
            out.internal_summary = None
            out.raw_payload = None
        diag_out.append(out)

    # Escalations (admin only)
    esc_out = []
    if is_admin:
        esc_result = await db.execute(
            select(SupportEscalation)
            .where(SupportEscalation.session_id == session_id)
            .order_by(SupportEscalation.created_at.desc())
        )
        esc_out = [SupportEscalationOut.model_validate(e) for e in esc_result.scalars().all()]

    return SupportSessionDetail(
        session=SupportSessionOut.model_validate(session),
        messages=msg_out,
        diagnostics=diag_out,
        escalations=esc_out,
    )


# ── Run Diagnostics ─────────────────────────────────────────────

@router.post("/diagnostics/run", response_model=list[SupportDiagnosticOut])
async def run_diagnostics(
    body: DiagnosticRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run system diagnostics and return results."""
    session = await _get_session_or_404(db, body.session_id, current_user)

    from app.services.support.orchestrator import run_system_test

    diagnostics, _ = await run_system_test(db, session)
    await db.commit()

    is_admin = _is_admin(current_user)
    results = []
    # Re-fetch from DB to get proper IDs
    diag_result = await db.execute(
        select(SupportDiagnostic)
        .where(SupportDiagnostic.session_id == body.session_id)
        .order_by(SupportDiagnostic.created_at.desc())
        .limit(len(diagnostics))
    )
    for d in diag_result.scalars().all():
        out = SupportDiagnosticOut.model_validate(d)
        if not is_admin:
            out.internal_summary = None
            out.raw_payload = None
        results.append(out)

    return results


# ── Escalate ────────────────────────────────────────────────────

@router.post("/escalate")
async def escalate(
    body: EscalationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Escalate a support session to human support (Zoho Desk).

    Returns full ticket metadata for admins, calm confirmation for subscribers.
    """
    await _get_session_or_404(db, body.session_id, current_user)

    from app.services.support.escalation import create_escalation

    escalation = await create_escalation(
        db,
        session_id=body.session_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        reason=body.reason,
        additional_notes=body.additional_notes,
    )

    if _is_admin(current_user):
        return SupportEscalationOut.model_validate(escalation)

    # Subscriber: calm confirmation only — no Zoho/internal details
    return SupportEscalationCustomerOut(
        id=escalation.id,
        session_id=escalation.session_id,
        status="submitted",
        message=(
            "Your support request has been submitted. "
            "We've included the checks already completed so you don't need to repeat them. "
            "Our team will review this and follow up shortly."
        ),
        created_at=escalation.created_at,
    )


# ── Remediation (Admin only) ────────────────────────────────────

@router.get("/remediation", response_model=list[RemediationActionOut])
async def list_remediations(
    status_filter: str | None = Query(None, alias="status"),
    action_type: str | None = Query(None),
    verification: str | None = Query(None, alias="verification_status"),
    tenant_id: str | None = Query(None),
    site_id: int | None = Query(None),
    device_id: int | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List remediation actions across all sessions. Admin/SuperAdmin only."""
    if not _is_admin(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")

    q = select(SupportRemediationAction)

    if current_user.role == "SuperAdmin" and tenant_id:
        q = q.where(SupportRemediationAction.tenant_id == tenant_id)
    elif current_user.role != "SuperAdmin":
        q = q.where(SupportRemediationAction.tenant_id == current_user.tenant_id)

    if status_filter:
        q = q.where(SupportRemediationAction.status == status_filter)
    if action_type:
        q = q.where(SupportRemediationAction.action_type == action_type)
    if verification:
        q = q.where(SupportRemediationAction.verification_status == verification)
    if site_id is not None:
        q = q.where(SupportRemediationAction.site_id == site_id)
    if device_id is not None:
        q = q.where(SupportRemediationAction.device_id == device_id)

    q = q.order_by(desc(SupportRemediationAction.created_at)).limit(limit)
    result = await db.execute(q)
    return [RemediationActionOut.model_validate(r) for r in result.scalars().all()]


@router.post("/remediation/run")
async def run_remediation(
    body: RemediationRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run a remediation action. Admin/SuperAdmin only."""
    if not _is_admin(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")

    from app.services.support.self_healing import attempt_remediation

    tenant_id = body.tenant_id or current_user.tenant_id

    result = await attempt_remediation(
        db,
        action_type=body.action_type,
        tenant_id=tenant_id,
        trigger_source="admin",
        session_id=body.session_id,
        escalation_id=body.escalation_id,
        site_id=body.site_id,
        device_id=body.device_id,
        issue_category=body.issue_category,
    )
    await db.commit()
    return result


@router.get("/remediation/{session_id}", response_model=list[RemediationActionOut])
async def get_remediations(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get remediation actions for a session. Admin/SuperAdmin only."""
    if not _is_admin(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")

    await _get_session_or_404(db, session_id, current_user)

    from app.services.support.self_healing import get_session_remediations
    actions = await get_session_remediations(db, session_id)
    return [RemediationActionOut.model_validate(a) for a in actions]


# ── Helpers ─────────────────────────────────────────────────────

async def _get_session_or_404(db: AsyncSession, session_id: UUID, current_user: User) -> SupportSession:
    """Fetch session, enforce tenant isolation."""
    result = await db.execute(
        select(SupportSession).where(SupportSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Support session not found")

    # Tenant isolation — admins from same tenant or superadmin
    if session.tenant_id != current_user.tenant_id and current_user.role != "SuperAdmin":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Support session not found")

    return session


def _sanitize_structured(structured: dict) -> dict:
    """Remove internal-only fields from AI structured response for customer users."""
    sanitized = {**structured}
    sanitized.pop("probable_cause", None)
    sanitized.pop("escalation_reason", None)
    sanitized.pop("diagnostics", None)
    sanitized.pop("raw_payload", None)
    return sanitized
