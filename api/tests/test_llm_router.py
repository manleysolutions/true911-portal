"""Router-level tests — feature flag, RBAC, internal-only gate, fallback.

These tests exercise the full ``/api/llm`` surface end-to-end against
a minimal FastAPI app (the same approach as
``tests/test_health_system.py``), with the DB dependency and current
user replaced by stubs.

What they prove:

  * FEATURE_LLLM=false → router returns 404 (no-op deploy guarantee).
  * Missing VIEW_AI_SUMMARY → 403 from require_permission.
  * Customer-tenant Admin (real tenant not in INTERNAL_TENANT_IDS) →
    403 from _require_internal_context.
  * Internal-tenant Admin → 200 and a HealthSummaryResponse-shaped
    payload (deterministic since the orchestrator is stubbed).
  * SuperAdmin → 200 regardless of tenant.
  * /refresh endpoint forwards force_refresh=True to the orchestrator.

The orchestrator is patched at the router import path so we test the
gate logic, not the deterministic builder (which has its own tests).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers.llm import router as llm_router


# ─── Test-harness helpers ──────────────────────────────────────────


def _build_app(*, user) -> FastAPI:
    """Build a minimal FastAPI app that mounts llm_router with stubbed deps."""
    app = FastAPI()
    app.include_router(llm_router, prefix="/api/llm")

    async def _stub_get_current_user():
        return user

    async def _stub_get_db():
        yield SimpleNamespace()  # never used because orchestrator is stubbed

    app.dependency_overrides[get_current_user] = _stub_get_current_user
    app.dependency_overrides[get_db] = _stub_get_db
    return app


def _stub_user(*, role, tenant_id="default", original_tenant_id=None, impersonating=False):
    """User-shaped object the dependencies + orchestrator both accept."""
    u = SimpleNamespace(
        id=uuid.uuid4(),
        email=f"{role.lower()}@example.com",
        role=role,
        tenant_id=tenant_id,
    )
    u._original_tenant_id = original_tenant_id or tenant_id
    u._is_impersonating = impersonating
    return u


def _deterministic_response() -> dict:
    """The orchestrator's payload shape — we stub generate_health_summary
    to return this so the router can serialize it via HealthSummaryResponse."""
    return {
        "summary_id": "ai-abc123",
        "scope": "fleet",
        "scope_id": None,
        "current_status": "Fleet stable.",
        "likely_issue": None,
        "recommended_next_step": "Continue monitoring.",
        "confidence": 0.80,
        "sources_used": ["sites:tenant=default"],
        "customer_safe_summary": None,
        "internal_summary": "Fleet stable. Continue monitoring.",
        "generated_at": "2026-05-23T12:00:00Z",
        "model": "deterministic",
        "deterministic_fallback": True,
        "source": "fallback",
    }


# ─── Feature flag (default-off no-op) ──────────────────────────────


class TestFeatureFlag:
    """The headline guarantee: FEATURE_LLLM=false is a no-op deploy."""

    def test_feature_off_returns_404(self):
        # Default settings.FEATURE_LLLM should be 'false'.  Even a
        # SuperAdmin gets 404 when the flag is off.
        user = _stub_user(role="SuperAdmin", tenant_id="default")
        client = TestClient(_build_app(user=user))
        with patch("app.routers.llm.settings.FEATURE_LLLM", "false"):
            r = client.get("/api/llm/health-summary?scope=fleet")
        assert r.status_code == 404

    def test_feature_off_refresh_returns_404(self):
        user = _stub_user(role="SuperAdmin", tenant_id="default")
        client = TestClient(_build_app(user=user))
        with patch("app.routers.llm.settings.FEATURE_LLLM", "false"):
            r = client.post("/api/llm/health-summary/refresh?scope=fleet")
        assert r.status_code == 404

    def test_feature_off_does_not_call_orchestrator(self):
        """Hard guarantee — provider is never reached when flag is off."""
        user = _stub_user(role="SuperAdmin", tenant_id="default")
        client = TestClient(_build_app(user=user))
        stub = AsyncMock(return_value=_deterministic_response())
        with patch("app.routers.llm.settings.FEATURE_LLLM", "false"), \
             patch("app.routers.llm.generate_health_summary", new=stub):
            client.get("/api/llm/health-summary?scope=fleet")
        stub.assert_not_called()


# ─── RBAC + internal-only gate (flag ON) ────────────────────────────


class TestRBACAndInternalGate:
    def test_internal_admin_passes(self):
        user = _stub_user(role="Admin", tenant_id="default")  # "default" ∈ INTERNAL_TENANT_IDS
        client = TestClient(_build_app(user=user))
        stub = AsyncMock(return_value=_deterministic_response())
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"), \
             patch("app.routers.llm.generate_health_summary", new=stub):
            r = client.get("/api/llm/health-summary?scope=fleet")
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == "fleet"
        stub.assert_awaited_once()

    def test_superadmin_passes(self):
        user = _stub_user(role="SuperAdmin", tenant_id="default")
        client = TestClient(_build_app(user=user))
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"), \
             patch("app.routers.llm.generate_health_summary",
                   new=AsyncMock(return_value=_deterministic_response())):
            r = client.get("/api/llm/health-summary?scope=fleet")
        assert r.status_code == 200

    def test_customer_tenant_admin_blocked_by_internal_gate(self):
        # Admin role HAS VIEW_AI_SUMMARY per permissions.json, but their
        # real tenant is not in INTERNAL_TENANT_IDS → internal-only
        # gate refuses.
        user = _stub_user(
            role="Admin",
            tenant_id="restoration-hardware",
            original_tenant_id="restoration-hardware",
        )
        client = TestClient(_build_app(user=user))
        stub = AsyncMock(return_value=_deterministic_response())
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"), \
             patch("app.routers.llm.generate_health_summary", new=stub):
            r = client.get("/api/llm/health-summary?scope=fleet")
        assert r.status_code == 403
        assert "internal-only" in r.json()["detail"].lower()
        stub.assert_not_called()

    def test_manager_blocked_by_permission(self):
        # Manager does NOT have VIEW_AI_SUMMARY per permissions.json.
        user = _stub_user(role="Manager", tenant_id="default")
        client = TestClient(_build_app(user=user))
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"):
            r = client.get("/api/llm/health-summary?scope=fleet")
        assert r.status_code == 403

    def test_user_blocked_by_permission(self):
        user = _stub_user(role="User", tenant_id="default")
        client = TestClient(_build_app(user=user))
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"):
            r = client.get("/api/llm/health-summary?scope=fleet")
        assert r.status_code == 403


# ─── Parameter validation ──────────────────────────────────────────


class TestParameterValidation:
    def test_site_scope_requires_scope_id(self):
        user = _stub_user(role="SuperAdmin", tenant_id="default")
        client = TestClient(_build_app(user=user))
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"):
            r = client.get("/api/llm/health-summary?scope=site")
        assert r.status_code == 422
        assert "scope_id" in r.json()["detail"]

    def test_invalid_scope_rejected(self):
        user = _stub_user(role="SuperAdmin", tenant_id="default")
        client = TestClient(_build_app(user=user))
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"):
            r = client.get("/api/llm/health-summary?scope=universe")
        assert r.status_code == 422


# ─── Refresh forwards force_refresh ────────────────────────────────


class TestRefreshEndpoint:
    def test_refresh_passes_force_refresh_true(self):
        user = _stub_user(role="SuperAdmin", tenant_id="default")
        client = TestClient(_build_app(user=user))
        stub = AsyncMock(return_value=_deterministic_response())
        with patch("app.routers.llm.settings.FEATURE_LLLM", "true"), \
             patch("app.routers.llm.generate_health_summary", new=stub):
            r = client.post("/api/llm/health-summary/refresh?scope=fleet")
        assert r.status_code == 200
        # Inspect kwargs the orchestrator was called with
        kwargs = stub.await_args.kwargs
        assert kwargs["force_refresh"] is True
        assert kwargs["scope"] == "fleet"
