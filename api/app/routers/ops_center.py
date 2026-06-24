"""AI Customer Operations Center / Support Center — API router.

Caller-facing Tier-1 support workflow.  Every endpoint returns 404 when
``FEATURE_OPS_CENTER`` is not ``"true"`` so a misconfigured client cannot
tell the feature exists (mirrors the LLLM / Assurance pattern).

Phase 1 is OPERATOR-driven: an authenticated internal agent (or the AI on
the caller's behalf) drives the workflow.  Platform operators may look up
assets across all tenants (a support rep does not know the caller's tenant
yet); customer-tenant users are restricted to their own tenant.

Security invariants enforced here:
  * Sensitive matched fields (tenant id, device id) are withheld from the
    session view until the caller is VERIFIED (or the session is a
    declared life-safety emergency).
  * Triage (which reads device state) requires a verified session or an
    emergency.
  * Every lookup / OTP / verification / escalation appends an audit event,
    and key security events also write a tenant-scoped AuditLogEntry.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    is_platform_user,
    require_permission,
)
from app.models.ops_center import AssetIdentity, OpsSessionEvent, OpsSupportSession
from app.models.user import User
from app.schemas.ops_center import (
    IDENTIFIER_TYPES,
    ISSUE_CATEGORIES,
    SESSION_SOURCES,
    AssetIdentityCreate,
    AssetIdentityOut,
    AssetLookupRequest,
    AssetLookupResponse,
    AssetMatch,
    EscalateRequest,
    EscalateResponse,
    HandoffSummary,
    SendOtpRequest,
    SendOtpResponse,
    SessionCreate,
    SessionDetail,
    SessionEventOut,
    SessionOut,
    TriageResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.services.audit_logger import log_audit
from app.services.ops_center import lookup as lookup_svc
from app.services.ops_center import sessions as session_svc
from app.services.ops_center import triage as triage_svc
from app.services.ops_center.normalize import mask_phone, normalize_identifier

logger = logging.getLogger("true911.ops_center")
router = APIRouter()


# ── gates / helpers ──────────────────────────────────────────────────

def _require_feature() -> None:
    if settings.FEATURE_OPS_CENTER.lower() != "true":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


def _restrict_tenant(user: User) -> str | None:
    """None => search all tenants (platform operator). Otherwise the
    caller's own tenant (customer-tenant user)."""
    return None if is_platform_user(user) else user.tenant_id


def _reveal_sensitive(session: OpsSupportSession) -> bool:
    return session.verification_status == "verified" or bool(session.is_emergency)


def _serialize_session(session: OpsSupportSession) -> SessionOut:
    out = SessionOut.model_validate(session)
    if not _reveal_sensitive(session):
        # Withhold sensitive matched data until verified / emergency.
        out.matched_tenant_id = None
        out.matched_device_id = None
    return out


