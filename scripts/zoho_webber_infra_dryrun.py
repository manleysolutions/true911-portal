#!/usr/bin/env python3
"""Zoho lifecycle ingest DRY RUN — Webber Infra test case. Writes NOTHING.

Runs a sample (or supplied) Zoho Subscription_Mgmt payload through the real
pipeline — routing match -> field extraction -> lifecycle normalization ->
sanitization -> the exact review serialization an operator would see — and prints
the result. It NEVER touches the database: no upsert, no observation row, no
production write. There is no flag that makes it persist.

This demonstrates the Webber Infra case from the request: Zoho shows the
subscription as "De-activated", which normalizes to the `deactivated` lifecycle
state and is explicitly NOT presented as healthy active monitoring — while the
existing True911 site is left completely untouched.

Usage:
    cd api
    python ../scripts/zoho_webber_infra_dryrun.py
    python ../scripts/zoho_webber_infra_dryrun.py --status Active
    python ../scripts/zoho_webber_infra_dryrun.py --json /path/to/real_payload.json
"""

import argparse
import json
import os
import sys

# Make the api/ package importable and load api/.env (for routing/flag config).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "api", ".env"))


# Sample Webber Infra Subscription_Mgmt payload (varied key spellings + a secret
# to demonstrate redaction). The Zoho contract is not finalized — extraction is
# tolerant of spelling, so this is illustrative, not authoritative.
WEBBER_SAMPLE = {
    "module": "Subscription_Mgmt",
    "event_type": "subscription_mgmt_changed",
    "org_id": "webber",
    "Subscription_Mgmt_ID": "ZSM-WEBBER-001",
    "Account_Name": "Webber Infra",
    "FacilityName": "Webber Infrastructure — Bldg A",
    "Mobile_Number": "+15555550123",
    "Device_Activation_Status": "De-activated",
    "Connection_Type": "Static IP",
    "Subscription_Type": "IoT Data",
    "Monthly_Recurring_Charge": "$45.00",
    "Service_Term_Ends": "2026-12-31",
    "auth_token": "super-secret-should-be-redacted",
}


def build_dryrun_report(payload: dict, *, normalize: bool = True) -> dict:
    """Run the in-memory pipeline and return a printable report. No DB writes."""
    from app.config import settings
    from app.models.external_record_map import ExternalRecordMap
    from app.models.zoho_subscription_record import ZohoSubscriptionRecord
    from app.routers.zoho_review import serialize_review_row
    from app.services.zoho_payload_sanitizer import sanitize, top_level_keys
    from app.services.zoho_routing import is_zoho_subscription_event
    from app.services.zoho_status_normalizer import normalize_activation_status
    from app.services.zoho_subscription_ingest import extract_subscription_fields

    matched = is_zoho_subscription_event(payload, settings)
    fields = extract_subscription_fields(payload)
    raw_status = fields.get("device_activation_status")
    lifecycle = normalize_activation_status(raw_status) if normalize else None
    org_id = str(payload.get("org_id") or payload.get("tenant_id") or "webber")

    # Build the SAME staging objects the ingest would create — but in memory
    # only; these are never added to a session.
    rec = ZohoSubscriptionRecord(
        org_id=org_id,
        subscription_mgmt_id=fields.get("subscription_mgmt_id"),
        account_name=fields.get("account_name"),
        facility_name=fields.get("facility_name"),
        msisdn=fields.get("msisdn"),
        device_activation_status=raw_status,
        connection_type=fields.get("connection_type"),
        subscription_type=fields.get("subscription_type"),
        mrc=fields.get("mrc"),
        service_term_ends=fields.get("service_term_ends"),
        lifecycle_state=lifecycle,
        raw_json=sanitize(payload),
    )
    rec_map = ExternalRecordMap(
        org_id=org_id, source="zoho_crm", module="Subscription_Mgmt",
        external_record_id=fields.get("subscription_mgmt_id"), map_status="unmapped",
    )

    return {
        "org_id": org_id,
        "routing_matched": matched,
        "ingest_flag_on": str(settings.FEATURE_ZOHO_SUBSCRIPTION_INGEST).strip().lower() == "true",
        "normalizer_flag_on": str(settings.FEATURE_ZOHO_STATUS_NORMALIZER).strip().lower() == "true",
        "raw_device_activation_status": raw_status,
        "normalized_lifecycle_state": lifecycle,
        "review_row": serialize_review_row(rec, rec_map),
        "sanitized_payload": sanitize(payload),
        "top_level_keys": top_level_keys(payload),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Zoho lifecycle ingest dry run (writes nothing).")
    parser.add_argument("--json", help="Path to a real Zoho payload JSON file (default: Webber sample)")
    parser.add_argument("--status", help="Override Device Activation Status (e.g. Active, Suspended)")
    parser.add_argument("--no-normalize", action="store_true", help="Skip lifecycle normalization")
    args = parser.parse_args()

    if args.json:
        with open(args.json, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    else:
        payload = dict(WEBBER_SAMPLE)
    if args.status:
        payload["Device_Activation_Status"] = args.status

    report = build_dryrun_report(payload, normalize=not args.no_normalize)
    review = report["review_row"]

    print("=" * 70)
    print("  ZOHO LIFECYCLE INGEST — DRY RUN (nothing written)")
    print("=" * 70)
    print(f"  org_id:               {report['org_id']}")
    print(f"  routing matched:      {report['routing_matched']}")
    print(f"  FEATURE_ZOHO_SUBSCRIPTION_INGEST: {report['ingest_flag_on']}")
    print(f"  FEATURE_ZOHO_STATUS_NORMALIZER:   {report['normalizer_flag_on']}")
    print()
    print("  Would stage ZohoSubscriptionRecord:")
    print(_indent(json.dumps(review, indent=2, ensure_ascii=False)))
    print()
    print(f"  Raw status:           {report['raw_device_activation_status']!r}")
    print(f"  Normalized lifecycle: {report['normalized_lifecycle_state']!r}")
    print(f"  Presents as active monitoring: {review['presents_as_active_monitoring']}")
    print()
    print("  Sanitized payload (secrets redacted):")
    print(_indent(json.dumps(report["sanitized_payload"], indent=2, ensure_ascii=False)))
    print()
    print("  ⚠  DRY RUN — no DB writes, no observation row, no production change.")
    print("  ⚠  The existing True911 site is NOT modified by ingest (staging only).")
    if not report["normalizer_flag_on"] and not args.no_normalize:
        print("  ⚠  FEATURE_ZOHO_STATUS_NORMALIZER is OFF in this env — in real ingest")
        print("     lifecycle_state would be stored as NULL (raw status still kept).")
    if not report["ingest_flag_on"]:
        print("  ⚠  FEATURE_ZOHO_SUBSCRIPTION_INGEST is OFF — real webhook would fall")
        print("     through to needs_mapping and stage nothing.")
    print("=" * 70)
    return 0


def _indent(text: str, pad: str = "    ") -> str:
    return "\n".join(pad + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
