"""Tests for RequestVisibilityMiddleware (X-Request-ID + log line)."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import REQUEST_ID_HEADER, RequestVisibilityMiddleware


def _build_app() -> FastAPI:
    """Minimal FastAPI app with only the visibility middleware mounted."""
    app = FastAPI()
    app.add_middleware(RequestVisibilityMiddleware)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/teapot")
    def teapot():
        from fastapi import HTTPException
        raise HTTPException(status_code=418, detail="i'm a teapot")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


class TestRequestIdHeader:
    def test_generated_when_missing(self, client):
        r = client.get("/ok")
        assert r.status_code == 200
        rid = r.headers.get(REQUEST_ID_HEADER)
        assert rid, "X-Request-ID should be present on the response"
        # uuid4 hex is 32 chars; allow flexibility but require non-trivial length
        assert len(rid) >= 16

    def test_preserved_when_supplied(self, client):
        incoming = "client-supplied-request-id-123"
        r = client.get("/ok", headers={REQUEST_ID_HEADER: incoming})
        assert r.headers.get(REQUEST_ID_HEADER) == incoming

    def test_present_on_error_responses(self, client):
        r = client.get("/teapot")
        assert r.status_code == 418
        assert r.headers.get(REQUEST_ID_HEADER), \
            "X-Request-ID should still be set on non-2xx responses"


class TestRequestLogging:
    def test_logs_method_path_status_duration_request_id(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="true911.request"):
            r = client.get("/ok")
        rid = r.headers[REQUEST_ID_HEADER]

        records = [rec for rec in caplog.records if rec.name == "true911.request"]
        assert records, "expected at least one log record from true911.request"
        msg = records[-1].getMessage()
        assert "method=GET" in msg
        assert "path=/ok" in msg
        assert "status_code=200" in msg
        assert "duration_ms=" in msg
        assert f"request_id={rid}" in msg

    def test_log_does_not_leak_authorization_header(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="true911.request"):
            client.get(
                "/ok",
                headers={"Authorization": "Bearer super-secret-token-xyz"},
            )

        for rec in caplog.records:
            if rec.name != "true911.request":
                continue
            text = rec.getMessage()
            assert "super-secret-token-xyz" not in text
            assert "Authorization" not in text
            assert "Bearer" not in text
