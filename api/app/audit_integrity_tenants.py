"""Read-only audit of the Integrity duplicate-tenant situation (ipm vs integrity-pm).

NEVER writes — only SELECTs. Prints per-tenant counts + identities and a
cross-tenant analysis so an operator can decide which tenant is real before any
(separate, future) cleanup. Does not delete, migrate, or modify anything.

Run:
    python -m app.audit_integrity_tenants
    AUDIT_TENANTS=ipm,integrity-pm python -m app.audit_integrity_tenants
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_TENANTS = ["ipm", "integrity-pm"]


async def _per_tenant(db, tid: str) -> dict:
    from sqlalchemy import func, select

    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.models.device import Device
    from app.models.sim import Sim
    from app.models.user import User
    from app.models.subscription import Subscription
    from app.models.registration import Registration

    async def count(model, *where):
        q = select(func.count()).select_from(model).where(model.tenant_id == tid)
        for w in where:
            q = q.where(w)
        return int((await db.execute(q)).scalar() or 0)

    customers = (await db.execute(
        select(Customer.id, Customer.name, Customer.zoho_account_id)
        .where(Customer.tenant_id == tid))).all()
    sites = (await db.execute(
        select(Site.site_id, Site.site_name, Site.customer_id, Site.status, Site.e911_status)
        .where(Site.tenant_id == tid))).all()
    users = (await db.execute(
        select(User.email, User.role, User.is_active).where(User.tenant_id == tid))).all()

    return {
        "tenant_id": tid,
        "customers": [{"id": c[0], "name": c[1], "zoho": c[2]} for c in customers],
        "sites": [{"site_id": s[0], "name": s[1], "customer_id": s[2],
                   "status": s[3], "e911": s[4]} for s in sites],
        "users": [{"email": u[0], "role": u[1], "active": u[2]} for u in users],
        "service_units": await count(ServiceUnit),
        "devices": await count(Device),
        "sims": await count(Sim),
        "registrations": await count(Registration),
        "subscriptions": await count(Subscription),
        "subscriptions_active": await count(Subscription, Subscription.status == "active"),
    }


def _print_tenant(rep: dict) -> None:
    print(f"\nTenant: {rep['tenant_id']}")
    print(f"  customers:     {len(rep['customers'])}")
    for c in rep["customers"]:
        print(f"      - id={c['id']} name={c['name']!r} zoho={c['zoho']}")
    print(f"  sites:         {len(rep['sites'])}")
    for s in rep["sites"]:
        print(f"      - {s['site_id']} {s['name']!r} customer_id={s['customer_id']} "
              f"status={s['status']} e911={s['e911']}")
    print(f"  service_units: {rep['service_units']}")
    print(f"  devices:       {rep['devices']}")
    print(f"  sims:          {rep['sims']}")
    print(f"  users:         {len(rep['users'])}")
    for u in rep["users"]:
        print(f"      - {u['email']} role={u['role']} active={u['active']}")
    print(f"  registrations: {rep['registrations']}")
    print(f"  subscriptions: {rep['subscriptions']} (active {rep['subscriptions_active']})")


def _analyze(reports: list[dict]) -> list[str]:
    """Cross-tenant + orphan notes. Pure over the gathered reports."""
    notes: list[str] = []

    # Which tenant has substantive data?
    def weight(r):
        return len(r["customers"]) + len(r["sites"]) + r["devices"] + len(r["users"])

    ranked = sorted(reports, key=weight, reverse=True)
    survivor = ranked[0] if ranked and weight(ranked[0]) > 0 else None
    obsolete = [r for r in reports if r is not survivor]

    if survivor:
        notes.append(f"Survivor candidate: '{survivor['tenant_id']}' "
                     f"(customers={len(survivor['customers'])}, sites={len(survivor['sites'])}, "
                     f"devices={survivor['devices']}, users={len(survivor['users'])}).")
    for r in obsolete:
        if weight(r) == 0:
            notes.append(f"Obsolete/empty: '{r['tenant_id']}' has zero customers/sites/devices/users "
                         f"— safe to purge ONLY after confirming nothing references it.")
        else:
            notes.append(f"Non-empty secondary: '{r['tenant_id']}' still holds data "
                         f"(customers={len(r['customers'])}, sites={len(r['sites'])}, "
                         f"devices={r['devices']}, users={len(r['users'])}) — would need migration, not deletion.")

    # Duplicate customers by zoho account across tenants.
    zoho_seen: dict[str, list[str]] = {}
    for r in reports:
        for c in r["customers"]:
            if c["zoho"]:
                zoho_seen.setdefault(c["zoho"], []).append(f"{r['tenant_id']}:cust#{c['id']}")
    for zoho, owners in zoho_seen.items():
        if len(owners) > 1:
            notes.append(f"Duplicate customer by Zoho account {zoho}: {owners}")

    # Sites pointing at a customer_id that belongs to a different tenant.
    cust_ids_by_tenant = {r["tenant_id"]: {c["id"] for c in r["customers"]} for r in reports}
    for r in reports:
        for s in r["sites"]:
            cid = s["customer_id"]
            if cid is not None and cid not in cust_ids_by_tenant.get(r["tenant_id"], set()):
                owner = next((tt for tt, ids in cust_ids_by_tenant.items() if cid in ids), "UNKNOWN")
                notes.append(f"Cross-tenant site→customer: site {s['site_id']} (tenant {r['tenant_id']}) "
                             f"references customer_id={cid} owned by tenant '{owner}'.")
    return notes


async def run(tenant_ids: list[str]) -> None:
    from app.database import AsyncSessionLocal

    print("=" * 64)
    print("Integrity duplicate-tenant audit (READ-ONLY — no writes)")
    print("=" * 64)
    print(f"  tenants: {', '.join(tenant_ids)}")

    async with AsyncSessionLocal() as db:
        reports = [await _per_tenant(db, tid) for tid in tenant_ids]

    for rep in reports:
        _print_tenant(rep)

    print("\n" + "=" * 64)
    print("ANALYSIS")
    print("=" * 64)
    for note in _analyze(reports):
        print(f"  - {note}")
    print("\n  (Findings only — this script writes nothing. Any cleanup is a "
          "separate, reviewed step.)")


def main() -> None:
    tenant_ids = [t.strip() for t in os.environ.get(
        "AUDIT_TENANTS", ",".join(DEFAULT_TENANTS)).split(",") if t.strip()]
    try:
        asyncio.run(run(tenant_ids))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
