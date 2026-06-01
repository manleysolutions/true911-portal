"""Tests for the Vola health chain: adapter capture (last heartbeat / signal),
sync online/offline persistence, customer-view fields, and the hardware-agnostic
boundary (core never imports vendor adapters)."""

from __future__ import annotations

import pathlib
import re
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.services.device_health.adapters.vola import VolaCloudAdapter, _parse_vola_timestamp
from app.services.device_health.models import DeviceHealth, VendorStatus
from app.services.device_health.status import NormalizedStatus
from app.sync_device_health import compute_device_updates

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


class _FakeVola:
    def __init__(self, devices):
        self._devices = devices

    async def get_device_list(self, usage_status="inUse"):
        return {"deviceList": self._devices}


# ── Adapter captures last heartbeat + signal ─────────────────────────
class TestVolaAdapterCapture:
    @pytest.mark.asyncio
    async def test_captures_last_seen_firmware_ip(self, monkeypatch):
        monkeypatch.setattr(settings, "VOLA_EMAIL", "x@example.com")
        monkeypatch.setattr(settings, "VOLA_PASSWORD", "pw")
        client = _FakeVola([{
            "deviceSN": "VOLA00325600226", "status": "Online",
            "softwareVersion": "1.0.9", "ip": "10.0.0.5",
            "lastUpdateTime": "Jun 01 2026 09:00", "rssi": "-71",
        }])
        vs = await VolaCloudAdapter(client=client).probe(serial="VOLA00325600226")
        assert vs.normalized_status == NormalizedStatus.ONLINE
        assert vs.firmware == "1.0.9"
        assert vs.static_ip == "10.0.0.5"
        assert vs.last_seen is not None and vs.last_seen.year == 2026
        assert vs.signal_strength == -71.0

    def test_parse_vola_timestamp(self):
        assert _parse_vola_timestamp("Jun 01 2026 09:00").hour == 9
        assert _parse_vola_timestamp("2026-06-01T09:00:00Z").tzinfo is not None
        assert _parse_vola_timestamp("not a date") is None
        assert _parse_vola_timestamp(None) is None


# ── Sync persists online/offline distinctly ──────────────────────────
class TestSyncOnlineOffline:
    def test_online_refreshes_liveness_and_heartbeat(self):
        vs = VendorStatus(vendor="vola", available=True,
                          normalized_status=NormalizedStatus.ONLINE,
                          firmware="1.0.9", static_ip="10.0.0.5", last_seen=NOW)
        ch = compute_device_updates([vs], now=NOW)["device"]
        assert ch["vola_last_sync"] == NOW
        assert ch["network_status"] == "online"
        assert ch["firmware_version"] == "1.0.9"
        assert ch["wan_ip"] == "10.0.0.5"
        assert ch["last_heartbeat"] == NOW

    def test_offline_does_not_refresh_liveness(self):
        vs = VendorStatus(vendor="vola", available=True,
                          normalized_status=NormalizedStatus.OFFLINE)
        ch = compute_device_updates([vs], now=NOW)["device"]
        assert "vola_last_sync" not in ch       # not kept "fresh"
        assert ch["network_status"] == "offline"


# ── Customer view exposes the Part-5 fields, no raw payloads ─────────
class TestCustomerViewFields:
    def test_view_has_type_heartbeat_firmware(self):
        dh = DeviceHealth(
            tenant_id="integrity-pm", device_id="VOLA-VOLA00325600226",
            service_unit_name="Elevator 1", device_name="Elevator 1",
            model="LM150", carrier="tmobile", site_name="Belle Terre at Sunrise",
            voice_type="volte", status=NormalizedStatus.ONLINE, firmware="1.0.9",
            last_heartbeat=NOW, last_check_in=NOW,
            recommended_action="No action needed.")
        v = dh.to_customer_view()
        assert v["device_type"] == "LM150"
        assert v["firmware"] == "1.0.9"
        assert v["last_heartbeat"] is not None
        assert v["status"] == "Online"
        # never leak raw vendor payloads to the customer
        assert "raw_payload" not in v
        assert "vendors" not in v
        assert "vola_org_id" not in v


# ── Hardware-agnostic boundary ───────────────────────────────────────
class TestHardwareAgnosticCore:
    def test_core_modules_do_not_import_vendor_adapters(self):
        core = (pathlib.Path(__file__).resolve().parents[1]
                / "app" / "services" / "device_health")
        core_files = [
            "status.py", "reason_codes.py", "classifier.py", "scoring.py",
            "recommended_action.py", "models.py", "service.py", "__init__.py",
        ]
        vendor = re.compile(r"(adapters|integrations)\.(vola|tmobile|telnyx|inseego)")
        offenders = [f for f in core_files
                     if vendor.search((core / f).read_text(encoding="utf-8"))]
        assert not offenders, (
            f"core device_health modules must stay hardware-agnostic; vendor "
            f"imports found in: {offenders}"
        )
