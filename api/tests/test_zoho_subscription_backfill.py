"""Tests for the Zoho Subscription_Mgmt staging backfill (pure, no Zoho/DB)."""

from __future__ import annotations

from pathlib import Path

from app.backfill_zoho_subscription_staging import (
    STAGING_TABLES,
    account_matches,
    classify_action,
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
