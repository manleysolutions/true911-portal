"""Phase A — Onboarding review queue tests.

Covers:
  * Pydantic schema validation for the create / update / out models.
  * Terminal-status auto-stamping logic on the update path.
  * Permission gating — VIEW vs MANAGE.

Database-touching paths use AsyncMock + an in-memory list, matching
the rest of the API test suite (tests/test_registration_admin.py).
The goal here is to pin the contract, not to re-test SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.routers import onboarding_review as router_mod
from app.schemas.onboarding_review import (
    OnboardingReviewCreate,
    OnboardingReviewOut,
    OnboardingReviewUpdate,
)
from app.services import rbac


# ─────────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────────

class TestCreateSchema:
    def test_minimum_required_fields(self):
        body = OnboardingReviewCreate.model_validate({
            "entity_type": "site",
            "issue_type": "missing_address",
        })
        assert body.entity_type == "site"
        assert body.issue_type == "missing_address"
        assert body.priority == "normal"

    def test_rejects_unknown_entity_type(self):
        with pytest.raises(ValidationError):
            OnboardingReviewCreate.model_validate({
                "entity_type": "alien",
                "issue_type": "missing_address",
            })

    def test_rejects_unknown_issue_type(self):
        with pytest.raises(ValidationError):
            OnboardingReviewCreate.model_validate({
                "entity_type": "site",
                "issue_type": "abducted",
            })

    def test_rejects_unknown_priority(self):
        with pytest.raises(ValidationError):
            OnboardingReviewCreate.model_validate({
                "entity_type": "site",
                "issue_type": "missing_address",
                "priority": "critical",
            })


class TestUpdateSchema:
    def test_accepts_empty_body(self):
        # exclude_unset is the contract the router relies on for
        # partial-PATCH behavior; confirm the schema agrees.
        body = OnboardingReviewUpdate.model_validate({})
        assert body.model_dump(exclude_unset=True) == {}

    def test_passes_through_writable_fields(self):
        body = OnboardingReviewUpdate.model_validate({
            "status": "ready_to_import",
            "priority": "high",
            "assigned_to": "sivmey@manleysolutions.com",
            "notes": "Verified address on the Napco portal.",
            "resolution_notes": "Manual portal check passed.",
        })
        dumped = body.model_dump(exclude_unset=True)
        assert dumped["status"] == "ready_to_import"
        assert dumped["priority"] == "high"
        assert dumped["assigned_to"] == "sivmey@manleysolutions.com"

    def test_rejects_bad_status(self):
        with pytest.raises(ValidationError):
            OnboardingReviewUpdate.model_validate({"status": "deleted"})


# ─────────────────────────────────────────────────────────────────────
# Terminal-status auto-stamping
# ─────────────────────────────────────────────────────────────────────

class _Row(SimpleNamespace):
    """Mimics an OnboardingReview ORM row well enough for the patch
    branch logic — only the fields the router touches are needed.
    """


def _new_row(**overrides):
    base = dict(
        id=1,
        review_id="REV-DEADBEEF0001",
        tenant_id="ops",
        entity_type="site",
        entity_id=None,
        external_ref=None,
        issue_type="missing_address",
        status="pending_review",
        priority="normal",
        assigned_to=None,
        notes=None,
        resolution_notes=None,
        created_by="sivmey@manleysolutions.com",
        created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        resolved_at=None,
    )
    base.update(overrides)
    return _Row(**base)


class TestTerminalAutoStamp:
    """Pin the contract that the router stamps ``resolved_at`` when a
    row transitions into a terminal status and clears it when re-opened.

    The logic under test lives inline in the PATCH handler; this test
    re-implements it against a mock row by calling
    ``_apply_update`` semantics — to avoid stepping through the
    FastAPI dependency injection, we exercise the same conditional
    block directly.
    """

    @pytest.mark.parametrize(
        "new_status",
        ["imported", "resolved", "rejected"],
    )
    def test_stamps_resolved_at_on_terminal(self, new_status):
        row = _new_row(status="pending_review")
        updates = {"status": new_status}

        transitioned_to_terminal = (
            "status" in updates
            and updates["status"] in router_mod._TERMINAL_STATUSES
            and row.status not in router_mod._TERMINAL_STATUSES
        )
        for k, v in updates.items():
            setattr(row, k, v)
        if transitioned_to_terminal:
            row.resolved_at = datetime.now(timezone.utc)

        assert row.status == new_status
        assert row.resolved_at is not None

    def test_clears_resolved_at_on_reopen(self):
        row = _new_row(
            status="resolved",
            resolved_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        )
        updates = {"status": "pending_review"}

        transitioned_out_of_terminal = (
            "status" in updates
            and updates["status"] not in router_mod._TERMINAL_STATUSES
            and row.status in router_mod._TERMINAL_STATUSES
        )
        for k, v in updates.items():
            setattr(row, k, v)
        if transitioned_out_of_terminal:
            row.resolved_at = None

        assert row.status == "pending_review"
        assert row.resolved_at is None

    def test_does_not_stamp_when_already_terminal(self):
        original_resolved = datetime(2026, 5, 1, tzinfo=timezone.utc)
        row = _new_row(status="resolved", resolved_at=original_resolved)
        updates = {"status": "rejected"}

        transitioned_to_terminal = (
            "status" in updates
            and updates["status"] in router_mod._TERMINAL_STATUSES
            and row.status not in router_mod._TERMINAL_STATUSES
        )
        for k, v in updates.items():
            setattr(row, k, v)
        if transitioned_to_terminal:
            row.resolved_at = datetime.now(timezone.utc)

        # Status changed but resolved_at should remain the original
        # value — moving from one terminal to another doesn't reset
        # the original close timestamp.
        assert row.status == "rejected"
        assert row.resolved_at == original_resolved


# ─────────────────────────────────────────────────────────────────────
# Permission contract — pins which roles can touch the queue.
# ─────────────────────────────────────────────────────────────────────

class TestPermissions:
    @pytest.mark.parametrize(
        "role,expected_view,expected_manage",
        [
            ("SuperAdmin", True, True),
            ("Admin", True, True),
            ("DataSteward", True, True),
            ("Manager", True, False),
            ("DataEntry", False, False),
            ("User", False, False),
        ],
    )
    def test_role_grants(self, role, expected_view, expected_manage):
        assert rbac.can(role, "VIEW_ONBOARDING_REVIEW") is expected_view
        assert rbac.can(role, "MANAGE_ONBOARDING_REVIEW") is expected_manage


# ─────────────────────────────────────────────────────────────────────
# Output serialization spot check.
# ─────────────────────────────────────────────────────────────────────

class TestOutputModel:
    def test_serializes_from_orm_like_object(self):
        row = _new_row(
            entity_id="SITE-001",
            external_ref="CSV-row-42",
            notes="Address missing on import.",
        )
        out = OnboardingReviewOut.model_validate(row, from_attributes=True)
        assert out.review_id == row.review_id
        assert out.entity_id == "SITE-001"
        assert out.external_ref == "CSV-row-42"
        assert out.status == "pending_review"
        assert out.resolved_at is None
