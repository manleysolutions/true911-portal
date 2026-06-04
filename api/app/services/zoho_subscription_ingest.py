"""Stage Zoho Subscription_Mgmt webhook events into shadow tables — Phase 1.

Gated by ``FEATURE_ZOHO_SUBSCRIPTION_INGEST`` (the processor checks the flag;
this module assumes it is on).  Everything here writes ONLY to the additive
staging tables — ``zoho_subscription_records``, ``external_record_map``,
``zoho_payload_observations`` — and NEVER to sites/devices/lines/customers.

The Zoho field contract is not finalized, so field extraction is tolerant: each
logical field is matched against several likely key spellings via a normalized
(lowercase, non-alphanumeric-stripped) key index, so "Account_Name",
"Account Name" and "account_name" all resolve.

``lifecycle_state`` is left untouched here — the Phase 2 normalizer
(``FEATURE_ZOHO_STATUS_NORMALIZER``) is the only writer of that column.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.external_record_map import ExternalRecordMap
from app.models.integration_event import IntegrationEvent
from app.models.zoho_payload_observation import ZohoPayloadObservation
from app.models.zoho_subscription_record import ZohoSubscriptionRecord
from app.services.zoho_payload_sanitizer import sanitize, top_level_keys
from app.services.zoho_status_normalizer import normalize_activation_status

logger = logging.getLogger("true911.zoho_subscription_ingest")


def _flag_on(value: str) -> bool:
    return str(value).strip().lower() == "true"

_MODULE = "Subscription_Mgmt"
_SOURCE = "zoho_crm"

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _norm(key: str) -> str:
    return _NON_ALNUM.sub("", str(key).lower())


def _index_by_norm(payload: dict[str, Any]) -> dict[str, Any]:
    """Map normalized key -> value (first occurrence wins)."""
    idx: dict[str, Any] = {}
    for k, v in payload.items():
        nk = _norm(k)
        if nk not in idx:
            idx[nk] = v
    return idx


def _get(idx: dict[str, Any], *candidates: str) -> Optional[Any]:
    for cand in candidates:
        nc = _norm(cand)
        if nc in idx:
            val = idx[nc]
            if val is not None and val != "":
                return val
    return None


def _parse_decimal(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^0-9.\-]", "", str(val))
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def extract_subscription_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Pure: pull the task-3 lifecycle fields from a Zoho payload (tolerant keys)."""
    if not isinstance(payload, dict):
        return {}
    idx = _index_by_norm(payload)
    # Account / Parent_Account are CRM-API lookup objects ({name, id}); webhook
    # payloads send plain strings. Resolve name + id, falling back to the parent.
    account_val = _get(idx, "Account", "Account_Name", "Account Name")
    parent_val = _get(idx, "Parent_Account", "Parent Account", "ParentAccount")
    return {
        "subscription_mgmt_id": _coerce_str(
            _get(idx, "Subscription_Mgmt_ID", "Subscription Mgmt ID",
                 "subscription_mgmt_id", "Subscription_ID", "external_record_id",
                 "external_id", "id")
        ),
        "account_name": (_coerce_str(_lookup_name(account_val))
                         or _coerce_str(_lookup_name(parent_val))),
        # Not persisted (no column — would need a migration); retained in raw_json.
        "external_account_id": (_coerce_str(_lookup_id(account_val))
                                or _coerce_str(_lookup_id(parent_val))),
        "facility_name": _coerce_str(_get(idx, "FacilityName", "Facility_Name", "Facility Name")),
        "msisdn": _coerce_str(
            _get(idx, "MSISDN", "Mobile_Number", "Mobile Number", "Mobile", "Phone_Number")
        ),
        "device_activation_status": _coerce_str(
            _get(idx, "Device_Activation_Status", "Device Activation Status", "Activation_Status")
        ),
        "connection_type": _coerce_str(_get(idx, "Connection_Type", "Connection Type")),
        "subscription_type": _coerce_str(_get(idx, "Subscription_Type", "Subscription Type")),
        "mrc": _parse_decimal(
            _get(idx, "Monthly_Charges_MS", "Monthly_Recurring_Charge",
                 "Monthly Recurring Charge", "MRC")
        ),
        "service_term_ends": _parse_date(
            _get(idx, "Svc_Term_Ends", "Service_Term_Ends", "Service Term Ends",
                 "Term_End", "term_end_date")
        ),
    }


def _coerce_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _lookup_name(val: Any) -> Any:
    """Resolve a Zoho lookup field to its display name.

    The CRM API returns lookups (Account / Parent_Account) as
    ``{"name": "...", "id": "..."}``; webhook payloads send a plain string.
    Pass-through for non-dict values keeps both formats working.
    """
    if isinstance(val, dict):
        return val.get("name") or val.get("Name")
    return val


