"""Generic, READ-ONLY portfolio audit — evaluate every tenant the same way.

The methodology we used for Integrity, generalized to all customers: per tenant
it gathers OPERATIONAL vs ARCHIVED record counts, E911 completeness, a device
reachability proxy, classifies the tenant (active / retired / archive-only /
duplicate-name / orphaned / empty / healthy), and computes a Tenant Health
Score with Operational Risks and Cleanup Opportunities.

NEVER writes — only SELECTs.  No production changes.

Run:
    python -m app.portfolio_audit                          # all tenants
    PORTFOLIO_AUDIT_TENANT=restoration-hardware python -m app.portfolio_audit
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# A record is ARCHIVED when its status is one of these (set by the cleanup flow).
ARCHIVED_STATUSES = frozenset({"archived", "retired"})
# E911 status values that count as a verified dispatchable location.
VERIFIED_E911 = frozenset({"validated", "verified", "confirmed"})
# Device "fresh" window for the reachability proxy (audit-grade, not real-time).
DEVICE_FRESH_DAYS = int(os.environ.get("PORTFOLIO_DEVICE_FRESH_DAYS", "7"))

OPERATIONAL_KINDS = ("customers_op", "sites_op", "service_units", "devices",
                     "sims", "users", "subscriptions", "registrations")


@dataclass
class TenantMetrics:
    tenant_id: str
    name: str = ""
    is_active: bool = True
    # operational counts
    customers_op: int = 0
    sites_op: int = 0
    service_units: int = 0
    devices: int = 0
    sims: int = 0
    users: int = 0
    subscriptions: int = 0
    registrations: int = 0
    # archived counts
    customers_archived: int = 0
    sites_archived: int = 0
    # E911 (over operational sites)
    sites_with_e911_address: int = 0
    sites_e911_verified: int = 0
    # device reachability (over operational devices)
    devices_with_heartbeat: int = 0
    devices_fresh: int = 0
    # cross-tenant context
    duplicate_name: bool = False


# ── Pure classification + scoring (no I/O) ───────────────────────────

def has_operational_records(m: TenantMetrics) -> bool:
    return any(getattr(m, k) > 0 for k in OPERATIONAL_KINDS)


def classify_tenant(m: TenantMetrics) -> dict:
    """Return {'primary': <status>, 'flags': [...]} — works for ANY tenant."""
    op = has_operational_records(m)
    archived = (m.customers_archived + m.sites_archived) > 0
    orphaned = (m.sites_op > 0 or m.devices > 0) and m.customers_op == 0

    flags: list[str] = []
    if m.is_active:
        flags.append("active")
    else:
        flags.append("retired")
    if not op and archived:
        flags.append("archive-only")
    if not op and not archived:
        flags.append("empty")
    if m.duplicate_name:
        flags.append("duplicate-name")
    if orphaned:
        flags.append("orphaned")
    if m.is_active and op and not orphaned and not m.duplicate_name:
        flags.append("healthy")

    if not m.is_active:
        primary = "RETIRED / ARCHIVE ONLY" if not op else "RETIRED (has operational records — investigate)"
    elif not op:
        primary = "ARCHIVE ONLY" if archived else "EMPTY"
    elif orphaned:
        primary = "ORPHANED"
    else:
        primary = "ACTIVE"
    return {"primary": primary, "flags": flags}


def score_tenant(m: TenantMetrics) -> dict:
    """Deterministic 0–100 Tenant Health Score (None when no operational records).

    Weights (life-safety first): E911 40 · device reachability 30 · ownership 20
    · hygiene 10.
    """
    if not has_operational_records(m):
        return {"score": None, "components": {}, "note": "no operational records — score not applicable"}

    e911 = (m.sites_e911_verified / m.sites_op) if m.sites_op else 0.0
    # No devices on an operational tenant = cannot confirm reachability → 0.
    dev = (m.devices_fresh / m.devices) if m.devices else 0.0
    own = 1.0 if m.customers_op > 0 else 0.0
    hyg = 1.0
    if m.duplicate_name:
        hyg -= 0.5
    if (m.sites_op > 0 or m.devices > 0) and m.customers_op == 0:
        hyg -= 0.5
    hyg = max(0.0, hyg)

    components = {
        "e911": round(e911 * 40, 1),
        "device_health": round(dev * 30, 1),
        "ownership": round(own * 20, 1),
        "hygiene": round(hyg * 10, 1),
    }
    return {"score": round(sum(components.values())), "components": components}


def risks_and_opportunities(m: TenantMetrics) -> dict:
    risks: list[str] = []
    opps: list[str] = []
    op = has_operational_records(m)

    if op:
        missing_e911 = max(0, m.sites_op - m.sites_e911_verified)
        if missing_e911:
            risks.append(f"{missing_e911} active site(s) without verified E911")
        if m.devices and m.devices_fresh < m.devices:
            risks.append(f"{m.devices - m.devices_fresh} device(s) without a fresh heartbeat ({DEVICE_FRESH_DAYS}d)")
        if m.sites_op > 0 and m.devices == 0:
            risks.append("active sites but no devices — cannot confirm reachability")
        if m.customers_op == 0 and (m.sites_op > 0 or m.devices > 0):
            risks.append("operational records with no owning customer (orphaned)")
        if m.duplicate_name:
            opps.append("shares a name with another tenant — verify it is not a duplicate")
    if not m.is_active and op:
        risks.append("RETIRED tenant still holds operational records — investigate before purge")

    if (m.customers_archived + m.sites_archived) > 0:
        if m.is_active and not op:
            opps.append("archive-only but still active — consider retiring the tenant")
        if not m.is_active:
            opps.append("retired with archived rows — eligible for final purge once confirmed")
    if m.is_active and not op and (m.customers_archived + m.sites_archived) == 0:
        opps.append("empty + active — eligible for purge-empty")
    return {"risks": risks, "opportunities": opps}


def assess_tenant(m: TenantMetrics) -> dict:
    """Full per-tenant assessment (pure)."""
    cls = classify_tenant(m)
    sc = score_tenant(m)
    ro = risks_and_opportunities(m)
    return {
        "tenant_id": m.tenant_id, "name": m.name, "is_active": m.is_active,
        "status": cls["primary"], "flags": cls["flags"],
        "score": sc["score"], "components": sc["components"],
        "operational": {k.replace("_op", ""): getattr(m, k) for k in OPERATIONAL_KINDS},
        "archived": {"customers": m.customers_archived, "sites": m.sites_archived},
        "e911": {"sites": m.sites_op, "with_address": m.sites_with_e911_address,
                 "verified": m.sites_e911_verified},
        "device_health": {"devices": m.devices, "with_heartbeat": m.devices_with_heartbeat,
                          "fresh": m.devices_fresh},
        "risks": ro["risks"], "opportunities": ro["opportunities"],
    }


# ── Read-only DB loader ──────────────────────────────────────────────

async def load_metrics(db, tenant_filter: str | None = None) -> list[TenantMetrics]:
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

    tq = select(Tenant)
    if tenant_filter:
        tq = tq.where(Tenant.tenant_id == tenant_filter)
    tenants = (await db.execute(tq.order_by(Tenant.created_at))).scalars().all()

    def lower_in(col, values):
        return func.lower(func.coalesce(col, "")).in_(list(values))

    async def grouped(col_tenant, *where):
        q = select(col_tenant, func.count()).group_by(col_tenant)
        for w in where:
            q = q.where(w)
        return {r[0]: int(r[1]) for r in (await db.execute(q)).all()}

    archived = lambda col: lower_in(col, ARCHIVED_STATUSES)  # noqa: E731
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=DEVICE_FRESH_DAYS)

    customers_arch = await grouped(Customer.tenant_id, archived(Customer.status))
    customers_op = await grouped(Customer.tenant_id, ~archived(Customer.status))
    sites_arch = await grouped(Site.tenant_id, archived(Site.status))
    sites_op = await grouped(Site.tenant_id, ~archived(Site.status))
    sites_e911_addr = await grouped(Site.tenant_id, ~archived(Site.status),
                                    func.coalesce(Site.e911_street, "") != "")
    sites_e911_ver = await grouped(Site.tenant_id, ~archived(Site.status),
                                   lower_in(Site.e911_status, VERIFIED_E911))
    units = await grouped(ServiceUnit.tenant_id)
    devices = await grouped(Device.tenant_id)
    devices_hb = await grouped(Device.tenant_id, Device.last_heartbeat.is_not(None))
    devices_fresh = await grouped(Device.tenant_id, Device.last_heartbeat >= cutoff)
    sims = await grouped(Sim.tenant_id)
    users = await grouped(User.tenant_id)
    subs = await grouped(Subscription.tenant_id)
    regs = await grouped(Registration.tenant_id)

    # Duplicate-name detection across the loaded tenants.
    name_counts: dict[str, int] = {}
    for t in tenants:
        name_counts[(t.name or "").strip().lower()] = name_counts.get((t.name or "").strip().lower(), 0) + 1

    out: list[TenantMetrics] = []
    for t in tenants:
        tid = t.tenant_id
        out.append(TenantMetrics(
            tenant_id=tid, name=t.name, is_active=bool(getattr(t, "is_active", True)),
            customers_op=customers_op.get(tid, 0), customers_archived=customers_arch.get(tid, 0),
            sites_op=sites_op.get(tid, 0), sites_archived=sites_arch.get(tid, 0),
            service_units=units.get(tid, 0), devices=devices.get(tid, 0), sims=sims.get(tid, 0),
            users=users.get(tid, 0), subscriptions=subs.get(tid, 0), registrations=regs.get(tid, 0),
            sites_with_e911_address=sites_e911_addr.get(tid, 0), sites_e911_verified=sites_e911_ver.get(tid, 0),
            devices_with_heartbeat=devices_hb.get(tid, 0), devices_fresh=devices_fresh.get(tid, 0),
            duplicate_name=name_counts.get((t.name or "").strip().lower(), 0) > 1,
        ))
    return out


def _print_assessment(a: dict) -> None:
    print(f"\nTenant: {a['tenant_id']}  ({a['name']})")
    print(f"  Status: {a['status']}   flags={a['flags']}")
    print(f"  Health Score: {a['score'] if a['score'] is not None else 'n/a'}   {a['components']}")
    op = a["operational"]
    print("  Operational: " + ", ".join(f"{k}={v}" for k, v in op.items()))
    print(f"  Archived:    customers={a['archived']['customers']}, sites={a['archived']['sites']}")
    e = a["e911"]
    print(f"  E911: {e['verified']}/{e['sites']} active sites verified ({e['with_address']} have an address)")
    d = a["device_health"]
    print(f"  Device Health: {d['fresh']}/{d['devices']} devices fresh ({d['with_heartbeat']} ever reported)")
    if a["risks"]:
        print("  Operational Risks:")
        for r in a["risks"]:
            print(f"      ! {r}")
    if a["opportunities"]:
        print("  Cleanup Opportunities:")
        for o in a["opportunities"]:
            print(f"      ~ {o}")


async def run(tenant_filter: str | None = None) -> list[dict]:
    from app.database import AsyncSessionLocal

    print("=" * 68)
    print("Portfolio audit (READ-ONLY — no writes)")
    print(f"  scope: {tenant_filter or 'ALL tenants'}")
    print("=" * 68)

    async with AsyncSessionLocal() as db:
        metrics = await load_metrics(db, tenant_filter)
    assessments = [assess_tenant(m) for m in metrics]
    for a in assessments:
        _print_assessment(a)

    print("\n" + "=" * 68)
    print("PORTFOLIO SUMMARY")
    print("=" * 68)
    scored = [a for a in assessments if a["score"] is not None]
    print(f"  tenants: {len(assessments)}  (scored: {len(scored)})")
    for a in sorted(scored, key=lambda x: x["score"]):
        print(f"    {a['score']:>3}  {a['tenant_id']:24} {a['status']}")
    for a in assessments:
        if a["score"] is None:
            print(f"     -   {a['tenant_id']:24} {a['status']}")
    print("\n  (Audit only — this script writes nothing.)")
    return assessments


def main() -> None:
    tenant_filter = os.environ.get("PORTFOLIO_AUDIT_TENANT") or None
    try:
        asyncio.run(run(tenant_filter))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: portfolio audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
