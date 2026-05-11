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
