"""Tests for /api/health/system.

The endpoint is exposed via app.routers.health which we mount on a
minimal FastAPI app — the same approach used in
tests/test_request_visibility.py — so the tests don't drag in the full
main.py startup chain.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.health import router as health_router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(health_router, prefix="/api")
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


# A passing async stub for _check_db so the "healthy" path doesn't
# require a real database during tests.
async def _ok_db() -> str:
    return "ok"


# A failing async stub used to drive the "degraded" path.
async def _error_db() -> str:
    return "error"


class TestHealthSystem:
    def test_healthy_returns_200_and_all_ok(self, client):
        with patch("app.routers.health._check_db", new=_ok_db):
            r = client.get("/api/health/system")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["checks"] == {"app": "ok", "db": "ok", "auth": "ok"}

    def test_db_failure_returns_503_and_db_error(self, client):
        with patch("app.routers.health._check_db", new=_error_db):
            r = client.get("/api/health/system")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["checks"]["db"] == "error"
        # app and auth are unaffected by DB failure.
        assert body["checks"]["app"] == "ok"
        assert body["checks"]["auth"] == "ok"

    def test_response_never_contains_secrets(self, client):
        """The success body is a fixed shape; verify it never leaks
        the things that would be most damaging if surfaced."""
        with patch("app.routers.health._check_db", new=_ok_db):
            r = client.get("/api/health/system")
        text = r.text.lower()
        assert "postgres" not in text
        assert "postgresql" not in text
        assert "password" not in text
        assert "secret" not in text
        assert "bearer" not in text
        assert "traceback" not in text
        # Sanity — the body really is the documented shape.
        assert set(r.json().keys()) == {"status", "checks"}
        assert set(r.json()["checks"].keys()) == {"app", "db", "auth"}

    def test_db_exception_does_not_leak_to_response(self, client):
        """Drive the real _check_db path with an exception whose
        message looks sensitive, and confirm none of it reaches the
        response body or the status JSON."""
        sensitive_message = (
            "Connection refused: postgres://hidden:topsecret@dbhost:5432/db"
        )
        with patch(
            "app.routers.health.AsyncSessionLocal",
            side_effect=Exception(sensitive_message),
        ):
            r = client.get("/api/health/system")
        assert r.status_code == 503
        body_text = r.text
        assert "topsecret" not in body_text
        assert "postgres://" not in body_text
        assert "Connection refused" not in body_text
        assert "Traceback" not in body_text
        assert r.json()["checks"]["db"] == "error"

    def test_auth_check_marks_error_when_secret_missing(self, client):
        """If JWT_SECRET is empty, auth must report 'error' and the
        overall status must be 'degraded' even when DB is healthy."""
        with patch("app.routers.health._check_db", new=_ok_db), \
             patch("app.routers.health.settings.JWT_SECRET", ""):
            r = client.get("/api/health/system")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["checks"]["auth"] == "error"
        assert body["checks"]["db"] == "ok"
