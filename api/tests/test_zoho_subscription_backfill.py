"""Tests for the Zoho Subscription_Mgmt staging backfill (pure, no Zoho/DB)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.backfill_zoho_subscription_staging import (
    DEFAULT_FIELDS,
    DEFAULT_MODULE,
    STAGING_TABLES,
    account_matches,
    classify_action,
    fetch_subscription_records,
    resolve_fields,
    resolve_org_id,
    should_apply,
)


# ── --customer filter matching ───────────────────────────────────────────
def test_account_matches():
    assert account_matches("Webber Infra", "Webber Infrastructure, LLC") is True
    assert account_matches("webber", "WEBBER INFRA") is True
    assert account_matches("Webber", "Restoration Hardware #351") is False
    assert account_matches(None, "anything") is True       # no filter -> all
    assert account_matches("Webber", None) is False


# ── idempotent action classification ─────────────────────────────────────
def test_classify_action():
    assert classify_action(None) == "insert"
    assert classify_action(object()) == "update"


# ── APPLY gate (dry-run-first + feature flag) ────────────────────────────
def test_should_apply_requires_flag(monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_BACKFILL", "false")
    assert should_apply(True) is False        # requested but flag off -> dry-run
    assert should_apply(False) is False
    monkeypatch.setattr("app.config.settings.FEATURE_ZOHO_BACKFILL", "true")
    assert should_apply(True) is True
    assert should_apply(False) is False       # not requested -> never writes


def test_resolve_org_id(monkeypatch):
    monkeypatch.setattr("app.config.settings.ZOHO_BACKFILL_ORG_ID", "org-x")
    assert resolve_org_id() == "org-x"
    monkeypatch.setattr("app.config.settings.ZOHO_BACKFILL_ORG_ID", "")
    monkeypatch.setattr("app.config.settings.ZOHO_CRM_ORG_ID", "crm-org")
    assert resolve_org_id() == "crm-org"
    monkeypatch.setattr("app.config.settings.ZOHO_CRM_ORG_ID", "")
    assert resolve_org_id() == "zoho_crm"


# ── declared write surface is staging-only ───────────────────────────────
def test_staging_tables_are_shadow_only():
    assert set(STAGING_TABLES) == {"zoho_subscription_records", "external_record_map"}
    for op in ("customers", "sites", "devices", "lines", "subscriptions"):
        assert op not in STAGING_TABLES


# ── source-level safety guarantees ───────────────────────────────────────
def test_no_operational_writes_or_deletes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "backfill_zoho_subscription_staging.py").read_text(encoding="utf-8")
    lower = src.lower()
    # Never deletes anything.
    for forbidden in (".delete(", "db.delete", "delete from", "drop "):
        assert forbidden not in lower, f"backfill must never delete; found {forbidden!r}"
    # Does not import or write operational models.
    for op_model in ("from app.models.customer", "from app.models.site",
                     "from app.models.device", "from app.models.line",
                     "from app.models.subscription"):
        assert op_model not in src, f"backfill must not touch operational models ({op_model})"
    # Reuses the existing staging upsert (single write path).
    assert "_upsert_subscription_record" in src
    assert "_upsert_record_map" in src
    # The only commit is gated behind the apply branch.
    assert "if apply:" in src and "await db.commit()" in src


def test_dry_run_default_documented():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "backfill_zoho_subscription_staging.py").read_text(encoding="utf-8")
    assert "DRY RUN" in src and "FEATURE_ZOHO_BACKFILL" in src


# ── module name + fields param (Render-confirmed Zoho contract) ──────────
def test_default_module_is_subscription_mgmnt():
    assert DEFAULT_MODULE == "Subscription_Mgmnt"   # the live (misspelled) API name


def test_default_fields_cover_required_set():
    for f in ("id", "Account_Name", "FacilityName", "Mobile_Number",
              "Device_Activation_Status", "Subscription_Type", "Connection_Type",
              "Monthly_Recurring_Charge", "Service_Term_Ends", "Modified_Time"):
        assert f in DEFAULT_FIELDS


def test_resolve_fields_default_and_overrides(monkeypatch):
    monkeypatch.setattr("app.config.settings.ZOHO_SUBSCRIPTION_FIELDS", "")
    assert resolve_fields(None) == ",".join(DEFAULT_FIELDS)
    # CLI override wins
    assert resolve_fields("id,Account_Name") == "id,Account_Name"
    # env override
    monkeypatch.setattr("app.config.settings.ZOHO_SUBSCRIPTION_FIELDS", "id,FacilityName")
    assert resolve_fields(None) == "id,FacilityName"
    # CLI beats env
    assert resolve_fields("id,Mobile_Number") == "id,Mobile_Number"
    # dedupe + trim
    assert resolve_fields(" id , id , Account_Name ") == "id,Account_Name"


@pytest.mark.asyncio
async def test_fields_param_sent_to_zoho(monkeypatch):
    from app.services import zoho_crm
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    captured = {}

    async def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"data": [{"id": "1", "Account_Name": "Webber Infrastructure"}],
                "info": {"more_records": False}}

    monkeypatch.setattr(zoho_crm, "_zoho_get", AsyncMock(side_effect=fake_get))
    fields = "id,Account_Name,Device_Activation_Status"
    out = await fetch_subscription_records("Subscription_Mgmnt", "Webber", fields)

    assert captured["path"] == "/Subscription_Mgmnt"
    assert captured["params"]["fields"] == fields      # fields param included
    assert len(out) == 1


@pytest.mark.asyncio
async def test_module_error_propagates_clearly(monkeypatch):
    from app.services import zoho_crm
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)

    async def boom(path, params=None):
        raise zoho_crm.ZohoCRMError(f"Zoho API {path}: 400 REQUIRED_PARAM_MISSING fields")

    monkeypatch.setattr(zoho_crm, "_zoho_get", AsyncMock(side_effect=boom))
    with pytest.raises(zoho_crm.ZohoCRMError, match="REQUIRED_PARAM_MISSING"):
        await fetch_subscription_records("Subscription_Mgmnt", "Webber",
                                         ",".join(DEFAULT_FIELDS))


@pytest.mark.asyncio
async def test_not_configured_raises_clear(monkeypatch):
    from app.services import zoho_crm
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: False)
    with pytest.raises(RuntimeError, match="Zoho CRM not configured"):
        await fetch_subscription_records("Subscription_Mgmnt", "Webber", "id")
