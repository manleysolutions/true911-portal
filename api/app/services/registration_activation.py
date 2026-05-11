"""Phase R5 — activation hand-off + customer invite/access.

Two side effects, one module:

  1. ``issue_invite`` fires on the transition into ``ready_for_activation``.
     Creates (or reuses, or rotates) a User row tied to the registration's
     submitter_email so the customer can claim portal access via the
     existing /auth/invite/{token} flow.

  2. ``mark_customer_complete`` fires on the transition into ``active``.
     Flips the resolved Customer's onboarding_status to ``complete``.

Both helpers run inside the transition's open transaction (driven by
``registration_service.transition_status``); their writes share the
single commit at the end of the transition, and a failure rolls back
the entire transition along with the side effect.

What R5 does NOT do
===================

  * Send the invite email — the operator copies the URL out-of-band
  * Promote the invited user past ``role="User"``
  * Create more than one invited user per registration
  * Call any external integration (T-Mobile, Field Nation, billing,
    E911 carrier, provisioning)
  * Modify the existing /auth/invite/{token} accept flow

These restrictions are enforced by what this module imports: only
the User / Customer / AuditLogEntry / RegistrationStatusEvent models
plus ``hash_password`` from the auth service.
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit_log_entry import AuditLogEntry
from app.models.customer import Customer
from app.models.registration import Registration
from app.models.registration_status_event import RegistrationStatusEvent
from app.models.user import User
from app.services.auth import hash_password
from app.services.registration_service import Status

logger = logging.getLogger("true911.registration.activation")


# Invite TTL.  30 days mirrors the R1 resume-token window; matches the
# longest acceptance horizon we expect for a customer to claim a
# portal account after their install is QA-approved.
INVITE_TTL = timedelta(days=30)

# Default role for the customer's first user account.  The R4 plan
# locks this in: invite as ``User`` (read-only); operator promotes to
# Admin manually via the existing /api/admin/users surface.
INVITE_ROLE = "User"


# ─────────────────────────────────────────────────────────────────────
# Structured error
# ─────────────────────────────────────────────────────────────────────

class ActivationError(Exception):
    """Structured error raised by the activation side effects.

    Mirrors the R4 ``ConversionError`` shape so the API layer surfaces
    a consistent ``{stage, message, next_steps, details}`` body to the
    reviewer.  The state-machine transition itself is rolled back when
    one of these is raised — see ``run_activation_hook`` below.
    """

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        next_steps: str = "",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.stage = stage
        self.message = message
        self.next_steps = next_steps
        self.details: dict[str, Any] = details or {}
        super().__init__(f"{stage}: {message}")


# ─────────────────────────────────────────────────────────────────────
# Outcome dataclasses
# ─────────────────────────────────────────────────────────────────────

@dataclass
class InviteOutcome:
    """Return value from ``issue_invite``.

    ``invite_token`` is plaintext and present only when the action is
    ``created`` or ``rotated`` — the operator's one-time view of the
    secret.  When the action is ``reused`` or ``skipped_active``, the
    token is None because the server cannot recover the plaintext
    from storage.
    """

    user_id: str  # UUID stringified
    email: str
    action: str  # "created" | "rotated" | "reused" | "skipped_active"
    invite_token: Optional[str] = None
    invite_url: Optional[str] = None
    invite_expires_at: Optional[datetime] = None


@dataclass
class CustomerOutcome:
    """Return value from ``mark_customer_complete``."""

    customer_id: int
    action: str  # "completed" | "skipped_already_complete" | "skipped_on_hold"
    previous_status: Optional[str] = None
    new_status: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _invite_url(token: str) -> str:
    """Build the customer-facing invite URL.

    Format mirrors the password-reset URL pattern from ``auth.py``:
    PUBLIC_URL + /login?invite=<token>.  The login page reads the
    ``invite`` query parameter and routes to the existing accept-invite
    flow.  No new public route is required.
    """
    return f"{settings.PUBLIC_URL}/login?invite={token}"


def _generate_invite_token() -> str:
    """48 bytes of entropy, URL-safe base64.

    Stored plaintext at rest because the existing /auth/invite/{token}
    handler does a direct equality lookup against ``users.invite_token``.
    Hashing would require a wider change touching the password-reset
    reuse of the same column; documented in the R5 plan §10.
    """
    return secrets.token_urlsafe(48)


def _throwaway_password() -> str:
    """Random password the invited user never sees.

    Set on creation so the column's NOT NULL constraint is satisfied;
    overwritten when the customer accepts the invite via
    /auth/invite/{token}/accept.  Independent random bytes — never
    related to the invite token.
    """
    return hash_password(secrets.token_urlsafe(48))


def _audit(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_email: Optional[str],
    action: str,
    target_type: str,
    target_id: Optional[str],
    summary: str,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Append one AuditLogEntry row.  Matches the ``_audit`` helper in
    registration_conversion so the activation breadcrumbs read the
    same as the conversion ones in the global audit log.
    """
    db.add(AuditLogEntry(
        entry_id=f"activation-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        category="activation",
        action=action,
        actor=actor_email,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        detail_json=json.dumps(detail) if detail else None,
    ))


