"""Registration-conversion production audit (READ-ONLY) — prerequisite for CT-1.

For every site reachable through ``registration_locations.materialized_site_id``
report what conversion wrote and what has happened to the site since, then
classify it from EVIDENCE (never from status strings alone):

  A  CLEARLY STILL PLANNED / NEVER DEPLOYED
  B  SUBSEQUENTLY DEPLOYED WITH EVIDENCE
  C  AMBIGUOUS / REQUIRES OPERATOR REVIEW

Strictly read-only: SELECTs inside a READ ONLY transaction (Postgres), always
rolled back.  No writes, backfills, status changes, invites or customer edits.
Emails are masked in output.

Run (operator, Render shell):
    python -m app.audit_registration_conversions
    python -m app.audit_registration_conversions --export-json conversions.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import func, select, text  # noqa: E402

CLASSES = {
    "A": "CLEARLY STILL PLANNED / NEVER DEPLOYED",
    "B": "SUBSEQUENTLY DEPLOYED WITH EVIDENCE",
    "C": "AMBIGUOUS / REQUIRES OPERATOR REVIEW",
}
# A site edited more than this long after it was created was touched after conversion.
EDIT_GRACE = timedelta(minutes=5)
_LIVE_LINE = {"active"}
_LIVE_DEVICE = {"active"}


def mask_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None if not email else "***"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


@dataclass
class SiteEvidence:
    registration_id: str
    registration_status: str
    tenant_id: str
    site_pk: int
    site_id: str
    site_name: Optional[str]
    address: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    edited_after_conversion: bool
    status: Optional[str]
    onboarding_status: Optional[str]
    e911_status: Optional[str]
    e911_confirmation_required: Optional[bool]
    address_source: Optional[str]
    lines_total: int = 0
    lines_active: int = 0
    devices_total: int = 0
    devices_active: int = 0
    devices_with_heartbeat: int = 0
    last_heartbeat: Optional[str] = None
    telemetry_events: int = 0
    service_unit_statuses: dict = field(default_factory=dict)
    provisioning_rows: int = 0
    operator_audit_rows: int = 0          # audit_log_entries for the site, excluding conversion's own
    action_audit_rows: int = 0
    e911_change_logs: int = 0
    e911_review_actions: int = 0
    invite_issued: bool = False
    invite_role: Optional[str] = None
    invite_user_active: Optional[bool] = None
    invite_email_masked: Optional[str] = None
    classification: str = "C"
    reasons: list = field(default_factory=list)


def classify(ev: SiteEvidence) -> tuple[str, list[str]]:
    """Pure: evidence -> (class, reasons).  Status strings are reported, never trusted."""
    live = []
    if ev.devices_with_heartbeat:
        live.append(f"{ev.devices_with_heartbeat} device(s) have reported a heartbeat")
    if ev.telemetry_events:
        live.append(f"{ev.telemetry_events} telemetry event(s)")
    if ev.lines_active:
        live.append(f"{ev.lines_active} active line(s)")
    if ev.devices_active:
        live.append(f"{ev.devices_active} active device(s)")
    any_artifact = (ev.lines_total or ev.devices_total or ev.provisioning_rows or ev.telemetry_events)
    touched = (ev.operator_audit_rows or ev.action_audit_rows or ev.e911_change_logs
               or ev.e911_review_actions or ev.edited_after_conversion)

    # B needs operational signal (heartbeat/telemetry) AND an inventory artifact in service.
    if (ev.devices_with_heartbeat or ev.telemetry_events) and (ev.devices_active or ev.lines_active):
        return "B", live
    if not any_artifact and not touched:
        return "A", ["no lines, devices, telemetry or provisioning; untouched since conversion"]
    reasons = live[:]
    if ev.devices_total or ev.lines_total:
        reasons.append(f"{ev.devices_total} device(s) / {ev.lines_total} line(s) present without "
                       "corroborating operational evidence" if not live else "partial evidence")
    if ev.provisioning_rows:
        reasons.append(f"{ev.provisioning_rows} provisioning queue row(s)")
    if ev.edited_after_conversion:
        reasons.append("site edited after conversion")
    if ev.operator_audit_rows or ev.action_audit_rows:
        reasons.append(f"{ev.operator_audit_rows + ev.action_audit_rows} operator/audit action(s)")
    if ev.e911_change_logs or ev.e911_review_actions:
        reasons.append("E911 change/review activity exists")
    return "C", reasons or ["evidence incomplete"]


def _iso(v) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else (str(v) if v is not None else None)


async def collect(db) -> list[SiteEvidence]:
    from app.models.action_audit import ActionAudit
    from app.models.audit_log_entry import AuditLogEntry
    from app.models.device import Device
    from app.models.e911_change_log import E911ChangeLog
    from app.models.line import Line
    from app.models.provisioning_queue import ProvisioningQueueItem
    from app.models.registration import Registration
    from app.models.registration_location import RegistrationLocation
    from app.models.service_unit import ServiceUnit
    from app.models.site import Site
    from app.models.telemetry_event import TelemetryEvent
    from app.models.user import User

    rows = (await db.execute(
        select(RegistrationLocation, Registration, Site)
        .join(Registration, Registration.id == RegistrationLocation.registration_id)
        .join(Site, Site.id == RegistrationLocation.materialized_site_id)
        .where(RegistrationLocation.materialized_site_id.isnot(None))
        .order_by(Registration.id, RegistrationLocation.id)
    )).all()

    out: list[SiteEvidence] = []
    for _loc, reg, site in rows:
        sid = site.site_id
        edited = bool(site.created_at and site.updated_at
                      and site.updated_at - site.created_at > EDIT_GRACE)
        ev = SiteEvidence(
            registration_id=reg.registration_id, registration_status=reg.status,
            tenant_id=site.tenant_id, site_pk=site.id, site_id=sid, site_name=site.site_name,
            address=", ".join(x for x in (site.e911_street, site.e911_city, site.e911_state,
                                          site.e911_zip) if x) or None,
            created_at=_iso(site.created_at), updated_at=_iso(site.updated_at),
            edited_after_conversion=edited, status=site.status,
            onboarding_status=site.onboarding_status, e911_status=site.e911_status,
            e911_confirmation_required=site.e911_confirmation_required,
            address_source=site.address_source,
        )
        lines = (await db.execute(select(Line.status).where(Line.site_id == sid))).scalars().all()
        ev.lines_total, ev.lines_active = len(lines), sum(1 for s in lines if (s or "").lower() in _LIVE_LINE)
        devs = (await db.execute(select(Device.status, Device.last_heartbeat)
                                 .where(Device.site_id == sid))).all()
        ev.devices_total = len(devs)
        ev.devices_active = sum(1 for s, _ in devs if (s or "").lower() in _LIVE_DEVICE)
        beats = [hb for _, hb in devs if hb is not None]
        ev.devices_with_heartbeat = len(beats)
        ev.last_heartbeat = _iso(max(beats)) if beats else None
        ev.telemetry_events = (await db.execute(select(func.count()).select_from(TelemetryEvent)
                                                .where(TelemetryEvent.site_id == sid))).scalar() or 0
        for st, n in (await db.execute(select(ServiceUnit.status, func.count())
                                       .where(ServiceUnit.site_id == sid)
                                       .group_by(ServiceUnit.status))).all():
            ev.service_unit_statuses[st or "null"] = n
        ev.provisioning_rows = (await db.execute(
            select(func.count()).select_from(ProvisioningQueueItem).where(
                (ProvisioningQueueItem.resolved_site_id == sid)
                | (ProvisioningQueueItem.current_site_id == sid)
                | (ProvisioningQueueItem.suggested_site_id == sid)))).scalar() or 0
        ev.operator_audit_rows = (await db.execute(
            select(func.count()).select_from(AuditLogEntry).where(
                AuditLogEntry.site_id == sid, AuditLogEntry.category != "conversion"))).scalar() or 0
        ev.action_audit_rows = (await db.execute(select(func.count()).select_from(ActionAudit)
                                                 .where(ActionAudit.site_id == sid))).scalar() or 0
        ev.e911_review_actions = (await db.execute(
            select(func.count()).select_from(ActionAudit).where(
                ActionAudit.site_id == sid, ActionAudit.action_type.like("e911%")))).scalar() or 0
        ev.e911_change_logs = (await db.execute(select(func.count()).select_from(E911ChangeLog)
                                                .where(E911ChangeLog.site_id == sid))).scalar() or 0
        email = (reg.submitter_email or "").strip().lower()
        if email and reg.target_tenant_id:
            user = (await db.execute(select(User).where(
                func.lower(User.email) == email, User.tenant_id == reg.target_tenant_id))).scalars().first()
            if user is not None:
                ev.invite_issued = True
                ev.invite_role, ev.invite_user_active = user.role, user.is_active
                ev.invite_email_masked = mask_email(user.email)
        ev.classification, ev.reasons = classify(ev)
        out.append(ev)
    return out


async def run(export_json: Optional[str] = None) -> dict:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            await db.execute(text("SET TRANSACTION READ ONLY"))
        try:
            sites = await collect(db)
        finally:
            await db.rollback()               # never commit anything
    counts = {k: sum(1 for s in sites if s.classification == k) for k in CLASSES}
    report = {"read_only": True, "generated_at": datetime.now(timezone.utc).isoformat(),
              "converted_sites": len(sites),
              "registrations": len({s.registration_id for s in sites}),
              "counts": counts, "classes": CLASSES, "sites": [asdict(s) for s in sites]}
    if export_json:
        with open(export_json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
    return report


def _print(report: dict) -> None:
    print(f"Registration-conversion audit (READ-ONLY) — {report['converted_sites']} site(s) "
          f"from {report['registrations']} registration(s)")
    for k, label in CLASSES.items():
        print(f"  {k}  {label}: {report['counts'][k]}")
    for s in report["sites"]:
        print(f"\n[{s['classification']}] {s['registration_id']} → {s['tenant_id']}/{s['site_id']} "
              f"({s['site_name']})")
        print(f"    status={s['status']!r} onboarding={s['onboarding_status']!r} "
              f"e911_status={s['e911_status']!r} confirm_required={s['e911_confirmation_required']} "
              f"address_source={s['address_source']!r}")
        print(f"    lines {s['lines_active']}/{s['lines_total']} active · devices {s['devices_active']}/"
              f"{s['devices_total']} active, {s['devices_with_heartbeat']} with heartbeat "
              f"(last {s['last_heartbeat']}) · telemetry {s['telemetry_events']} · units "
              f"{s['service_unit_statuses']}")
        print(f"    provisioning {s['provisioning_rows']} · audit {s['operator_audit_rows']} · actions "
              f"{s['action_audit_rows']} · e911 logs {s['e911_change_logs']} / reviews "
              f"{s['e911_review_actions']} · edited_after_conversion={s['edited_after_conversion']}")
        print(f"    invite: issued={s['invite_issued']} role={s['invite_role']!r} "
              f"active={s['invite_user_active']} ({s['invite_email_masked']})")
        print(f"    why: {'; '.join(s['reasons'])}")


def main() -> None:
    p = argparse.ArgumentParser(description="Read-only audit of registration-converted sites.")
    p.add_argument("--export-json", default=None)
    args = p.parse_args()
    _print(asyncio.run(run(export_json=args.export_json)))


if __name__ == "__main__":
    main()
