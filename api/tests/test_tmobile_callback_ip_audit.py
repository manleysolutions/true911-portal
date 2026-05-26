"""Tests for TmobileCallbackAuditMiddleware (R3 — passive IP audit).

Behavior matrix proved here:

  Flag value   CF-Connecting-IP   In allowlist   Expectation
  ─────────    ────────────────   ────────────   ────────────────────────────
  off          missing            n/a            silent, 200 ack
  off          set                outside        silent, 200 ack (flag gates)
  on           missing            n/a            silent, 200 ack (no claim)
  on           set                inside         silent, 200 ack
  on           set                outside        WARNING logged, 200 ack
  on           set, malformed     n/a            silent, 200 ack (defensive)

The CRITICAL invariant across all rows: response code and body are
identical to the no-middleware case.  The PIT validator must never see
a difference — enforcement is the Cloudflare WAF rule in front of
pit-api.manleysolutions.com, not this middleware.

Also covered:
  * Allowlist parsing: single IPs, inclusive ranges, CIDR blocks,
    malformed entries (skipped not fatal).
  * Path scope: only ``/tmobile/wholesale/callback/*`` triggers the
    audit; every other path is an immediate pass-through.
  * Surface containment: the new flag is only referenced from
    config.py + middleware.py + this test file.
"""

from __future__ import annotations

import logging
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.middleware import (
    TmobileCallbackAuditMiddleware,
    _ip_in_allowlist,
    _parse_allowlist,
)
from app.routers.tmobile_callback import router as tmobile_router


# ─── Test app fixture ──────────────────────────────────────────────