def _status_event(
    db: AsyncSession,
    registration: Registration,
    *,
    note: str,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
) -> None:
    """Append a ``registration_status_events`` row that does NOT
    change the registration's status.

    Same idiom as ``_status_event`` in registration_conversion.py —
    the activation event sits *alongside* the actual transition's
    own status-event row (which was already added by the state
    machine in transition_status before the hook ran).
    """
    db.add(RegistrationStatusEvent(
        registration_id=registration.id,
        from_status=registration.status,
        to_status=registration.status,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        note=note,
    ))


# ─────────────────────────────────────────────────────────────────────
# Invite side effect
# ─────────────────────────────────────────────────────────────────────

async def issue_invite(
    db: AsyncSession,
    registration: Registration,
    *,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
) -> InviteOutcome:
    """Issue (or reuse, or rotate) a portal invite for the registration's
    submitter.

    Idempotency rules (see R5 plan §5):
      * existing user, already active        -> skip
      * existing user, valid pending invite  -> reuse (no new token)
      * existing user, expired/no token      -> rotate (new token)
      * no existing user                     -> create

    Cross-tenant email collision (an existing user with the same email
    in a *different* tenant) is rejected with ActivationError — the
    users.email unique index would otherwise either fail the INSERT
    or silently re-tenant an existing account.  Neither is acceptable.
    """

    # ── Prerequisites ─────────────────────────────────────────────
    if not registration.customer_id:
        raise ActivationError(
            stage="validate_prerequisites",
            message="registration has no customer_id — convert it first",
            next_steps=(
                "Run conversion before transitioning to ready_for_activation "
                "so the customer + tenant exist."
            ),
        )
    if not registration.target_tenant_id:
        raise ActivationError(
            stage="validate_prerequisites",
            message="registration has no target_tenant_id — convert it first",
            next_steps="Run conversion first.",
        )
    raw_email = (registration.submitter_email or "").strip()
    if not raw_email or "@" not in raw_email:
        raise ActivationError(
            stage="validate_prerequisites",
            message="registration.submitter_email is missing or malformed",
            next_steps=(
                "Edit the registration to set a valid submitter email "
                "before activation."
            ),
            details={"submitter_email": registration.submitter_email},
        )
    email = raw_email.lower()
    tenant_id = registration.target_tenant_id

    # ── Lookup by lowercased email ────────────────────────────────
    # We use func.lower() so legacy mixed-case rows still match —
    # historic imports may not be uniformly lowercased.
    result = await db.execute(
        select(User).where(func.lower(User.email) == email)
    )
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing is not None:
        # Cross-tenant collision is fatal — the unique index on
        # users.email means we cannot have two rows with the same
        # email in different tenants, but we also can't silently
        # re-tenant an existing user.
        if existing.tenant_id != tenant_id:
            raise ActivationError(
                stage="issue_invite",
                message=(
                    f"email '{email}' already belongs to tenant "
                    f"'{existing.tenant_id}', not this registration's "
                    f"target tenant '{tenant_id}'"
                ),
                next_steps=(
                    "Reconcile the email collision manually before "
                    "retrying the activation transition."
                ),
                details={
                    "submitter_email": email,
                    "existing_tenant_id": existing.tenant_id,
                    "target_tenant_id": tenant_id,
                },
            )

        # Already accepted — nothing to do.
        if existing.is_active:
            _status_event(
                db, registration,
                note=f"invite: user id={existing.id} is already active, skipped",
                actor_user_id=actor_user_id, actor_email=actor_email,
            )
            return InviteOutcome(
                user_id=str(existing.id),
                email=email,
                action="skipped_active",
                invite_expires_at=existing.invite_expires_at,
            )

        # Inactive user with a still-valid invite — reuse without
        # rotating the token.  The plaintext was handed out on the
        # previous transition and can't be recovered now.
        if (
            existing.invite_token
            and existing.invite_expires_at
            and _is_future(existing.invite_expires_at, now)
        ):
            _status_event(
                db, registration,
                note=f"invite: reused active invite for user id={existing.id}",
                actor_user_id=actor_user_id, actor_email=actor_email,
            )
            return InviteOutcome(
                user_id=str(existing.id),
                email=email,
                action="reused",
                invite_expires_at=existing.invite_expires_at,
            )

        # Existing user, no usable invite — rotate.
        new_token = _generate_invite_token()
        existing.invite_token = new_token
        existing.invite_expires_at = now + INVITE_TTL
        existing.must_change_password = True
        url = _invite_url(new_token)
        _status_event(
            db, registration,
            note=(
                f"invite: rotated token for user id={existing.id} "
                f"(prior expired or absent)"
            ),
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        _audit(
            db,
            tenant_id=tenant_id,
            actor_email=actor_email,
            action="rotate_invite_token",
            target_type="user",
            target_id=str(existing.id),
            summary=f"Rotated invite token for {email}",
            detail={
                "registration_id": registration.registration_id,
                "tenant_id": tenant_id,
                "invite_expires_at": existing.invite_expires_at.isoformat(),
            },
        )
        logger.info(
            "Invite rotated: user=%s email=%s registration=%s",
            existing.id, email, registration.registration_id,
        )
        return InviteOutcome(
            user_id=str(existing.id),
            email=email,
            action="rotated",
            invite_token=new_token,
            invite_url=url,
            invite_expires_at=existing.invite_expires_at,
        )

    # ── No existing user — create one ─────────────────────────────
    new_token = _generate_invite_token()
    expires_at = now + INVITE_TTL
    name = (registration.submitter_name or "").strip() or email.split("@")[0]
    # Client-assign the UUID PK so the value is available before the
    # INSERT round-trip — matters for the in-memory fake session used
    # by the integration tests and is harmless on real Postgres.
    user = User(
        id=uuid.uuid4(),
        email=email,
        name=name,
        password_hash=_throwaway_password(),
        role=INVITE_ROLE,
        tenant_id=tenant_id,
        is_active=False,
        must_change_password=True,
        invite_token=new_token,
        invite_expires_at=expires_at,
    )
    db.add(user)
    await db.flush()

    url = _invite_url(new_token)
    _status_event(
        db, registration,
        note=f"invite: created user id={user.id} email={email}",
        actor_user_id=actor_user_id, actor_email=actor_email,
    )
    _audit(
        db,
        tenant_id=tenant_id,
        actor_email=actor_email,
        action="create_invited_user",
        target_type="user",
        target_id=str(user.id),
        summary=f"Invited {email} to tenant {tenant_id} as {INVITE_ROLE}",
        detail={
            "registration_id": registration.registration_id,
            "tenant_id": tenant_id,
            "role": INVITE_ROLE,
            "invite_expires_at": expires_at.isoformat(),
        },
    )
    logger.info(
        "Invite created: user=%s email=%s tenant=%s registration=%s",
        user.id, email, tenant_id, registration.registration_id,
    )

    return InviteOutcome(
        user_id=str(user.id),
        email=email,
        action="created",
        invite_token=new_token,
        invite_url=url,
        invite_expires_at=expires_at,
    )


# ─────────────────────────────────────────────────────────────────────
# Activation side effect
# ─────────────────────────────────────────────────────────────────────

# customers.onboarding_status values we may safely transition to
# "complete".  Other values (notably "on_hold") indicate the operator
# has manually set the customer's lifecycle and we don't trample.
_COMPLETABLE_ONBOARDING_STATES: frozenset[Optional[str]] = frozenset(
    {None, "", "pending", "in_progress"}
)


async def mark_customer_complete(
    db: AsyncSession,
    registration: Registration,
    *,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
) -> CustomerOutcome:
    """Flip the registration's resolved Customer to onboarding_status
    = "complete" on the transition into ``active``.

    Idempotency rules (see R5 plan §5):
      * customer.onboarding_status already "complete" -> skip
      * customer.onboarding_status == "on_hold"       -> skip (don't trample)
      * else                                          -> set to "complete"

    Also stamps ``registration.activated_at`` the first time this
    helper runs for a given registration.
    """

    if not registration.customer_id:
        raise ActivationError(
            stage="validate_prerequisites",
            message="registration has no customer_id — convert it first",
            next_steps="Run conversion before transitioning to active.",
        )

    customer = await db.get(Customer, registration.customer_id)
    if customer is None:
        raise ActivationError(
            stage="mark_customer_complete",
            message=(
                f"customer id={registration.customer_id} no longer exists"
            ),
            next_steps=(
                "Investigate why the converted customer was deleted before "
                "retrying."
            ),
        )

    previous = customer.onboarding_status
    now = datetime.now(timezone.utc)

    if previous == "complete":
        _status_event(
            db, registration,
            note=f"activation: customer id={customer.id} already complete, skipped",
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        if registration.activated_at is None:
            # First time anyone activated this registration even though
            # the customer was already complete (e.g. converted-then-
            # activated by a different path).  Stamp the registration
            # for parity with the normal flow.
            registration.activated_at = now
        return CustomerOutcome(
            customer_id=customer.id,
            action="skipped_already_complete",
            previous_status=previous,
            new_status=previous,
        )

    if previous == "on_hold":
        _status_event(
            db, registration,
            note=(
                f"activation: customer id={customer.id} is on_hold, "
                "onboarding_status not modified"
            ),
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        # We do NOT stamp activated_at here because the customer is
        # explicitly paused; activation has not really happened.
        return CustomerOutcome(
            customer_id=customer.id,
            action="skipped_on_hold",
            previous_status=previous,
            new_status=previous,
        )

    if previous not in _COMPLETABLE_ONBOARDING_STATES:
        # Unknown manual state — treat as "don't trample" by default.
        # Better to surface the surprise to the audit log than to
        # quietly overwrite an operator's intent.
        _status_event(
            db, registration,
            note=(
                f"activation: customer id={customer.id} has unrecognised "
                f"onboarding_status={previous!r}; not modified"
            ),
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        return CustomerOutcome(
            customer_id=customer.id,
            action="skipped_on_hold",  # treat unknown as on_hold-like
            previous_status=previous,
            new_status=previous,
        )

    customer.onboarding_status = "complete"
    if registration.activated_at is None:
        registration.activated_at = now

    _status_event(
        db, registration,
        note=(
            f"activation: customer id={customer.id} onboarding_status "
            f"{previous or 'null'} -> complete"
        ),
        actor_user_id=actor_user_id, actor_email=actor_email,
    )
    _audit(
        db,
        tenant_id=customer.tenant_id,
        actor_email=actor_email,
        action="customer_activated",
        target_type="customer",
        target_id=str(customer.id),
        summary=f"Customer {customer.name} marked onboarding_status=complete",
        detail={
            "registration_id": registration.registration_id,
            "previous_status": previous,
        },
    )
    logger.info(
        "Customer activated: customer=%s registration=%s previous=%s",
        customer.id, registration.registration_id, previous,
    )

    return CustomerOutcome(
        customer_id=customer.id,
        action="completed",
        previous_status=previous,
        new_status="complete",
    )


# ─────────────────────────────────────────────────────────────────────
# Read-only status
# ─────────────────────────────────────────────────────────────────────

@dataclass
class _InviteStatusResult:
    has_invite: bool
    user_id: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = False
    has_pending_invite: bool = False
    invite_expires_at: Optional[datetime] = None


async def get_invite_status(
    db: AsyncSession,
    registration: Registration,
) -> _InviteStatusResult:
    """Read-only: report whether the registration's submitter has
    portal access yet.

    Returns ``has_invite=False`` when no User row matches the
    (lowercased submitter_email, target_tenant_id) pair — either the
    registration hasn't reached ready_for_activation, or the convert
    step hasn't run.

    The plaintext invite token is deliberately omitted from the
    response.  Operators only see it once, at issuance time.
    """
    if not registration.target_tenant_id or not registration.submitter_email:
        return _InviteStatusResult(has_invite=False)

    email = registration.submitter_email.strip().lower()
    result = await db.execute(
        select(User).where(
            func.lower(User.email) == email,
            User.tenant_id == registration.target_tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        return _InviteStatusResult(has_invite=False)

    has_pending = (
        not user.is_active
        and user.invite_token is not None
        and user.invite_expires_at is not None
        and _is_future(user.invite_expires_at)
    )
    return _InviteStatusResult(
        has_invite=True,
        user_id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        has_pending_invite=has_pending,
        invite_expires_at=user.invite_expires_at,
    )


# ─────────────────────────────────────────────────────────────────────
# Dispatcher — called from registration_service.transition_status
# ─────────────────────────────────────────────────────────────────────

async def run_activation_hook(
    db: AsyncSession,
    registration: Registration,
    to_status: str,
    *,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
):
    """Run the side effect appropriate to the transition's target.

    Called from ``registration_service.transition_status`` after the
    registration's status has been mutated but before commit, so the
    helper's writes share the transition's single commit.  Any raised
    exception causes the calling code to roll back; the status change
    and the side-effect writes go together or not at all.
    """
    if to_status == Status.READY_FOR_ACTIVATION:
        return await issue_invite(
            db, registration,
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
    if to_status == Status.ACTIVE:
        return await mark_customer_complete(
            db, registration,
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
    return None


# ─────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────

def _is_future(when: datetime, now: Optional[datetime] = None) -> bool:
    """Compare a datetime against the current moment, treating naive
    timestamps as UTC.  Matches the convention used by
    ``registration_service.is_token_expired``.
    """
    if when is None:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when > now