async def _load_session(db: AsyncSession, session_id: UUID, user: User) -> OpsSupportSession:
    session = (
        await db.execute(select(OpsSupportSession).where(OpsSupportSession.id == session_id))
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    # Customer-tenant users may only touch their own sessions.
    if not is_platform_user(user):
        owns = user.tenant_id in {session.matched_tenant_id, session.opened_by_tenant_id}
        if not owns:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return session


async def _audit(db, session, *, action, summary, detail=None, actor=None):
    """Mirror a key security event to the tenant-scoped central audit log
    (only when a tenant is known)."""
    tenant = session.matched_tenant_id
    if not tenant:
        return
    await log_audit(
        db,
        tenant_id=tenant,
        category="security",
        action=action,
        summary=summary,
        actor=actor,
        target_type="ops_support_session",
        target_id=session.session_ref,
        site_id=session.matched_site_id,
        device_id=session.matched_device_id,
        detail=detail,
    )


def _match_to_schema(m: lookup_svc.RawAssetMatch, *, reveal_tenant: bool) -> AssetMatch:
    return AssetMatch(
        asset_kind=m.asset_kind,
        asset_ref=m.asset_ref,
        label=m.label,
        category=m.category,
        site_name=m.site_name,
        building_name=m.building_name,
        matched_identifier_type=m.matched_identifier_type,
        match_source=m.match_source,
        has_contact_on_file=bool(m.contact_phone),
        contact_name=m.contact_name,
        contact_phone_masked=mask_phone(m.contact_phone) if m.contact_phone else None,
        tenant_id=m.tenant_id if reveal_tenant else None,
    )


# ── metadata ─────────────────────────────────────────────────────────

@router.get("/meta")
async def get_meta(current_user: User = Depends(require_permission("OPS_CENTER_VIEW"))):
    """Controlled vocabularies for the Support Center UI."""
    _require_feature()
    return {
        "issue_categories": ISSUE_CATEGORIES,
        "sources": SESSION_SOURCES,
        "identifier_types": IDENTIFIER_TYPES,
    }


# ── asset lookup ─────────────────────────────────────────────────────

@router.post("/lookup-asset", response_model=AssetLookupResponse)
async def lookup_asset(
    body: AssetLookupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_OPERATE")),
):
    """Find assets by a real-world identifier. Returns REDACTED matches."""
    _require_feature()
    if body.identifier_type and body.identifier_type not in IDENTIFIER_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown identifier_type")

    restrict = _restrict_tenant(current_user)
    reveal_tenant = is_platform_user(current_user)
    matches = await lookup_svc.find_assets(
        db,
        identifier=body.identifier,
        identifier_type=body.identifier_type,
        restrict_tenant_id=restrict,
    )

    # Attach the best match to a session, if one was supplied.
    if body.session_id is not None and matches:
        session = await _load_session(db, body.session_id, current_user)
        session_svc.attach_match(session, matches[0])
        await session_svc.record_event(
            db, session, event_type="asset_matched", actor=current_user.email,
            summary=f"Asset matched: {matches[0].asset_kind} {matches[0].asset_ref}.",
            detail={"match_source": matches[0].match_source},
        )
        await _audit(db, session, action="ops_asset_matched", actor=current_user.email,
                     summary=f"Caller asset matched for session {session.session_ref}.")
        await db.commit()
    else:
        # Pure lookup is still an audited event when scoped to a tenant.
        logger.info(
            "ops_center lookup by %s (platform=%s) matches=%d",
            current_user.email, reveal_tenant, len(matches),
        )

    note = None
    if not matches:
        note = "No matching asset found. Verify the identifier or escalate to a human agent."
    return AssetLookupResponse(
        query=body.identifier,
        match_count=len(matches),
        matches=[_match_to_schema(m, reveal_tenant=reveal_tenant) for m in matches],
        note=note,
    )


# ── session lifecycle ────────────────────────────────────────────────

@router.post("/session", response_model=SessionDetail, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_OPERATE")),
):
    """Open a support session. Optionally attempt an immediate asset match."""
    _require_feature()
    if body.source not in SESSION_SOURCES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown source")
    if body.issue_category and body.issue_category not in ISSUE_CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown issue_category")

    session = await session_svc.create_session(
        db,
        caller_phone=body.caller_phone,
        source=body.source,
        issue_category=body.issue_category,
        issue_summary=body.issue_summary,
        is_emergency=body.is_emergency,
        operator=current_user,
    )

    if body.identifier:
        matches = await lookup_svc.find_assets(
            db,
            identifier=body.identifier,
            identifier_type=body.identifier_type,
            restrict_tenant_id=_restrict_tenant(current_user),
        )
        if matches:
            session_svc.attach_match(session, matches[0])
            await session_svc.record_event(
                db, session, event_type="asset_matched", actor=current_user.email,
                summary=f"Asset matched on creation: {matches[0].asset_kind} {matches[0].asset_ref}.",
            )

    # Emergency path: allow a limited incident immediately, unverified.
    if body.is_emergency:
        await session_svc.create_emergency_incident(db, session, actor=current_user.email)
        session.verification_status = "bypassed_emergency"

    await db.commit()
    await db.refresh(session)
    return await _session_detail(db, session)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_VIEW")),
):
    _require_feature()
    q = select(OpsSupportSession)
    if not is_platform_user(current_user):
        q = q.where(
            or_(
                OpsSupportSession.matched_tenant_id == current_user.tenant_id,
                OpsSupportSession.opened_by_tenant_id == current_user.tenant_id,
            )
        )
    if status_filter:
        q = q.where(OpsSupportSession.status == status_filter)
    q = q.order_by(desc(OpsSupportSession.updated_at)).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [_serialize_session(s) for s in rows]