def _lookup_id(val: Any) -> Any:
    """Resolve a Zoho lookup field to its record id, or None for a plain string."""
    if isinstance(val, dict):
        return val.get("id") or val.get("Id")
    return None


# ── DB writes (staging only) ─────────────────────────────────────────

async def record_observation(
    db: AsyncSession, event: IntegrationEvent, *, matched: bool
) -> ZohoPayloadObservation:
    """Persist a sanitized, secret-free structural snapshot of the payload.

    Captures matched AND unmatched Zoho events so the real contract can be
    learned from production.  The full body remains on event.payload_json.
    """
    payload = event.payload_json or {}
    module = str(payload.get("module") or "").strip() or None
    obs = ZohoPayloadObservation(
        org_id=event.org_id,
        module=module[:100] if module else None,
        event_type=(event.event_type or None),
        matched_subscription=matched,
        top_level_keys=top_level_keys(payload),
        sanitized_payload=sanitize(payload),
        integration_event_id=event.id,
    )
    db.add(obs)
    await db.flush()
    return obs


async def ingest_subscription_event(
    db: AsyncSession, event: IntegrationEvent
) -> dict[str, Any]:
    """Upsert a Zoho Subscription_Mgmt record into staging (idempotent).

    Returns a result dict including ``event_status`` for the processor to apply.
    Never touches production tables.
    """
    payload = event.payload_json or {}
    fields = extract_subscription_fields(payload)
    sub_mgmt_id = fields.get("subscription_mgmt_id")

    if not sub_mgmt_id:
        # Cannot key the staging row; the observation already captured the
        # payload for inspection.  Surface as needs_mapping (no data lost).
        logger.info(
            "Zoho subscription event %s has no resolvable Subscription Mgmt ID; "
            "marked needs_mapping for review", event.id,
        )
        return {
            "event_status": "needs_mapping",
            "reason": "missing subscription_mgmt_id",
        }

    rec_map = await _upsert_record_map(db, event.org_id, sub_mgmt_id)
    rec = await _upsert_subscription_record(
        db, event.org_id, fields, sanitize(payload), event.id, rec_map.id
    )

    return {
        "event_status": "processed",
        "action": "staged",
        "subscription_record_id": rec.id,
        "subscription_mgmt_id": sub_mgmt_id,
        "map_status": rec_map.map_status,
        "device_activation_status": rec.device_activation_status,
        "lifecycle_state": rec.lifecycle_state,
    }


async def _upsert_record_map(
    db: AsyncSession, org_id: str, external_record_id: str
) -> ExternalRecordMap:
    result = await db.execute(
        select(ExternalRecordMap).where(
            ExternalRecordMap.source == _SOURCE,
            ExternalRecordMap.module == _MODULE,
            ExternalRecordMap.external_record_id == external_record_id,
        )
    )
    rec_map = result.scalar_one_or_none()
    if rec_map is None:
        rec_map = ExternalRecordMap(
            org_id=org_id,
            source=_SOURCE,
            module=_MODULE,
            external_record_id=external_record_id,
            map_status="unmapped",  # never auto-confirmed
        )
        db.add(rec_map)
        await db.flush()
    return rec_map


async def _upsert_subscription_record(
    db: AsyncSession,
    org_id: str,
    fields: dict[str, Any],
    sanitized_payload: dict[str, Any],
    event_id: int,
    rec_map_id: int,
) -> ZohoSubscriptionRecord:
    result = await db.execute(
        select(ZohoSubscriptionRecord).where(
            ZohoSubscriptionRecord.org_id == org_id,
            ZohoSubscriptionRecord.subscription_mgmt_id == fields["subscription_mgmt_id"],
        )
    )
    rec = result.scalar_one_or_none()
    if rec is None:
        rec = ZohoSubscriptionRecord(
            org_id=org_id,
            subscription_mgmt_id=fields["subscription_mgmt_id"],
        )
        db.add(rec)

    # Overwrite only with present values, so a partial later payload never nulls
    # previously-captured data (additive / non-destructive).
    for col in (
        "account_name", "facility_name", "msisdn", "device_activation_status",
        "connection_type", "subscription_type", "mrc", "service_term_ends",
    ):
        val = fields.get(col)
        if val is not None:
            setattr(rec, col, val)

    # Normalize to a canonical LIFECYCLE state, gated by FEATURE_ZOHO_STATUS_NORMALIZER.
    # Computed from the EFFECTIVE device_activation_status (post preserve-on-missing
    # merge above).  When the flag is off, lifecycle_state is left untouched (NULL on
    # create; prior value preserved on update) so this stays a pure additive opt-in.
    if _flag_on(settings.FEATURE_ZOHO_STATUS_NORMALIZER):
        rec.lifecycle_state = normalize_activation_status(rec.device_activation_status)

    rec.external_record_map_id = rec_map_id
    rec.last_event_id = event_id
    rec.raw_json = sanitized_payload
    await db.flush()
    return rec
