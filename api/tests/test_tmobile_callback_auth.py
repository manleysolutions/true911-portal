"""Tests for C2 — T-Mobile callback authentication (ingest gate).

Proves:

  * FEATURE_TMOBILE_CALLBACK_AUTH off  → ingest path is byte-identical
    to pre-C2 (the ingest flag remains the only gate).
  * AUTH on + valid token (header OR query) → ingest proceeds.
  * AUTH on + missing / wrong / unconfigured token → ingest is SKIPPED
    (no IntegrationPayload, no job enqueue) but the handler STILL returns
    HTTP 200 (always-200 PIT-validator contract preserved).
  * AUTH on + TMOBILE_CALLBACK_IP_ENFORCE on → source IP must also be
    allowlisted; otherwise ingest is skipped (still 200).
  * AUTH never overrides the ingest kill-switch: ingest flag off → never
    archives, regardless of token.
  * The auth token in a ?token= query is redacted from logs.

Same minimal-app + AsyncMock-db pattern as
tests/test_tmobile_callback_integration.py — no real database.
"""

from __future__ import annotations

import contextlib
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_db
from app.routers.tmobile_callback import router as tmobile_router

PROVISIONING = "/tmobile/wholesale/callback/provisioning"
VALID_TOKEN = "s3cr3t-callback-token-abc123"
TOKEN_HEADER = "X-True911-Callback-Token"


# ─── Test app + db override (mirrors the integration test) ─────────


def _build_app_with_db(db) -> FastAPI:
    app = FastAPI()
    app.include_router(tmobile_router, prefix="/tmobile/wholesale")

    async def _stub_get_db():
        yield db

    app.dependency_overrides[get_db] = _stub_get_db
    return app


def _capture_db_mock():
    db = MagicMock()
    db.added = []
    db.add = lambda obj: db.added.append(obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


@contextlib.contextmanager
def _configure(**overrides):
    """Patch settings attributes on the shared singleton for the block.

    Accepts any Settings attribute name → value.  Because both the router
    and the auth helper resolve the same ``app.config.settings`` object,
    patching it here is visible to both.
    """
    with contextlib.ExitStack() as stack:
        for name, value in overrides.items():
            stack.enter_context(patch.object(settings, name, value))
        # Default enqueue stub so a proceeding ingest never hits Redis.
        stack.enter_context(
            patch(
                "app.routers.tmobile_callback.job_service.create_and_enqueue",
                new=AsyncMock(return_value=SimpleNamespace(id=1)),
            )
        )
        yield


# ═══════════════════════════════════════════════════════════════════
# AUTH OFF → byte-identical to pre-C2 (ingest flag is the only gate)
# ═══════════════════════════════════════════════════════════════════


def test_auth_off_ingest_on_archives_without_token():
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="false",
        TMOBILE_CALLBACK_TOKEN="",
    ):
        r = client.post(PROVISIONING, json={"iccid": "89014103211118510720"})
    assert r.status_code == 200
    assert len(db.added) == 1  # archived, no token required when auth off


# ═══════════════════════════════════════════════════════════════════
# AUTH ON + valid token → ingest proceeds
# ═══════════════════════════════════════════════════════════════════


def test_auth_on_valid_token_header_archives():
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
    ):
        r = client.post(
            PROVISIONING,
            json={"iccid": "X"},
            headers={TOKEN_HEADER: VALID_TOKEN},
        )
    assert r.status_code == 200
    assert len(db.added) == 1


def test_auth_on_valid_token_query_archives_and_redacts_log(caplog):
    caplog.set_level(logging.INFO, logger="true911.tmobile_callback")
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
    ):
        r = client.post(f"{PROVISIONING}?token={VALID_TOKEN}", json={"iccid": "X"})
    assert r.status_code == 200
    assert len(db.added) == 1
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    # The shared secret must never appear in the log stream.
    assert VALID_TOKEN not in log_text
    assert "[REDACTED]" in log_text


# ═══════════════════════════════════════════════════════════════════
# AUTH ON + bad/missing/unconfigured token → SKIP ingest, still 200
# ═══════════════════════════════════════════════════════════════════


