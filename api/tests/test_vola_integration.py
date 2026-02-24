"""Tests for the Vola Connector proxy layer.

All connector HTTP calls are mocked with respx — no real connector or
Vola credentials needed.
"""

from __future__ import annotations

import pytest
import respx
import httpx
from unittest import mock

from app.config import settings


# Use a deterministic base URL for the mock connector
CONNECTOR = "http://test-connector:8811"


@pytest.fixture(autouse=True)
def _set_connector_url():
    """Point VOLA_CONNECTOR_BASE_URL at a fake host for every test."""
    with mock.patch.object(settings, "VOLA_CONNECTOR_BASE_URL", CONNECTOR):
        yield


# ── Auth: non-admin gets 403 ────────────────────────────────────────────────

@respx.mock
def test_non_admin_blocked(user_client):
    resp = user_client.get("/api/integrations/vola/health")
    assert resp.status_code == 403


# ── Health ───────────────────────────────────────────────────────────────────

@respx.mock
def test_health(admin_client):
    respx.get(f"{CONNECTOR}/health").mock(
        return_value=httpx.Response(200, json={
            "status": "ok",
            "service": "true911-vola-connector",
            "vola_base_url": "https://cloudapi.volanetworks.net",
        })
    )

    resp = admin_client.get("/api/integrations/vola/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Devices list ─────────────────────────────────────────────────────────────

@respx.mock
def test_devices_list(admin_client):
    respx.get(f"{CONNECTOR}/vola/devices").mock(
        return_value=httpx.Response(200, json={
            "total": 2,
            "devices": [
                {
                    "device_sn": "SN001",
                    "mac": "AA:BB:CC:DD:EE:01",
                    "model": "FIP16Plus",
                    "firmware_version": "1.2.3",
                    "ip": "10.0.0.11",
                    "status": "online",
                    "usage_status": "inUse",
                    "org_id": "org1",
                    "org_name": "Demo Org",
                },
                {
                    "device_sn": "SN002",
                    "mac": "AA:BB:CC:DD:EE:02",
                    "model": "FIP16Plus",
                    "firmware_version": "1.2.4",
                    "ip": "10.0.0.12",
                    "status": "offline",
                    "usage_status": "inUse",
                    "org_id": "org1",
                    "org_name": "Demo Org",
                },
            ],
        })
    )

    resp = admin_client.get("/api/integrations/vola/devices")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["devices"]) == 2
    assert body["devices"][0]["device_sn"] == "SN001"


@respx.mock
def test_devices_list_custom_status(admin_client):
    respx.get(f"{CONNECTOR}/vola/devices").mock(
        return_value=httpx.Response(200, json={"total": 0, "devices": []})
    )

    resp = admin_client.get("/api/integrations/vola/devices?usage_status=notInUse")
    assert resp.status_code == 200


# ── Reboot ───────────────────────────────────────────────────────────────────

@respx.mock
def test_reboot(admin_client):
    respx.post(f"{CONNECTOR}/vola/device/reboot").mock(
        return_value=httpx.Response(200, json={
            "task_id": "task_reboot_1",
        })
    )

    resp = admin_client.post("/api/integrations/vola/devices/SN001/reboot")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == "task_reboot_1"


# ── Get params sync ──────────────────────────────────────────────────────────

@respx.mock
def test_get_params_sync(admin_client):
    respx.post(f"{CONNECTOR}/vola/device/params/get_sync").mock(
        return_value=httpx.Response(200, json={
            "task_id": "task_gp_1",
            "device_sn": "SN001",
            "status": "success",
            "raw_task_result": {"taskId": "task_gp_1"},
            "extracted_values": {
                "Device.DeviceInfo.SoftwareVersion": "2.1.5",
                "Device.DeviceInfo.ModelName": "FIP16Plus",
            },
        })
    )

    resp = admin_client.post("/api/integrations/vola/devices/SN001/params/get_sync", json={
        "parameter_names": [
            "Device.DeviceInfo.SoftwareVersion",
            "Device.DeviceInfo.ModelName",
        ],
        "timeout_seconds": 15,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["extracted_values"]["Device.DeviceInfo.SoftwareVersion"] == "2.1.5"


# ── Set params sync ──────────────────────────────────────────────────────────

@respx.mock
def test_set_params_sync(admin_client):
    respx.post(f"{CONNECTOR}/vola/device/params/set_sync").mock(
        return_value=httpx.Response(200, json={
            "task_id": "task_sp_1",
            "device_sn": "SN001",
            "status": "success",
            "raw_task_result": {"taskId": "task_sp_1", "result": "ok"},
            "applied": {"Device.DeviceInfo.ProvisioningCode": "SITE-42"},
        })
    )

    resp = admin_client.post("/api/integrations/vola/devices/SN001/params/set_sync", json={
        "parameter_values": [["Device.DeviceInfo.ProvisioningCode", "SITE-42"]],
        "timeout_seconds": 15,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["applied"]["Device.DeviceInfo.ProvisioningCode"] == "SITE-42"


# ── Upstream errors propagate cleanly ────────────────────────────────────────

@respx.mock
def test_upstream_502(admin_client):
    respx.get(f"{CONNECTOR}/vola/devices").mock(
        return_value=httpx.Response(502, json={"detail": "Vola unreachable"})
    )

    resp = admin_client.get("/api/integrations/vola/devices")
    assert resp.status_code == 502


@respx.mock
def test_upstream_504_timeout(admin_client):
    respx.post(f"{CONNECTOR}/vola/device/params/get_sync").mock(
        return_value=httpx.Response(504, json={
            "detail": {
                "message": "Task did not complete within 20s",
                "task_id": "task_slow",
                "device_sn": "SN001",
            }
        })
    )

    resp = admin_client.post("/api/integrations/vola/devices/SN001/params/get_sync", json={
        "parameter_names": ["Device.DeviceInfo.SoftwareVersion"],
    })
    assert resp.status_code == 504


@respx.mock
def test_connector_unreachable(admin_client):
    """When the connector is completely down, we should get a 502."""
    respx.get(f"{CONNECTOR}/vola/devices").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    resp = admin_client.get("/api/integrations/vola/devices")
    assert resp.status_code == 502
    assert "unreachable" in resp.json()["detail"]


# ── API key header ───────────────────────────────────────────────────────────

@respx.mock
def test_api_key_sent_when_configured(admin_client):
    """Verify x-api-key header is forwarded to the connector."""
    route = respx.get(f"{CONNECTOR}/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    with mock.patch.object(settings, "VOLA_CONNECTOR_API_KEY", "secret-key-123"):
        resp = admin_client.get("/api/integrations/vola/health")

    assert resp.status_code == 200
    # Inspect the request that was sent to the connector
    assert route.calls[0].request.headers["x-api-key"] == "secret-key-123"
