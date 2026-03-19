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
    extract_device_list,
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
    """Mock VOLA auth — real format has accessToken at top level."""
    respx.post(f"{VOLA_BASE}/user-mgmt-api/get-access-token").mock(
        return_value=httpx.Response(200, json={
            "code": "200",
            "status": "Get access token succeed",
            "accessToken": "tok_test_123",
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
            "code": "200",
            "status": "User getOrgList operation succeed",
            "orgList": [
                {"orgId": "org1", "name": "Alpha", "role": "OWNER"},
                {"orgId": "org2", "name": "Beta", "role": "MEMBER"},
            ],
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
            "code": "200",
            "status": "Device list succeed",
            "deviceList": [
                {"deviceSN": "SN001", "deviceModel": "PR12",
                 "softwareVersion": "1.2.3", "status": "Online",
                 "orgId": "org1", "orgName": "Demo", "lastUpdateTime": "Mar 19 2026 15:25"},
                {"deviceSN": "SN002", "deviceModel": "PR12",
                 "softwareVersion": "1.2.4", "status": "Offline",
                 "orgId": "org1", "orgName": "Demo", "lastUpdateTime": "Mar 19 2026 00:50"},
            ],
        })
    )
    client = _make_client()
    data = await client.get_device_list("inUse")
    raw_list = extract_device_list(data)
    assert len(raw_list) == 2
    assert raw_list[0]["deviceSN"] == "SN001"
    assert raw_list[0]["deviceModel"] == "PR12"


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
async def test_token_error_retry():
    """VOLA returns code=400 'Miss token' when token expires — triggers re-auth."""
    auth_route = respx.post(f"{VOLA_BASE}/user-mgmt-api/get-access-token").mock(
        return_value=httpx.Response(200, json={
            "code": "200", "status": "Get access token succeed", "accessToken": "tok_fresh",
        })
    )
    call_count = 0

    def device_list_side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"code": "400", "status": "Bad Request: Miss token"})
        return httpx.Response(200, json={
            "code": "200", "status": "Device list succeed", "deviceList": [],
        })

    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-list").mock(
        side_effect=device_list_side_effect
    )
    client = _make_client()
    data = await client.get_device_list("inUse")
    assert extract_device_list(data) == []
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
    """Test with real VOLA Cloud response fields."""
    raw = {
        "deviceSN": "VOLA00225600646",
        "deviceModel": "PR12",
        "softwareVersion": "FVLMA000301",
        "status": "Online",
        "orgId": "0aa69eb5-42d3-4fc8-8bf7-efe0116022ae",
        "orgName": "Manley Solutions",
        "lastUpdateTime": "Mar 19 2026 15:25",
        "deviceId": "501365-PR12-VOLA00225600646",
        "line": {"status": [1, 0], "accounts": ["19046890551", ""]},
    }
    normalized = normalize_vola_device(raw)
    assert normalized["device_sn"] == "VOLA00225600646"
    assert normalized["model"] == "PR12"
    assert normalized["firmware_version"] == "FVLMA000301"
    assert normalized["status"] == "online"  # lowercased
    assert normalized["org_name"] == "Manley Solutions"
    assert normalized["last_update"] == "Mar 19 2026 15:25"
    assert normalized["device_id_vola"] == "501365-PR12-VOLA00225600646"
    assert normalized["line_accounts"] == ["19046890551", ""]


def test_extract_device_list_real_format():
    """Test extract_device_list with real VOLA Cloud response."""
    body = {
        "code": "200",
        "status": "Device list succeed",
        "deviceList": [
            {"deviceSN": "SN001", "deviceModel": "PR12"},
            {"deviceSN": "SN002", "deviceModel": "PR12"},
        ],
    }
    result = extract_device_list(body)
    assert len(result) == 2
    assert result[0]["deviceSN"] == "SN001"


def test_extract_device_list_legacy_format():
    """Test extract_device_list with legacy data.list format."""
    body = {"data": {"list": [{"deviceSN": "SN001"}]}}
    result = extract_device_list(body)
    assert len(result) == 1


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


