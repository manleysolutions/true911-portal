"""Tests for the hardware-agnostic device-health layer.

Pure logic + vendor adapters (mocked) get full coverage here, following the
house pattern (no in-memory DB).  The DB assembly (service.build_device_health)
and the flag-gated routes are exercised against real Postgres before launch
(see docs/DEVICE_HEALTH_LAYER.md).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.device_health import (
    DeviceHealth,
    NormalizedStatus,
    ReasonCode,
    VendorStatus,
    classify,
    recommend,
)
from app.services.device_health.adapters import (
    ALL_VENDORS,
    adapter_status_summary,
    get_status_adapter,
)
from app.services.device_health.adapters.tmobile import TMobileAdapter
from app.services.device_health.adapters.vola import VolaCloudAdapter
from app.services.device_health.classifier import normalize_carrier
from app.services.device_health.reason_codes import primary_reason
from app.services.device_health.scoring import DeviceContext, score
from app.services.device_health.status import from_canonical
from app.services.health.signals import HealthSignals
from app.services.health.states import CanonicalDeviceState
from app.sync_device_health import compute_device_updates

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def fresh(seconds_ago: int = 0) -> datetime:
    return NOW - timedelta(seconds=seconds_ago)


# ── Classifier ───────────────────────────────────────────────────────
class TestClassifier:
    def test_lm150_is_vola_cellular_volte(self):
        c = classify(model="LM150", device_type="VoLTE ATA",
                     hardware_model_id="flyingvoice-lm150", carrier="tmobile")
        assert c.vendor_cloud == "vola"
        assert c.connection_type == "cellular"
        assert c.voice_type == "volte"
        assert c.carrier_vendor == "tmobile"
        assert c.probe_vendors == ("vola", "tmobile")

    def test_cisco_ata_is_sip_over_lte_with_telnyx(self):
        c = classify(model="Cisco ATA191", carrier="tmobile")
        assert c.connection_type == "sip_over_lte"
        assert c.voice_type == "analog"
        assert "telnyx" in c.probe_vendors
        assert "tmobile" in c.probe_vendors

    def test_inseego_is_cellular_modem(self):
        c = classify(model="Inseego FX3100", device_type="Cellular Router")
        assert c.connection_type == "cellular_modem"
        assert c.vendor_cloud is None

    def test_ms130_classifies_without_vendor_cloud(self):
        c = classify(model="MS130v4", carrier="verizon")
        assert c.connection_type == "cellular"
        assert c.carrier_vendor == "verizon"
        assert c.vendor_cloud is None

    def test_unknown_device_with_carrier_is_cellular(self):
        c = classify(model="MysteryBox-9000", carrier="t-mobile")
        assert c.connection_type == "cellular"
        assert c.probe_vendors == ("tmobile",)

    def test_carrier_aliases(self):
        assert normalize_carrier("T-Mobile") == "tmobile"
        assert normalize_carrier("VZW") == "verizon"
        assert normalize_carrier(None) is None


# ── Status mapping ───────────────────────────────────────────────────
class TestStatusMapping:
    def test_canonical_to_normalized(self):
        assert from_canonical(CanonicalDeviceState.CONNECTED) == NormalizedStatus.ONLINE
        assert from_canonical(CanonicalDeviceState.ATTENTION) == NormalizedStatus.ATTENTION
        assert from_canonical(CanonicalDeviceState.OFFLINE) == NormalizedStatus.OFFLINE
        assert from_canonical(CanonicalDeviceState.PROVISIONING) == NormalizedStatus.UNKNOWN
        assert from_canonical(CanonicalDeviceState.DECOMMISSIONED) == NormalizedStatus.UNKNOWN


# ── Reason codes / recommended action ────────────────────────────────
class TestReasons:
    def test_primary_reason_orders_by_urgency(self):
        assert primary_reason([ReasonCode.MISSING_CREDENTIALS,
                               ReasonCode.DEVICE_OFFLINE]) == ReasonCode.DEVICE_OFFLINE
        assert primary_reason([]) == ReasonCode.OK

    def test_recommend_maps_each_reason(self):
        assert "No action" in recommend([ReasonCode.OK])
        assert "SIM" in recommend([ReasonCode.SIM_INACTIVE])
        assert "VoLTE" in recommend([ReasonCode.VOLTE_NOT_READY])
        assert "registered" in recommend([ReasonCode.SIP_UNREGISTERED])


# ── Scoring ──────────────────────────────────────────────────────────
class TestScoring:
    def test_online_ok(self):
        s = score(HealthSignals(last_heartbeat_at=fresh(0)), now=NOW)
        assert s.status == NormalizedStatus.ONLINE
        assert s.reasons == [ReasonCode.OK]

    def test_stale_is_offline(self):
        s = score(HealthSignals(last_heartbeat_at=fresh(600)), now=NOW)
        assert s.status == NormalizedStatus.OFFLINE
        assert ReasonCode.DEVICE_OFFLINE in s.reasons

    def test_never_seen_is_unknown_no_heartbeat(self):
        s = score(HealthSignals(device_lifecycle="provisioning"), now=NOW)
        assert s.status == NormalizedStatus.UNKNOWN
        assert ReasonCode.NO_RECENT_HEARTBEAT in s.reasons

    def test_sim_inactive_downgrades_fresh_device(self):
        s = score(HealthSignals(last_heartbeat_at=fresh(0)),
                  DeviceContext(sim_status="suspended"), now=NOW)
        assert s.status == NormalizedStatus.ATTENTION
        assert ReasonCode.SIM_INACTIVE in s.reasons

    def test_volte_not_ready(self):
        s = score(HealthSignals(last_heartbeat_at=fresh(0)),
                  DeviceContext(voice_type="volte", volte_enabled=False,
                                has_call_history=True), now=NOW)
        assert s.status == NormalizedStatus.ATTENTION
        assert ReasonCode.VOLTE_NOT_READY in s.reasons

    def test_sip_unregistered_is_attention(self):
        s = score(HealthSignals(last_heartbeat_at=fresh(0), sip_status="unregistered"),
                  now=NOW)
        assert s.status == NormalizedStatus.ATTENTION
        assert ReasonCode.SIP_UNREGISTERED in s.reasons

    def test_network_disconnected_is_attention(self):
        s = score(HealthSignals(last_heartbeat_at=fresh(0), network_status="disconnected"),
                  now=NOW)
        assert s.status == NormalizedStatus.ATTENTION
        assert ReasonCode.DEVICE_OFFLINE in s.reasons

    def test_voice_device_no_calls_flags_informational(self):
        s = score(HealthSignals(last_heartbeat_at=fresh(0)),
                  DeviceContext(voice_type="volte", has_call_history=False), now=NOW)
        assert s.status == NormalizedStatus.ONLINE
        assert ReasonCode.NO_RECENT_CALL_ACTIVITY in s.reasons


# ── DeviceHealth / customer view ─────────────────────────────────────
class TestModels:
    def _belle_terre_unit(self) -> DeviceHealth:
        return DeviceHealth(
            tenant_id="integrity-pm", device_id="VOLA-VOLA00325600226",
            device_name="Elevator 1", model="LM150", carrier="tmobile",
            site_name="Belle Terre at Sunrise", service_unit_id="IPM-BELLE-TERRE-EL1",
            service_unit_name="Elevator 1", connection_type="cellular",
            voice_type="volte", status=NormalizedStatus.ONLINE,
            reason_codes=[ReasonCode.OK], recommended_action="No action needed.",
            last_check_in=NOW)

    def test_customer_view_simple_language(self):
        view = self._belle_terre_unit().to_customer_view()
        assert view["property"] == "Belle Terre at Sunrise"
        assert view["unit"] == "Elevator 1"
        assert view["device"] == "Elevator 1"
        assert view["carrier"] == "tmobile"
        assert view["voice_path"] == "VoLTE"
        assert view["status"] == "Online"
        assert "recommended_action" in view

    def test_to_dict_includes_reason_codes(self):
        d = self._belle_terre_unit().to_dict()
        assert d["status"] == "Online"
        assert d["reason_codes"] == ["OK"]
        assert d["voice_type"] == "volte"


# ── Vola adapter ─────────────────────────────────────────────────────
class _FakeVolaClient:
    def __init__(self, device_list=None, raise_exc=None):
        self._device_list = device_list or []
        self._raise = raise_exc

    async def get_device_list(self, usage_status="inUse"):
        if self._raise:
            raise self._raise
        return {"deviceList": self._device_list}


class TestVolaAdapter:
    @pytest.mark.asyncio
    async def test_missing_credentials(self, monkeypatch):
        monkeypatch.setattr(settings, "VOLA_EMAIL", "")
        monkeypatch.setattr(settings, "VOLA_PASSWORD", "")
        vs = await VolaCloudAdapter().probe(serial="VOLA00325600226")
        assert vs.available is False
        assert ReasonCode.MISSING_CREDENTIALS in vs.reason_codes

    @pytest.mark.asyncio
    async def test_online_match_by_serial(self, monkeypatch):
        monkeypatch.setattr(settings, "VOLA_EMAIL", "x@example.com")
        monkeypatch.setattr(settings, "VOLA_PASSWORD", "pw")
        client = _FakeVolaClient([{"deviceSN": "VOLA00325600226", "status": "Online",
                                   "softwareVersion": "1.0.9", "ip": "10.0.0.5"}])
        vs = await VolaCloudAdapter(client=client).probe(serial="VOLA00325600226")
        assert vs.available is True
        assert vs.normalized_status == NormalizedStatus.ONLINE
        assert vs.firmware == "1.0.9"
        assert vs.static_ip == "10.0.0.5"
        assert vs.reason_codes == [ReasonCode.OK]

    @pytest.mark.asyncio
    async def test_offline_and_not_found(self, monkeypatch):
        monkeypatch.setattr(settings, "VOLA_EMAIL", "x@example.com")
        monkeypatch.setattr(settings, "VOLA_PASSWORD", "pw")
        client = _FakeVolaClient([{"deviceSN": "VOLA00325600227", "status": "Offline"}])
        off = await VolaCloudAdapter(client=client).probe(serial="VOLA00325600227")
        assert off.normalized_status == NormalizedStatus.OFFLINE
        assert ReasonCode.DEVICE_OFFLINE in off.reason_codes
        missing = await VolaCloudAdapter(client=client).probe(serial="NOPE")
        assert missing.reason_codes == [ReasonCode.DEVICE_NOT_FOUND]

    @pytest.mark.asyncio
    async def test_api_failure(self, monkeypatch):
        monkeypatch.setattr(settings, "VOLA_EMAIL", "x@example.com")
        monkeypatch.setattr(settings, "VOLA_PASSWORD", "pw")
        client = _FakeVolaClient(raise_exc=RuntimeError("boom"))
        vs = await VolaCloudAdapter(client=client).probe(serial="VOLA00325600226")
        assert vs.available is False
        assert ReasonCode.VENDOR_API_UNAVAILABLE in vs.reason_codes


# ── T-Mobile adapter ─────────────────────────────────────────────────
class _FakeTMobileClient:
    def __init__(self, configured=True, response=None, raise_exc=None):
        self._configured = configured
        self._response = response or {}
        self._raise = raise_exc

    @property
    def is_configured(self):
        return self._configured

    async def subscriber_inquiry(self, msisdn):
        if self._raise:
            raise self._raise
        return self._response


class TestTMobileAdapter:
    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        vs = await TMobileAdapter(client=_FakeTMobileClient(configured=False)).probe(
            msisdn="7542697860")
        assert vs.available is False
        assert ReasonCode.MISSING_CREDENTIALS in vs.reason_codes

    @pytest.mark.asyncio
    async def test_iccid_only_is_unsupported(self):
        vs = await TMobileAdapter(client=_FakeTMobileClient()).probe(
            iccid="8901240204219433645")
        assert vs.normalized_status == NormalizedStatus.UNKNOWN
        assert ReasonCode.DEVICE_NOT_FOUND in vs.reason_codes
        assert "MSISDN" in vs.error

    @pytest.mark.asyncio
    async def test_active_subscriber(self):
        client = _FakeTMobileClient(response={"status": "active", "iccid": "89012"})
        vs = await TMobileAdapter(client=client).probe(msisdn="7542697860")
        assert vs.normalized_status == NormalizedStatus.ONLINE
        assert vs.sim_status == "active"
        assert vs.reason_codes == [ReasonCode.OK]

    @pytest.mark.asyncio
    async def test_suspended_subscriber(self):
        client = _FakeTMobileClient(response={"status": "suspended"})
        vs = await TMobileAdapter(client=client).probe(msisdn="7542697860")
        assert vs.normalized_status == NormalizedStatus.OFFLINE
        assert ReasonCode.SIM_INACTIVE in vs.reason_codes

    @pytest.mark.asyncio
    async def test_api_error(self):
        client = _FakeTMobileClient(raise_exc=RuntimeError("503"))
        vs = await TMobileAdapter(client=client).probe(msisdn="7542697860")
        assert vs.available is False
        assert ReasonCode.VENDOR_API_UNAVAILABLE in vs.reason_codes


# ── Registry ─────────────────────────────────────────────────────────
class TestRegistry:
    def test_known_vendors_resolve(self):
        assert get_status_adapter("vola").vendor == "vola"
        assert get_status_adapter("tmobile").vendor == "tmobile"

    def test_unknown_vendor_falls_back_to_future(self):
        assert get_status_adapter("nope").vendor == "future"
        assert get_status_adapter(None).vendor == "future"

    def test_adapter_status_summary_shape(self):
        summary = adapter_status_summary()
        assert len(summary) == len(ALL_VENDORS)
        for row in summary:
            assert "vendor" in row and "configured" in row


# ── Sync update computation ──────────────────────────────────────────
class TestSyncUpdates:
    def test_vola_status_updates_sync_and_firmware(self):
        statuses = [VendorStatus(vendor="vola", available=True,
                                 normalized_status=NormalizedStatus.ONLINE,
                                 firmware="1.0.9", static_ip="10.0.0.5")]
        changes = compute_device_updates(statuses, now=NOW)
        assert changes["device"]["vola_last_sync"] == NOW
        assert changes["device"]["firmware_version"] == "1.0.9"
        assert changes["device"]["wan_ip"] == "10.0.0.5"

    def test_tmobile_active_updates_network_event_and_sim(self):
        statuses = [VendorStatus(vendor="tmobile", available=True,
                                 normalized_status=NormalizedStatus.ONLINE,
                                 sim_status="active")]
        changes = compute_device_updates(statuses, now=NOW)
        assert changes["device"]["last_network_event"] == NOW
        assert changes["sim"]["status"] == "active"

    def test_unavailable_status_is_ignored(self):
        statuses = [VendorStatus(vendor="vola", available=False,
                                 reason_codes=[ReasonCode.MISSING_CREDENTIALS])]
        changes = compute_device_updates(statuses, now=NOW)
        assert changes["device"] == {}
        assert changes["sim"] == {}


# ── Tenant isolation (router helpers + model contract) ───────────────
class TestTenantIsolation:
    def test_device_health_carries_only_its_tenant(self):
        # The service stamps tenant_id from the scoped query arg; a DeviceHealth
        # never carries a foreign tenant. (DB scoping itself is covered by the
        # signals_loader contract this service reuses.)
        dh = DeviceHealth(tenant_id="integrity-pm", device_id="d1")
        assert dh.tenant_id == "integrity-pm"
        assert dh.to_dict()["tenant_id"] == "integrity-pm"

    def test_property_rollup_worst_wins(self):
        from app.routers.device_health import _rollup, _status_counts
        healths = [
            DeviceHealth(tenant_id="t", device_id="a", status=NormalizedStatus.ONLINE),
            DeviceHealth(tenant_id="t", device_id="b", status=NormalizedStatus.ATTENTION),
        ]
        assert _rollup(healths) == "Attention Needed"
        counts = _status_counts(healths)
        assert counts["Online"] == 1 and counts["Attention Needed"] == 1
        assert _rollup([]) == "Unknown"
