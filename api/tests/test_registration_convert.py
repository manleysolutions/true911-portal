"""Phase R4 — registration → production conversion tests.

The conversion path is the only code in the codebase that materialises
staging rows into production tables.  These tests cover:

  * the request-schema validation that gates the endpoint
  * the convertable-state allow-list
  * id-generation helpers (slugify, next_available_site_id, _unit_id)
  * the subscription-skip rule (no plan code -> no subscription)

DB-touching paths (resolve_tenant, materialize_sites, etc.) are not
exercised here because the project does not stand up an in-memory
test database — every existing async-DB test mocks AsyncSession the
same way.  We follow that pattern: pure functions and the schema
layer get full coverage; orchestration is covered by an integration
test against the real Postgres before launch.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from app.schemas.registration import RegistrationConvertRequest
from app.services import registration_conversion as conv
from app.services.registration_service import Status


# ─────────────────────────────────────────────────────────────────────
# Request schema validation
# ─────────────────────────────────────────────────────────────────────

def _ok_body(**overrides) -> dict:
    body = {
        "tenant_choice": "create_new",
        "new_tenant_id": "acme",
        "new_tenant_name": "Acme Corp",
        "customer_choice": "create_new",
        "create_subscription": False,
        "dry_run": False,
        "confirm": True,
    }
    body.update(overrides)
    return body


class TestConvertRequestSchema:
    def test_minimum_body_validates(self):
        RegistrationConvertRequest.model_validate(_ok_body())

    def test_rejects_invalid_tenant_choice(self):
        with pytest.raises(ValidationError):
            RegistrationConvertRequest.model_validate(_ok_body(tenant_choice="unsure"))

    def test_attach_existing_requires_existing_tenant_id(self):
        # Switching to attach_existing without supplying existing_tenant_id
        # is a malformed request that the server can reject in schema layer
        # rather than letting it through to the service.
        with pytest.raises(ValidationError):
            RegistrationConvertRequest.model_validate(_ok_body(
                tenant_choice="attach_existing",
                new_tenant_id=None,
                new_tenant_name=None,
            ))

    def test_attach_existing_with_tenant_id_validates(self):
        RegistrationConvertRequest.model_validate(_ok_body(
            tenant_choice="attach_existing",
            existing_tenant_id="acme",
            new_tenant_id=None,
            new_tenant_name=None,
        ))

    def test_create_new_requires_slug_and_name(self):
        with pytest.raises(ValidationError):
            RegistrationConvertRequest.model_validate(_ok_body(new_tenant_id=None))
        with pytest.raises(ValidationError):
            RegistrationConvertRequest.model_validate(_ok_body(new_tenant_name=None))

    def test_customer_attach_existing_requires_id(self):
        with pytest.raises(ValidationError):
            RegistrationConvertRequest.model_validate(_ok_body(
                customer_choice="attach_existing",
            ))

    def test_real_run_requires_confirm(self):
        # A fat-finger Convert click without confirm=true must fail
        # schema validation so the service never runs.
        with pytest.raises(ValidationError) as exc:
            RegistrationConvertRequest.model_validate(_ok_body(confirm=False))
        assert "confirm must be true" in str(exc.value)

    def test_dry_run_does_not_require_confirm(self):
        # Dry runs are read-only — confirm is unnecessary.
        RegistrationConvertRequest.model_validate(_ok_body(dry_run=True, confirm=False))

    def test_invalid_customer_choice_rejected(self):
        with pytest.raises(ValidationError):
            RegistrationConvertRequest.model_validate(_ok_body(customer_choice="maybe"))


# ─────────────────────────────────────────────────────────────────────
# Convertable-state allow-list
# ─────────────────────────────────────────────────────────────────────

class TestIsConvertable:
    @pytest.mark.parametrize("state", [
        Status.INTERNAL_REVIEW,
        Status.PENDING_CUSTOMER_INFO,
        Status.PENDING_EQUIPMENT_ASSIGNMENT,
        Status.PENDING_SIM_ASSIGNMENT,
        Status.PENDING_INSTALLER_SCHEDULE,
        Status.SCHEDULED,
        Status.INSTALLED,
        Status.QA_REVIEW,
        Status.READY_FOR_ACTIVATION,
        Status.SUBMITTED,
    ])
    def test_convertable_states(self, state):
        reg = SimpleNamespace(status=state)
        assert conv.is_convertable(reg) is True, f"{state} should be convertable"

    @pytest.mark.parametrize("state", [Status.DRAFT, Status.CANCELLED, Status.ACTIVE])
    def test_non_convertable_states(self, state):
        reg = SimpleNamespace(status=state)
        assert conv.is_convertable(reg) is False, f"{state} must be rejected"

    def test_pending_customer_info_is_allowed_per_plan(self):
        # The R4 plan explicitly calls out: do not block conversion just
        # because we're waiting on the customer for clarification.  Lock
        # this expectation in so a future tightening doesn't silently
        # regress it.
        reg = SimpleNamespace(status=Status.PENDING_CUSTOMER_INFO)
        assert conv.is_convertable(reg) is True


# ─────────────────────────────────────────────────────────────────────
# id slug helpers
# ─────────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_uppercase_and_dash_separated(self):
        assert conv._slugify("Tiffany Gardens East") == "TIFFANY-GARDENS-EAST"

    def test_collapses_runs_of_punctuation(self):
        assert conv._slugify("North  --  Tower!!") == "NORTH-TOWER"

    def test_strips_leading_and_trailing_dashes(self):
        assert conv._slugify("---name---") == "NAME"

    def test_falls_back_to_LOC_on_empty_or_junk(self):
        # Slugify must never return "" — the caller uses the slug as
        # the first portion of a site_id and an empty string would
        # produce "-2", "-3" etc. with no human-readable prefix.
        assert conv._slugify("") == "LOC"
        assert conv._slugify("!!!") == "LOC"
        assert conv._slugify(None) == "LOC"

    def test_numbers_preserved(self):
        assert conv._slugify("Building 2 East") == "BUILDING-2-EAST"


class TestUnitId:
    def test_zero_pads_sequence_to_two_digits(self):
        # Matches the existing SiteOnboarding.jsx convention so a
        # human reading the rows can't tell which came from the
        # operator wizard vs. the registration wizard.
        assert conv._unit_id("SITE-A", 1) == "SITE-A-U01"
        assert conv._unit_id("SITE-A", 9) == "SITE-A-U09"

    def test_three_digit_sequences_still_unique(self):
        # 100+ units per site is unusual but the format should not
        # collide once we cross 99.
        assert conv._unit_id("SITE-A", 99) == "SITE-A-U99"
        assert conv._unit_id("SITE-A", 100) == "SITE-A-U100"


class TestSubscriptionExternalId:
    def test_uses_registration_public_id(self):
        # The "reg:" prefix is the lookup key the convert helper uses
        # to make subscription creation idempotent across retries.
        reg = SimpleNamespace(registration_id="REG-ABC123")
        assert conv._subscription_external_id(reg) == "reg:REG-ABC123"


# ─────────────────────────────────────────────────────────────────────
# ConversionError shape
# ─────────────────────────────────────────────────────────────────────

class TestConversionError:
    def test_carries_stage_and_message(self):
        err = conv.ConversionError(
            stage="resolve_tenant",
            message="tenant 'acme' does not exist",
            next_steps="Create it first.",
            details={"existing_tenant_id": "acme"},
        )
        assert err.stage == "resolve_tenant"
        assert err.message == "tenant 'acme' does not exist"
        assert err.next_steps == "Create it first."
        assert err.details == {"existing_tenant_id": "acme"}

    def test_details_defaults_to_empty_dict(self):
        # The API layer json-serializes details; a None value would
        # produce {"details": null} which is uglier than {"details": {}}.
        err = conv.ConversionError(stage="x", message="y")
        assert err.details == {}

    def test_str_includes_stage_and_message(self):
        # The exception's repr shows up in logs — verify it's useful
        # for grepping a failure.
        err = conv.ConversionError(stage="create_site", message="bad slug")
        assert "create_site" in str(err)
        assert "bad slug" in str(err)


# ─────────────────────────────────────────────────────────────────────
# Forbidden imports — guard the "no external automation" rule
# ─────────────────────────────────────────────────────────────────────

class TestNoForbiddenImports:
    """The R4 design forbids the conversion service from calling any
    external integration (T-Mobile, Field Nation, billing, E911
    carrier, provisioning).  Encode that as a test so a regression
    that imports those modules from the conversion path fails CI.
    """

    def test_conversion_module_does_not_import_forbidden_modules(self):
        # Scan only real ``import X`` and ``from X import …`` lines.
        # A bare keyword in the docstring (e.g. "no billing-side
        # calls") shouldn't trip the guard — only actual imports do.
        import inspect, re
        src = inspect.getsource(conv)
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
        }
        # Match by leaf module name so "app.services.provision_deploy"
        # is caught the same as "provision_deploy".
        used_leaves = {mod.rsplit(".", 1)[-1] for mod in import_lines}
        leaked = forbidden_modules & used_leaves
        assert not leaked, (
            f"registration_conversion.py imports forbidden modules "
            f"{sorted(leaked)} — Phase R4 forbids external-integration "
            f"calls in the convert path."
        )


# ═══════════════════════════════════════════════════════════════════
# Integration-style coverage (in-memory fake AsyncSession)
# ═══════════════════════════════════════════════════════════════════
#
# The project has no Postgres test fixture and no aiosqlite dep, so
# this test drives the real convert_registration function through a
# hand-rolled in-memory AsyncSession substitute.  The fake handles
# only the SELECT shapes convert_registration actually issues — it
# is not a general SQL engine.  See FakeAsyncSession below for the
# query patterns covered.
#
# What this catches that the pure-function tests above cannot:
#   - Row-count expectations across multiple model classes
#   - materialized_*_id stamps on staging rows
#   - registration.customer_id / target_tenant_id stamps
#   - Phase 3a invariant: Sites carry non-null customer_id
#   - Idempotency: re-running convert with the same body is a no-op


from app.models.audit_log_entry import AuditLogEntry
from app.models.customer import Customer
from app.models.registration import Registration
from app.models.registration_location import RegistrationLocation
from app.models.registration_service_unit import RegistrationServiceUnit
from app.models.registration_status_event import RegistrationStatusEvent
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.subscription import Subscription
from app.models.tenant import Tenant


# ── Query interpreter helpers ───────────────────────────────────────

def _extract_predicates(whereclause):
    """Walk an SQLAlchemy where clause into [(col_name, op_name, value)] tuples.

    Handles BinaryExpression and BooleanClauseList (AND), which together
    cover every where clause convert_registration emits.
    """
    from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

    if whereclause is None:
        return []
    if isinstance(whereclause, BinaryExpression):
        col_name = getattr(whereclause.left, "key", None) or getattr(
            whereclause.left, "name", None
        )
        right = whereclause.right
        # Right side is normally a BindParameter wrapping a Python literal.
        value = getattr(right, "value", None)
        if value is None and hasattr(right, "effective_value"):
            value = right.effective_value
        op_name = getattr(whereclause.operator, "__name__", "eq")
        return [(col_name, op_name, value)]
    if isinstance(whereclause, BooleanClauseList):
        out = []
        for clause in whereclause.clauses:
            out.extend(_extract_predicates(clause))
        return out
    return []


def _apply_predicate(obj, col_name, op, value):
    attr = getattr(obj, col_name, None)
    if op == "eq":
        return attr == value
    if op == "in_op":
        try:
            return attr in value
        except TypeError:
            return False
    return False


# ── FakeAsyncSession ────────────────────────────────────────────────

class FakeAsyncSession:
    """Minimal AsyncSession substitute for the convert path.

    Tracks add/flush/commit/rollback transactional semantics, hands out
    auto-incrementing integer PKs eagerly on ``add()``, and interprets
    the limited set of SELECT shapes convert_registration uses.
    """

    def __init__(self):
        # Committed rows, keyed by model class.
        self._committed: dict[type, list] = {}
        # Rows added but not yet committed.
        self._pending: list = []
        # PK generator, keyed by model class.
        self._next_pk: dict[type, int] = {}
        self.commit_count = 0
        self.rollback_count = 0

    # ── Public seed helper (test setup) ────────────────────────────
    def seed_committed(self, *instances):
        """Insert objects directly into the committed pool, bypassing
        the pending step.  Used to set up a registration + locations +
        service units before exercising convert.
        """
        for inst in instances:
            cls = type(inst)
            if getattr(inst, "id", None) is None:
                pk = self._next_pk.get(cls, 1)
                self._next_pk[cls] = pk + 1
                inst.id = pk
            self._committed.setdefault(cls, []).append(inst)

    # ── AsyncSession surface ───────────────────────────────────────
    def add(self, instance):
        cls = type(instance)
        if getattr(instance, "id", None) is None:
            pk = self._next_pk.get(cls, 1)
            self._next_pk[cls] = pk + 1
            instance.id = pk
        self._pending.append(instance)

    async def flush(self):
        # PKs are assigned eagerly in add().  Real SQLAlchemy would
        # round-trip to the DB here, but the convert code only uses
        # flush to materialize PKs — which we've already done.
        pass

    async def commit(self):
        self.commit_count += 1
        for inst in self._pending:
            cls = type(inst)
            self._committed.setdefault(cls, []).append(inst)
        self._pending = []

    async def rollback(self):
        self.rollback_count += 1
        for inst in self._pending:
            inst._rolled_back = True
        self._pending = []

    async def refresh(self, instance):
        # No-op: in real SQLAlchemy this reloads from the DB which
        # would revert in-memory mutations on a rollback.  The convert
        # path's real-run case does not rely on this, so we skip it.
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

    # ── Test helpers ───────────────────────────────────────────────
    def all_committed(self, model: type) -> list:
        """Snapshot of committed rows for an assertion."""
        return list(self._committed.get(model, []))

    def count(self, model: type) -> int:
        return len(self._committed.get(model, []))

    def _all_visible(self, model: type) -> list:
        out = list(self._committed.get(model, []))
        for inst in self._pending:
            if isinstance(inst, model) and not getattr(inst, "_rolled_back", False):
                out.append(inst)
        return out


class _FakeResult:
    def __init__(self, session: FakeAsyncSession, stmt):
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

        # If the descriptor's name matches the model class name, this
        # was a ``select(Model)``.  Otherwise it was ``select(Model.col)``.
        name = first.get("name")
        is_model = name == entity.__name__
        col_name = None if is_model else name

        candidates = self._session._all_visible(entity)

        whereclause = getattr(stmt, "whereclause", None)
        if whereclause is not None:
            for c_name, op, value in _extract_predicates(whereclause):
                candidates = [c for c in candidates if _apply_predicate(c, c_name, op, value)]

        # Ordering — convert uses ``ORDER BY <col> ASC`` only.
        order_clauses = getattr(stmt, "_order_by_clauses", None) or []
        for clause in order_clauses:
            # ASC wraps the column in a UnaryExpression; the inner
            # element exposes .key.  We default to ASC because that's
            # all the convert path uses.
            inner = getattr(clause, "element", clause)
            order_col = getattr(inner, "key", None) or getattr(inner, "name", None)
            if order_col:
                candidates.sort(key=lambda c: (getattr(c, order_col, 0) or 0))

        return candidates, is_model, col_name

    def scalar_one_or_none(self):
        if not self._items:
            return None
        first = self._items[0]
        if self._is_model:
            return first
        return getattr(first, self._col_name, None)

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


# ── Sample-data builder ─────────────────────────────────────────────

def _build_integrity_property_management(db: FakeAsyncSession) -> Registration:
    """Seed the Integrity Property Management scenario.

    Returns a Registration in ``internal_review`` with two locations
    and four service units, mirroring the sample pathway documented
    in the Phase R4 plan.
    """
    reg = Registration(
        registration_id="REG-INTEGRITY",
        tenant_id="ops",
        status="internal_review",
        resume_token_hash="hash-not-used-here",
        resume_token_expires_at=datetime.now(timezone.utc).replace(year=2099),
        submitter_email="cindy@example.com",
        submitter_name="Cindy Whittle",
        submitter_phone="954-346-0677",
        customer_name="Integrity Property Management",
        poc_name="Cindy Whittle",
        poc_phone="954-346-0677",
        selected_plan_code="monitoring_e911",
        plan_quantity_estimate=4,
    )
    db.seed_committed(reg)

    east = RegistrationLocation(
        registration_id=reg.id,
        location_label="Tiffany Gardens East",
        street="100 East Tower Lane",
        city="Tampa",
        state="FL",
        zip="33601",
        country="US",
    )
    north = RegistrationLocation(
        registration_id=reg.id,
        location_label="Tiffany Gardens North",
        street="200 North Tower Way",
        city="Tampa",
        state="FL",
        zip="33602",
        country="US",
    )
    db.seed_committed(east, north)

    units = [
        RegistrationServiceUnit(
            registration_id=reg.id,
            registration_location_id=east.id,
            unit_label="TGE1",
            unit_type="elevator_phone",
            phone_number_existing="9543129018",
            hardware_model_request="MS130v4",
            carrier_request="T-Mobile",
            quantity=1,
        ),
        RegistrationServiceUnit(
            registration_id=reg.id,
            registration_location_id=east.id,
            unit_label="TGE2",
            unit_type="elevator_phone",
            phone_number_existing="9543521164",
            hardware_model_request="MS130v4",
            carrier_request="T-Mobile",
            quantity=1,
        ),
        RegistrationServiceUnit(
            registration_id=reg.id,
            registration_location_id=north.id,
            unit_label="TGN1",
            unit_type="elevator_phone",
            phone_number_existing="9542349975",
            hardware_model_request="MS130v4",
            carrier_request="T-Mobile",
            quantity=1,
        ),
        RegistrationServiceUnit(
            registration_id=reg.id,
            registration_location_id=north.id,
            unit_label="TGN2",
            unit_type="elevator_phone",
            phone_number_existing="9543521634",
            hardware_model_request="MS130v4",
            carrier_request="T-Mobile",
            quantity=1,
        ),
    ]
    db.seed_committed(*units)
    return reg


# ── Datetime import for the sample builder ──────────────────────────

from datetime import datetime, timezone  # noqa: E402  (used by sample builder)


# ── Integration test ────────────────────────────────────────────────

class TestConvertIntegrityPropertyManagement:
    """End-to-end exercise of convert_registration using the
    Integrity Property Management sample submission.
    """

    @pytest.mark.asyncio
    async def test_full_path_creates_expected_rows_and_stamps(self):
        db = FakeAsyncSession()
        reg = _build_integrity_property_management(db)

        result = await conv.convert_registration(
            db, reg,
            tenant_choice="create_new",
            existing_tenant_id=None,
            new_tenant_id="integrity-property-management",
            new_tenant_name="Integrity Property Management",
            customer_choice="create_new",
            existing_customer_id=None,
            create_subscription=True,
            dry_run=False,
            actor_user_id=None,
            actor_email="ops@true911.com",
        )

        # ── Row counts ────────────────────────────────────────────
        assert db.count(Tenant) == 1, "exactly one tenant created"
        assert db.count(Customer) == 1, "exactly one customer created"
        assert db.count(Site) == 2, "one site per registration_location"
        assert db.count(ServiceUnit) == 4, "one service unit per registration_service_unit"
        assert db.count(Subscription) == 1, "subscription created when plan code is present"

        # ── Tenant + Customer wiring ──────────────────────────────
        tenant = db.all_committed(Tenant)[0]
        customer = db.all_committed(Customer)[0]
        assert tenant.tenant_id == "integrity-property-management"
        assert tenant.name == "Integrity Property Management"
        assert customer.tenant_id == tenant.tenant_id
        assert customer.name == "Integrity Property Management"
        assert customer.onboarding_status == "in_progress"

        # ── Phase 3a invariant: every Site carries customer_id ────
        sites = db.all_committed(Site)
        for s in sites:
            assert s.customer_id == customer.id, \
                f"Site {s.site_id} missing customer_id linkage"
            assert s.tenant_id == tenant.tenant_id
            assert s.customer_name == customer.name

        # ── Site labels and slug shape ────────────────────────────
        site_ids = sorted(s.site_id for s in sites)
        assert site_ids == ["TIFFANY-GARDENS-EAST", "TIFFANY-GARDENS-NORTH"], (
            f"unexpected site slugs: {site_ids}"
        )

        # ── Service units linked to the right sites ───────────────
        units = db.all_committed(ServiceUnit)
        east_units = [u for u in units if u.site_id == "TIFFANY-GARDENS-EAST"]
        north_units = [u for u in units if u.site_id == "TIFFANY-GARDENS-NORTH"]
        assert len(east_units) == 2
        assert len(north_units) == 2
        # Auto-generated unit ids follow the SITE-XX-UNN convention.
        east_unit_ids = sorted(u.unit_id for u in east_units)
        assert east_unit_ids == ["TIFFANY-GARDENS-EAST-U01", "TIFFANY-GARDENS-EAST-U02"]
        for u in units:
            assert u.status == "pending_install", \
                "service units should land as pending_install, not active"

        # ── Subscription wiring ──────────────────────────────────
        sub = db.all_committed(Subscription)[0]
        assert sub.tenant_id == tenant.tenant_id
        assert sub.customer_id == customer.id
        assert sub.plan_name == "monitoring_e911"
        assert sub.status == "pending"
        assert sub.qty_lines == 4
        assert sub.external_subscription_id == "reg:REG-INTEGRITY"
        assert sub.external_source == "registration"

        # ── Materialized stamps on staging rows ───────────────────
        # All Registration / RegistrationLocation / RegistrationServiceUnit
        # rows were seeded into the committed pool, so reading them
        # back through the session's committed map is the same as
        # what a real subsequent SELECT would return.
        assert reg.target_tenant_id == tenant.tenant_id
        assert reg.customer_id == customer.id
        assert reg.approved_at is not None
        assert reg.status == "internal_review", \
            "convert must not transition the registration's workflow status"

        locations = db.all_committed(RegistrationLocation)
        assert len(locations) == 2
        for loc in locations:
            assert loc.materialized_site_id is not None, \
                f"location {loc.location_label} did not get its materialized_site_id stamped"
            # The stamp must point at a real Site.
            assert any(s.id == loc.materialized_site_id for s in sites), \
                f"location {loc.location_label} stamp points at a missing Site"

        reg_units = db.all_committed(RegistrationServiceUnit)
        assert len(reg_units) == 4
        for ru in reg_units:
            assert ru.materialized_service_unit_id is not None, \
                f"unit {ru.unit_label} did not get its materialized_service_unit_id stamped"
            assert any(u.id == ru.materialized_service_unit_id for u in units), \
                f"unit {ru.unit_label} stamp points at a missing ServiceUnit"

        # ── Result payload sanity ─────────────────────────────────
        assert result.dry_run is False
        assert result.tenant.was_created is True
        assert result.customer.was_created is True
        assert all(s.was_created for s in result.sites)
        assert all(u.was_created for u in result.service_units)
        assert result.subscription is not None
        assert result.subscription.was_created is True

        # ── Audit + timeline rows landed ─────────────────────────
        # Six status events fire on a successful real run:
        # tenant resolved, customer resolved, sites, units,
        # subscription, complete.
        status_events = db.all_committed(RegistrationStatusEvent)
        notes = [e.note for e in status_events]
        assert any("tenant resolved" in n for n in notes)
        assert any("customer resolved" in n for n in notes)
        assert any("site(s)" in n for n in notes)
        assert any("service unit(s)" in n for n in notes)
        assert any("subscription" in n for n in notes)
        assert any("convert: complete" in n for n in notes)
        # Audit log: one summary row + one per created production row.
        audits = db.all_committed(AuditLogEntry)
        actions = {a.action for a in audits}
        assert "convert_registration" in actions
        assert "create_tenant" in actions
        assert "create_customer" in actions
        assert "create_site" in actions
        assert "create_service_unit" in actions
        assert "create_subscription" in actions

        # ── Idempotency: a second convert is a no-op ──────────────
        # Use the same request body — the stamps on the registration
        # / locations / units must cause every step to short-circuit.
        before_counts = {
            Tenant: db.count(Tenant),
            Customer: db.count(Customer),
            Site: db.count(Site),
            ServiceUnit: db.count(ServiceUnit),
            Subscription: db.count(Subscription),
        }

        result_2 = await conv.convert_registration(
            db, reg,
            tenant_choice="create_new",
            existing_tenant_id=None,
            new_tenant_id="integrity-property-management",
            new_tenant_name="Integrity Property Management",
            customer_choice="create_new",
            existing_customer_id=None,
            create_subscription=True,
            dry_run=False,
            actor_user_id=None,
            actor_email="ops@true911.com",
        )

        for model, before in before_counts.items():
            after = db.count(model)
            assert after == before, (
                f"retry created extra {model.__name__} rows "
                f"(before={before}, after={after}) — idempotency broken"
            )
        # Every section of the second result reports was_created=False.
        assert result_2.tenant.was_created is False
        assert result_2.customer.was_created is False
        assert all(s.was_created is False for s in result_2.sites)
        assert all(u.was_created is False for u in result_2.service_units)
        assert result_2.subscription is not None
        assert result_2.subscription.was_created is False

    @pytest.mark.asyncio
    async def test_convert_without_plan_code_skips_subscription(self):
        """The convert path should silently skip Subscription creation
        when ``create_subscription=true`` but ``selected_plan_code`` is
        empty — the wizard can legitimately ship one without the other.
        """
        db = FakeAsyncSession()
        reg = _build_integrity_property_management(db)
        reg.selected_plan_code = None  # opt out

        result = await conv.convert_registration(
            db, reg,
            tenant_choice="create_new",
            existing_tenant_id=None,
            new_tenant_id="integrity-property-management",
            new_tenant_name="Integrity Property Management",
            customer_choice="create_new",
            existing_customer_id=None,
            create_subscription=True,
            dry_run=False,
            actor_user_id=None,
            actor_email="ops@true911.com",
        )

        assert db.count(Subscription) == 0
        assert result.subscription is None
        # And the rest of the materialisation still happened.
        assert db.count(Tenant) == 1
        assert db.count(Customer) == 1
        assert db.count(Site) == 2
        assert db.count(ServiceUnit) == 4
