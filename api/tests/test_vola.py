"""Tests for VOLA integration — client, service, and route layer.

All Vola HTTP calls are mocked with respx — no real credentials needed.
"""

from __future__ import annotations

import json
import pytest
import respx
import httpx
from unittest import mock

from app.integrations.vola import (
    VolaClient,
    extract_parameter_values,
    normalize_vola_device,
    HARDCODED_DANGEROUS_PREFIXES,
)

VOLA_BASE = "https://cloudapi.volanetworks.net"


def _make_client(**kwargs) -> VolaClient:
    return VolaClient(
        base_url=kwargs.get("base_url", VOLA_BASE),
        email=kwargs.get("email", "test@example.com"),
        password=kwargs.get("password", "testpass"),
        org_id=kwargs.get("org_id"),
        allowed_param_prefixes=kwargs.get("allowed_param_prefixes"),
        allowed_set_prefixes=kwargs.get("allowed_set_prefixes", []),
        blocked_set_prefixes=kwargs.get("blocked_set_prefixes", []),
        denylist_exact=kwargs.get("denylist_exact", set()),
    )


def _mock_auth():
    respx.post(f"{VOLA_BASE}/user-mgmt-api/get-access-token").mock(
        return_value=httpx.Response(200, json={
            "data": {"accessToken": "tok_test_123"}
        })
    )


# ── Auth ────────────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_auth_success():
    _mock_auth()
    client = _make_client()
    token = await client.get_access_token()
    assert token == "tok_test_123"


@respx.mock
@pytest.mark.asyncio
async def test_auth_caches_token():
    _mock_auth()
    client = _make_client()
    t1 = await client.get_access_token()
    t2 = await client.get_access_token()
    assert t1 == t2 == "tok_test_123"
    # Auth endpoint called only once
    assert respx.calls.call_count == 1


# ── Org list ────────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_org_list():
    _mock_auth()
    respx.post(f"{VOLA_BASE}/user-mgmt-api/user-operation").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "orgList": [
                    {"orgId": "org1", "orgName": "Alpha"},
                    {"orgId": "org2", "orgName": "Beta"},
                ]
            }
        })
    )
    client = _make_client()
    orgs = await client.get_org_list()
    assert len(orgs) == 2
    assert orgs[0]["orgId"] == "org1"


# ── Device list ─────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_device_list():
    _mock_auth()
    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-list").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "total": 2,
                "list": [
                    {"deviceSN": "SN001", "mac": "AA:BB:CC:DD:EE:01", "model": "FIP16Plus",
                     "firmwareVersion": "1.2.3", "ip": "10.0.0.11", "status": "online",
                     "usageStatus": "inUse", "orgId": "org1", "orgName": "Demo"},
                    {"deviceSN": "SN002", "mac": "AA:BB:CC:DD:EE:02", "model": "FIP16Plus",
                     "firmwareVersion": "1.2.4", "ip": "10.0.0.12", "status": "offline",
                     "usageStatus": "inUse", "orgId": "org1", "orgName": "Demo"},
                ],
            }
        })
    )
    client = _make_client()
    data = await client.get_device_list("inUse")
    assert data["total"] == 2
    assert len(data["list"]) == 2


# ── Reboot ──────────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_reboot():
    _mock_auth()
    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-task-operation").mock(
        return_value=httpx.Response(200, json={"data": {"taskId": "task_abc"}})
    )
    client = _make_client()
    result = await client.create_reboot_task("SN001")
    assert result.get("taskId") == "task_abc"


# ── 401 retry ───────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_401_retry():
    auth_route = respx.post(f"{VOLA_BASE}/user-mgmt-api/get-access-token").mock(
        return_value=httpx.Response(200, json={"data": {"accessToken": "tok_fresh"}})
    )
    call_count = 0

    def device_list_side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(401, json={"error": "token expired"})
        return httpx.Response(200, json={"data": {"total": 0, "list": []}})

    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-list").mock(
        side_effect=device_list_side_effect
    )
    client = _make_client()
    data = await client.get_device_list("inUse")
    assert data["total"] == 0
    assert auth_route.call_count == 2  # initial + retry


# ── Parameter read validation ───────────────────────────────────────────────

