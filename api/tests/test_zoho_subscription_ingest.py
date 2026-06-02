"""Phase 1 — Zoho subscription lifecycle ingest (flag-gated, staging only).

Covers the pure routing/sanitizer/extraction logic plus the staging upsert via a
lightweight fake async session (no real DB, matching the house test pattern).

Webber Infra is the test case: a Subscription_Mgmt record with
Device Activation Status = "De-activated".  These tests assert the data is
STAGED (and the raw status preserved) and that ONLY staging models are written —
never sites/devices/lines.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.external_record_map import ExternalRecordMap
from app.models.zoho_payload_observation import ZohoPayloadObservation
from app.models.zoho_subscription_record import ZohoSubscriptionRecord
from app.services import zoho_subscription_ingest as ingest
from app.services.zoho_payload_sanitizer import sanitize, top_level_keys
from app.services.zoho_routing import is_zoho_subscription_event


# ── Webber Infra sample payload (contract not finalized — varied spellings) ──
def _webber_payload(**overrides):
    payload = {
        "module": "Subscription_Mgmt",
        "Subscription_Mgmt_ID": "ZSM-WEBBER-001",
        "Account_Name": "Webber Infra",
        "FacilityName": "Webber Infrastructure — Bldg A",
        "Mobile_Number": "+15555550123",
        "Device_Activation_Status": "De-activated",
        "Connection_Type": "Static IP",
        "Subscription_Type": "IoT Data",
        "Monthly_Recurring_Charge": "$45.00",
        "Service_Term_Ends": "2026-12-31",
        "auth_token": "super-secret-value",
    }
    payload.update(overrides)
    return payload


class _FakeResult:
    def scalar_one_or_none(self):
        return None  # always "not found" -> upserts create new rows


class _FakeSession:
    """Minimal async session: selects miss, add() records, flush() assigns ids."""
    def __init__(self):
        self.added = []
        self._id = 0

    async def execute(self, *a, **k):
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                self._id += 1
                obj.id = self._id


def _event(payload, *, source="zoho", org_id="webber", event_id=7, event_type=None):
    return SimpleNamespace(
        id=event_id,
        org_id=org_id,
        source=source,
        event_type=event_type,
        payload_json=payload,
    )


# ── Routing (pure) ───────────────────────────────────────────────────
class TestRouting:
    def _settings(self, modules="Subscription_Mgmt", events=""):
        return SimpleNamespace(
            ZOHO_SUBSCRIPTION_MODULES=modules,
            ZOHO_SUBSCRIPTION_EVENT_TYPES=events,
        )

    def test_matches_on_module(self):
        assert is_zoho_subscription_event({"module": "Subscription_Mgmt"}, self._settings())

    def test_module_match_is_case_insensitive(self):
        assert is_zoho_subscription_event({"module": "subscription_mgmt"}, self._settings())

    def test_matches_on_event_type_when_configured(self):
        s = self._settings(modules="", events="zoho_subscription_upsert")
        assert is_zoho_subscription_event({"event_type": "zoho_subscription_upsert"}, s)

    def test_no_match_for_other_module(self):
        assert not is_zoho_subscription_event({"module": "Accounts"}, self._settings())

    def test_empty_event_type_config_never_matches_blank(self):
        # Blank EVENT_TYPES must not match an absent/blank event_type.
        assert not is_zoho_subscription_event({"event_type": ""}, self._settings(events=""))

    def test_either_signal_is_sufficient(self):
        s = self._settings(modules="Subscription_Mgmt", events="evt_x")
        assert is_zoho_subscription_event({"event_type": "evt_x"}, s)
        assert is_zoho_subscription_event({"module": "Subscription_Mgmt"}, s)


# ── Sanitizer (pure) ─────────────────────────────────────────────────
class TestSanitizer:
    def test_redacts_sensitive_keys(self):
        out = sanitize({
            "auth_token": "abc", "api_key": "k", "password": "p",
            "Authorization": "Bearer x", "signature": "s", "client_secret": "cs",
        })
        assert all(v == "<redacted>" for v in out.values())

    def test_preserves_business_fields(self):
        out = sanitize(_webber_payload())
        assert out["Account_Name"] == "Webber Infra"
        assert out["Device_Activation_Status"] == "De-activated"
        # the secret is gone
        assert out["auth_token"] == "<redacted>"

    def test_does_not_over_redact_key_substring(self):
        # "Subscription_Mgmt_Key" must NOT be redacted (only bare key/auth are).
        out = sanitize({"Subscription_Mgmt_Key": "ZSM-1"})
        assert out["Subscription_Mgmt_Key"] == "ZSM-1"

    def test_recurses_into_nested(self):
        out = sanitize({"data": {"token": "t", "name": "ok"}, "items": [{"secret": "x"}]})
        assert out["data"]["token"] == "<redacted>"
        assert out["data"]["name"] == "ok"
        assert out["items"][0]["secret"] == "<redacted>"

    def test_top_level_keys(self):
        assert top_level_keys({"b": 1, "a": 2}) == ["a", "b"]
        assert top_level_keys("not a dict") == []


# ── Field extraction (pure) ──────────────────────────────────────────
class TestExtraction:
    def test_extracts_all_task3_fields(self):
        f = ingest.extract_subscription_fields(_webber_payload())
        assert f["subscription_mgmt_id"] == "ZSM-WEBBER-001"
        assert f["account_name"] == "Webber Infra"
        assert f["facility_name"] == "Webber Infrastructure — Bldg A"
        assert f["msisdn"] == "+15555550123"
        assert f["device_activation_status"] == "De-activated"
        assert f["connection_type"] == "Static IP"
        assert f["subscription_type"] == "IoT Data"
        assert f["mrc"] == 45.0
        assert f["service_term_ends"] == date(2026, 12, 31)

    def test_tolerates_alternate_key_spellings(self):
        f = ingest.extract_subscription_fields({
            "Subscription Mgmt ID": "ZSM-2",
            "account_name": "Acme",
            "MSISDN": "15555551212",
            "Device Activation Status": "Active",
            "MRC": 30,
        })
        assert f["subscription_mgmt_id"] == "ZSM-2"
        assert f["account_name"] == "Acme"
        assert f["msisdn"] == "15555551212"
        assert f["device_activation_status"] == "Active"
        assert f["mrc"] == 30.0

    def test_missing_fields_are_none(self):
        f = ingest.extract_subscription_fields({"Subscription_Mgmt_ID": "x"})
        assert f["subscription_mgmt_id"] == "x"
        assert f["facility_name"] is None
        assert f["mrc"] is None
        assert f["service_term_ends"] is None


# ── Staging upsert (fake session — no real DB, no production writes) ──
class TestIngestStaging:
    @pytest.mark.asyncio
    async def test_webber_infra_is_staged_and_only_staging_models_written(self):
        db = _FakeSession()
        event = _event(_webber_payload())

        result = await ingest.ingest_subscription_event(db, event)

        assert result["event_status"] == "processed"
        assert result["action"] == "staged"
        assert result["device_activation_status"] == "De-activated"

        # ONLY staging models were written — never Site/Device/Line/Customer.
        types = {type(o) for o in db.added}
        assert types == {ExternalRecordMap, ZohoSubscriptionRecord}

        sub = next(o for o in db.added if isinstance(o, ZohoSubscriptionRecord))
        assert sub.subscription_mgmt_id == "ZSM-WEBBER-001"
        assert sub.account_name == "Webber Infra"
        assert sub.device_activation_status == "De-activated"
        assert sub.mrc == 45.0
        assert sub.service_term_ends == date(2026, 12, 31)
        # Phase 1 does not normalize — lifecycle_state stays unset.
        assert getattr(sub, "lifecycle_state", None) is None
        # raw_json is sanitized (secret stripped).
        assert sub.raw_json["auth_token"] == "<redacted>"

        rec_map = next(o for o in db.added if isinstance(o, ExternalRecordMap))
        assert rec_map.module == "Subscription_Mgmt"
        assert rec_map.external_record_id == "ZSM-WEBBER-001"
        assert rec_map.map_status == "unmapped"  # never auto-confirmed

    @pytest.mark.asyncio
    async def test_normalizer_flag_off_leaves_lifecycle_none(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_STATUS_NORMALIZER", "false")
        db = _FakeSession()
        result = await ingest.ingest_subscription_event(db, _event(_webber_payload()))
        assert result["lifecycle_state"] is None
        sub = next(o for o in db.added if isinstance(o, ZohoSubscriptionRecord))
        assert sub.lifecycle_state is None

    @pytest.mark.asyncio
    async def test_normalizer_flag_on_sets_deactivated(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_STATUS_NORMALIZER", "true")
        db = _FakeSession()
        # Webber Infra Device Activation Status = "De-activated"
        result = await ingest.ingest_subscription_event(db, _event(_webber_payload()))
        assert result["lifecycle_state"] == "deactivated"
        sub = next(o for o in db.added if isinstance(o, ZohoSubscriptionRecord))
        assert sub.lifecycle_state == "deactivated"
        # Raw status still preserved verbatim alongside the normalized state.
        assert sub.device_activation_status == "De-activated"

    @pytest.mark.asyncio
    async def test_missing_subscription_id_is_needs_mapping(self):
        db = _FakeSession()
        event = _event({"module": "Subscription_Mgmt", "Account_Name": "No ID Co"})

        result = await ingest.ingest_subscription_event(db, event)

        assert result["event_status"] == "needs_mapping"
        # No staging subscription row created when it can't be keyed.
        assert not any(isinstance(o, ZohoSubscriptionRecord) for o in db.added)

    @pytest.mark.asyncio
    async def test_observation_captures_sanitized_structure(self):
        db = _FakeSession()
        event = _event(_webber_payload(), event_type="subscription_mgmt_changed")

        obs = await ingest.record_observation(db, event, matched=True)

        assert isinstance(obs, ZohoPayloadObservation)
        assert obs.matched_subscription is True
        assert obs.module == "Subscription_Mgmt"
        assert obs.integration_event_id == 7
        assert "Account_Name" in obs.top_level_keys
        assert obs.sanitized_payload["auth_token"] == "<redacted>"


# ── Processor flag gating (additive / no-regression guarantee) ───────
class _LoadResult:
    def __init__(self, event):
        self._event = event

    def scalar_one_or_none(self):
        return self._event


class _LoadSession:
    """Async session that returns a preset event on the first load select."""
    def __init__(self, event):
        self._event = event
        self.flush = AsyncMock()

    async def execute(self, *a, **k):
        return _LoadResult(self._event)


def _db_event(payload, **kw):
    # Mutable object so the processor can set .status / .processed_at.
    return SimpleNamespace(
        id=1, org_id="webber", source="zoho",
        event_type=kw.get("event_type", "subscription_mgmt"),
        payload_json=payload, status="received", error=None, processed_at=None,
    )


class TestProcessorFlagGating:
    @pytest.mark.asyncio
    async def test_flag_off_subscription_event_is_needs_mapping_untouched(self, monkeypatch):
        from app.services import integration_processor as proc

        monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_SUBSCRIPTION_INGEST", "false")
        spy = AsyncMock()
        monkeypatch.setattr(proc.zoho_subscription_ingest, "record_observation", spy)
        monkeypatch.setattr(proc.zoho_subscription_ingest, "ingest_subscription_event", spy)

        event = _db_event(_webber_payload())
        db = _LoadSession(event)
        job = SimpleNamespace(payload={"integration_event_id": 1})

        result = await proc.process_integration_event(db, job)

        # Exactly today's behavior: unknown type -> needs_mapping, no ingest.
        assert event.status == "needs_mapping"
        assert result["status"] == "needs_mapping"
        spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_flag_on_matched_routes_to_staging(self, monkeypatch):
        from app.services import integration_processor as proc

        monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_SUBSCRIPTION_INGEST", "true")
        obs_spy = AsyncMock()
        ingest_spy = AsyncMock(return_value={"event_status": "processed", "action": "staged"})
        monkeypatch.setattr(proc.zoho_subscription_ingest, "record_observation", obs_spy)
        monkeypatch.setattr(proc.zoho_subscription_ingest, "ingest_subscription_event", ingest_spy)

        event = _db_event(_webber_payload())
        db = _LoadSession(event)
        job = SimpleNamespace(payload={"integration_event_id": 1})

        result = await proc.process_integration_event(db, job)

        obs_spy.assert_awaited_once()
        ingest_spy.assert_awaited_once()
        assert event.status == "processed"
        assert result["action"] == "staged"
        assert "event_status" not in result  # popped before return
