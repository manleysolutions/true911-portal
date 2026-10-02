"""PP-0: the production API never serves framework-generated docs or schema.

Rule: docs are enabled ONLY when APP_MODE is explicitly "demo"; production, a
missing/empty value and any unrecognised value disable them (fail-safe).
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, api_docs_enabled

DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


@pytest.mark.parametrize("mode", ["production", "Production", "", None, "prod", "dev",
                                  "development", "staging", "test", "demo-ish", " "])
def test_docs_are_off_for_every_non_demo_mode(mode):
    assert api_docs_enabled(mode) is False


@pytest.mark.parametrize("mode", ["demo", "DEMO", " Demo "])
def test_docs_are_on_only_for_explicit_demo(mode):
    assert api_docs_enabled(mode) is True


def test_default_app_mode_is_production_so_a_missing_variable_disables_docs():
    assert Settings.model_fields["APP_MODE"].default == "production"
    assert api_docs_enabled(Settings.model_fields["APP_MODE"].default) is False


def test_production_app_serves_no_docs_or_schema_and_normal_endpoints_still_work():
    import app.main as main
    assert main.settings.APP_MODE != "demo"          # the test suite runs with the production default
    paths = {getattr(r, "path", None) for r in main.app.routes}
    for p in DOC_PATHS:
        assert p not in paths, p
    client = TestClient(main.app)
    for p in DOC_PATHS:
        r = client.get(p)
        assert r.status_code == 404, (p, r.status_code)
        assert "openapi" not in r.text.lower() and "swagger" not in r.text.lower()
    health = client.get("/api/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert len([r for r in main.app.routes if getattr(r, "path", "").startswith("/api/")]) > 100


def _app_like_main(mode):
    """Construct an app with exactly the kwargs main.py derives from APP_MODE."""
    on = api_docs_enabled(mode)
    app = FastAPI(title="TRUE911 API", version="1.0.0",
                  docs_url="/docs" if on else None,
                  redoc_url="/redoc" if on else None,
                  openapi_url="/openapi.json" if on else None)

    @app.get("/api/health")
    async def _h():
        return {"status": "ok"}
    return app


def test_demo_mode_keeps_developer_docs():
    client = TestClient(_app_like_main("demo"))
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200 and "/api/health" in schema.json()["paths"]


def test_main_builds_fastapi_from_the_shared_rule():
    import app.main as main
    src = inspect.getsource(main)
    assert "api_docs_enabled(settings.APP_MODE)" in src
    for kw in ('docs_url="/docs" if _DOCS else None', 'redoc_url="/redoc" if _DOCS else None',
               'openapi_url="/openapi.json" if _DOCS else None'):
        assert kw in src, kw
