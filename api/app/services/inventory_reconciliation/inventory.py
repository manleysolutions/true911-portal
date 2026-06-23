"""Read-only True911 inventory loader for reconciliation.

Builds the canonical ``True911Item`` list from Device + its resolved Site,
Customer, ServiceUnit, E911, and last telemetry. Optionally tenant-scoped
(customer-agnostic — pass any tenant). SELECT-only; never writes.
"""

from __future__ import annotations

from typing import Optional

from app.services.inventory_reconciliation.models import True911Item


async def load_true911_inventory(db, *, tenant_id: Optional[str] = None) -> list[True911Item]:
    from sqlalchemy import select
    from app.models.device import Device
    from app.models.service_unit import ServiceUnit
    from app.models.site import Site

    dq = select(Device)
    sq = select(Site)
    uq = select(ServiceUnit)
    if tenant_id:
        dq = dq.where(Device.tenant_id == tenant_id)
        sq = sq.where(Site.tenant_id == tenant_id)
        uq = uq.where(ServiceUnit.tenant_id == tenant_id)

    devices = (await db.execute(dq)).scalars().all()
    sites = {s.site_id: s for s in (await db.execute(sq)).scalars().all()}
    unit_by_device: dict = {}
    for u in (await db.execute(uq)).scalars().all():
        if u.device_id:
            unit_by_device.setdefault(u.device_id, u)

    items: list[True911Item] = []
    for d in devices:
        site = sites.get(d.site_id)
        unit = unit_by_device.get(d.device_id)
        items.append(True911Item(
            device_id=d.device_id,
            iccid=d.iccid,
            radio_number=d.serial_number,   # NAPCO RadioNumber is stored as the device serial
            site_id=d.site_id,
            site_name=(site.site_name if site else None),
            customer_name=(site.customer_name if site else None),
            service_unit_id=(unit.unit_id if unit else None),
            e911_status=(site.e911_status if site else None),
            last_telemetry=(d.last_heartbeat.isoformat() if d.last_heartbeat else None),
        ))
    return items
