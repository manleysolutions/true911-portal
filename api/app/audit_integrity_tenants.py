"""Read-only, ARCHIVE-AWARE audit of the Integrity tenants (ipm vs integrity-pm).

NEVER writes — only SELECTs.  Distinguishes OPERATIONAL records from ARCHIVED
records (status archived/retired), reports the tenant's active/retired status,
and resolves a retired tenant with no operational records to
``RETIRED / ARCHIVE ONLY`` rather than "would need migration".

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
ARCHIVED_STATUSES = {"archived", "retired"}


def _is_archived(status) -> bool:
    return (status or "").strip().lower() in ARCHIVED_STATUSES


async def _per_tenant(db, tid: str) -> dict:
    from sqlalchemy import func, select

    from app.models.tenant import Tenant
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

    is_active = (await db.execute(
        select(Tenant.is_active).where(Tenant.tenant_id == tid))).scalar_one_or_none()

    customers = [{"id": c[0], "name": c[1], "zoho": c[2], "status": c[3]} for c in (await db.execute(
        select(Customer.id, Customer.name, Customer.zoho_account_id, Customer.status)
        .where(Customer.tenant_id == tid))).all()]
    sites = [{"site_id": s[0], "name": s[1], "customer_id": s[2], "status": s[3], "e911": s[4]}
             for s in (await db.execute(
                 select(Site.site_id, Site.site_name, Site.customer_id, Site.status, Site.e911_status)
                 .where(Site.tenant_id == tid))).all()]
    users = [{"email": u[0], "role": u[1], "active": u[2]} for u in (await db.execute(
        select(User.email, User.role, User.is_active).where(User.tenant_id == tid))).all()]

    cust_op = [c for c in customers if not _is_archived(c["status"])]
    sites_op = [s for s in sites if not _is_archived(s["status"])]

    return {
        "tenant_id": tid,
        "is_active": bool(is_active) if is_active is not None else False,
        "exists": is_active is not None,
        "customers": customers,
        "sites": sites,
        "users": users,
        "operational": {
            "customers": len(cust_op),
            "sites": len(sites_op),
            "service_units": await count(ServiceUnit),
            "devices": await count(Device),
            "sims": await count(Sim),
            "users": len(users),
            "registrations": await count(Registration),
            "subscriptions": await count(Subscription),
        },
        "archived": {
            "customers": sum(1 for c in customers if _is_archived(c["status"])),
            "sites": sum(1 for s in sites if _is_archived(s["status"])),
        },
        "subscriptions_active": await count(Subscription, Subscription.status == "active"),
    }


def _status_of(rep: dict) -> str:
    op = sum(rep["operational"].values())
    archived = rep["archived"]["customers"] + rep["archived"]["sites"]
    if not rep["is_active"]:
        return "RETIRED / ARCHIVE ONLY" if op == 0 else "RETIRED (still holds operational records — investigate)"
    if op == 0:
        return "ARCHIVE ONLY (still active)" if archived else "EMPTY"
    return "ACTIVE"


def _print_tenant(rep: dict) -> None:
    print(f"\nTenant: {rep['tenant_id']}")
    print("\n  Operational:")
    for k, v in rep["operational"].items():
        print(f"    {k:14}: {v}")
    print("\n  Archived:")
    print(f"    customers     : {rep['archived']['customers']}")
    print(f"    sites         : {rep['archived']['sites']}")
    print(f"\n  Status:\n    {'RETIRED' if not rep['is_active'] else 'ACTIVE'}\n    {_status_of(rep)}")


def _analyze(reports: list[dict]) -> list[str]:
    """Cross-tenant + archive-aware notes. Pure over the gathered reports."""
    notes: list[str] = []

    def op_weight(r):
        return sum(r["operational"].values())

    ranked = sorted(reports, key=op_weight, reverse=True)
    survivor = ranked[0] if ranked and op_weight(ranked[0]) > 0 else None

    if survivor:
        o = survivor["operational"]
        notes.append(f"Survivor: '{survivor['tenant_id']}' is the operational tenant "
                     f"(customers={o['customers']}, sites={o['sites']}, devices={o['devices']}, users={o['users']}).")
    for r in reports:
        if r is survivor:
            continue
        op = op_weight(r)
        arch = r["archived"]["customers"] + r["archived"]["sites"]
        if op == 0 and not r["is_active"]:
            notes.append(f"'{r['tenant_id']}': RETIRED / ARCHIVE ONLY — no operational records "
                         f"({arch} archived rows kept for audit). Eligible for final purge once confirmed.")
        elif op == 0 and r["is_active"]:
            notes.append(f"'{r['tenant_id']}': no operational records but still ACTIVE "
                         f"({arch} archived) — consider retiring the tenant.")
        elif op > 0:
            notes.append(f"'{r['tenant_id']}': still holds {op} operational record(s) — "
                         f"consolidation incomplete; do not purge.")

    # Duplicate customers by Zoho account across tenants — OPERATIONAL only
    # (archived duplicates are the intended cleanup result).
    zoho_seen: dict[str, list[str]] = {}
    for r in reports:
        for c in r["customers"]:
            if c["zoho"] and not _is_archived(c["status"]):
                zoho_seen.setdefault(c["zoho"], []).append(f"{r['tenant_id']}:cust#{c['id']}")
    for zoho, owners in zoho_seen.items():
        if len(owners) > 1:
            notes.append(f"Duplicate OPERATIONAL customer by Zoho account {zoho}: {owners}")

    # Operational sites pointing at a customer in a different tenant.
    op_cust_by_tenant = {r["tenant_id"]: {c["id"] for c in r["customers"] if not _is_archived(c["status"])}
                         for r in reports}
    for r in reports:
        for s in r["sites"]:
            if _is_archived(s["status"]):
                continue
            cid = s["customer_id"]
            if cid is not None and cid not in op_cust_by_tenant.get(r["tenant_id"], set()):
                owner = next((tt for tt, ids in op_cust_by_tenant.items() if cid in ids), "UNKNOWN")
                notes.append(f"Cross-tenant site→customer: site {s['site_id']} (tenant {r['tenant_id']}) "
                             f"references customer_id={cid} owned by tenant '{owner}'.")
    return notes


async def run(tenant_ids: list[str]) -> None:
    from app.database import AsyncSessionLocal

    print("=" * 64)
    print("Integrity tenant audit — ARCHIVE-AWARE (READ-ONLY — no writes)")
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
    print("\n  (Findings only — this script writes nothing.)")


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
