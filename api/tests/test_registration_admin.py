"""Phase R3 — internal admin/ops registration review tests.

Targets the service-layer helpers introduced by Phase R3 and the
schema validation around the admin-edit and transition surfaces.
Database-touching paths are exercised through AsyncMock — matching
the pattern in test_registration_public.py and test_phase3a_dual_write.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.schemas.registration import (
    RegistrationAdminUpdate,
    RegistrationCancelRequest,
    RegistrationDetailOut,
    RegistrationRequestInfoRequest,
    RegistrationStatusEventOut,
    RegistrationTransitionRequest,
)
from app.services import registration_service as svc


def _mock_db():
    db = AsyncMock()
    db.add = lambda *args, **kwargs: None
    return db


# ─────────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────────

class TestAdminUpdateSchema:
    def test_accepts_empty_body(self):
        # exclude_unset is the contract the router relies on for the
        # partial-PATCH behavior — confirm the schema agrees.
        body = RegistrationAdminUpdate.model_validate({})
        assert body.model_dump(exclude_unset=True) == {}

    def test_passes_through_writable_fields(self):
        body = RegistrationAdminUpdate.model_validate({
            "reviewer_notes": "Looks good.",
            "target_tenant_id": "acme",
            "selected_plan_code": "monitoring_e911",
            "plan_quantity_estimate": 12,
            "billing_method": "ach",
            "installer_notes": "Park near the loading dock.",
        })
        d = body.model_dump(exclude_unset=True)
        assert d["reviewer_notes"] == "Looks good."
        assert d["target_tenant_id"] == "acme"
        assert d["plan_quantity_estimate"] == 12

    def test_rejects_oversized_reviewer_notes(self):
        with pytest.raises(ValidationError):
            RegistrationAdminUpdate.model_validate({"reviewer_notes": "x" * 8001})

    def test_rejects_negative_quantity(self):
        with pytest.raises(ValidationError):
            RegistrationAdminUpdate.model_validate({"plan_quantity_estimate": -1})

    def test_silently_ignores_unknown_keys(self):
        # Pydantic's default behavior is to ignore unknowns rather than
        # raise — the router relies on this to safely accept whatever
        # the frontend sends and have the service module gate the
        # actual writes via _ADMIN_WRITABLE_FIELDS.
        body = RegistrationAdminUpdate.model_validate({
            "reviewer_notes": "ok",
            "status": "should be ignored — only /transition can set status",
            "customer_id": 999,
        })
        dumped = body.model_dump(exclude_unset=True)
        assert "status" not in dumped
        assert "customer_id" not in dumped


class TestTransitionRequestSchema:
    def test_requires_to_status(self):
        with pytest.raises(ValidationError):
            RegistrationTransitionRequest.model_validate({})

    def test_accepts_optional_note(self):
        body = RegistrationTransitionRequest.model_validate(
            {"to_status": "internal_review"}
        )
        assert body.note is None

    def test_rejects_oversized_note(self):
        with pytest.raises(ValidationError):
            RegistrationTransitionRequest.model_validate(
                {"to_status": "internal_review", "note": "x" * 4001}
            )


class TestRequestInfoSchema:
    def test_requires_message(self):
        with pytest.raises(ValidationError):
            RegistrationRequestInfoRequest.model_validate({})

    def test_rejects_empty_message(self):
        with pytest.raises(ValidationError):
            RegistrationRequestInfoRequest.model_validate({"message": ""})

    def test_rejects_oversized_message(self):
        with pytest.raises(ValidationError):
            RegistrationRequestInfoRequest.model_validate({"message": "x" * 4001})


class TestCancelSchema:
    def test_requires_reason(self):
        with pytest.raises(ValidationError):
            RegistrationCancelRequest.model_validate({})

    def test_rejects_empty_reason(self):
        with pytest.raises(ValidationError):
            RegistrationCancelRequest.model_validate({"reason": ""})


# ─────────────────────────────────────────────────────────────────────
# admin_update_registration
# ─────────────────────────────────────────────────────────────────────

class TestAdminUpdateService:
    @pytest.mark.asyncio
    async def test_only_writes_allow_listed_fields(self):
        # If a regression widens _ADMIN_WRITABLE_FIELDS by accident,
        # this guards against quietly accepting status, customer_id,
        # or submitter_email through the admin surface.
        db = _mock_db()
        reg = SimpleNamespace(
            status=svc.Status.SUBMITTED,
            reviewer_notes=None,
            target_tenant_id=None,
            selected_plan_code=None,
            plan_quantity_estimate=None,
            billing_method=None,
            installer_notes=None,
            customer_name=None,
            customer_legal_name=None,
            customer_id=None,
            submitter_email="cindy@example.com",
        )
        await svc.admin_update_registration(db, reg, {
            "reviewer_notes": "ok",
            "selected_plan_code": "monitoring",
            "status": "active",  # MUST be ignored
            "customer_id": 42,    # MUST be ignored
            "submitter_email": "evil@example.com",  # MUST be ignored
        })
        assert reg.reviewer_notes == "ok"
        assert reg.selected_plan_code == "monitoring"
        assert reg.status == svc.Status.SUBMITTED  # unchanged
        assert reg.customer_id is None
        assert reg.submitter_email == "cindy@example.com"

    @pytest.mark.asyncio
    async def test_admin_can_correct_misentered_customer_name(self):
        # This is the production bug from the staging Integrity test:
        # the wizard's ambiguous "Company / Property Name" label led
        # the submitter to type a building name into customer_name.
        # The operator must be able to fix it via the existing admin
        # update surface BEFORE conversion materialises the wrong
        # account.  Lock this in so a future tightening of the
        # allow-list doesn't accidentally re-block it.
        db = _mock_db()
        reg = SimpleNamespace(
            status=svc.Status.INTERNAL_REVIEW,
            reviewer_notes=None,
            target_tenant_id=None,
            selected_plan_code=None,
            plan_quantity_estimate=None,
            billing_method=None,
            installer_notes=None,
            customer_name="Tiffany Gardens East",  # wrong
            customer_legal_name=None,
            customer_id=None,
            submitter_email="cindy@example.com",
        )
        await svc.admin_update_registration(db, reg, {
            "customer_name": "Integrity Property Management",
            "customer_legal_name": "Integrity Property Management LLC",
        })
        assert reg.customer_name == "Integrity Property Management"
        assert reg.customer_legal_name == "Integrity Property Management LLC"

    @pytest.mark.asyncio
    async def test_no_commit_when_no_allow_listed_fields(self):
        # When the body carries only ignored fields, we should not
        # spam a DB round trip — keeps the audit / updated_at clean.
        db = _mock_db()
        reg = SimpleNamespace(
            status=svc.Status.SUBMITTED, reviewer_notes=None, target_tenant_id=None,
            selected_plan_code=None, plan_quantity_estimate=None,
            billing_method=None, installer_notes=None,
        )
        await svc.admin_update_registration(db, reg, {
            "status": "active", "customer_id": 1,
        })
        assert db.commit.await_count == 0


# ─────────────────────────────────────────────────────────────────────
# request_more_info / cancel_registration
# ─────────────────────────────────────────────────────────────────────

class TestRequestMoreInfo:
    @pytest.mark.asyncio
    async def test_transitions_from_internal_review_to_pending_customer_info(self):
        db = _mock_db()
        reg = SimpleNamespace(
            id=1,
            registration_id="REG-AAA",
            status=svc.Status.INTERNAL_REVIEW,
            submitted_at=datetime.now(timezone.utc),
            cancelled_at=None,
        )
        await svc.request_more_info(
            db, reg,
            message="What's your access code?",
            actor_user_id=uuid.uuid4(),
            actor_email="ops@true911.com",
        )
        assert reg.status == svc.Status.PENDING_CUSTOMER_INFO

    @pytest.mark.asyncio
    async def test_request_info_from_draft_is_rejected(self):
        # Drafts haven't been submitted yet — asking for more info
        # from a draft is nonsensical and the state machine should
        # surface that as IllegalStatusTransitionError so the router
        # returns 409.
        db = _mock_db()
        reg = SimpleNamespace(
            id=1, registration_id="REG-AAA", status=svc.Status.DRAFT,
            submitted_at=None, cancelled_at=None,
        )
        with pytest.raises(svc.IllegalStatusTransitionError):
            await svc.request_more_info(
                db, reg, message="Why?",
                actor_user_id=None, actor_email="ops@true911.com",
            )


class TestCancelRegistration:
    @pytest.mark.asyncio
    async def test_stamps_reason_on_registration_row(self):
        # The list view reads cancel_reason directly off the
        # registration to avoid joining status_events.  Confirm the
        # service mirrors the reason there as well as in the audit
        # trail.
        db = _mock_db()
        reg = SimpleNamespace(
            id=1, registration_id="REG-AAA",
            status=svc.Status.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            cancelled_at=None, cancel_reason=None,
        )
        await svc.cancel_registration(
            db, reg, reason="duplicate of REG-BBB",
            actor_user_id=None, actor_email="ops@true911.com",
        )
        assert reg.status == svc.Status.CANCELLED
        assert reg.cancel_reason == "duplicate of REG-BBB"
        assert reg.cancelled_at is not None

    @pytest.mark.asyncio
    async def test_cancel_is_reachable_from_non_terminal_states(self):
        # Cancellation should be possible at any point in the
        # workflow.  Spot-check the late-stage states where this
        # property is most likely to regress.
        for state in [svc.Status.SCHEDULED, svc.Status.INSTALLED, svc.Status.QA_REVIEW]:
            db = _mock_db()
            reg = SimpleNamespace(
                id=1, registration_id="REG-AAA", status=state,
                submitted_at=None, cancelled_at=None, cancel_reason=None,
            )
            await svc.cancel_registration(
                db, reg, reason="changed our mind",
                actor_user_id=None, actor_email="ops@true911.com",
            )
            assert reg.status == svc.Status.CANCELLED, f"failed from {state}"

    @pytest.mark.asyncio
    async def test_cancel_from_already_cancelled_is_rejected(self):
        db = _mock_db()
        reg = SimpleNamespace(
            id=1, registration_id="REG-AAA", status=svc.Status.CANCELLED,
            submitted_at=None, cancelled_at=datetime.now(timezone.utc),
            cancel_reason="prior",
        )
        with pytest.raises(svc.IllegalStatusTransitionError):
            await svc.cancel_registration(
                db, reg, reason="dup", actor_user_id=None, actor_email="ops@true911.com",
            )


# ─────────────────────────────────────────────────────────────────────
# Regression — RegistrationStatusEventOut accepts a UUID actor_user_id
# ─────────────────────────────────────────────────────────────────────

class TestStatusEventUuidSerialization:
    """Regression for the production ValidationError where the schema
    declared ``actor_user_id: Optional[str]`` but the ORM hands us a
    ``UUID(as_uuid=True)`` value — Pydantic v2 in strict mode rejected
    the coercion and GET /api/registrations/{id} returned 500.

    The fix declares the field as ``Optional[UUID]`` and lets Pydantic
    v2 serialise it to a string in JSON output natively.  These tests
    pin the contract so it can't regress.
    """

    def _orm_event(self, actor_user_id):
        # Mimic the SQLAlchemy ORM row that the router pipes into
        # model_validate.  SimpleNamespace gives the same attribute-
        # access surface model_validate(from_attributes=True) reads.
        return SimpleNamespace(
            id=42,
            registration_id=7,
            from_status="qa_review",
            to_status="ready_for_activation",
            actor_user_id=actor_user_id,
            actor_email="ops@true911.com",
            note="invite issued",
            created_at=datetime.now(timezone.utc),
        )

    def test_model_validate_accepts_real_uuid(self):
        actor = uuid.uuid4()
        out = RegistrationStatusEventOut.model_validate(self._orm_event(actor))
        # Internal representation stays a UUID — no premature stringify.
        assert isinstance(out.actor_user_id, uuid.UUID)
        assert out.actor_user_id == actor

    def test_model_validate_accepts_none(self):
        out = RegistrationStatusEventOut.model_validate(self._orm_event(None))
        assert out.actor_user_id is None

    def test_json_dump_serialises_uuid_to_canonical_string(self):
        # The wire format is what the frontend consumes — confirm the
        # canonical 8-4-4-4-12 hex-with-dashes form lands there.
        actor = uuid.UUID("12345678-1234-5678-1234-567812345678")
        out = RegistrationStatusEventOut.model_validate(self._orm_event(actor))
        dumped = out.model_dump(mode="json")
        assert dumped["actor_user_id"] == "12345678-1234-5678-1234-567812345678"

    def test_detail_out_reviewer_user_id_round_trip(self):
        # Same idiom applies to RegistrationDetailOut.reviewer_user_id —
        # locking this in too because the same router builds it from the
        # ORM via model_validate.  We construct a minimal payload that
        # satisfies the parent RegistrationOut required fields.
        reviewer = uuid.uuid4()
        detail = RegistrationDetailOut.model_validate({
            "id": 1,
            "registration_id": "REG-X",
            "tenant_id": "ops",
            "status": "internal_review",
            "submitter_email": "x@example.com",
            "resume_token_expires_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "reviewer_user_id": reviewer,
        })
        assert isinstance(detail.reviewer_user_id, uuid.UUID)
        assert detail.model_dump(mode="json")["reviewer_user_id"] == str(reviewer)