@router.get("/session/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_VIEW")),
):
    _require_feature()
    session = await _load_session(db, session_id, current_user)
    return await _session_detail(db, session)


async def _session_detail(db: AsyncSession, session: OpsSupportSession) -> SessionDetail:
    events = (
        await db.execute(
            select(OpsSessionEvent)
            .where(OpsSessionEvent.session_id == session.id)
            .order_by(OpsSessionEvent.created_at.asc(), OpsSessionEvent.id.asc())
        )
    ).scalars().all()
    base = _serialize_session(session)
    detail = SessionDetail(**base.model_dump())
    detail.events = [SessionEventOut.model_validate(e) for e in events]
    return detail


# ── OTP ──────────────────────────────────────────────────────────────

@router.post("/session/{session_id}/send-otp", response_model=SendOtpResponse)
async def send_otp(
    session_id: UUID,
    body: SendOtpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_OPERATE")),
):
    _require_feature()
    session = await _load_session(db, session_id, current_user)
    if not session.matched_tenant_id and not body.destination_override:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No matched asset / contact for this session — run lookup-asset first.",
        )
    result = await session_svc.issue_otp(
        db, session, destination_override=body.destination_override, actor=current_user.email,
    )
    await _audit(db, session, action="ops_otp_sent", actor=current_user.email,
                 summary=f"OTP {'sent' if result['ok'] else 'send failed'} for session {session.session_ref}.",
                 detail={"otp_status": result["otp_status"]})
    await db.commit()
    return SendOtpResponse(session_id=session.id, **{k: result[k] for k in (
        "otp_status", "destination_masked", "provider", "simulated", "expires_at", "message")})


@router.post("/session/{session_id}/verify-otp", response_model=VerifyOtpResponse)
async def verify_otp(
    session_id: UUID,
    body: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_OPERATE")),
):
    _require_feature()
    session = await _load_session(db, session_id, current_user)
    result = await session_svc.verify_otp(db, session, code=body.code, actor=current_user.email)
    await _audit(db, session, action="ops_otp_verified" if result["verified"] else "ops_otp_failed",
                 actor=current_user.email,
                 summary=f"Caller verification {'succeeded' if result['verified'] else 'failed'} "
                         f"for session {session.session_ref}.")
    await db.commit()
    return VerifyOtpResponse(session_id=session.id, **result)


# ── triage ───────────────────────────────────────────────────────────

@router.post("/session/{session_id}/triage", response_model=TriageResponse)
async def triage(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_OPERATE")),
):
    """Run diagnostics. Requires a VERIFIED session (or a declared emergency)."""
    _require_feature()
    session = await _load_session(db, session_id, current_user)
    if not _reveal_sensitive(session):
        await session_svc.record_event(
            db, session, event_type="sensitive_access_blocked", actor=current_user.email,
            summary="Triage blocked — caller not verified.",
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Caller is not verified. Verify by OTP (or declare an emergency) before running diagnostics.",
        )
    result = await triage_svc.run_triage(db, session)
    await session_svc.record_event(
        db, session, event_type="triage_run", actor=current_user.email,
        summary=f"Triage run — overall={result['overall']}.",
        detail={"overall": result["overall"]},
    )
    await db.commit()
    return TriageResponse(**result)