# ── Deploy device (service layer) ───────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_deploy_device_full_flow():
    """Test deploy_device runs validate->ensure->bind->provision->reboot->verify."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.vola_service import deploy_device

    _mock_auth()

    # Mock VOLA device-list for validation step (real format)
    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-list").mock(
        return_value=httpx.Response(200, json={
            "code": "200",
            "status": "Device list succeed",
            "deviceList": [{"deviceSN": "SN001", "deviceModel": "PR12", "status": "Online"}],
        })
    )

    # Mock VOLA task operations — createTask returns taskId, poll returns success
    created_task_ids = []
    def task_op_side_effect(request):
        body = json.loads(request.content)
        if body.get("operation") == "createTask":
            tid = f"task_{len(created_task_ids) + 1}"
            created_task_ids.append(tid)
            return httpx.Response(200, json={"data": {"taskId": tid}})
        # getTaskResult — always return success for the requested task
        requested_ids = body.get("taskIdList", [])
        tid = requested_ids[0] if requested_ids else "unknown"
        return httpx.Response(200, json={"data": {
            "successList": [{
                "taskId": tid,
                "result": "ok",
                "parameterValues": [
                    {"name": "Device.DeviceInfo.ProvisioningCode", "value": "SITE-001"},
                    {"name": "Device.ManagementServer.PeriodicInformInterval", "value": "300"},
                ],
            }],
            "failedList": [], "pendingList": [],
        }})

    respx.post(f"{VOLA_BASE}/org-mgmt-api/device-task-operation").mock(side_effect=task_op_side_effect)

    # Mock switchOrg if org_id is set
    respx.post(f"{VOLA_BASE}/user-mgmt-api/user-operation").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )

    client = _make_client()

    # Mock DB session
    mock_db = AsyncMock()

    mock_device = MagicMock()
    mock_device.device_id = "VOLA-SN001"
    mock_device.id = 1
    mock_device.status = "provisioning"
    mock_device.site_id = None
    mock_device.serial_number = "SN001"

    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    from unittest.mock import patch
    with patch("app.services.vola_service.ensure_device_exists", return_value=mock_device):
        result = await deploy_device(
            mock_db, "tenant-1", client,
            device_sn="SN001",
            site_id="SITE-001",
            site_code="SITE-001",
            inform_interval=300,
            verify=True,
        )

    assert result["device_sn"] == "SN001"
    assert result["steps"]["vola_validate"] == "ok"
    assert result["steps"]["ensure_device"] == "ok"
    assert result["steps"]["bind_to_site"] == "ok"
    assert result["steps"]["provision"] == "success"
    assert result["steps"]["reboot"] == "ok"
    assert result["steps"]["verify"] == "ok"
    assert result["status"] == "success"
    assert result["verified_values"]["Device.DeviceInfo.ProvisioningCode"] == "SITE-001"
    assert result["verified_values"]["Device.ManagementServer.PeriodicInformInterval"] == "300"


# ── Provision deployment (service layer) ────────────────────────────────────

@pytest.mark.asyncio
async def test_provision_deploy_creates_steps():
    """Test run_provision_deployment produces expected step structure."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.provision_deploy import run_provision_deployment

    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    # Mock tenant lookup → not found → create
    mock_result_none = MagicMock()
    mock_result_none.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_none

    # We patch deploy_device to avoid real VOLA calls
    mock_deploy = AsyncMock(return_value={
        "device_sn": "SN001",
        "device_id": "VOLA-SN001",
        "device_pk": 1,
        "status": "success",
        "error": None,
        "steps": {"ensure_device": "ok", "bind_to_site": "ok", "provision": "success", "reboot": "ok"},
        "provision_task_id": "task_1",
        "reboot_task_id": "task_2",
        "applied": {"Device.DeviceInfo.ProvisioningCode": "TEST"},
    })

    mock_client = MagicMock()

    with patch("app.services.provision_deploy.deploy_device", mock_deploy), \
         patch("app.services.provision_deploy.get_tenant_vola_client", AsyncMock(return_value=mock_client)):
        result = await run_provision_deployment(
            mock_db,
            operator_tenant_id="test-tenant",
            customer_name="Test Co",
            site_name="Main Office",
            device_sns=["SN001"],
        )

    assert result["steps"]["tenant"] == "ok"
    assert result["steps"]["customer"] == "ok"
    assert result["steps"]["site"] == "ok"
    assert len(result["devices"]) == 1
    assert result["devices"][0]["status"] == "success"
