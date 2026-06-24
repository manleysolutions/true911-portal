"""Support session lifecycle: creation, OTP issue/verify, escalation.

Security notes:
  * OTP codes are generated with :mod:`secrets` and NEVER stored or logged
    in plaintext — only a salted SHA-256 hash is persisted, and comparison
    is constant-time.
  * Every state change appends an :class:`OpsSessionEvent` audit row.
  * The matched tenant is recorded on the session and on every challenge /
    event so the verification trail is answerable per-tenant.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.incident import Incident
from app.models.ops_center import OpsOtpChallenge, OpsSessionEvent, OpsSupportSession
from app.services.ops_center.lookup import RawAssetMatch
from app.services.ops_center.normalize import mask_phone, normalize_phone
from app.services.ops_center.otp import get_otp_provider


# ── small helpers ────────────────────────────────────────────────────

def new_session_ref() -> str:
    return f"OPS-{secrets.token_hex(4).upper()}"


def generate_code(length: Optional[int] = None) -> str:
    n = length or settings.OPS_CENTER_OTP_CODE_LENGTH
    n = max(4, min(n, 10))
    return "".join(str(secrets.randbelow(10)) for _ in range(n))


def _salt() -> str:
    return settings.JWT_SECRET or "ops-center-otp"


def hash_code(code: str, session_id) -> str:
    return hashlib.sha256(f"{session_id}:{code}:{_salt()}".encode()).hexdigest()


def hash_destination(destination: str) -> str:
    return hashlib.sha256(f"{destination}:{_salt()}".encode()).hexdigest()


async def record_event(
    db: AsyncSession,
    session: OpsSupportSession,
    *,
    event_type: str,
    summary: str,
    actor: Optional[str] = None,
    detail: Optional[dict] = None,
) -> OpsSessionEvent:
    ev = OpsSessionEvent(
        session_id=session.id,
        tenant_id=session.matched_tenant_id,
        event_type=event_type,
        actor=actor or "system",
        summary=summary,
        detail=detail,
    )
    db.add(ev)
    return ev


# ── session creation + match attachment ──────────────────────────────

async def create_session(
    db: AsyncSession,
    *,
    caller_phone: Optional[str],
    source: str,
    issue_category: Optional[str],
    issue_summary: Optional[str],
    is_emergency: bool,
    operator,
) -> OpsSupportSession:
    session = OpsSupportSession(
        session_ref=new_session_ref(),
        caller_phone=caller_phone,
        caller_phone_normalized=normalize_phone(caller_phone) if caller_phone else None,
        source=source,
        issue_category=issue_category,
        issue_summary=issue_summary,
        is_emergency=bool(is_emergency),
        status="open",
        verification_status="unverified",
        escalation_status="none",
        opened_by_user_id=getattr(operator, "id", None),
        opened_by_email=getattr(operator, "email", None),
        opened_by_tenant_id=getattr(operator, "tenant_id", None),
    )
    db.add(session)
    await db.flush()  # assign id for the event FK
    await record_event(
        db,
        session,
        event_type="session_created",
        actor=getattr(operator, "email", None),
        summary=f"Session {session.session_ref} created (source={source}, emergency={bool(is_emergency)}).",
        detail={"issue_category": issue_category},
    )
    return session


def attach_match(session: OpsSupportSession, match: RawAssetMatch) -> None:
    """Copy a chosen asset match onto the session (no contact plaintext)."""
    session.matched_tenant_id = match.tenant_id
    session.matched_site_id = match.site_id
    session.matched_device_id = match.device_id
    session.matched_service_unit_id = match.service_unit_id
    session.matched_asset_identity_id = match.asset_identity_id
    session.matched_asset_kind = match.asset_kind
    session.matched_label = match.label or match.site_name
    session.contact_name = match.contact_name
    session.contact_phone_masked = mask_phone(match.contact_phone) if match.contact_phone else None
    if session.status == "open":
        session.status = "matched"
    # Stash the full contact destination in meta so send-otp can use it
    # without re-running lookup.  This is server-only state; the API never
    # echoes it back (only the masked form is exposed).
    meta = dict(session.meta or {})
    if match.contact_phone:
        meta["_contact_phone"] = match.contact_phone
    meta["identifiers_used"] = sorted(
        set(meta.get("identifiers_used", []))
        | ({match.matched_identifier_type} if match.matched_identifier_type else set())
    )
    session.meta = meta


# ── OTP issue / verify ───────────────────────────────────────────────

async def issue_otp(
    db: AsyncSession,
    session: OpsSupportSession,
    *,
    destination_override: Optional[str],
    actor: Optional[str],
) -> dict:
    destination = destination_override or (session.meta or {}).get("_contact_phone")
    if not destination:
        await record_event(
            db,
            session,
            event_type="otp_failed",
            actor=actor,
            summary="OTP not sent — no authorized contact on file for the matched asset.",
        )
        return {
            "ok": False,
            "otp_status": "failed",
            "destination_masked": None,
            "provider": settings.OPS_CENTER_OTP_PROVIDER,
            "simulated": False,
            "expires_at": None,
            "message": "No authorized contact on file. Escalate to a human agent to verify the caller.",
        }

    # Cancel any still-open challenge on this session.
    open_q = select(OpsOtpChallenge).where(
        OpsOtpChallenge.session_id == session.id,
        OpsOtpChallenge.status == "sent",
    )
    for prior in (await db.execute(open_q)).scalars().all():
        prior.status = "cancelled"

    code = generate_code()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.OPS_CENTER_OTP_TTL_SECONDS)

    challenge = OpsOtpChallenge(
        session_id=session.id,
        tenant_id=session.matched_tenant_id,
        destination_masked=mask_phone(destination),
        destination_hash=hash_destination(destination),
        code_hash=hash_code(code, session.id),
        provider=settings.OPS_CENTER_OTP_PROVIDER,
        status="sent",
        attempts=0,
        max_attempts=settings.OPS_CENTER_OTP_MAX_ATTEMPTS,
        expires_at=expires_at,
    )
    db.add(challenge)

    provider = get_otp_provider(settings)
    result = await provider.send(
        destination=destination,
        code=code,
        session_ref=session.session_ref,
        context={"issue_category": session.issue_category},
    )
    challenge.provider_message_id = result.message_id
    if not result.ok:
        challenge.status = "failed"
        session.verification_status = "failed"
        await record_event(
            db, session, event_type="otp_failed", actor=actor,
            summary=f"OTP delivery failed via {result.provider}.",
            detail={"error": result.error},
        )
        return {
            "ok": False, "otp_status": "failed",
            "destination_masked": challenge.destination_masked,
            "provider": result.provider, "simulated": result.simulated,
            "expires_at": None, "message": result.error or "Delivery failed.",
        }

    session.verification_status = "otp_sent"
    if session.status in ("open", "matched"):
        session.status = "verifying"
    await record_event(
        db, session, event_type="otp_sent", actor=actor,
        summary=f"OTP sent to {challenge.destination_masked} via {result.provider}"
                f"{' (simulated)' if result.simulated else ''}.",
        detail={"provider": result.provider, "simulated": result.simulated},
    )
    return {
        "ok": True, "otp_status": "otp_sent",
        "destination_masked": challenge.destination_masked,
        "provider": result.provider, "simulated": result.simulated,
        "expires_at": expires_at,
        "message": "Verification code sent." + (" (simulated — no SMS delivered)" if result.simulated else ""),
    }


async def verify_otp(
    db: AsyncSession,
    session: OpsSupportSession,
    *,
    code: str,
    actor: Optional[str],
) -> dict:
    q = (
        select(OpsOtpChallenge)
        .where(OpsOtpChallenge.session_id == session.id, OpsOtpChallenge.status == "sent")
        .order_by(OpsOtpChallenge.created_at.desc())
    )
    challenge = (await db.execute(q)).scalars().first()
    if challenge is None:
        return {"verified": False, "verification_status": session.verification_status,
                "attempts_remaining": None, "message": "No active verification code. Request a new code."}

    now = datetime.now(timezone.utc)
    expires_at = challenge.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is not None and now > expires_at:
        challenge.status = "expired"
        await record_event(db, session, event_type="otp_failed", actor=actor,
                           summary="Verification code expired before entry.")
        return {"verified": False, "verification_status": session.verification_status,
                "attempts_remaining": 0, "message": "Code expired. Request a new code."}

    challenge.attempts += 1
    expected = challenge.code_hash
    supplied = hash_code((code or "").strip(), session.id)
    if hmac.compare_digest(expected, supplied):
        challenge.status = "verified"
        challenge.verified_at = now
        session.verification_status = "verified"
        session.status = "verified"
        await record_event(db, session, event_type="otp_verified", actor=actor,
                           summary=f"Caller verified via OTP to {challenge.destination_masked}.")
        return {"verified": True, "verification_status": "verified",
                "attempts_remaining": None, "message": "Caller verified."}

    remaining = max(0, challenge.max_attempts - challenge.attempts)
    if remaining == 0:
        challenge.status = "failed"
        session.verification_status = "failed"
    await record_event(db, session, event_type="otp_failed", actor=actor,
                       summary=f"Incorrect verification code ({remaining} attempt(s) remaining).")
    return {"verified": False,
            "verification_status": session.verification_status,
            "attempts_remaining": remaining,
            "message": "Incorrect code." if remaining else "Incorrect code. Maximum attempts reached — request a new code."}


# ── escalation / handoff ─────────────────────────────────────────────

async def create_emergency_incident(
    db: AsyncSession, session: OpsSupportSession, *, actor: Optional[str]
) -> Optional[Incident]:
    """Create a LIMITED life-safety incident while verification continues.

    Allowed even when the caller is unverified — the spec requires an
    emergency path that does not block on verification.  Only minimal,
    non-sensitive detail is recorded.
    """
    incident_id = f"INC-OPS-{secrets.token_hex(4).upper()}"
    incident = Incident(
        incident_id=incident_id,
        tenant_id=session.matched_tenant_id or (session.opened_by_tenant_id or "unknown"),
        site_id=session.matched_site_id or "UNKNOWN",
        opened_at=datetime.now(timezone.utc),
        severity="critical",
        status="open",
        summary=f"Emergency reported via Support Center session {session.session_ref}.",
        category="life_safety",
        source="ops_center",
        incident_type=session.issue_category or "general_support",
        description=(session.issue_summary or "")[:2000],
        created_by=actor or "ops_center",
    )
    db.add(incident)
    session.incident_ref = incident_id
    await record_event(
        db, session, event_type="emergency_incident_created", actor=actor,
        summary=f"Limited life-safety incident {incident_id} created (verification not required for emergencies).",
        detail={"incident_id": incident_id},
    )
    return incident


def build_handoff_summary(
    session: OpsSupportSession,
    diagnostics: Optional[list[dict]] = None,
    *,
    reveal_sensitive: bool,
) -> dict:
    """Assemble the human-handoff summary.

    ``reveal_sensitive`` MUST mirror the session-view redaction rule
    (verified OR emergency).  When it is False the matched customer/tenant
    and device identifiers are withheld from the returned payload — exactly
    the fields ``_serialize_session`` blanks — so an unverified, non-emergency
    escalation never exposes which customer/device the caller *claimed*.  The
    data still lives on the session server-side for an internal operator to
    look up by ``session_ref`` through normal tenant-scoped tools.
    """
    meta = session.meta or {}
    return {
        "session_ref": session.session_ref,
        "issue_category": session.issue_category,
        "issue_summary": session.issue_summary,
        "is_emergency": session.is_emergency,
        "verification_status": session.verification_status,
        # Sensitive matched identifiers — gated, aligned with _serialize_session.
        "customer": session.matched_tenant_id if reveal_sensitive else None,
        "device_id": session.matched_device_id if reveal_sensitive else None,
        # Non-sensitive context the session view also exposes pre-verification.
        "site_id": session.matched_site_id,
        "service_unit_id": session.matched_service_unit_id,
        "asset_label": session.matched_label,
        "identifiers_used": list(meta.get("identifiers_used", [])),
        "diagnostics": diagnostics or [],
        "recommended_next_action": (
            "Escalated as a life-safety emergency — contact the caller/site immediately."
            if session.is_emergency
            else "Review diagnostics and contact the caller to resolve or dispatch."
        ),
        "handoff_number": session.handoff_number,
    }