# ── escalation / handoff ─────────────────────────────────────────────

@router.post("/session/{session_id}/escalate", response_model=EscalateResponse)
async def escalate(
    session_id: UUID,
    body: EscalateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_OPERATE")),
):
    """Escalate to a human. Builds a handoff summary; optionally opens an
    incident.  Allowed for unverified sessions (handoff is the safe fallback
    when verification cannot complete) and for emergencies."""
    _require_feature()
    session = await _load_session(db, session_id, current_user)

    handoff_number = body.handoff_number or settings.OPS_CENTER_HANDOFF_NUMBER or None
    session.handoff_number = handoff_number

    # Diagnostics are only attached to the handoff when the caller is
    # verified / emergency — keeps sensitive device data out otherwise.
    diagnostics: list[dict] = []
    if _reveal_sensitive(session):
        triage_result = await triage_svc.run_triage(db, session)
        diagnostics = triage_result["checks"]

    if (body.create_incident or session.is_emergency) and not session.incident_ref:
        await session_svc.create_emergency_incident(db, session, actor=current_user.email)

    session.escalation_status = "created" if session.incident_ref else "requested"
    if session.status not in ("resolved", "closed"):
        session.status = "escalated"

    summary_dict = session_svc.build_handoff_summary(session, diagnostics)
    if body.reason:
        summary_dict["recommended_next_action"] = body.reason

    await session_svc.record_event(
        db, session, event_type="escalated", actor=current_user.email,
        summary=f"Escalated to human support (status={session.escalation_status}).",
        detail={"handoff_number": handoff_number, "incident_ref": session.incident_ref},
    )
    await _audit(db, session, action="ops_escalated", actor=current_user.email,
                 summary=f"Session {session.session_ref} escalated to human support.")
    await db.commit()
    await db.refresh(session)

    return EscalateResponse(
        session_id=session.id,
        escalation_status=session.escalation_status,
        incident_ref=session.incident_ref,
        ticket_ref=session.ticket_ref,
        handoff_number=handoff_number,
        handoff_summary=HandoffSummary(**summary_dict),
    )


# ── asset identity management (internal) ─────────────────────────────

@router.post("/asset-identities", response_model=AssetIdentityOut, status_code=201)
async def create_asset_identity(
    body: AssetIdentityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_MANAGE_ASSETS")),
):
    _require_feature()
    if body.identifier_type not in IDENTIFIER_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown identifier_type")
    if body.asset_kind not in ("device", "site", "service_unit", "line"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown asset_kind")

    ai = AssetIdentity(
        tenant_id=current_user.tenant_id,
        identifier_type=body.identifier_type,
        identifier_value=body.identifier_value,
        identifier_value_normalized=normalize_identifier(body.identifier_type, body.identifier_value),
        asset_kind=body.asset_kind,
        asset_ref=body.asset_ref,
        site_id=body.site_id,
        device_id=body.device_id,
        service_unit_id=body.service_unit_id,
        label=body.label,
        category=body.category,
        source=body.source or "manual",
    )
    db.add(ai)
    await db.commit()
    await db.refresh(ai)
    return AssetIdentityOut.model_validate(ai)


@router.get("/asset-identities", response_model=list[AssetIdentityOut])
async def list_asset_identities(
    asset_ref: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("OPS_CENTER_MANAGE_ASSETS")),
):
    _require_feature()
    q = select(AssetIdentity).where(AssetIdentity.tenant_id == current_user.tenant_id)
    if asset_ref:
        q = q.where(AssetIdentity.asset_ref == asset_ref)
    q = q.order_by(desc(AssetIdentity.created_at)).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [AssetIdentityOut.model_validate(r) for r in rows]
