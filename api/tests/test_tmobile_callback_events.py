"""Tests for the T-Mobile Wholesale event-specific callback endpoints.

Mounts only the tmobile_callback router on a minimal FastAPI app — same
pattern as test_health_system.py — to avoid pulling in the full
main.py startup chain (auth, DB, etc.).
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.tmobile_callback import router as tmobile_router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(tmobile_router, prefix="/tmobile/wholesale")
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


EVENT_PATHS = [
    ("provisioning", "/tmobile/wholesale/callback/provisioning"),
    ("usage", "/tmobile/wholesale/callback/usage"),
    ("device_change", "/tmobile/wholesale/callback/device-change"),
    ("subscriber_status", "/tmobile/wholesale/callback/subscriber-status"),
    ("static_ip", "/tmobile/wholesale/callback/static-ip"),
    ("cim", "/tmobile/wholesale/callback/cim"),
]


# ── 200-OK contract on GET and POST ───────────────────────────────

@pytest.mark.parametrize("event,path", EVENT_PATHS)
def test_get_returns_200_with_ack(client, event, path):
    r = client.get(path)
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "ok",
        "provider": "t-mobile",
        "event": event,
        "message": "Callback endpoint reachable",
    }


@pytest.mark.parametrize("event,path", EVENT_PATHS)
def test_post_with_valid_json_returns_200(client, event, path):
    r = client.post(path, json={"sample": "payload", "n": 42})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["event"] == event


@pytest.mark.parametrize("event,path", EVENT_PATHS)
def test_post_with_empty_body_returns_200(client, event, path):
    r = client.post(path, content=b"")
    assert r.status_code == 200
    assert r.json()["event"] == event


@pytest.mark.parametrize("event,path", EVENT_PATHS)
def test_post_with_invalid_json_returns_200(client, event, path):
    r = client.post(
        path,
        content=b"not-valid-json{{{",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["event"] == event


# ── Header redaction in logs ──────────────────────────────────────

def test_logs_redact_sensitive_headers(client, caplog):
    caplog.set_level(logging.INFO, logger="true911.tmobile_callback")
    r = client.post(
        "/tmobile/wholesale/callback/provisioning",
        json={"hello": "world"},
        headers={
            "Authorization": "Bearer super-secret-token-123",
            "X-Api-Key": "consumer-key-abc",
            "X-Auth-Token": "private-456",
            "Cookie": "session=should-not-leak",
            "User-Agent": "tmobile-validator/1.0",
        },
    )
    assert r.status_code == 200

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "super-secret-token-123" not in log_text
    assert "consumer-key-abc" not in log_text
    assert "private-456" not in log_text
    assert "should-not-leak" not in log_text
    # Non-sensitive headers should still be visible for debugging.
    assert "tmobile-validator/1.0" in log_text
    # Redaction marker should appear for at least one of the stripped headers.
    assert "[REDACTED]" in log_text


def test_logs_include_event_and_path(client, caplog):
    caplog.set_level(logging.INFO, logger="true911.tmobile_callback")
    r = client.post("/tmobile/wholesale/callback/usage", json={"x": 1})
    assert r.status_code == 200
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "event=usage" in log_text
    assert "/tmobile/wholesale/callback/usage" in log_text


# ── Backwards compatibility: original /callback unchanged ─────────

def test_legacy_get_callback_still_works(client):
    r = client.get("/tmobile/wholesale/callback")
    assert r.status_code == 200
    assert r.json() == {"success": True, "message": "callback received"}


def test_legacy_post_callback_still_works(client):
    r = client.post("/tmobile/wholesale/callback", json={"any": "body"})
    assert r.status_code == 200
    assert r.json() == {"success": True, "message": "callback received"}