def _build_app():
    """Build a FastAPI app with the audit middleware + callback router.

    Uses a do-nothing AsyncMock db so the archive helper (gated by the
    other flag) never errors even if the test forgets to patch it.
    """
    app = FastAPI()
    app.add_middleware(TmobileCallbackAuditMiddleware)
    app.include_router(tmobile_router, prefix="/tmobile/wholesale")

    db = MagicMock()
    db.added = []
    db.add = lambda obj: db.added.append(obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    async def _stub_get_db():
        yield db

    app.dependency_overrides[get_db] = _stub_get_db
    app.state.captured_db = db
    return app


@pytest.fixture(autouse=True)
def _clear_parse_cache():
    """The lru_cache on _parse_allowlist is keyed by the spec string,
    so it's safe across tests — but explicit clear prevents cross-test
    state from a developer adding a non-string-keyed cache later.
    """
    _parse_allowlist.cache_clear()
    yield
    _parse_allowlist.cache_clear()


# ═══════════════════════════════════════════════════════════════════
# Allowlist parser — single IPs / ranges / CIDR / malformed
# ═══════════════════════════════════════════════════════════════════


class TestAllowlistParser:
    def test_default_tmobile_ranges_cover_known_ips(self):
        """The default spec must cover every IP T-Mobile published."""
        spec = "206.29.176.74-206.29.176.79,208.54.104.32-208.54.104.37"
        ranges = _parse_allowlist(spec)
        for ip in [
            "206.29.176.74", "206.29.176.75", "206.29.176.76",
            "206.29.176.77", "206.29.176.78", "206.29.176.79",
            "208.54.104.32", "208.54.104.33", "208.54.104.34",
            "208.54.104.35", "208.54.104.36", "208.54.104.37",
        ]:
            assert _ip_in_allowlist(ip, ranges), f"{ip} should be allowed"

    def test_outside_ips_rejected_by_default_allowlist(self):
        ranges = _parse_allowlist(
            "206.29.176.74-206.29.176.79,208.54.104.32-208.54.104.37"
        )
        for ip in [
            "206.29.176.73",   # one below low end of first range
            "206.29.176.80",   # one above high end of first range
            "208.54.104.31",   # one below second range
            "208.54.104.38",   # one above second range
            "1.2.3.4",
            "127.0.0.1",
        ]:
            assert not _ip_in_allowlist(ip, ranges), f"{ip} must NOT be allowed"

    def test_single_ip_entry(self):
        ranges = _parse_allowlist("10.0.0.5")
        assert _ip_in_allowlist("10.0.0.5", ranges)
        assert not _ip_in_allowlist("10.0.0.6", ranges)

    def test_cidr_entry(self):
        ranges = _parse_allowlist("10.0.0.0/30")  # .0 .1 .2 .3
        for ip in ["10.0.0.0", "10.0.0.1", "10.0.0.2", "10.0.0.3"]:
            assert _ip_in_allowlist(ip, ranges)
        assert not _ip_in_allowlist("10.0.0.4", ranges)

    def test_reversed_range_normalises(self):
        """Operator typo: high-low order should not silently drop the range."""
        ranges = _parse_allowlist("10.0.0.10-10.0.0.1")
        assert _ip_in_allowlist("10.0.0.5", ranges)

    def test_mixed_entry_types(self):
        ranges = _parse_allowlist("10.0.0.5,192.168.0.0/30,172.16.0.1-172.16.0.3")
        assert _ip_in_allowlist("10.0.0.5", ranges)
        assert _ip_in_allowlist("192.168.0.2", ranges)
        assert _ip_in_allowlist("172.16.0.2", ranges)
        assert not _ip_in_allowlist("10.0.0.6", ranges)

    def test_malformed_entry_skipped_not_fatal(self, caplog):
        """A single bad value must not invalidate the rest of the list."""
        with caplog.at_level(logging.WARNING, logger="true911.tmobile_callback_audit"):
            ranges = _parse_allowlist("not-an-ip,10.0.0.5,999.999.999.999")
        assert _ip_in_allowlist("10.0.0.5", ranges)
        assert any("malformed allowlist entry" in r.message for r in caplog.records)

    def test_empty_spec_returns_empty(self):
        assert _parse_allowlist("") == ()
        assert _parse_allowlist(",,,") == ()

    def test_non_ipv4_header_does_not_match(self):
        ranges = _parse_allowlist("10.0.0.5")
        assert not _ip_in_allowlist("not-an-ip", ranges)
        assert not _ip_in_allowlist("::1", ranges)  # IPv6 unsupported by design


# ═══════════════════════════════════════════════════════════════════
# Middleware behavior — the full matrix
# ═══════════════════════════════════════════════════════════════════


class TestMiddlewareFlagOff:
    """Flag off → middleware is a pass-through.  No logs, no behavior change."""

    def test_no_logging_when_flag_off_even_with_outside_ip(self, caplog):
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "false"
        ), patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.post(
                "/tmobile/wholesale/callback/provisioning",
                json={},
                headers={"CF-Connecting-IP": "1.2.3.4"},
            )

        assert r.status_code == 200
        assert not any(
            "tmobile_callback_ip_audit" in rec.message for rec in caplog.records
        )

    def test_flag_unset_value_treated_as_off(self, caplog):
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", ""
        ), patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.post(
                "/tmobile/wholesale/callback/usage",
                json={},
                headers={"CF-Connecting-IP": "1.2.3.4"},
            )

        assert r.status_code == 200
        assert not any(
            "tmobile_callback_ip_audit" in rec.message for rec in caplog.records
        )


