"""BACKLOG A15 hardening: /api/debug/cors is SuperAdmin-only, CORS_ORIGINS is
validated at startup, and an unset value fails closed outside explicit demo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, parse_cors_origins

PROD = "https://true911.com,https://www.true911.com,https://true911-web-demo.onrender.com"
PROD_LIST = ["https://true911.com", "https://www.true911.com", "https://true911-web-demo.onrender.com"]
# The exact shape of the production mistake corrected on 2026-10-02.
PRIOR_MISTAKE = ("https://true911.com,https://www.true911.com,https://true911-web-demo.onrender.com,"
                 "https://true911-web-prod.onrender.com\nPUBLIC_URL=https://www.true911.com")


# ── /api/debug/cors is an operator diagnostic, SuperAdmin only ───────
@pytest.fixture()
def main_client():
    import app.main as main
    from app.dependencies import get_current_user
    yield main.app, get_current_user
    main.app.dependency_overrides.pop(get_current_user, None)


def _as(app, dep, role):
    app.dependency_overrides[dep] = lambda: SimpleNamespace(role=role, tenant_id="t", id=1, email="u@x",
                                                            is_active=True, is_platform_user=role == "SuperAdmin")
    return TestClient(app)


def test_debug_cors_denies_anonymous(main_client):
    app, _ = main_client
    r = TestClient(app).get("/api/debug/cors")
    assert r.status_code in (401, 403)
    assert "allow_origins" not in r.text


@pytest.mark.parametrize("role", ["CUSTOMER_ADMIN", "CUSTOMER_VIEWER", "User", "Admin", "Manager"])
def test_debug_cors_denies_non_superadmin(main_client, role):
    app, dep = main_client
    r = _as(app, dep, role).get("/api/debug/cors")
    assert r.status_code == 403 and "allow_origins" not in r.text


def test_debug_cors_allows_superadmin(main_client):
    app, dep = main_client
    r = _as(app, dep, "SuperAdmin").get("/api/debug/cors")
    assert r.status_code == 200
    assert set(r.json()) == {"allow_origins", "allow_credentials", "cors_is_wildcard", "mode"}


# ── parsing / validation ──────────────────────────────────────────────
def test_valid_production_values_initialize():
    assert parse_cors_origins(PROD, "production") == PROD_LIST
    assert parse_cors_origins(" https://www.true911.com , https://true911.com/ ", "production") == \
        ["https://www.true911.com", "https://true911.com"]
    assert parse_cors_origins('["https://www.true911.com"]', "production") == ["https://www.true911.com"]
    assert parse_cors_origins("http://localhost:5173", "demo") == ["http://localhost:5173"]
    s = Settings(_env_file=None, CORS_ORIGINS=PROD, APP_MODE="production")
    assert s.cors_origin_list == PROD_LIST and s.cors_is_wildcard is False


@pytest.mark.parametrize("bad", [
    PRIOR_MISTAKE,
    "https://www.true911.com\r",
    "PUBLIC_URL=https://www.true911.com",
    "https://www.true911.com,PUBLIC_URL=https://x.example",
    "https://www.true911.com,,https://true911.com",
    "https://www.true911.com,",
    "www.true911.com",
    "ftp://www.true911.com",
    "https://www.true911.com/login",
    "https://www.true911.com?x=1",
    "https://user@www.true911.com",
    "https://www.true911.com:70000",
    "https://www.true911 .com",
    '["https://www.true911.com", 7]',
    "[not json",
])
def test_malformed_values_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_cors_origins(bad, "production")


def test_malformed_value_fails_configuration_at_startup():
    """Settings() is constructed at import (app.config.settings), and the Render
    start command imports it via alembic before uvicorn: a ValidationError here
    means the new deploy never becomes healthy."""
    with pytest.raises(ValidationError, match="line break"):
        Settings(_env_file=None, CORS_ORIGINS=PRIOR_MISTAKE, APP_MODE="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CORS_ORIGINS="PUBLIC_URL=https://www.true911.com", APP_MODE="production")


def test_malformed_env_var_fails_settings(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", PRIOR_MISTAKE)
    monkeypatch.setenv("APP_MODE", "production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# ── fail-closed default; demo keeps local convenience ────────────────
@pytest.mark.parametrize("mode", ["production", "", None, "staging", "dev", "Production "])
def test_unset_cors_outside_demo_is_no_cross_origin(mode):
    assert parse_cors_origins("", mode) == []
    assert parse_cors_origins(None, mode) == []


@pytest.mark.parametrize("mode", ["production", "", "staging", "dev"])
def test_wildcard_is_refused_outside_demo(mode):
    with pytest.raises(ValueError, match="only permitted when APP_MODE=demo"):
        parse_cors_origins("*", mode)


def test_demo_unset_and_explicit_wildcard_keep_local_development():
    assert parse_cors_origins("", "demo") == ["*"]
    assert parse_cors_origins("*", " DEMO ") == ["*"]
    s = Settings(_env_file=None, CORS_ORIGINS="", APP_MODE="demo")
    assert s.cors_is_wildcard is True
    with pytest.raises(ValueError):
        parse_cors_origins("*,https://www.true911.com", "demo")


def test_default_settings_do_not_enable_wildcard():
    assert Settings.model_fields["CORS_ORIGINS"].default == ""
    s = Settings(_env_file=None, APP_MODE="production")
    assert s.cors_origin_list == [] and s.cors_is_wildcard is False


# ── preflight behaviour ──────────────────────────────────────────────
def _cors_app(origins):
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/auth/me")
    async def _me():
        return {"ok": True}
    return app


def _preflight(client, origin):
    r = client.options("/api/auth/me", headers={"Origin": origin, "Access-Control-Request-Method": "GET",
                                                "Access-Control-Request-Headers": "authorization"})
    return r.headers.get("access-control-allow-origin")


def test_production_origins_pass_preflight_and_others_fail():
    c = TestClient(_cors_app(parse_cors_origins(PROD, "production")))
    for o in PROD_LIST:
        assert _preflight(c, o) == o
    for o in ("https://true911-web-prod.onrender.com", "https://evil.example", "http://www.true911.com"):
        assert _preflight(c, o) is None


def test_real_app_with_unset_cors_refuses_cross_origin_but_serves_api():
    import app.main as main
    assert main.settings.cors_origin_list == []           # test env: production default, unset
    c = TestClient(main.app)
    assert _preflight(c, "https://www.true911.com") is None
    assert c.get("/api/health").status_code == 200        # same-origin / server calls unaffected
