"""Tests for the GET /api/config/features endpoint — Phase 1 contract.

The frontend uses this to decide whether to render the AI nav item
and Command card, so the new ``lllm`` key being present and reading
``FEATURE_LLLM`` is part of the no-op-deploy guarantee.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from app.main import app
    return TestClient(app)


class TestFeatureFlagsEndpoint:
    def test_lllm_key_present(self, client):
        r = client.get("/api/config/features")
        assert r.status_code == 200
        body = r.json()
        assert "lllm" in body
        # Existing keys still present — no regression.
        assert "samantha" in body
        assert "line_intelligence" in body

    def test_lllm_false_by_default(self, client):
        # Whatever the env says, exercise the 'false' branch.
        with patch("app.main.settings.FEATURE_LLLM", "false"):
            r = client.get("/api/config/features")
        assert r.json()["lllm"] is False

    def test_lllm_true_when_flag_on(self, client):
        with patch("app.main.settings.FEATURE_LLLM", "true"):
            r = client.get("/api/config/features")
        assert r.json()["lllm"] is True

    def test_case_insensitive_truthy(self, client):
        with patch("app.main.settings.FEATURE_LLLM", "TRUE"):
            r = client.get("/api/config/features")
        assert r.json()["lllm"] is True
