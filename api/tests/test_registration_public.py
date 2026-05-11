"""Phase R1 — registration_service unit tests.

Pure-function and lightweight DB-mocked coverage for the staging-side
of the customer registration workflow.  The conversion path (which
materialises customers / sites / service_units) is out of scope for
R1 and not exercised here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.schemas.registration import (
    MAX_LOCATIONS_PER_REGISTRATION,
    MAX_SERVICE_UNITS_PER_LOCATION,
    MAX_SERVICE_UNITS_PER_REGISTRATION,
    RegistrationCreate,
    RegistrationLocationIn,
    RegistrationServiceUnitIn,
    RegistrationUpdate,
)
from app.services import registration_service as svc


# ─────────────────────────────────────────────────────────────────────
# Token helpers
# ─────────────────────────────────────────────────────────────────────

class TestResumeToken:
    def test_generate_returns_url_safe_string(self):
        token = svc.generate_resume_token()
        assert isinstance(token, str)
        # secrets.token_urlsafe(48) => ~64 chars of url-safe base64
        assert len(token) >= 48
        # URL-safe alphabet only
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_hash_is_deterministic_and_hex(self):
        token = "abc123"
        h = svc.hash_resume_token(token)
        assert h == svc.hash_resume_token(token)
        # sha256 hex is 64 chars
        assert len(h) == 64
        int(h, 16)  # raises if non-hex

    def test_hash_differs_from_plaintext(self):
        token = "abc123"
        assert svc.hash_resume_token(token) != token

    def test_token_matches_happy_path(self):
        token = svc.generate_resume_token()
        h = svc.hash_resume_token(token)
        assert svc.token_matches(token, h) is True

    def test_token_matches_rejects_wrong_token(self):
        token = svc.generate_resume_token()
        h = svc.hash_resume_token(token)
        assert svc.token_matches(token + "x", h) is False

    def test_token_matches_handles_missing_inputs(self):
        # Both missing token and missing hash must produce False —
        # never raise — so the resume-token-required guard collapses
        # cleanly to a 403.
        h = svc.hash_resume_token("real")
        assert svc.token_matches(None, h) is False
        assert svc.token_matches("", h) is False
        assert svc.token_matches("real", None) is False
        assert svc.token_matches("real", "") is False
        assert svc.token_matches(None, None) is False

    def test_is_token_expired_true_for_past(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert svc.is_token_expired(past) is True

    def test_is_token_expired_false_for_future(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        assert svc.is_token_expired(future) is False

    def test_is_token_expired_treats_naive_as_utc(self):
        # Mirrors the auth.py reset-token expiry comparison: a naive
        # timestamp is assumed UTC rather than raising.
        naive_past = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None)
        assert svc.is_token_expired(naive_past) is True

    def test_is_token_expired_true_for_none(self):
        assert svc.is_token_expired(None) is True


# ─────────────────────────────────────────────────────────────────────
# verify_resume_token
# ─────────────────────────────────────────────────────────────────────

def _reg_with_token(token: str, *, expires_in_days: int = 30):
    return SimpleNamespace(
        resume_token_hash=svc.hash_resume_token(token),
        resume_token_expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        status=svc.Status.DRAFT,
    )


class TestVerifyResumeToken:
    def test_accepts_correct_token(self):
        reg = _reg_with_token("good-token")
        svc.verify_resume_token(reg, "good-token")  # no raise

    def test_rejects_missing_token_as_invalid_not_expired(self):
        reg = _reg_with_token("good-token")
        with pytest.raises(svc.ResumeTokenInvalid):
            svc.verify_resume_token(reg, None)

    def test_rejects_wrong_token_as_invalid(self):
        reg = _reg_with_token("good-token")
        with pytest.raises(svc.ResumeTokenInvalid):
            svc.verify_resume_token(reg, "bad-token")

    def test_rejects_expired_token_as_expired_not_invalid(self):
        """Order matters — an expired-but-correct token must surface as
        Expired (HTTP 410), not Invalid (HTTP 403).  If this assertion
        regresses, the public endpoints will return the wrong status
        code on expiry and the UI will tell the customer the wrong
        thing.
        """
        reg = _reg_with_token("good-token", expires_in_days=-1)
        with pytest.raises(svc.ResumeTokenExpired):
            svc.verify_resume_token(reg, "good-token")


# ─────────────────────────────────────────────────────────────────────
# registration_id generator
# ─────────────────────────────────────────────────────────────────────

class TestRegistrationId:
    def test_format_prefix_and_length(self):
        rid = svc.generate_registration_id()
        assert rid.startswith("REG-")
        # 6 hex bytes => 12 uppercase hex chars after the prefix
        assert len(rid) == len("REG-") + 12

    def test_distinct_calls_produce_distinct_ids(self):
        ids = {svc.generate_registration_id() for _ in range(100)}
        assert len(ids) == 100


# ─────────────────────────────────────────────────────────────────────
# Status state machine
# ─────────────────────────────────────────────────────────────────────

class TestStateMachine:
    def test_draft_can_submit(self):
        assert svc.is_legal_transition(svc.Status.DRAFT, svc.Status.SUBMITTED)

    def test_draft_can_cancel(self):
        # Cancellation is reachable from any non-terminal state.
        assert svc.is_legal_transition(svc.Status.DRAFT, svc.Status.CANCELLED)

    def test_draft_cannot_jump_to_active(self):
        assert not svc.is_legal_transition(svc.Status.DRAFT, svc.Status.ACTIVE)

    def test_active_is_terminal(self):
        for status in svc.ALL_STATUSES:
            assert not svc.is_legal_transition(svc.Status.ACTIVE, status)

    def test_cancelled_is_terminal(self):
        for status in svc.ALL_STATUSES:
            assert not svc.is_legal_transition(svc.Status.CANCELLED, status)

    def test_unknown_target_status_rejected(self):
        assert not svc.is_legal_transition(svc.Status.DRAFT, "magic_status")

    def test_qa_review_can_loop_back_to_equipment(self):
        # QA failing kicks the registration back to fix gear — the
        # state machine must allow it explicitly, since this is the
        # only documented backward edge.
        assert svc.is_legal_transition(
            svc.Status.QA_REVIEW, svc.Status.PENDING_EQUIPMENT_ASSIGNMENT
        )

    def test_allowed_next_includes_cancelled_for_non_terminals(self):
        for status in svc.ALL_STATUSES - svc.TERMINAL_STATUSES:
            assert svc.Status.CANCELLED in svc.allowed_next_statuses(status), \
                f"{status} should permit cancellation"

    def test_allowed_next_excludes_cancelled_for_terminals(self):
        for status in svc.TERMINAL_STATUSES:
            assert svc.Status.CANCELLED not in svc.allowed_next_statuses(status)


# ─────────────────────────────────────────────────────────────────────
# Editability gate
# ─────────────────────────────────────────────────────────────────────

class TestEditabilityGate:
    def test_draft_is_publicly_editable(self):
        reg = SimpleNamespace(status=svc.Status.DRAFT)
        assert svc.is_publicly_editable(reg) is True

    @pytest.mark.parametrize("status", sorted(svc.ALL_STATUSES - {svc.Status.DRAFT}))
    def test_non_draft_is_not_publicly_editable(self, status):
        reg = SimpleNamespace(status=status)
        assert svc.is_publicly_editable(reg) is False


# ─────────────────────────────────────────────────────────────────────
# Schema validation (payload caps, email format)
# ─────────────────────────────────────────────────────────────────────

class TestRegistrationCreateValidation:
    def _ok_body(self, **overrides) -> dict:
        body = {
            "submitter_email": "cindy@example.com",
            "submitter_name": "Cindy Whittle",
            "submitter_phone": "954-346-0677",
            "customer_name": "Integrity Property Management",
            "use_case_summary": "Four elevator emergency phones",
            "locations": [],
        }
        body.update(overrides)
        return body

    def test_minimum_body_is_valid(self):
        RegistrationCreate.model_validate(self._ok_body())

    def test_rejects_bad_email_format(self):
        with pytest.raises(ValidationError):
            RegistrationCreate.model_validate(self._ok_body(submitter_email="not-an-email"))

    def test_rejects_oversized_locations(self):
        too_many = [
            {"location_label": f"Loc {i}"}
            for i in range(MAX_LOCATIONS_PER_REGISTRATION + 1)
        ]
        with pytest.raises(ValidationError):
            RegistrationCreate.model_validate(self._ok_body(locations=too_many))

    def test_accepts_max_locations(self):
        ok = [
            {"location_label": f"Loc {i}"}
            for i in range(MAX_LOCATIONS_PER_REGISTRATION)
        ]
        RegistrationCreate.model_validate(self._ok_body(locations=ok))

    def test_rejects_oversized_units_in_single_location(self):
        units = [
            {"unit_label": f"U{i}", "unit_type": "elevator_phone"}
            for i in range(MAX_SERVICE_UNITS_PER_LOCATION + 1)
        ]
        body = self._ok_body(locations=[{
            "location_label": "Tower",
            "service_units": units,
        }])
        with pytest.raises(ValidationError):
            RegistrationCreate.model_validate(body)

    def test_rejects_oversized_total_units_across_locations(self):
        # Stay under the per-location cap, but blow past the total cap
        # by spreading units across many locations.
        per_loc = MAX_SERVICE_UNITS_PER_LOCATION
        # Many locations of per_loc units adds up faster than the
        # total cap allows.
        n_locations = (MAX_SERVICE_UNITS_PER_REGISTRATION // per_loc) + 2
        locations = [
            {
                "location_label": f"Loc {i}",
                "service_units": [
                    {"unit_label": f"U{i}-{j}", "unit_type": "elevator_phone"}
                    for j in range(per_loc)
                ],
            }
            for i in range(n_locations)
        ]
        with pytest.raises(ValidationError) as exc:
            RegistrationCreate.model_validate(self._ok_body(locations=locations))
        # Make sure the failure mentions the *total* unit cap, not just
        # a per-location list cap — otherwise we know the model_validator
        # didn't run.
        assert "too many service units" in str(exc.value)

    def test_rejects_negative_plan_quantity(self):
        with pytest.raises(ValidationError):
            RegistrationCreate.model_validate(self._ok_body(plan_quantity_estimate=-1))

    def test_rejects_oversized_use_case_summary(self):
        with pytest.raises(ValidationError):
            RegistrationCreate.model_validate(
                self._ok_body(use_case_summary="x" * 8001)
            )

    def test_unit_quantity_lower_bound_enforced(self):
        # Per-unit quantity must be >= 1 — zero or negative is a bug
        # in the wizard, not a legal request.
        with pytest.raises(ValidationError):
            RegistrationServiceUnitIn.model_validate(
                {"unit_label": "U1", "unit_type": "elevator_phone", "quantity": 0}
            )


class TestRegistrationUpdateValidation:
    def test_ignores_unset_fields(self):
        body = RegistrationUpdate.model_validate({})
        # exclude_unset is the contract that drives the partial-update
        # path in update_registration — verify the schema agrees.
        assert body.model_dump(exclude_unset=True) == {}

    def test_normalizes_pass_through_fields(self):
        body = RegistrationUpdate.model_validate({
            "customer_name": "Acme",
            "use_case_summary": "x" * 100,
        })
        dumped = body.model_dump(exclude_unset=True)
        assert dumped == {"customer_name": "Acme", "use_case_summary": "x" * 100}

    def test_rejects_oversized_installer_notes(self):
        with pytest.raises(ValidationError):
            RegistrationUpdate.model_validate({"installer_notes": "x" * 4001})


# ─────────────────────────────────────────────────────────────────────
# submit_registration / transition_status (DB mocked)
# ─────────────────────────────────────────────────────────────────────

def _mock_db():
    """An AsyncMock with the shape registration_service expects: add()
    is sync, commit() and refresh() are awaited.  No actual SQL runs.
    """

    db = AsyncMock()
    # `add` on a real SQLAlchemy session is synchronous; AsyncMock would
    # turn it into an awaitable by default, breaking the call site.
    db.add = lambda *args, **kwargs: None
    return db


class TestSubmitRegistration:
    @pytest.mark.asyncio
    async def test_draft_to_submitted_stamps_timestamp_and_logs_event(self):
        db = _mock_db()
        reg = SimpleNamespace(
            id=1,
            registration_id="REG-AAA",
            status=svc.Status.DRAFT,
            submitter_email="cindy@example.com",
            submitted_at=None,
            cancelled_at=None,
        )

        result = await svc.submit_registration(db, reg)

        assert result is reg
        assert reg.status == svc.Status.SUBMITTED
        assert reg.submitted_at is not None
        # commit/refresh ran exactly once for this transition.
        assert db.commit.await_count == 1
        assert db.refresh.await_count == 1

    @pytest.mark.asyncio
    async def test_already_submitted_raises_illegal_transition(self):
        db = _mock_db()
        reg = SimpleNamespace(
            id=1,
            registration_id="REG-AAA",
            status=svc.Status.SUBMITTED,
            submitter_email="cindy@example.com",
            submitted_at=datetime.now(timezone.utc),
            cancelled_at=None,
        )

        with pytest.raises(svc.IllegalStatusTransitionError):
            await svc.submit_registration(db, reg)


class TestTransitionStatus:
    @pytest.mark.asyncio
    async def test_cancellation_stamps_cancelled_at(self):
        db = _mock_db()
        reg = SimpleNamespace(
            id=2,
            registration_id="REG-BBB",
            status=svc.Status.DRAFT,
            submitted_at=None,
            cancelled_at=None,
        )

        await svc.transition_status(
            db, reg,
            to_status=svc.Status.CANCELLED,
            actor_email="ops@true911.com",
            note="customer changed mind",
        )

        assert reg.status == svc.Status.CANCELLED
        assert reg.cancelled_at is not None

    @pytest.mark.asyncio
    async def test_rejects_unknown_target_status(self):
        db = _mock_db()
        reg = SimpleNamespace(
            id=3, registration_id="REG-CCC",
            status=svc.Status.DRAFT, submitted_at=None, cancelled_at=None,
        )
        with pytest.raises(svc.IllegalStatusTransitionError):
            await svc.transition_status(db, reg, to_status="bogus")

    @pytest.mark.asyncio
    async def test_rejects_illegal_forward_jump(self):
        db = _mock_db()
        reg = SimpleNamespace(
            id=4, registration_id="REG-DDD",
            status=svc.Status.DRAFT, submitted_at=None, cancelled_at=None,
        )
        with pytest.raises(svc.IllegalStatusTransitionError):
            # Cannot skip from draft straight to active.
            await svc.transition_status(db, reg, to_status=svc.Status.ACTIVE)
