"""Integration tests for the FEATURE_HEALTH_NORMALIZER flag.

What we prove:

  * FEATURE_HEALTH_NORMALIZER=false → LLLMContext.load_fleet/load_site
    use the legacy path, byte-identical to the pre-MVP behavior.
    No call into app.services.health is made.

  * FEATURE_HEALTH_NORMALIZER=true  → only the AI Health Summary
    (i.e. LLLMContext) routes through the new normalizer.  No other
    consumer is touched.

  * sources_used surfaces the new evidence trail only in the
    normalized path — the 'health_normalizer:v1' tag is the canary
    that lets an audit-log reader tell which derivation ran.

  * The headline bug-fix scenario: a site whose only liveness signal
    is a fresh Telnyx CDR is counted as CONNECTED by the normalizer.

Tests use AsyncMock for the AsyncSession and patch.object on the
LLLMContext loaders so we exercise the flag-branch logic without
needing a real database.  Same pattern as tests/test_health_signals_loader.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.health import (
    CanonicalDeviceState,
    CanonicalSiteState,
    HealthSignals,
    compute_device_state,
    compute_site_state,
)
from app.services.llm.context import LLLMContext


_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


def _stub_user(tenant_id: str = "tenant-x", role: str = "SuperAdmin"):
    u = SimpleNamespace(
        id=uuid.uuid4(),
        email=f"{role.lower()}@example.com",
        role=role,
        tenant_id=tenant_id,
    )
    u._original_tenant_id = tenant_id
    u._is_impersonating = False
    return u


# ═══════════════════════════════════════════════════════════════════
# Flag-branch routing
# ═══════════════════════════════════════════════════════════════════


class TestFlagRouting:
    @pytest.mark.asyncio
    async def test_flag_off_calls_legacy_fleet_loader(self):
        """FEATURE_HEALTH_NORMALIZER=false → _load_fleet_legacy invoked,
        _load_fleet_normalized NOT invoked.  Confirms no-op-when-off."""
        ctx = LLLMContext(user=_stub_user(), db=MagicMock())
        legacy = AsyncMock(return_value="legacy-result")
        normalized = AsyncMock(return_value="normalized-result")
        with patch.object(ctx, "_load_fleet_legacy", new=legacy), \
             patch.object(ctx, "_load_fleet_normalized", new=normalized), \
             patch("app.services.llm.context.settings.FEATURE_HEALTH_NORMALIZER", "false"):
            result = await ctx.load_fleet()
        legacy.assert_awaited_once()
        normalized.assert_not_called()
        assert result == "legacy-result"

    @pytest.mark.asyncio
    async def test_flag_on_calls_normalized_fleet_loader(self):
        """FEATURE_HEALTH_NORMALIZER=true → _load_fleet_normalized invoked,
        _load_fleet_legacy NOT invoked."""
        ctx = LLLMContext(user=_stub_user(), db=MagicMock())
        legacy = AsyncMock(return_value="legacy-result")
        normalized = AsyncMock(return_value="normalized-result")
        with patch.object(ctx, "_load_fleet_legacy", new=legacy), \
             patch.object(ctx, "_load_fleet_normalized", new=normalized), \
             patch("app.services.llm.context.settings.FEATURE_HEALTH_NORMALIZER", "true"):
            result = await ctx.load_fleet()
        normalized.assert_awaited_once()
        legacy.assert_not_called()
        assert result == "normalized-result"

    @pytest.mark.asyncio
    async def test_flag_off_calls_legacy_site_loader(self):
        ctx = LLLMContext(user=_stub_user(), db=MagicMock())
        legacy = AsyncMock(return_value="legacy-site")
        normalized = AsyncMock(return_value="normalized-site")
        with patch.object(ctx, "_load_site_legacy", new=legacy), \
             patch.object(ctx, "_load_site_normalized", new=normalized), \
             patch("app.services.llm.context.settings.FEATURE_HEALTH_NORMALIZER", "false"):
            await ctx.load_site("site-1")
        legacy.assert_awaited_once_with("site-1")
        normalized.assert_not_called()

    @pytest.mark.asyncio
    async def test_flag_on_calls_normalized_site_loader(self):
        ctx = LLLMContext(user=_stub_user(), db=MagicMock())
        legacy = AsyncMock(return_value="legacy-site")
        normalized = AsyncMock(return_value="normalized-site")
        with patch.object(ctx, "_load_site_legacy", new=legacy), \
             patch.object(ctx, "_load_site_normalized", new=normalized), \
             patch("app.services.llm.context.settings.FEATURE_HEALTH_NORMALIZER", "true"):
            await ctx.load_site("site-1")
        normalized.assert_awaited_once_with("site-1")
        legacy.assert_not_called()

    @pytest.mark.asyncio
    async def test_unset_or_empty_flag_treated_as_off(self):
        """Any value other than 'true' (case-insensitive) routes to
        legacy.  Defense against typos in env var values."""
        for flag_value in ("", "yes", "1", "True ", "TRUE"):
            ctx = LLLMContext(user=_stub_user(), db=MagicMock())
            legacy = AsyncMock(return_value="legacy")
            normalized = AsyncMock(return_value="normalized")
            with patch.object(ctx, "_load_fleet_legacy", new=legacy), \
                 patch.object(ctx, "_load_fleet_normalized", new=normalized), \
                 patch(
                     "app.services.llm.context.settings.FEATURE_HEALTH_NORMALIZER",
                     flag_value,
                 ):
                await ctx.load_fleet()
            # Only EXACTLY 'true' (after lower+strip) routes normalized.
            if flag_value.strip().lower() == "true":
                normalized.assert_awaited_once()
            else:
                legacy.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════
# sources_used canary
# ═══════════════════════════════════════════════════════════════════


class TestSourcesUsedCanary:
    """The 'health_normalizer:v1' tag in sources_used is the audit-log
    canary — operators reading the audit row can immediately tell
    which derivation produced the summary."""

    @pytest.mark.asyncio
    async def test_legacy_path_omits_normalizer_tag(self):
        """When flag is off, sources_used does NOT contain
        'health_normalizer:v1' — verified by NOT patching the legacy
        loader and running its real signature."""
        ctx = LLLMContext(user=_stub_user(), db=MagicMock())

        # Stub the methods the legacy path actually calls so we don't
        # need to drive the full DB.
        legacy_fleet_snap = AsyncMock(return_value=SimpleNamespace(
            total_sites=0, connected_sites=0, sites_needing_attention=0,
            active_incidents=0, critical_incidents=0, stale_devices=0,
        ))
        with patch.object(ctx, "_build_fleet_snapshot", new=legacy_fleet_snap), \
             patch.object(ctx, "_load_open_incidents",
                          new=AsyncMock(return_value=[])), \
             patch("app.services.llm.context.settings.FEATURE_HEALTH_NORMALIZER", "false"):
            result = await ctx.load_fleet()

        assert "health_normalizer:v1" not in result.sources_used

    @pytest.mark.asyncio
    async def test_normalized_path_emits_normalizer_tag(self):
        """When flag is on, sources_used INCLUDES 'health_normalizer:v1'
        plus the expanded evidence trail (carrier liveness, vola sync,
        telnyx call_records)."""
        ctx = LLLMContext(user=_stub_user(), db=MagicMock())

        # Stub the inner DB calls _load_fleet_normalized makes so we
        # don't need a real DB — we're testing the WIRING, not the
        # underlying signal_loader (covered separately).
        from app.services.llm import context as context_module
        with patch.object(context_module, "load_signals_for_tenant",
                          new=AsyncMock(return_value={})), \
             patch.object(ctx, "_load_open_incidents",
                          new=AsyncMock(return_value=[])), \
             patch("app.services.llm.context.settings.FEATURE_HEALTH_NORMALIZER", "true"):

            # Make the AsyncSession produce empty results for the four
            # SQL queries _load_fleet_normalized still issues
            # (device→site map, total sites, active incidents,
            # critical incidents).
            empty_results = [
                _empty_rows_result(),     # device→site map
                _scalar_result(0),         # total sites
                _scalar_result(0),         # active incidents
                _scalar_result(0),         # critical incidents
            ]
            ctx.db.execute = AsyncMock(side_effect=empty_results)

            result = await ctx.load_fleet()

        assert "health_normalizer:v1" in result.sources_used
        assert any("telnyx liveness" in s for s in result.sources_used)
        assert any("carrier liveness" in s for s in result.sources_used)
        assert any("inseego liveness" in s for s in result.sources_used)


# ═══════════════════════════════════════════════════════════════════
# Headline bug-fix: Telnyx-only liveness counts as CONNECTED
# ═══════════════════════════════════════════════════════════════════


class TestTelnyxOnlyLivenessIsConnected:
    """The HEALTH_STATUS_AUDIT.md Scenario B regression: a site whose
    only liveness signal is a fresh Telnyx CDR was previously counted
    as 'stale' / 'Not Connected'.  With the normalizer it counts as
    CONNECTED."""

    @pytest.mark.asyncio
    async def test_normalizer_treats_fresh_telnyx_cdr_as_connected(self):
        """Pure end-to-end on the normalizer: heartbeat=None,
        carrier_event=None, call_event=30s ago → CONNECTED.

        This is the most important behavioral change in the MVP.
        """
        sig = HealthSignals(
            last_heartbeat_at=None,
            last_carrier_event_at=None,
            last_call_event_at=_NOW - timedelta(seconds=30),
            last_vola_sync_at=None,
            device_lifecycle="active",
        )
        assert compute_device_state(sig, now=_NOW) == CanonicalDeviceState.CONNECTED

    @pytest.mark.asyncio
    async def test_normalizer_treats_fresh_carrier_event_as_connected(self):
        """Scenario A: Verizon poll wrote last_network_event recently,
        edge client never reported."""
        sig = HealthSignals(
            last_carrier_event_at=_NOW - timedelta(seconds=45),
            device_lifecycle="active",
        )
        assert compute_device_state(sig, now=_NOW) == CanonicalDeviceState.CONNECTED

    @pytest.mark.asyncio
    async def test_site_with_only_telnyx_evidence_rolls_up_connected(self):
        """End-to-end at site granularity: a single-device site whose
        only liveness is Telnyx → site state CONNECTED."""
        sig = HealthSignals(
            last_call_event_at=_NOW - timedelta(seconds=30),
            device_lifecycle="active",
        )
        device_state = compute_device_state(sig, now=_NOW)
        site_state = compute_site_state([device_state])
        assert site_state == CanonicalSiteState.CONNECTED


# ═══════════════════════════════════════════════════════════════════
# Surface containment: only AI Health Summary is touched
# ═══════════════════════════════════════════════════════════════════


class TestSurfaceContainment:
    """The MVP guarantee: only app/services/llm/context.py reads
    FEATURE_HEALTH_NORMALIZER.  Command Center, Map, Sites, Devices,
    and the attention engine must not import the health package.

    This is a static check executed at test time — it will fail
    the moment any future commit adds an unexpected import,
    catching a scope violation before it lands.
    """

    def test_only_llm_context_reads_the_flag(self):
        """grep-style guard: FEATURE_HEALTH_NORMALIZER must only be
        referenced in (a) app/config.py (declares it), (b) app/services/
        llm/context.py (consumes it), and (c) app/services/health/
        __init__.py (informational docstring).  Any other reference
        means the MVP scope was widened without governance."""
        import pathlib

        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        allowlist = {
            pathlib.Path("config.py"),
            pathlib.Path("services/llm/context.py"),
            pathlib.Path("services/health/__init__.py"),
        }
        offending = []
        for p in api_root.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if "FEATURE_HEALTH_NORMALIZER" not in text:
                continue
            rel = p.relative_to(api_root)
            if rel not in allowlist:
                offending.append(str(rel))
        assert not offending, (
            f"FEATURE_HEALTH_NORMALIZER referenced outside the allowlist: "
            f"{offending}.  MVP scope is AI Health Summary only.  Widening "
            f"the consumer list requires updating "
            f"docs/HEALTH_NORMALIZER_MVP.md and this test."
        )

    def test_command_map_sites_devices_attention_do_not_import_health_package(self):
        """The health package must only be imported by:
          * app/services/llm/context.py        (the AI Health Summary)
          * app/services/assurance/loader.py   (the Assurance Engine — approved
            second consumer; reuses compute_device_state/load_signals_for_site,
            flag-gated by FEATURE_ASSURANCE_ENGINE)
          * other modules within app/services/health/
          * app/services/device_health/         (the hardware-agnostic
                                                  Device Health layer — a
                                                  governed consumer behind
                                                  FEATURE_DEVICE_HEALTH; see
                                                  docs/DEVICE_HEALTH_LAYER.md)
          * test files

        Any OTHER import means the rollout (Devices → Command → Map
        → Attention) jumped ahead of plan.

        Uses a precise import pattern — ``from app.services.health
        import`` / ``import app.services.health`` — so the legacy
        ``app.services.health_scoring`` module (unrelated, predates
        the new package) is not a false positive.
        """
        import pathlib
        import re

        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        # Match only the exact package, not health_scoring / health_check / etc.
        import_pattern = re.compile(
            r"^\s*(?:from|import)\s+app\.services\.health\b(?!_)",
            re.MULTILINE,
        )
        offending = []
        for p in api_root.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if not import_pattern.search(text):
                continue
            rel = p.relative_to(api_root)
            allowed = (
                rel == pathlib.Path("services/llm/context.py")
                or rel == pathlib.Path("services/assurance/loader.py")
                or rel.parts[:2] == ("services", "health")
                or rel.parts[:2] == ("services", "device_health")
            )
            if not allowed:
                offending.append(str(rel))
        assert not offending, (
            f"app.services.health imported outside the allowlist: "
            f"{offending}.  The MVP only wires the AI Health Summary."
        )


# ─── Helpers ────────────────────────────────────────────────────────


def _empty_rows_result():
    r = MagicMock()
    r.all.return_value = []
    return r


def _scalar_result(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r
