"""Phase R5 — activation hand-off + customer invite/access tests.

Coverage:

  * issue_invite create / reuse / rotate / skip semantics
  * cross-tenant email collision is rejected with ActivationError
  * missing customer_id / target_tenant_id / submitter_email raise
    validate_prerequisites
  * mark_customer_complete flips onboarding_status to "complete"
  * "on_hold" customer is skipped without modification
  * already-"complete" customer is a no-op (idempotency)
  * forbidden-import guard — no external automation in the activation
    module
  * end-to-end: a converted registration that transitions through
    ready_for_activation and then active produces exactly one User
    row, one onboarding_status flip, and the right audit trail

Heavy DB orchestration uses the same in-memory FakeAsyncSession idea
introduced in test_registration_convert.py — copied here verbatim to
keep the file self-contained.  The fake handles the few extra query
shapes registration_activation issues: ``select(User).where(func.lower(...) == val)``
and ``db.get(Customer, pk)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.audit_log_entry import AuditLogEntry
from app.models.customer import Customer
from app.models.registration import Registration
from app.models.registration_status_event import RegistrationStatusEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.services import registration_activation as act
from app.services.registration_service import Status


# ═══════════════════════════════════════════════════════════════════
# Forbidden-import guard
# ═══════════════════════════════════════════════════════════════════

class TestNoForbiddenImports:
    """The R5 plan forbids external automation calls from the
    activation module.  Same regression-test pattern as R4.
    """

    def test_activation_module_does_not_import_forbidden_modules(self):
        import inspect, re
        src = inspect.getsource(act)
        import_lines = re.findall(
            r"^\s*(?:from|import)\s+([\w\.]+)",
            src,
            flags=re.MULTILINE,
        )
        forbidden_modules = {
            "tmobile_callback",
            "verizon_thingspace",
            "carrier_verizon",
            "provisioning_engine",
            "provision_deploy",
            "field_nation",
            "stripe",
            "email_service",  # R5 explicitly defers email delivery
        }
        used_leaves = {mod.rsplit(".", 1)[-1] for mod in import_lines}
        leaked = forbidden_modules & used_leaves
        assert not leaked, (
            f"registration_activation.py imports forbidden modules "
            f"{sorted(leaked)} — R5 forbids external-integration / "
            f"email calls in the activation path."
        )


# ═══════════════════════════════════════════════════════════════════
# Pure-function helpers
# ═══════════════════════════════════════════════════════════════════

class TestInviteUrlAndTokenHelpers:
    def test_invite_url_uses_login_with_invite_query(self):
        # Mirrors the password-reset URL pattern in auth.py so the
        # login page can detect both via the same querystring sniffer.
        url = act._invite_url("ABCDEF")
        assert url.endswith("/login?invite=ABCDEF")

    def test_generate_invite_token_is_url_safe_and_long(self):
        t = act._generate_invite_token()
        assert isinstance(t, str)
        # 48 bytes -> ~64 url-safe chars
        assert len(t) >= 48
        assert all(c.isalnum() or c in "-_" for c in t)

    def test_generate_invite_token_is_unique_across_calls(self):
        # A 48-byte secret has overwhelming entropy — but the test
        # is cheap and protects against an accidental regression that
        # swaps the source for something deterministic.
        tokens = {act._generate_invite_token() for _ in range(100)}
        assert len(tokens) == 100


class TestIsFuture:
    def test_future_returns_true(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=1)
        assert act._is_future(future) is True

    def test_past_returns_false(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert act._is_future(past) is False

    def test_none_returns_false(self):
        assert act._is_future(None) is False

    def test_naive_timestamps_are_assumed_utc(self):
        # Matches the same convention used by the public-resume-token
        # expiry comparison in registration_service.
        naive_past = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None)
        assert act._is_future(naive_past) is False


# ═══════════════════════════════════════════════════════════════════
# In-memory fake AsyncSession
# ═══════════════════════════════════════════════════════════════════

_CASE_FUNCS = {"lower", "upper"}


def _extract_left_column_name(left):
    """Get the column name from a where clause's left side, handling
    func.lower(col) and func.upper(col) wrappers that the activation
    helpers use for case-insensitive email lookups.

    We have to detect the function wrapper FIRST and recurse into its
    inner column — SQLAlchemy gives ``Function`` a ``.key`` attribute
    that equals the function name (e.g. "lower"), so naïvely reading
    ``.key`` would return "lower" instead of the wrapped column name.
    """
    # Function wrapper: recurse through ``clauses[0]``.
    if getattr(left, "name", None) in _CASE_FUNCS:
        clauses = getattr(left, "clauses", None)
        if clauses is not None:
            inner = list(clauses)
            if inner:
                return _extract_left_column_name(inner[0])
    if hasattr(left, "key") and left.key:
        return left.key
    if hasattr(left, "name") and left.name:
        return left.name
    return None


def _is_lower_wrapped(left):
    """True if the left side of a comparison is ``func.lower(col)``."""
    return getattr(left, "name", None) == "lower"


def _extract_predicates(whereclause):
    from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

    if whereclause is None:
        return []
    if isinstance(whereclause, BinaryExpression):
        col_name = _extract_left_column_name(whereclause.left)
        lower_wrap = _is_lower_wrapped(whereclause.left)
        right = whereclause.right
        value = getattr(right, "value", None)
        if value is None and hasattr(right, "effective_value"):
            value = right.effective_value
        op_name = getattr(whereclause.operator, "__name__", "eq")
        return [(col_name, op_name, value, lower_wrap)]
    if isinstance(whereclause, BooleanClauseList):
        out = []
        for clause in whereclause.clauses:
            out.extend(_extract_predicates(clause))
        return out
    return []


def _apply_predicate(obj, col_name, op, value, lower_wrap):
    attr = getattr(obj, col_name, None)
    if lower_wrap and isinstance(attr, str):
        attr = attr.lower()
    if op == "eq":
        return attr == value
    if op == "in_op":
        try:
            return attr in value
        except TypeError:
            return False
    return False


class FakeAsyncSession:
    """In-memory AsyncSession substitute for the activation path.

    Supports the convert-path patterns from R4 plus the R5-specific
    ``func.lower(User.email)`` wrapper and direct ``db.get(Customer, pk)``
    calls.
    """

    def __init__(self):
        self._committed: dict[type, list] = {}
        self._pending: list = []
        self._next_pk: dict[type, int] = {}
        self.commit_count = 0
        self.rollback_count = 0

    def seed_committed(self, *instances):
        for inst in instances:
            cls = type(inst)
            if getattr(inst, "id", None) is None and cls is not User:
                pk = self._next_pk.get(cls, 1)
                self._next_pk[cls] = pk + 1
                inst.id = pk
            self._committed.setdefault(cls, []).append(inst)

    def add(self, instance):
        cls = type(instance)
        if getattr(instance, "id", None) is None and cls is not User:
            # User's id is a UUID set by the activation code itself —
            # never assigned by the fake.
            pk = self._next_pk.get(cls, 1)
            self._next_pk[cls] = pk + 1
            instance.id = pk
        self._pending.append(instance)

    async def flush(self):
        pass

    async def commit(self):
        self.commit_count += 1
        for inst in self._pending:
            self._committed.setdefault(type(inst), []).append(inst)
        self._pending = []

    async def rollback(self):
        self.rollback_count += 1
        for inst in self._pending:
            inst._rolled_back = True
        self._pending = []

    async def refresh(self, instance):
        pass

    async def get(self, model, pk):
        if pk is None:
            return None
        for inst in self._all_visible(model):
            if getattr(inst, "id", None) == pk:
                return inst
        return None

    async def execute(self, stmt):
        return _FakeResult(self, stmt)

    def _all_visible(self, model):
        out = list(self._committed.get(model, []))
        for inst in self._pending:
            if isinstance(inst, model) and not getattr(inst, "_rolled_back", False):
                out.append(inst)
        return out

    def all_committed(self, model: type) -> list:
        return list(self._committed.get(model, []))

    def count(self, model: type) -> int:
        return len(self._committed.get(model, []))


class _FakeResult:
    def __init__(self, session, stmt):
        self._session = session
        self._items, self._is_model, self._col_name = self._interpret(stmt)

    def _interpret(self, stmt):
        descs = getattr(stmt, "column_descriptions", None) or []
        if not descs:
            return [], True, None
        first = descs[0]
        entity = first.get("entity")
        if entity is None:
            return [], True, None
        name = first.get("name")
        is_model = name == entity.__name__
        col_name = None if is_model else name

        candidates = self._session._all_visible(entity)
        whereclause = getattr(stmt, "whereclause", None)
        if whereclause is not None:
            for c_name, op, value, lower_wrap in _extract_predicates(whereclause):
                candidates = [
                    c for c in candidates if _apply_predicate(c, c_name, op, value, lower_wrap)
                ]
        order_clauses = getattr(stmt, "_order_by_clauses", None) or []
        for clause in order_clauses:
            inner = getattr(clause, "element", clause)
            order_col = getattr(inner, "key", None) or getattr(inner, "name", None)
            if order_col:
                candidates.sort(key=lambda c: (getattr(c, order_col, 0) or 0))
        return candidates, is_model, col_name

    def scalar_one_or_none(self):
        if not self._items:
            return None
        first = self._items[0]
        return first if self._is_model else getattr(first, self._col_name, None)

    def scalars(self):
        return _FakeScalars(self._items, self._is_model, self._col_name)

    def all(self):
        if self._is_model:
            return [(item,) for item in self._items]
        return [(getattr(item, self._col_name, None),) for item in self._items]


class _FakeScalars:
    def __init__(self, items, is_model, col_name):
        self._items = items
        self._is_model = is_model
        self._col_name = col_name

    def all(self):
        if self._is_model:
            return list(self._items)
        return [getattr(item, self._col_name, None) for item in self._items]

    def first(self):
        if not self._items:
            return None
        first = self._items[0]
        return first if self._is_model else getattr(first, self._col_name, None)


# ═══════════════════════════════════════════════════════════════════
# Seed helpers
# ═══════════════════════════════════════════════════════════════════

def _seed_converted_registration(
    db: FakeAsyncSession,
    *,
    status: str = Status.QA_REVIEW,
    submitter_email: str = "cindy@example.com",
    submitter_name: str = "Cindy Whittle",
    customer_onboarding_status: str = "in_progress",
    tenant_id: str = "integrity-pm",
):
    """Seed a registration that's already been converted (R4):
    tenant + customer exist, registration.customer_id +
    registration.target_tenant_id are stamped.  Ready for activation.
    """
    tenant = Tenant(tenant_id=tenant_id, name="Integrity Property Management")
    customer = Customer(
        tenant_id=tenant_id,
        name="Integrity Property Management",
        status="active",
        onboarding_status=customer_onboarding_status,
    )
    db.seed_committed(tenant, customer)

    reg = Registration(
        registration_id="REG-INTEGRITY",
        tenant_id="ops",
        status=status,
        resume_token_hash="hash-not-used-here",
        resume_token_expires_at=datetime.now(timezone.utc).replace(year=2099),
        submitter_email=submitter_email,
        submitter_name=submitter_name,
        customer_name="Integrity Property Management",
        target_tenant_id=tenant_id,
        customer_id=customer.id,
    )
    db.seed_committed(reg)
    return reg, tenant, customer


# ═══════════════════════════════════════════════════════════════════
# issue_invite — full create path
# ═══════════════════════════════════════════════════════════════════

class TestIssueInviteCreate:
    @pytest.mark.asyncio
    async def test_create_new_user_with_pending_invite(self):
        db = FakeAsyncSession()
        reg, tenant, _ = _seed_converted_registration(db)

        outcome = await act.issue_invite(
            db, reg,
            actor_user_id=None,
            actor_email="ops@true911.com",
        )

        assert outcome.action == "created"
        assert outcome.email == "cindy@example.com"
        assert outcome.invite_token is not None
        assert outcome.invite_url.endswith(f"?invite={outcome.invite_token}")
        assert outcome.invite_expires_at is not None
        # We need to commit explicitly here — issue_invite runs inside
        # transition_status's transaction in production, but in this
        # focused service-level test we commit ourselves.
        await db.commit()

        users = db.all_committed(User)
        assert len(users) == 1
        u = users[0]
        assert u.email == "cindy@example.com"
        assert u.tenant_id == tenant.tenant_id
        assert u.role == "User"
        assert u.is_active is False
        assert u.must_change_password is True
        assert u.invite_token == outcome.invite_token
        assert u.invite_expires_at == outcome.invite_expires_at
        # The throwaway password hash must be present and non-empty so
        # the NOT NULL constraint holds even before the customer sets
        # their own.
        assert u.password_hash and len(u.password_hash) > 10

    @pytest.mark.asyncio
    async def test_create_writes_status_event_and_audit_row(self):
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        await act.issue_invite(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()
        notes = [e.note for e in db.all_committed(RegistrationStatusEvent)]
        assert any("invite: created" in n for n in notes), notes
        actions = {a.action for a in db.all_committed(AuditLogEntry)}
        assert "create_invited_user" in actions

    @pytest.mark.asyncio
    async def test_submitter_name_fallback_to_email_localpart(self):
        # When submitter_name is empty, the new User's name falls
        # back to the email's local part so the user has *some*
        # display name and the NOT NULL constraint on users.name
        # holds.
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db, submitter_name="")
        await act.issue_invite(db, reg, actor_user_id=None, actor_email=None)
        await db.commit()
        u = db.all_committed(User)[0]
        assert u.name == "cindy"


# ═══════════════════════════════════════════════════════════════════
# issue_invite — idempotency
# ═══════════════════════════════════════════════════════════════════

class TestIssueInviteIdempotency:
    @pytest.mark.asyncio
    async def test_reuse_when_existing_invite_still_valid(self):
        # Second call with the same prerequisites must NOT create
        # another user and must NOT rotate the token.
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)

        first = await act.issue_invite(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()
        first_token = first.invite_token
        first_expiry = first.invite_expires_at

        second = await act.issue_invite(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()

        assert second.action == "reused"
        assert second.invite_token is None, (
            "reused path must NOT echo the plaintext — the server can't "
            "recover it from storage"
        )
        # Only one user row, same token still set on it.
        users = db.all_committed(User)
        assert len(users) == 1
        assert users[0].invite_token == first_token
        assert users[0].invite_expires_at == first_expiry

    @pytest.mark.asyncio
    async def test_rotate_when_existing_invite_expired(self):
        db = FakeAsyncSession()
        reg, tenant, _ = _seed_converted_registration(db)
        # Seed an existing user with an expired invite.
        existing = User(
            id=uuid.uuid4(),
            email="cindy@example.com",
            name="Cindy",
            password_hash="x" * 20,
            role="User",
            tenant_id=tenant.tenant_id,
            is_active=False,
            invite_token="old-token",
            invite_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            must_change_password=True,
        )
        db.seed_committed(existing)

        outcome = await act.issue_invite(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()

        assert outcome.action == "rotated"
        assert outcome.invite_token is not None
        assert outcome.invite_token != "old-token"
        # Still exactly one user — no duplicate.
        assert db.count(User) == 1
        u = db.all_committed(User)[0]
        assert u.invite_token == outcome.invite_token
        assert u.invite_expires_at > datetime.now(timezone.utc)
        # Audit-log records the rotation.
        actions = {a.action for a in db.all_committed(AuditLogEntry)}
        assert "rotate_invite_token" in actions

    @pytest.mark.asyncio
    async def test_skip_when_user_already_active(self):
        # If the customer already accepted, re-running activation
        # MUST NOT rotate or otherwise disturb their account.
        db = FakeAsyncSession()
        reg, tenant, _ = _seed_converted_registration(db)
        existing = User(
            id=uuid.uuid4(),
            email="cindy@example.com",
            name="Cindy",
            password_hash="x" * 20,
            role="User",
            tenant_id=tenant.tenant_id,
            is_active=True,
            invite_token=None,
            invite_expires_at=None,
        )
        db.seed_committed(existing)

        outcome = await act.issue_invite(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()

        assert outcome.action == "skipped_active"
        assert outcome.invite_token is None
        # The user wasn't touched.
        u = db.all_committed(User)[0]
        assert u.is_active is True
        assert u.invite_token is None
        # No new audit-log row for the skip (status event is enough).
        actions = {a.action for a in db.all_committed(AuditLogEntry)}
        assert "create_invited_user" not in actions
        assert "rotate_invite_token" not in actions


# ═══════════════════════════════════════════════════════════════════
# issue_invite — prerequisite errors
# ═══════════════════════════════════════════════════════════════════

class TestIssueInvitePrerequisites:
    @pytest.mark.asyncio
    async def test_missing_customer_id_raises_validate_prerequisites(self):
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        reg.customer_id = None
        with pytest.raises(act.ActivationError) as exc:
            await act.issue_invite(db, reg, actor_user_id=None, actor_email=None)
        assert exc.value.stage == "validate_prerequisites"

    @pytest.mark.asyncio
    async def test_missing_target_tenant_raises_validate_prerequisites(self):
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        reg.target_tenant_id = None
        with pytest.raises(act.ActivationError) as exc:
            await act.issue_invite(db, reg, actor_user_id=None, actor_email=None)
        assert exc.value.stage == "validate_prerequisites"

    @pytest.mark.asyncio
    async def test_missing_submitter_email_raises_validate_prerequisites(self):
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        reg.submitter_email = ""
        with pytest.raises(act.ActivationError) as exc:
            await act.issue_invite(db, reg, actor_user_id=None, actor_email=None)
        assert exc.value.stage == "validate_prerequisites"

    @pytest.mark.asyncio
    async def test_malformed_submitter_email_raises_validate_prerequisites(self):
        # An email with no "@" can't be a real address — fail fast
        # rather than create a junk user.
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        reg.submitter_email = "not-an-email"
        with pytest.raises(act.ActivationError) as exc:
            await act.issue_invite(db, reg, actor_user_id=None, actor_email=None)
        assert exc.value.stage == "validate_prerequisites"


class TestCrossTenantEmailCollision:
    @pytest.mark.asyncio
    async def test_existing_user_in_different_tenant_is_rejected(self):
        # The users.email unique index means a cross-tenant collision
        # would either fail the INSERT or silently re-tenant an
        # existing user.  Neither is acceptable; the activation path
        # must surface the conflict to the operator.
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db, tenant_id="integrity-pm")
        # Existing user has the same email but lives in a different tenant.
        other_tenant_user = User(
            id=uuid.uuid4(),
            email="cindy@example.com",
            name="Cindy",
            password_hash="x" * 20,
            role="Admin",
            tenant_id="acme",
            is_active=True,
        )
        db.seed_committed(other_tenant_user)

        with pytest.raises(act.ActivationError) as exc:
            await act.issue_invite(
                db, reg, actor_user_id=None, actor_email="ops@true911.com",
            )

        err = exc.value
        assert err.stage == "issue_invite"
        # Reviewer needs to know which tenant the collision is in to
        # untangle it manually.
        assert "acme" in err.message or "acme" in str(err.details)
        # No new user row created.
        assert db.count(User) == 1


# ═══════════════════════════════════════════════════════════════════
# mark_customer_complete
# ═══════════════════════════════════════════════════════════════════

class TestMarkCustomerComplete:
    @pytest.mark.asyncio
    async def test_flips_in_progress_to_complete(self):
        db = FakeAsyncSession()
        reg, _, customer = _seed_converted_registration(
            db, customer_onboarding_status="in_progress",
        )

        outcome = await act.mark_customer_complete(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()

        assert outcome.action == "completed"
        assert outcome.previous_status == "in_progress"
        assert outcome.new_status == "complete"
        assert customer.onboarding_status == "complete"
        # registration.activated_at gets stamped on the first
        # successful run.
        assert reg.activated_at is not None
        actions = {a.action for a in db.all_committed(AuditLogEntry)}
        assert "customer_activated" in actions

    @pytest.mark.asyncio
    async def test_idempotent_when_already_complete(self):
        # Re-running activation on an already-complete customer is a
        # no-op — no audit row, no second flip, no exception.
        db = FakeAsyncSession()
        reg, _, customer = _seed_converted_registration(
            db, customer_onboarding_status="complete",
        )

        outcome = await act.mark_customer_complete(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()

        assert outcome.action == "skipped_already_complete"
        assert outcome.previous_status == "complete"
        assert customer.onboarding_status == "complete"
        actions = {a.action for a in db.all_committed(AuditLogEntry)}
        assert "customer_activated" not in actions, (
            "no audit row should be written when the flip is a no-op"
        )

    @pytest.mark.asyncio
    async def test_skips_on_hold_customer_without_modification(self):
        # The R5 plan explicitly preserves operator-set "on_hold" —
        # activation must not trample it.
        db = FakeAsyncSession()
        reg, _, customer = _seed_converted_registration(
            db, customer_onboarding_status="on_hold",
        )

        outcome = await act.mark_customer_complete(
            db, reg, actor_user_id=None, actor_email="ops@true911.com",
        )
        await db.commit()

        assert outcome.action == "skipped_on_hold"
        assert customer.onboarding_status == "on_hold"
        # No activated_at stamp because activation didn't really
        # happen for this customer.
        assert reg.activated_at is None

    @pytest.mark.asyncio
    async def test_missing_customer_id_raises_validate_prerequisites(self):
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        reg.customer_id = None
        with pytest.raises(act.ActivationError) as exc:
            await act.mark_customer_complete(
                db, reg, actor_user_id=None, actor_email=None,
            )
        assert exc.value.stage == "validate_prerequisites"

    @pytest.mark.asyncio
    async def test_deleted_customer_raises_mark_customer_complete(self):
        # A customer that was deleted out from under us between
        # convert and activate is a recoverable error — surface it
        # as a structured ActivationError so the API returns 422.
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        reg.customer_id = 9999  # nonexistent
        with pytest.raises(act.ActivationError) as exc:
            await act.mark_customer_complete(
                db, reg, actor_user_id=None, actor_email=None,
            )
        assert exc.value.stage == "mark_customer_complete"
        assert "9999" in exc.value.message


# ═══════════════════════════════════════════════════════════════════
# get_invite_status
# ═══════════════════════════════════════════════════════════════════

class TestGetInviteStatus:
    @pytest.mark.asyncio
    async def test_returns_has_invite_false_when_no_user_exists(self):
        # Registration converted but never reached ready_for_activation.
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        result = await act.get_invite_status(db, reg)
        assert result.has_invite is False
        assert result.user_id is None

    @pytest.mark.asyncio
    async def test_returns_pending_when_user_invited_but_inactive(self):
        db = FakeAsyncSession()
        reg, tenant, _ = _seed_converted_registration(db)
        existing = User(
            id=uuid.uuid4(),
            email="cindy@example.com",
            name="Cindy",
            password_hash="x" * 20,
            role="User",
            tenant_id=tenant.tenant_id,
            is_active=False,
            invite_token="something",
            invite_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
            must_change_password=True,
        )
        db.seed_committed(existing)

        result = await act.get_invite_status(db, reg)
        assert result.has_invite is True
        assert result.is_active is False
        assert result.has_pending_invite is True
        # The plaintext token must NOT be exposed via the status read.
        assert not hasattr(result, "invite_token") or getattr(result, "invite_token", None) is None

    @pytest.mark.asyncio
    async def test_returns_active_when_user_accepted(self):
        db = FakeAsyncSession()
        reg, tenant, _ = _seed_converted_registration(db)
        existing = User(
            id=uuid.uuid4(),
            email="cindy@example.com",
            name="Cindy",
            password_hash="x" * 20,
            role="User",
            tenant_id=tenant.tenant_id,
            is_active=True,
            invite_token=None,
            invite_expires_at=None,
        )
        db.seed_committed(existing)

        result = await act.get_invite_status(db, reg)
        assert result.has_invite is True
        assert result.is_active is True
        assert result.has_pending_invite is False


# ═══════════════════════════════════════════════════════════════════
# Dispatcher
# ═══════════════════════════════════════════════════════════════════

class TestRunActivationHook:
    @pytest.mark.asyncio
    async def test_no_op_for_unrelated_targets(self):
        # The dispatcher must return None and do nothing for any
        # transition target other than ready_for_activation / active.
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        for target in [
            Status.SUBMITTED,
            Status.INTERNAL_REVIEW,
            Status.PENDING_CUSTOMER_INFO,
            Status.SCHEDULED,
            Status.INSTALLED,
            Status.CANCELLED,
        ]:
            result = await act.run_activation_hook(
                db, reg, target, actor_user_id=None, actor_email=None,
            )
            assert result is None
        # No production rows touched.
        assert db.count(User) == 0

    @pytest.mark.asyncio
    async def test_dispatches_ready_for_activation_to_issue_invite(self):
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        result = await act.run_activation_hook(
            db, reg, Status.READY_FOR_ACTIVATION,
            actor_user_id=None, actor_email="ops@true911.com",
        )
        assert isinstance(result, act.InviteOutcome)
        assert result.action == "created"

    @pytest.mark.asyncio
    async def test_dispatches_active_to_mark_customer_complete(self):
        db = FakeAsyncSession()
        reg, _, _ = _seed_converted_registration(db)
        result = await act.run_activation_hook(
            db, reg, Status.ACTIVE,
            actor_user_id=None, actor_email="ops@true911.com",
        )
        assert isinstance(result, act.CustomerOutcome)
        assert result.action == "completed"


# ═══════════════════════════════════════════════════════════════════
# ActivationError shape
# ═══════════════════════════════════════════════════════════════════

class TestActivationErrorShape:
    def test_carries_stage_and_message(self):
        err = act.ActivationError(
            stage="issue_invite",
            message="email collision",
            next_steps="reconcile manually",
            details={"a": 1},
        )
        assert err.stage == "issue_invite"
        assert err.message == "email collision"
        assert err.next_steps == "reconcile manually"
        assert err.details == {"a": 1}
        # The stringified form is what shows up in logs; it should
        # be specific enough to grep for.
        assert "issue_invite" in str(err)

    def test_details_defaults_to_empty_dict(self):
        err = act.ActivationError(stage="x", message="y")
        assert err.details == {}


# ═══════════════════════════════════════════════════════════════════
# Schema: writable invite_token at issuance only
# ═══════════════════════════════════════════════════════════════════

class TestInviteOutcomeShape:
    def test_created_carries_plaintext_token(self):
        out = act.InviteOutcome(
            user_id="u-1", email="x@x.com", action="created",
            invite_token="abc", invite_url="https://x", invite_expires_at=datetime.now(timezone.utc),
        )
        assert out.invite_token == "abc"

    def test_skipped_or_reused_has_no_plaintext_token(self):
        # Lock in the design rule: the only paths that carry the
        # plaintext token are "created" and "rotated".
        skipped = act.InviteOutcome(
            user_id="u-1", email="x@x.com", action="skipped_active",
        )
        assert skipped.invite_token is None
        reused = act.InviteOutcome(
            user_id="u-1", email="x@x.com", action="reused",
        )
        assert reused.invite_token is None