def test_auth_on_missing_token_skips_ingest_returns_200(caplog):
    caplog.set_level(logging.WARNING, logger="true911.tmobile_callback")
    db = _capture_db_mock()
    enqueue = AsyncMock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
    ), patch(
        "app.routers.tmobile_callback.job_service.create_and_enqueue", new=enqueue
    ):
        r = client.post(PROVISIONING, json={"iccid": "X"})
    assert r.status_code == 200  # contract preserved
    assert db.added == []  # NOT archived
    enqueue.assert_not_called()  # NOT enqueued
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "DENIED" in log_text and "reason=token_missing" in log_text


def test_auth_on_wrong_token_skips_ingest_returns_200(caplog):
    caplog.set_level(logging.WARNING, logger="true911.tmobile_callback")
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
    ):
        r = client.post(
            PROVISIONING,
            json={"iccid": "X"},
            headers={TOKEN_HEADER: "wrong-token-same-ish-length-aaa"},
        )
    assert r.status_code == 200
    assert db.added == []
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "reason=token_mismatch" in log_text


def test_auth_on_token_not_configured_fails_closed(caplog):
    """Misconfiguration must fail closed (skip ingest), never 500."""
    caplog.set_level(logging.WARNING)
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN="",  # on but unset
    ):
        r = client.post(
            PROVISIONING, json={"iccid": "X"}, headers={TOKEN_HEADER: "anything"}
        )
    assert r.status_code == 200  # never a 500
    assert db.added == []
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "reason=token_not_configured" in log_text


# ═══════════════════════════════════════════════════════════════════
# AUTH ON + IP enforcement (defense in depth)
# ═══════════════════════════════════════════════════════════════════


def test_ip_enforce_in_allowlist_archives():
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
        TMOBILE_CALLBACK_IP_ENFORCE="true",
        TMOBILE_CALLBACK_SOURCE_IPS="206.29.176.74-206.29.176.79",
    ):
        r = client.post(
            PROVISIONING,
            json={"iccid": "X"},
            headers={TOKEN_HEADER: VALID_TOKEN, "CF-Connecting-IP": "206.29.176.75"},
        )
    assert r.status_code == 200
    assert len(db.added) == 1


def test_ip_enforce_outside_allowlist_skips_ingest(caplog):
    caplog.set_level(logging.WARNING, logger="true911.tmobile_callback")
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
        TMOBILE_CALLBACK_IP_ENFORCE="true",
        TMOBILE_CALLBACK_SOURCE_IPS="206.29.176.74-206.29.176.79",
    ):
        r = client.post(
            PROVISIONING,
            json={"iccid": "X"},
            headers={TOKEN_HEADER: VALID_TOKEN, "CF-Connecting-IP": "8.8.8.8"},
        )
    assert r.status_code == 200
    assert db.added == []
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "reason=ip_not_allowlisted" in log_text


def test_ip_enforce_without_source_ip_skips_ingest(caplog):
    caplog.set_level(logging.WARNING, logger="true911.tmobile_callback")
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
        TMOBILE_CALLBACK_IP_ENFORCE="true",
    ):
        r = client.post(
            PROVISIONING, json={"iccid": "X"}, headers={TOKEN_HEADER: VALID_TOKEN}
        )
    assert r.status_code == 200
    assert db.added == []
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "reason=ip_enforce_no_source_ip" in log_text


# ═══════════════════════════════════════════════════════════════════
# Kill-switch precedence + reachability
# ═══════════════════════════════════════════════════════════════════


def test_ingest_off_never_archives_even_with_valid_token():
    """AUTH never re-enables ingest; the ingest flag is the kill switch."""
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="false",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
    ):
        r = client.post(
            PROVISIONING, json={"iccid": "X"}, headers={TOKEN_HEADER: VALID_TOKEN}
        )
    assert r.status_code == 200
    assert db.added == []


def test_get_probe_still_reachable_without_token():
    db = _capture_db_mock()
    client = TestClient(_build_app_with_db(db))
    with _configure(
        FEATURE_TMOBILE_CALLBACK_INGEST="true",
        FEATURE_TMOBILE_CALLBACK_AUTH="true",
        TMOBILE_CALLBACK_TOKEN=VALID_TOKEN,
    ):
        r = client.get(PROVISIONING)
    assert r.status_code == 200
    assert r.json()["event"] == "provisioning"