class TestMiddlewareFlagOn:
    """Flag on → audit fires only on outside IPs at the callback paths."""

    def test_silent_when_cf_header_missing(self, caplog):
        """Local dev / direct origin hit with no Cloudflare in path:
        no CF-Connecting-IP means the middleware cannot make a claim,
        so it stays silent (false-positive avoidance)."""
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "true"
        ), patch(
            "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
            "206.29.176.74-206.29.176.79",
        ), patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.post("/tmobile/wholesale/callback/provisioning", json={})

        assert r.status_code == 200
        assert not any(
            "tmobile_callback_ip_audit" in rec.message for rec in caplog.records
        )

    def test_silent_when_cf_header_inside_allowlist(self, caplog):
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "true"
        ), patch(
            "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
            "206.29.176.74-206.29.176.79,208.54.104.32-208.54.104.37",
        ), patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.post(
                "/tmobile/wholesale/callback/subscriber-status",
                json={},
                headers={"CF-Connecting-IP": "206.29.176.77"},
            )

        assert r.status_code == 200
        assert not any(
            "tmobile_callback_ip_audit" in rec.message for rec in caplog.records
        )

    def test_warning_when_cf_header_outside_allowlist(self, caplog):
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "true"
        ), patch(
            "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
            "206.29.176.74-206.29.176.79",
        ), patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.post(
                "/tmobile/wholesale/callback/cim",
                json={},
                headers={"CF-Connecting-IP": "1.2.3.4"},
            )

        # CRITICAL: response code unchanged.
        assert r.status_code == 200
        # WARNING line emitted exactly once with the source IP, path,
        # method, and the outside_allowlist marker.
        audit_records = [
            rec for rec in caplog.records
            if rec.name == "true911.tmobile_callback_audit"
            and "tmobile_callback_ip_audit:" in rec.message
        ]
        assert len(audit_records) == 1
        msg = audit_records[0].getMessage()
        assert "cf_connecting_ip=1.2.3.4" in msg
        assert "/tmobile/wholesale/callback/cim" in msg
        assert "method=POST" in msg
        assert "outside_allowlist=true" in msg

    def test_warning_on_get_too_not_just_post(self, caplog):
        """T-Mobile probes the URLs with GET first.  Audit must apply
        to every HTTP method so a scanner using GET is also visible."""
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "true"
        ), patch(
            "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
            "206.29.176.74-206.29.176.79",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.get(
                "/tmobile/wholesale/callback/usage",
                headers={"CF-Connecting-IP": "8.8.8.8"},
            )

        assert r.status_code == 200
        audit_records = [
            rec for rec in caplog.records
            if "tmobile_callback_ip_audit" in rec.message
        ]
        assert len(audit_records) == 1
        assert "method=GET" in audit_records[0].getMessage()

    def test_malformed_cf_header_does_not_match_and_logs(self, caplog):
        """An attacker putting garbage in CF-Connecting-IP (or a buggy
        proxy in front) should produce an outside-allowlist log line,
        not a crash."""
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "true"
        ), patch(
            "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
            "206.29.176.74-206.29.176.79",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.post(
                "/tmobile/wholesale/callback/static-ip",
                json={},
                headers={"CF-Connecting-IP": "not-an-ip"},
            )

        assert r.status_code == 200
        assert any(
            "tmobile_callback_ip_audit" in rec.message
            and "cf_connecting_ip=not-an-ip" in rec.getMessage()
            for rec in caplog.records
        )


# ═══════════════════════════════════════════════════════════════════
# Path scope — middleware only fires at the T-Mobile callback paths
# ═══════════════════════════════════════════════════════════════════


class TestPathScope:
    def test_non_callback_path_is_immediate_passthrough(self, caplog):
        """Other paths must not invoke the audit even on outside IPs.
        Tests the no-overhead-for-unrelated-traffic property."""
        app = FastAPI()
        app.add_middleware(TmobileCallbackAuditMiddleware)

        @app.get("/api/health")
        def _h():
            return {"status": "ok"}

        client = TestClient(app)

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "true"
        ), patch(
            "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
            "206.29.176.74-206.29.176.79",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            r = client.get(
                "/api/health",
                headers={"CF-Connecting-IP": "1.2.3.4"},
            )

        assert r.status_code == 200
        assert not any(
            "tmobile_callback_ip_audit" in rec.message for rec in caplog.records
        )

    def test_callback_prefix_match_is_exact(self, caplog):
        """A path that starts with the prefix but is not a real callback
        URL (404) must still be audited — we're catching probes, not
        only well-formed callbacks."""
        client = TestClient(_build_app())

        with patch(
            "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT", "true"
        ), patch(
            "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
            "206.29.176.74-206.29.176.79",
        ), caplog.at_level(
            logging.WARNING, logger="true911.tmobile_callback_audit"
        ):
            client.get(
                "/tmobile/wholesale/callback/nonexistent-event",
                headers={"CF-Connecting-IP": "9.9.9.9"},
            )

        # The router returns 404 (no handler) but the audit still fired.
        assert any(
            "tmobile_callback_ip_audit" in rec.message
            and "cf_connecting_ip=9.9.9.9" in rec.getMessage()
            for rec in caplog.records
        )


# ═══════════════════════════════════════════════════════════════════
# HTTP 200 contract preservation
# ═══════════════════════════════════════════════════════════════════


class TestResponseContractPreserved:
    """The load-bearing invariant: the audit middleware NEVER alters
    the response code or body.  Compare flag-on outside-IP vs flag-off
    and assert byte equality."""

    def _post(self, app, headers):
        client = TestClient(app)
        return client.post(
            "/tmobile/wholesale/callback/provisioning",
            json={"iccid": "89014103211118510720"},
            headers=headers,
        )

    def test_flag_on_outside_ip_response_identical_to_flag_off(self):
        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ):
            with patch(
                "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT",
                "false",
            ):
                baseline = self._post(
                    _build_app(),
                    headers={"CF-Connecting-IP": "1.2.3.4"},
                )

            with patch(
                "app.middleware.settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT",
                "true",
            ), patch(
                "app.middleware.settings.TMOBILE_CALLBACK_SOURCE_IPS",
                "206.29.176.74-206.29.176.79",
            ):
                audited = self._post(
                    _build_app(),
                    headers={"CF-Connecting-IP": "1.2.3.4"},
                )

        assert baseline.status_code == audited.status_code == 200
        assert baseline.json() == audited.json()


