"""Tests for the Integrity / Belle Terre onboarding (app.seed_integrity) and
the read-only verifier (app.verify_integrity).

Following the house pattern (test_registration_convert.py): the project does
not stand up an in-memory DB, so the *pure builders* and the *external-API*
paths get full coverage here.  The DB upsert layer is exercised by the real
Postgres dry-run before launch (see docs/INTEGRITY_BELLE_TERRE_ONBOARDING.md).
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import respx

from app.services import rbac
from app import seed_integrity as si
from app.verify_integrity import (
    check_vola_devices,
    tmobile_readiness,
    _expected_gaps,
)

VOLA_BASE = "https://cloudapi.volanetworks.net"


def _vola_client():
    from app.integrations.vola import VolaClient
    return VolaClient(
        base_url=VOLA_BASE, email="t@example.com", password="pw",
        org_id=None, allowed_param_prefixes=None, allowed_set_prefixes=[],
        blocked_set_prefixes=[], denylist_exact=set(),
    )


def _mock_auth():
    respx.post(f"{VOLA_BASE}/user-mgmt-api/get-access-token").mock(
        return_value=httpx.Response(200, json={
            "code": "200", "status": "ok", "accessToken": "tok_123"}))


# ── Tenant / customer builders ───────────────────────────────────────
class TestTenantCustomer:
    def test_tenant_slug_and_zoho(self):
        kw = si.build_tenant_kwargs()
        assert kw["tenant_id"] == "integrity-pm"
        assert kw["name"] == "Integrity Property Management"
        assert kw["zoho_account_id"] == "337391000069074135"

    def test_customer_links_to_zoho_account(self):
        kw = si.build_customer_kwargs()
        assert kw["tenant_id"] == "integrity-pm"
        assert kw["zoho_account_id"] == "337391000069074135"
        assert kw["customer_number"] == "15137"
        assert kw["status"] == "active"


# ── Site builders ────────────────────────────────────────────────────
class TestSites:
    def test_four_sites_built(self):
        assert len(si.SITES) == 4

    def test_belle_terre_has_full_e911(self):
        spec = next(s for s in si.SITES if s["site_id"] == si.BELLE_TERRE_SITE_ID)
        kw = si.build_site_kwargs(spec)
        assert kw["site_name"] == "Belle Terre at Sunrise"
        assert kw["e911_street"] == "7800 W Oakland Park Blvd"
        assert kw["e911_city"] == "Sunrise"
        assert kw["e911_state"] == "FL"
        assert kw["e911_zip"] == "33351"
        assert kw["status"] == "active"

    def test_placeholder_sites_have_no_e911_and_are_pending(self):
        placeholders = [s for s in si.SITES if s["site_id"] != si.BELLE_TERRE_SITE_ID]
        assert len(placeholders) == 3
        for spec in placeholders:
            kw = si.build_site_kwargs(spec)
            assert kw["status"] == "pending"
            assert "e911_street" not in kw  # never fabricated
            assert kw["e911_confirmation_required"] is True

    def test_site_names_spelled_exactly(self):
        names = {s["site_name"] for s in si.SITES}
        assert "Belle Terre at Sunrise" in names
        # Pompano name matches Zoho exactly — NOT "The Point at Pompano Beach".
        assert "The Pointe of Pompano Beach Condo Association" in names
        assert "The Point at Pompano Beach" not in names
        assert "Tiffany Gardens East" in names
        assert "Tiffany Gardens North" in names

    def test_pompano_is_inert_test_location(self):
        spec = next(s for s in si.SITES if s["site_id"] == "IPM-POMPANO")
        kw = si.build_site_kwargs(spec)
        assert kw["status"] == "pending"
        assert kw["onboarding_status"] == "test"
        assert "TEST LOCATION" in kw["notes"]
        assert "e911_street" not in kw  # never fabricated


# ── Device builders ──────────────────────────────────────────────────
class TestDevices:
    def test_three_lm150_devices(self):
        assert len(si.DEVICES) == 3
        for d in si.DEVICES:
            kw = si.build_device_kwargs(d)
            assert kw["model"] == "LM150"
            assert kw["manufacturer"] == "FlyingVoice"
            assert kw["hardware_model_id"] == "flyingvoice-lm150"
            assert kw["carrier"] == "tmobile"
            assert kw["serial_number"] == d["serial"]
            assert kw["imei"] == d["imei"]
            assert kw["iccid"] == d["iccid"]
            assert kw["msisdn"] == d["msisdn"]

    def test_device_id_scheme_matches_vola_sync(self):
        kw = si.build_device_kwargs(si.DEVICES[0])
        assert kw["device_id"] == "VOLA-VOLA00325600226"

    def test_vola_org_id_passthrough(self):
        kw = si.build_device_kwargs(si.DEVICES[0], vola_org_id="org-xyz")
        assert kw["vola_org_id"] == "org-xyz"
        kw2 = si.build_device_kwargs(si.DEVICES[0], vola_org_id=None)
        assert kw2["vola_org_id"] is None

    def test_volte_recorded_in_notes(self):
        kw = si.build_device_kwargs(si.DEVICES[0])
        assert "VoLTE enabled" in kw["notes"]
        assert "337391000069074135" in kw["notes"]  # zoho traceability


# ── SIM builders ─────────────────────────────────────────────────────
class TestSims:
    def test_sim_carrier_and_volte_meta(self):
        for d in si.DEVICES:
            kw = si.build_sim_kwargs(d)
            assert kw["carrier"] == "tmobile"
            assert kw["iccid"] == d["iccid"]
            assert kw["status"] == "active"
            assert kw["meta"]["volte_enabled"] is True


# ── Service-unit builders ────────────────────────────────────────────
class TestServiceUnits:
    def test_three_elevators_linked_to_devices(self):
        for d in si.DEVICES:
            kw = si.build_service_unit_kwargs(d)
            assert kw["unit_type"] == "elevator_phone"
            assert kw["unit_name"] == f"Elevator {d['elevator']}"
            assert kw["unit_id"] == f"IPM-BELLE-TERRE-EL{d['elevator']}"
            assert kw["device_id"] == si.device_id_for(d["serial"])


# ── Cross-cutting invariants ─────────────────────────────────────────
class TestInvariants:
    def test_every_record_is_tenant_scoped(self):
        """Isolation invariant — nothing leaks into another tenant."""
        records = (
            [si.build_tenant_kwargs(), si.build_customer_kwargs()]
            + [si.build_site_kwargs(s) for s in si.SITES]
            + [si.build_device_kwargs(d) for d in si.DEVICES]
            + [si.build_sim_kwargs(d) for d in si.DEVICES]
            + [si.build_service_unit_kwargs(d) for d in si.DEVICES]
        )
        for r in records:
            tid = r.get("tenant_id")
            assert tid == "integrity-pm"
            assert tid not in ("demo", "rh", "default")

    def test_natural_keys_unique(self):
        device_ids = [si.build_device_kwargs(d)["device_id"] for d in si.DEVICES]
        unit_ids = [si.build_service_unit_kwargs(d)["unit_id"] for d in si.DEVICES]
        iccids = [si.build_sim_kwargs(d)["iccid"] for d in si.DEVICES]
        site_ids = [s["site_id"] for s in si.SITES]
        for ids in (device_ids, unit_ids, iccids, site_ids):
            assert len(ids) == len(set(ids))


# ── RBAC visibility ──────────────────────────────────────────────────
class TestRbacVisibility:
    def test_integrity_users_can_view_sites_and_devices(self):
        for role in ("Admin", "Manager", "User"):
            assert rbac.can(role, "VIEW_SITES") is True
            assert rbac.can(role, "VIEW_DEVICES") is True

    def test_plain_user_cannot_manage_devices(self):
        assert rbac.can("User", "MANAGE_DEVICES") is False
        assert rbac.can("Manager", "MANAGE_DEVICES") is False
        assert rbac.can("Admin", "MANAGE_DEVICES") is True


# ── Vola live lookup (mocked) ────────────────────────────────────────
class TestVolaLookup:
    @respx.mock
    @pytest.mark.asyncio
    async def test_success_with_one_missing(self):
        _mock_auth()
        respx.post(f"{VOLA_BASE}/org-mgmt-api/device-list").mock(
            return_value=httpx.Response(200, json={
                "code": "200", "status": "ok", "deviceList": [
                    {"deviceSN": "VOLA00325600226", "deviceModel": "LM150",
                     "softwareVersion": "1.0.9", "status": "Online",
                     "orgId": "o1", "orgName": "Integrity",
                     "lastUpdateTime": "Jun 01 2026 09:00"},
                    {"deviceSN": "VOLA00325600227", "deviceModel": "LM150",
                     "softwareVersion": "1.0.9", "status": "Offline",
                     "orgId": "o1", "orgName": "Integrity",
                     "lastUpdateTime": "May 31 2026 22:00"},
                ]}))
        result = await check_vola_devices(_vola_client(), si.EXPECTED_SERIALS)
        assert result["ok"] is True
        assert result["devices"]["VOLA00325600226"]["status"] == "online"
        assert result["devices"]["VOLA00325600227"]["status"] == "offline"
        # third serial was not returned -> logged as missing
        assert "VOLA00325600230" in result["missing"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_failure_is_handled(self):
        _mock_auth()
        respx.post(f"{VOLA_BASE}/org-mgmt-api/device-list").mock(
            return_value=httpx.Response(500, json={"code": "500"}))
        result = await check_vola_devices(_vola_client(), si.EXPECTED_SERIALS)
        assert result["ok"] is False
        assert result["error"]
        assert set(result["missing"]) == set(si.EXPECTED_SERIALS)


# ── T-Mobile readiness (pure) ────────────────────────────────────────
class TestTmobileReadiness:
    def test_unconfigured_reports_callback_only(self):
        settings = SimpleNamespace(
            FEATURE_TMOBILE_CALLBACK_INGEST="false", TMOBILE_ENV="pit",
            TMOBILE_BASE_URL="", TMOBILE_TOKEN_URL="", TMOBILE_CONSUMER_KEY="",
            TMOBILE_CONSUMER_SECRET="", TMOBILE_ACCOUNT_ID="")
        tm = tmobile_readiness(settings)
        assert tm["callback_ingest_enabled"] is False
        assert tm["sync_lookup_live"] is False
        assert set(tm["taap_missing"]) == {
            "TMOBILE_BASE_URL", "TMOBILE_TOKEN_URL", "TMOBILE_CONSUMER_KEY",
            "TMOBILE_CONSUMER_SECRET", "TMOBILE_ACCOUNT_ID"}

    def test_configured_callback_and_partial_taap(self):
        settings = SimpleNamespace(
            FEATURE_TMOBILE_CALLBACK_INGEST="true", TMOBILE_ENV="prod",
            TMOBILE_BASE_URL="https://apis.t-mobile.com", TMOBILE_TOKEN_URL="",
            TMOBILE_CONSUMER_KEY="key", TMOBILE_CONSUMER_SECRET="",
            TMOBILE_ACCOUNT_ID="acct")
        tm = tmobile_readiness(settings)
        assert tm["callback_ingest_enabled"] is True
        assert "TMOBILE_BASE_URL" in tm["taap_present"]
        assert "TMOBILE_CONSUMER_KEY" in tm["taap_present"]
        assert "TMOBILE_TOKEN_URL" in tm["taap_missing"]


# ── Dashboard visibility gap detector ────────────────────────────────
class TestExpectedGaps:
    def test_detects_missing_records(self):
        empty = {"devices": [], "sims": [], "sites": []}
        gaps = _expected_gaps(empty)
        assert any("Belle Terre" in g for g in gaps)
        assert len([g for g in gaps if "serial" in g]) == 3
        assert len([g for g in gaps if "iccid" in g]) == 3

    def test_no_gaps_when_all_present(self):
        report = {
            "devices": [{"serial": s} for s in si.EXPECTED_SERIALS],
            "sims": [{"iccid": c} for c in si.EXPECTED_ICCIDS],
            "sites": [{"site_id": si.BELLE_TERRE_SITE_ID}],
        }
        assert _expected_gaps(report) == []