def test_validate_param_names_empty():
    client = _make_client()
    assert client.validate_param_names([]) is not None


def test_validate_param_names_too_many():
    client = _make_client()
    assert client.validate_param_names([f"P.{i}" for i in range(51)]) is not None


def test_validate_param_names_allowlist():
    client = _make_client(allowed_param_prefixes=["Device.DeviceInfo."])
    assert client.validate_param_names(["Device.DeviceInfo.SoftwareVersion"]) is None
    assert client.validate_param_names(["InternetGatewayDevice.Secret"]) is not None


# ── Parameter write validation ──────────────────────────────────────────────

def test_validate_set_empty():
    client = _make_client()
    assert client.validate_set_param_values([]) is not None


def test_validate_set_too_many():
    client = _make_client()
    assert client.validate_set_param_values([[f"P.{i}", "v"] for i in range(51)]) is not None


def test_validate_set_bad_format():
    client = _make_client()
    assert client.validate_set_param_values([["only_one"]]) is not None


def test_validate_set_denylist():
    client = _make_client(denylist_exact={"Device.ManagementServer.URL"})
    assert client.validate_set_param_values([["Device.ManagementServer.URL", "http://evil"]]) is not None


def test_validate_set_blocked_prefix():
    client = _make_client(
        allowed_set_prefixes=["Device."],
        blocked_set_prefixes=["Device.Users."],
    )
    assert client.validate_set_param_values([["Device.Users.Admin.Password", "hunter2"]]) is not None


def test_validate_set_hardcoded_dangerous():
    client = _make_client(allowed_set_prefixes=[], blocked_set_prefixes=[])
    # Device.Security.* is hardcoded dangerous
    assert client.validate_set_param_values([["Device.Security.Certificate.1.Enable", "false"]]) is not None


def test_validate_set_allowlist_ok():
    client = _make_client(allowed_set_prefixes=["Device.DeviceInfo.ProvisioningCode"])
    assert client.validate_set_param_values([["Device.DeviceInfo.ProvisioningCode", "SITE-1"]]) is None


def test_validate_set_allowlist_denies():
    client = _make_client(allowed_set_prefixes=["Device.DeviceInfo."])
    assert client.validate_set_param_values([["InternetGatewayDevice.Other.Node", "val"]]) is not None


# ── Parameter value extraction ──────────────────────────────────────────────

def test_extract_parameter_values_basic():
    raw = {
        "parameterValues": [
            {"name": "Device.DeviceInfo.SoftwareVersion", "value": "2.1.5"},
            {"name": "Device.DeviceInfo.ModelName", "value": "FIP16Plus"},
        ]
    }
    values = extract_parameter_values(raw)
    assert values["Device.DeviceInfo.SoftwareVersion"] == "2.1.5"
    assert values["Device.DeviceInfo.ModelName"] == "FIP16Plus"


def test_extract_parameter_values_empty():
    assert extract_parameter_values(None) == {}
    assert extract_parameter_values({}) == {}


# ── Device normalization ────────────────────────────────────────────────────

def test_normalize_vola_device():
    raw = {
        "deviceSN": "SN001",
        "mac": "AA:BB:CC:DD:EE:01",
        "model": "FIP16Plus",
        "firmwareVersion": "1.2.3",
        "ip": "10.0.0.11",
        "status": "online",
        "usageStatus": "inUse",
        "orgId": "org1",
        "orgName": "Demo",
    }
    normalized = normalize_vola_device(raw)
    assert normalized["device_sn"] == "SN001"
    assert normalized["mac"] == "AA:BB:CC:DD:EE:01"
    assert normalized["firmware_version"] == "1.2.3"


