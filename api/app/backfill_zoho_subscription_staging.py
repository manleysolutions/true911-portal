"""Zoho CRM Subscription_Mgmt → staging BACKFILL (dry-run-first, flag-gated).

The Zoho mirror (``zoho_subscription_records`` + ``external_record_map``) only
captures records delivered by webhook AFTER ``FEATURE_ZOHO_SUBSCRIPTION_INGEST``
was turned on.  Pre-existing Zoho subscriptions (e.g. Webber Infra) are absent,
so the reconciliation audit has no Zoho side to compare.  This tool PULLS
Subscription_Mgmt records from the Zoho CRM API and stages them through the SAME
additive upsert the webhook uses — nothing else changes.

Hard safety contract:
  * Reads from Zoho CRM (OAuth handled by app.services.zoho_crm).
  * Writes ONLY to the staging tables ``zoho_subscription_records`` and
    ``external_record_map``.  NEVER customers / sites / devices / lines /
    subscriptions.  NEVER deletes.
  * DRY-RUN by default — prints what WOULD be staged and writes nothing.  The
    APPLY (write) path additionally requires ``FEATURE_ZOHO_BACKFILL=true``.
  * Idempotent by ``(org_id, subscription_mgmt_id)`` — re-runs update in place,
    never duplicate.
  * Lifecycle is NOT changed here: ``lifecycle_state`` stays NULL unless the
    separate ``FEATURE_ZOHO_STATUS_NORMALIZER`` is enabled (same rule the webhook
    ingest follows).

Run:
    # Dry-run a single customer (no writes, no flag needed):
    python -m app.backfill_zoho_subscription_staging --customer "Webber Infra"
    # Dry-run everything:
    python -m app.backfill_zoho_subscription_staging --all
    # Apply for one customer (requires FEATURE_ZOHO_BACKFILL=true):
    FEATURE_ZOHO_BACKFILL=true python -m app.backfill_zoho_subscription_staging \
        --customer "Webber Infra" --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402

# Default Zoho CRM API module name. NOTE: the LIVE custom module is spelled
# "Subscription_Mgmnt" (confirmed in the Render shell) — intentionally distinct
# from the webhook payload label in ZOHO_SUBSCRIPTION_MODULES. Overridable via
# --module.
DEFAULT_MODULE = "Subscription_Mgmnt"

# Minimum safe field set requested on the Zoho v5 GET. Custom-module reads return
# 400 REQUIRED_PARAM_MISSING (fields) without an explicit `fields` param. These
# map to the staging columns via the webhook extractor's tolerant key index.
DEFAULT_FIELDS = (
    "id", "Account_Name", "FacilityName", "Mobile_Number",
    "Device_Activation_Status", "Subscription_Type", "Connection_Type",
    "Monthly_Recurring_Charge", "Service_Term_Ends", "Modified_Time",
)

# Staging tables this tool may write (APPLY mode only). Declared for the report
# and asserted by tests — operational tables are deliberately NOT in this set.
STAGING_TABLES = ("zoho_subscription_records", "external_record_map")


# ── pure helpers (unit-tested, no Zoho / no DB) ──────────────────────────
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _flag_on(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def resolve_org_id() -> str:
    """Stable org_id staging rows are keyed on (idempotency)."""
    return (settings.ZOHO_BACKFILL_ORG_ID.strip()
            or settings.ZOHO_CRM_ORG_ID.strip() or "zoho_crm")


def resolve_fields(cli_fields: Optional[str] = None) -> str:
    """Resolve the Zoho `fields` param: --fields > ZOHO_SUBSCRIPTION_FIELDS env >
    DEFAULT_FIELDS. Returns a normalized comma-separated string."""
    raw = (cli_fields or settings.ZOHO_SUBSCRIPTION_FIELDS or "").strip()
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            return ",".join(dict.fromkeys(parts))  # dedupe, preserve order
    return ",".join(DEFAULT_FIELDS)


def _norm_name(s: Optional[str]) -> str:
    return _NON_ALNUM.sub(" ", str(s or "").lower()).strip()


def account_matches(query: Optional[str], account_name: Optional[str]) -> bool:
    """Case/punctuation-insensitive substring match for the --customer filter."""
    q, n = _norm_name(query), _norm_name(account_name)
    if not q:
        return True            # no filter -> match all
    if not n:
        return False
    return q in n or n in q


def should_apply(apply_requested: bool) -> bool:
    """APPLY (write) only when explicitly requested AND the feature flag is on."""
    return bool(apply_requested) and _flag_on(settings.FEATURE_ZOHO_BACKFILL)


def classify_action(existing) -> str:
    """Idempotent action for one record: insert when absent, else update."""
    return "update" if existing is not None else "insert"


# ── Zoho read (reuses app.services.zoho_crm OAuth + GET) ──────────────────
async def fetch_subscription_records(
    module: str, customer: Optional[str], fields: str, *, max_pages: int = 100
) -> list[dict]:
    """Pull Subscription_Mgmt records from Zoho CRM, filtered by account name.

    Read-only against Zoho. ``fields`` is the required Zoho v5 `fields` param
    (comma-separated API names). Client-side account-name filter keeps it robust
    to custom field-API-name variance (the webhook extractor is tolerant too).
    """
    from app.services import zoho_crm
    from app.services.zoho_subscription_ingest import extract_subscription_fields

    if not zoho_crm.is_configured():
        raise RuntimeError(
            "Zoho CRM not configured — set ZOHO_CRM_CLIENT_ID / _CLIENT_SECRET / "
            "_REFRESH_TOKEN (run inside the environment that has them).")

    out: list[dict] = []
    page = 1
    while page <= max_pages:
        data = await zoho_crm._zoho_get(
            f"/{module}", params={"page": page, "per_page": 200, "fields": fields})
        records = data.get("data") or []
        if not records:
            break
        for raw in records:
            fields = extract_subscription_fields(raw)
            if customer and not account_matches(customer, fields.get("account_name")):
                continue
            out.append(raw)
        if not data.get("info", {}).get("more_records"):
            break
        page += 1
    return out


# ── orchestration ─────────────────────────────────────────────────────────
async def run(*, customer: Optional[str], do_all: bool, apply_requested: bool,
              module: str, fields: str) -> dict:
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.zoho_subscription_record import ZohoSubscriptionRecord
    from app.services.zoho_subscription_ingest import (
        extract_subscription_fields, _upsert_record_map, _upsert_subscription_record,
    )
    from app.services.zoho_payload_sanitizer import sanitize

    org_id = resolve_org_id()
    apply = should_apply(apply_requested)
    summary = {"fetched": 0, "staged_insert": 0, "staged_update": 0,
               "skipped_no_id": 0, "applied": apply, "org_id": org_id,
               "tables": list(STAGING_TABLES) if apply else []}

    if apply_requested and not apply:
        print("REFUSED to apply: set FEATURE_ZOHO_BACKFILL=true to authorize "
              "staging writes. Running as DRY-RUN instead.\n")

    raw_records = await fetch_subscription_records(module, customer, fields)
    summary["fetched"] = len(raw_records)

    mode = "APPLY (staging writes)" if apply else "DRY RUN (no writes)"
    print("=" * 74)
    print(f"Zoho Subscription_Mgmt → staging backfill — {mode}")
    print(f"  module={module}  org_id={org_id}  "
          f"filter={customer or '(all)'}  fetched={len(raw_records)}")
    print(f"  fields={fields}")
    print("=" * 74)

    async with AsyncSessionLocal() as db:
        for raw in raw_records:
            fields = extract_subscription_fields(raw)
            sub_id = fields.get("subscription_mgmt_id")
            if not sub_id:
                summary["skipped_no_id"] += 1
                print(f"  SKIP  account={fields.get('account_name')!r} — no resolvable "
                      "Subscription Mgmt ID")
                continue

            existing = (await db.execute(select(ZohoSubscriptionRecord).where(
                ZohoSubscriptionRecord.org_id == org_id,
                ZohoSubscriptionRecord.subscription_mgmt_id == sub_id,
            ))).scalar_one_or_none()
            action = classify_action(existing)
            summary[f"staged_{action}"] += 1
            print(f"  {action.upper():6} sub_id={sub_id} "
                  f"account={fields.get('account_name')!r} "
                  f"activation={fields.get('device_activation_status')!r} "
                  f"msisdn={fields.get('msisdn')!r}")

            if apply:
                rec_map = await _upsert_record_map(db, org_id, sub_id)
                await _upsert_subscription_record(
                    db, org_id, fields, sanitize(raw), None, rec_map.id)

        if apply:
            await db.commit()
            print("\nCOMMITTED to staging tables (zoho_subscription_records, "
                  "external_record_map). No operational records touched.")
        else:
            # No staging writes were issued in dry-run; rollback is belt-and-suspenders.
            await db.rollback()
            print("\nDRY RUN — nothing written. Re-run with "
                  "FEATURE_ZOHO_BACKFILL=true --apply to stage.")

    print("\nSUMMARY")
    for k in ("fetched", "staged_insert", "staged_update", "skipped_no_id",
              "applied", "org_id"):
        print(f"  {k:<16}: {summary[k]}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run-first Zoho Subscription_Mgmt → staging backfill.")
    parser.add_argument("--customer", help="filter by account name (e.g. 'Webber Infra')")
    parser.add_argument("--all", dest="do_all", action="store_true",
                        help="backfill every Subscription_Mgmt record")
    parser.add_argument("--apply", action="store_true",
                        help="WRITE to staging (requires FEATURE_ZOHO_BACKFILL=true)")
    parser.add_argument("--module", default=DEFAULT_MODULE,
                        help=f"Zoho module API name (default {DEFAULT_MODULE})")
    parser.add_argument("--fields", default=None,
                        help="comma-separated Zoho field API names "
                             "(default: ZOHO_SUBSCRIPTION_FIELDS env or the safe minimum set)")
    args = parser.parse_args()

    if not args.customer and not args.do_all:
        print("Specify --customer \"<name>\" or --all.")
        raise SystemExit(2)
    fields = resolve_fields(args.fields)
    # DRY_RUN=true (if set) forces dry-run even when --apply is passed.
    apply_requested = bool(args.apply)
    dry_run_env = os.environ.get("DRY_RUN")
    if dry_run_env is not None and _flag_on(dry_run_env):
        apply_requested = False
    try:
        asyncio.run(run(customer=args.customer, do_all=args.do_all,
                        apply_requested=apply_requested, module=args.module,
                        fields=fields))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: backfill aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
