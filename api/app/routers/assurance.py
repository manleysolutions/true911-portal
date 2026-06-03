"""Assurance Engine API — read-only customer-facing site assurance label.

Every route returns 404 when ``FEATURE_ASSURANCE_ENGINE`` is not exactly
``"true"`` (matching the ``FEATURE_LLLM`` / line-intelligence precedent), so a
misconfigured client cannot tell the surface exists.  When on, routes require
``VIEW_ASSURANCE`` and are tenant-scoped to the caller's effective tenant.

Read-only: no writes, no snapshots, no vendor payloads in the response.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, is_platform_user, require_permission
from app.models.user import User
from app.services.assurance import compute_site_assurance
from app.services.assurance.signals import AssuranceLabel
from app.services.assurance.loader import load_site_assurance_signals
from app.services.assurance import reason_codes as rc

router = APIRouter()

_DISCLAIMER = (
    "Status reflects the latest available platform data and does not replace "
    "required manual life-safety testing or regulatory inspections."
)

_LABEL_SUMMARY = {
    AssuranceLabel.PROTECTED: "Emergency calling is active and verified.",
    AssuranceLabel.ATTENTION: "This location is working, but we're reviewing an item to keep it fully protected.",
    AssuranceLabel.CRITICAL: "This location needs immediate attention — emergency calling may not work. Manley Solutions has been alerted.",
    AssuranceLabel.INACTIVE: "Service at this location is not currently active.",
    AssuranceLabel.PENDING_INSTALL: "This location is being set up. Protection will be confirmed once installation and testing are complete.",
    AssuranceLabel.UNKNOWN: "We're confirming the status of this location.",
}
_LABEL_RECOMMENDED = {
    AssuranceLabel.PROTECTED: "No action needed.",
    AssuranceLabel.ATTENTION: "Manley Solutions is reviewing this location.",
    AssuranceLabel.CRITICAL: "Manley Solutions has been alerted and is addressing this issue.",
    AssuranceLabel.INACTIVE: "No action needed — service is inactive.",
    AssuranceLabel.PENDING_INSTALL: "Installation and testing are in progress.",
    AssuranceLabel.UNKNOWN: "Manley Solutions is confirming this location's status.",
}
# Internal/support equivalent label string (customer sees "Protected").
_INTERNAL_LABEL = {AssuranceLabel.PROTECTED: "Active & Verified"}


def _require_feature() -> None:
    if settings.FEATURE_ASSURANCE_ENGINE.strip().lower() != "true":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


def _serialize_reasons(codes: tuple[str, ...], *, internal: bool) -> list[dict]:
    out = []
    for code in codes:
        meta = rc.ALL.get(code)
        if meta is None:
            continue
        entry = {"code": meta.code, "severity": meta.severity.value, "message": meta.customer_message}
        if internal:
            entry["internal_action"] = meta.internal_action
        out.append(entry)
    return out


@router.get("/site/{site_id}")
async def get_site_assurance(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_ASSURANCE")),
):
    """Compute the read-only assurance label for one site in the caller's tenant."""
    _require_feature()

    now = datetime.now(timezone.utc)
    signals = await load_site_assurance_signals(db, current_user.tenant_id, site_id)
    if signals is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    result = compute_site_assurance(signals, now=now)
    internal = is_platform_user(current_user)
    as_of = now.isoformat()

    devices = [
        {
            "device_id": d.device_id,
            "name": d.model or d.device_type or d.device_id,
            "device_type": d.device_type,
            "label": d.label.value,
            "last_heartbeat": d.last_heartbeat_at.isoformat() if d.last_heartbeat_at else None,
            "reasons": [c for c in d.reason_codes],
        }
        for d in result.devices
    ]
    service_units = [
        {
            "unit_id": u.unit_id,
            "unit_name": u.unit_name,
            "unit_type": u.unit_type,
            "status": u.status,
            "has_active_device": u.has_active_device,
        }
        for u in signals.service_units
    ]
    last_test = (
        {
            "at": signals.last_test.at.isoformat(),
            "result": signals.last_test.result,
            "source": signals.last_test.source,
        }
        if signals.last_test
        else None
    )

    statement = (
        f"Protected as of {as_of}"
        if result.label == AssuranceLabel.PROTECTED
        else _LABEL_SUMMARY[result.label]
    )

    return {
        "site_id": signals.site_id,
        "site_name": signals.site_name,
        "customer_name": signals.customer_name,
        "assurance_label": result.label.value,
        "internal_label": _INTERNAL_LABEL.get(result.label, result.label.value),
        "as_of": as_of,
        "statement": statement,
        "summary": _LABEL_SUMMARY[result.label],
        "recommended_action": _LABEL_RECOMMENDED[result.label],
        "reasons": _serialize_reasons(result.reason_codes, internal=internal),
        "devices": devices,
        "service_units": service_units,
        "e911_status": {
            "address_present": signals.e911_address_present,
            "status": signals.e911_status,
            "confirmation_required": signals.e911_confirmation_required,
        },
        "last_test": last_test,
        "disclaimer": _DISCLAIMER,
        "read_only": True,
    }
