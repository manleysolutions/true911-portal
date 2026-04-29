"""Tests for RequestVisibilityMiddleware (X-Request-ID + log line)."""

import logging

import pytest
from fastapi import FastAPI, Request
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

    # Mimics what get_current_user does on a successful auth: attach the
    # resolved identity to request.state so the middleware can log it.
    @app.get("/authed")
    def authed(request: Request):
        request.state.user_id = "user-abc-123"
        request.state.tenant_id = "tenant-xyz"
        return {"ok": True}

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


class TestUserTenantLogging:
    """user_id / tenant_id are read from request.state by the middleware.

    The auth dependency (get_current_user) is responsible for attaching them
    on successful auth; these tests stand in for that contract by setting
    request.state directly inside a route, so the middleware behavior is
    verified independently of the full auth/DB chain.
    """

    def test_unauthenticated_logs_user_and_tenant_as_none(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="true911.request"):
            r = client.get("/ok")
        assert r.status_code == 200

        records = [rec for rec in caplog.records if rec.name == "true911.request"]
        assert records
        msg = records[-1].getMessage()
        assert "user_id=None" in msg
        assert "tenant_id=None" in msg

    def test_authenticated_logs_user_and_tenant(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="true911.request"):
            r = client.get("/authed")
        assert r.status_code == 200

        records = [rec for rec in caplog.records if rec.name == "true911.request"]
        assert records
        msg = records[-1].getMessage()
        assert "user_id=user-abc-123" in msg
        assert "tenant_id=tenant-xyz" in msg

    def test_user_tenant_log_does_not_leak_authorization_header(self, client, caplog):
        """Belt-and-suspenders: the new fields must not introduce a leak."""
        with caplog.at_level(logging.INFO, logger="true911.request"):
            client.get(
                "/authed",
                headers={
                    "Authorization": "Bearer secret-token-abcdef",
                    "Cookie": "session=should-not-appear",
                },
            )

        for rec in caplog.records:
            if rec.name != "true911.request":
                continue
            text = rec.getMessage()
            assert "secret-token-abcdef" not in text
            assert "should-not-appear" not in text
            assert "Authorization" not in text
            assert "Cookie" not in text
            assert "Bearer" not in text
