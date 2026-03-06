"""
True911 Command — Report generation (CSV export).
"""

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, require_permission
from ..models.site import Site
from ..models.device import Device
from ..models.incident import Incident
from ..models.user import User

router = APIRouter()


def _stream_csv(rows: list[dict], filename: str) -> StreamingResponse:
    """Build a StreamingResponse from a list of dicts."""
    if not rows:
        buf = io.StringIO("No data\n")
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/portfolio")
async def export_portfolio_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_EXPORT_REPORTS")),
):
    """Export portfolio-level CSV with site status, device counts, incident counts."""
    tenant = current_user.tenant_id

    sites_q = await db.execute(select(Site).where(Site.tenant_id == tenant).order_by(Site.site_name))
    sites = list(sites_q.scalars().all())

    devices_q = await db.execute(select(Device).where(Device.tenant_id == tenant))
    devices = list(devices_q.scalars().all())

    incidents_q = await db.execute(select(Incident).where(Incident.tenant_id == tenant))
    incidents = list(incidents_q.scalars().all())

    # Build lookup maps
    dev_by_site: dict[str, list] = {}
    for d in devices:
        dev_by_site.setdefault(d.site_id, []).append(d)

    inc_by_site: dict[str, list] = {}
    for i in incidents:
        inc_by_site.setdefault(i.site_id, []).append(i)

    rows = []
    for s in sites:
        site_devs = dev_by_site.get(s.site_id, [])
        site_incs = inc_by_site.get(s.site_id, [])
        active_incs = [i for i in site_incs if i.status in ("new", "open", "acknowledged", "in_progress")]
        rows.append({
            "Site ID": s.site_id,
            "Site Name": s.site_name,
            "Customer": s.customer_name or "",
            "Status": s.status or "",
            "Kit Type": s.kit_type or "",
            "Address": f"{s.e911_street or ''}, {s.e911_city or ''}, {s.e911_state or ''} {s.e911_zip or ''}".strip(", "),
            "Total Devices": len(site_devs),
            "Active Devices": sum(1 for d in site_devs if d.status == "active"),
            "Total Incidents": len(site_incs),
            "Active Incidents": len(active_incs),
            "Critical Incidents": sum(1 for i in active_incs if i.severity == "critical"),
            "Last Check-in": s.last_checkin.isoformat() if s.last_checkin else "",
        })

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return _stream_csv(rows, f"true911_portfolio_{now_str}.csv")


@router.get("/reports/site/{site_id}")
async def export_site_report(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_EXPORT_REPORTS")),
):
    """Export site-level CSV with incident history and device details."""
    tenant = current_user.tenant_id

    site_q = await db.execute(select(Site).where(Site.tenant_id == tenant, Site.site_id == site_id))
    site = site_q.scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Site not found")

    incidents_q = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant, Incident.site_id == site_id)
        .order_by(Incident.opened_at.desc())
        .limit(200)
    )
    incidents = list(incidents_q.scalars().all())

    rows = []
    for inc in incidents:
        rows.append({
            "Incident ID": inc.incident_id,
            "Summary": inc.summary,
            "Severity": inc.severity,
            "Status": inc.status,
            "Type": inc.incident_type or "",
            "Source": inc.source or "",
            "Location": inc.location_detail or "",
            "Opened At": inc.opened_at.isoformat() if inc.opened_at else "",
            "Acknowledged By": inc.ack_by or "",
            "Acknowledged At": inc.ack_at.isoformat() if inc.ack_at else "",
            "Assigned To": inc.assigned_to or "",
            "Resolved At": inc.resolved_at.isoformat() if inc.resolved_at else "",
            "Resolution Notes": inc.resolution_notes or "",
            "Escalation Level": inc.escalation_level or 0,
        })

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    safe_name = site.site_name.replace(" ", "_")[:30] if site.site_name else site_id
    return _stream_csv(rows, f"true911_site_{safe_name}_{now_str}.csv")