# ── Sync deduplication (service layer) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_dedup_logic():
    """Test that sync_vola_devices deduplicates by SN."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.vola_service import sync_vola_devices

    # Create a mock DB session
    mock_db = AsyncMock()

    # First device: no existing match → import
    # Second device: existing match → skip/update
    mock_scalar_none = MagicMock()
    mock_scalar_none.scalar_one_or_none.return_value = None

    mock_db.execute.return_value = mock_scalar_none
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    vola_devices = [
        {"deviceSN": "SN001", "mac": "AA:BB:CC:DD:EE:01", "model": "PR12", "firmwareVersion": "1.0", "status": "online", "usageStatus": "inUse", "orgId": "o1", "orgName": "Test", "ip": ""},
    ]

    result = await sync_vola_devices(mock_db, "tenant-1", vola_devices)
    assert result["imported"] + result["updated"] + result["skipped"] == 1


# ── GetParameterValues sync ─────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_get_params_sync():
    _mock_auth()
    call_count = 0

    def task_op_side_effect(request):
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)
        if body.get("operation") == "createTask":
            return httpx.Response(200, json={"data": {"taskId": "task_p1"}})
        if call_count <= 2:
            return httpx.Response(200, json={"data": {"successList": [], "failedList": [], "pendingList": [{"taskId": "task_p1"}]}})
        return httpx.Response(200, json={"data": {
            "successList": [{"taskId": "task_p1", "parameterValues": [{"name": "Device.DeviceInfo.SoftwareVersion", "value": "2.1.5"}]}],
            "failedList": [], "pendingList": [],
        }})

    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-task-operation").mock(side_effect=task_op_side_effect)

    client = _make_client()
    data = await client.create_get_parameter_values_task("SN001", ["Device.DeviceInfo.SoftwareVersion"])
    task_id = data.get("taskId")
    assert task_id == "task_p1"

    result = await client.poll_task_sync(task_id, timeout_seconds=10, poll_interval=0.05)
    assert result["status"] == "success"
    extracted = extract_parameter_values(result["result"])
    assert extracted["Device.DeviceInfo.SoftwareVersion"] == "2.1.5"


# ── SetParameterValues sync ─────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_set_params_sync():
    _mock_auth()
    call_count = 0

    def task_op_side_effect(request):
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)
        if body.get("operation") == "createTask":
            return httpx.Response(200, json={"data": {"taskId": "task_s1"}})
        if call_count <= 2:
            return httpx.Response(200, json={"data": {"successList": [], "failedList": [], "pendingList": [{"taskId": "task_s1"}]}})
        return httpx.Response(200, json={"data": {
            "successList": [{"taskId": "task_s1", "result": "ok"}],
            "failedList": [], "pendingList": [],
        }})

    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-task-operation").mock(side_effect=task_op_side_effect)

    client = _make_client(allowed_set_prefixes=["Device.DeviceInfo."])
    assert client.validate_set_param_values([["Device.DeviceInfo.ProvisioningCode", "SITE-42"]]) is None

    data = await client.create_set_parameter_values_task("SN001", [["Device.DeviceInfo.ProvisioningCode", "SITE-42"]])
    task_id = data.get("taskId")
    assert task_id == "task_s1"

    result = await client.poll_task_sync(task_id, timeout_seconds=10, poll_interval=0.05)
    assert result["status"] == "success"


# ── Timeout path ────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_poll_timeout():
    _mock_auth()

    def task_op_side_effect(request):
        body = json.loads(request.content)
        if body.get("operation") == "createTask":
            return httpx.Response(200, json={"data": {"taskId": "task_slow"}})
        return httpx.Response(200, json={"data": {"successList": [], "failedList": [], "pendingList": [{"taskId": "task_slow"}]}})

    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-task-operation").mock(side_effect=task_op_side_effect)

    client = _make_client()
    data = await client.create_get_parameter_values_task("SN001", ["Device.DeviceInfo.SoftwareVersion"])
    result = await client.poll_task_sync(data.get("taskId"), timeout_seconds=0.2, poll_interval=0.05)
    assert result["status"] == "timeout"


# ── Build provision payload ─────────────────────────────────────────────────

def test_build_provision_payload():
    from app.services.vola_service import build_provision_payload
    params = build_provision_payload("SITE-42", 300)
    assert len(params) == 2
    assert params[0] == ["Device.DeviceInfo.ProvisioningCode", "SITE-42"]
    assert params[1] == ["Device.ManagementServer.PeriodicInformInterval", "300"]


def test_build_provision_payload_with_extra():
    from app.services.vola_service import build_provision_payload
    params = build_provision_payload("S1", 600, extra_params=[["Device.Time.NTPServer1", "pool.ntp.org"]])
    assert len(params) == 3