# ═══════════════════════════════════════════════════════════════════
# Surface containment
# ═══════════════════════════════════════════════════════════════════


class TestSurfaceContainment:
    """Same MVP scope guarantee pattern as the existing T-Mobile MVP
    tests.  Any future PR that references the audit flag from another
    module — or makes the middleware import an E911 / provisioning /
    customer / call-routing module — fails at PR time.
    """

    def test_only_config_and_middleware_reference_the_audit_flag(self):
        """FEATURE_TMOBILE_CALLBACK_IP_AUDIT may only appear in:
          * app/config.py         (declares it)
          * app/middleware.py     (reads it)
          * app/main.py           (comment at the middleware install site —
                                   no code consumes the flag here)
        """
        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        allowlist = {
            pathlib.Path("config.py"),
            pathlib.Path("middleware.py"),
            pathlib.Path("main.py"),
        }
        offending = []
        for p in api_root.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if "FEATURE_TMOBILE_CALLBACK_IP_AUDIT" not in text:
                continue
            rel = p.relative_to(api_root)
            if rel not in allowlist:
                offending.append(str(rel))
        assert not offending, (
            f"FEATURE_TMOBILE_CALLBACK_IP_AUDIT referenced outside the "
            f"allowlist: {offending}.  This is a passive observability flag — "
            f"any new consumer needs explicit governance approval."
        )

    def test_middleware_does_not_import_prohibited_modules(self):
        """The audit middleware must not import E911, provisioning,
        customer-record, call-routing, or any service module.  It only
        needs ipaddress, logging, starlette, and config."""
        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        text = (api_root / "middleware.py").read_text(encoding="utf-8")
        forbidden_substrings = [
            "app.routers.e911",
            "app.services.e911",
            "app.models.e911",
            "app.routers.provisioning",
            "app.services.provision",
            "app.services.line_service",
            "app.routers.calls",
            "app.routers.customers",
            "app.models.customer",
            "app.services.sim_service",
            "app.services.tmobile_callback_processor",
        ]
        leaks = [s for s in forbidden_substrings if s in text]
        assert not leaks, (
            f"middleware.py imports forbidden modules: {leaks}.  "
            f"The audit middleware is observability only — it must not "
            f"pull in business logic surfaces."
        )
