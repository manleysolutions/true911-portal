"""Shared test fixtures for True911 API tests.

The Vola integration tests don't need a real database — they only test the
proxy layer.  We override the auth dependency to inject a fake Admin user so
we never hit PostgreSQL.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_current_user


def _fake_admin():
    """Return a mock User object with Admin role."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@true911.test"
    user.name = "Test Admin"
    user.role = "Admin"
    user.tenant_id = "tenant_1"
    user.is_active = True
    return user


def _fake_non_admin():
    """Return a mock User object with User role (no admin perms)."""
    user = MagicMock()
    user.id = 2
    user.email = "user@true911.test"
    user.name = "Test User"
    user.role = "User"
    user.tenant_id = "tenant_1"
    user.is_active = True
    return user


@pytest.fixture()
def admin_client():
    """TestClient with auth overridden to an Admin user."""
    app.dependency_overrides[get_current_user] = lambda: _fake_admin()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def user_client():
    """TestClient with auth overridden to a non-admin User."""
    app.dependency_overrides[get_current_user] = lambda: _fake_non_admin()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
