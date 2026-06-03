"""Restoration Hardware — Portfolio Readiness Audit (READ-ONLY).

Customer-specific deep audit that explains EXACTLY what must happen to make a
customer customer-facing ready: per-site E911 readiness, per-device
monitorability (why device health is 0/N), the service-unit gap, and a
portfolio scorecard computed by the REAL Assurance engine.

NEVER writes — only SELECTs.  Does NOT validate E911, create service units, or
touch any other tenant.  Reuses:
  * app.services.assurance (engine + loader) for the scorecard, and
  * app.services.device_health.classifier for adapter/monitorability checks.
Neither import pulls in app.services.health directly, so the health
surface-containment guard is respected.

Run:
    RH_AUDIT_TENANT=restoration-hardware python -m app.audit_rh_readiness
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RH_TENANT = os.environ.get("RH_AUDIT_TENANT", "restoration-hardware")

E911_PARTS = ("e911_street", "e911_city", "e911_state", "e911_zip")
VERIFIED_E911 = frozenset({"validated", "verified", "confirmed"})

SCORECARD_LABELS = (
    "Protected", "Attention Needed", "Critical",
    "Inactive / Deactivated", "Pending Install", "Unknown",
)


# ── pure helpers (unit-tested) ───────────────────────────────────────────
def e911_readiness(site: dict) -> str:
    """Bucket a site's E911 dispatch readiness from its address fields + status.

    Returns one of:
      verified                         — e911_status already validated/verified/confirmed
      address_complete_needs_validation— all 4 address parts present, status not yet verified
      address_partial                  — some address parts present, some missing
      address_missing                  — no address parts at all
    """
    present = [p for p in E911_PARTS if (site.get(p) or "").strip()]
    status = (site.get("e911_status") or "").strip().lower()
    if status in VERIFIED_E911:
        return "verified"
    if len(present) == len(E911_PARTS):
        return "address_complete_needs_validation"
    if present:
        return "address_partial"
    return "address_missing"


def missing_e911_parts(site: dict) -> list[str]:
    return [p for p in E911_PARTS if not (site.get(p) or "").strip()]


def device_identifiers(d: dict) -> list[str]:
    """Vendor-matchable identifiers present on the device."""
    keys = ("serial_number", "imei", "iccid", "msisdn", "vola_org_id", "starlink_id")
    return [k for k in keys if (d.get(k) or "").strip()]


def diagnose_device(d: dict, probe_vendors: tuple) -> list[str]:
    """Why this device cannot (yet) be health-monitored. Empty list = monitorable."""
    reasons: list[str] = []
    if not probe_vendors:
        reasons.append("no vendor adapter recognises this device class "
                       "(model/type/carrier unmapped)")
    if not device_identifiers(d):
        reasons.append("no vendor identifiers (serial/imei/iccid/msisdn/vola_org_id) "
                       "— cannot be matched to a vendor account")
    if d.get("last_heartbeat") is None:
        reasons.append("never reported a heartbeat (last_heartbeat is NULL)")
    return reasons


def device_monitorable(d: dict, probe_vendors: tuple) -> bool:
    """A device is monitorable when an adapter recognises it AND it has an
    identifier the adapter can key on."""
    return bool(probe_vendors) and bool(device_identifiers(d))


def infer_unit_type(model, device_type, endpoint_type=None) -> str:
    """Best-guess emergency service-unit type from device identity fields."""
    s = " ".join(x for x in (model, device_type, endpoint_type) if x).lower()
    if "elevator" in s or "elv" in s:
        return "elevator_phone"
    if "fire" in s:
        return "fire_alarm_line"
    if "alarm" in s:
        return "alarm_line"
    if "callbox" in s or "call box" in s or "call-box" in s:
        return "emergency_call_station"
    if "fax" in s:
        return "fax_line"
    if "pots" in s or "ata" in s or "analog" in s:
        return "emergency_voice_line"
    return "emergency_voice_line"


def service_unit_gap(num_units: int, devices: list[dict]) -> dict:
    """Recommend service units inferred from device/site data when none exist.
    Recommendation only — creates nothing."""
    if num_units > 0:
        return {"has_units": True, "count": num_units, "suggestions": []}
    suggestions = [
        {
            "site_id": d.get("site_id"),
            "device_id": d.get("device_id"),
            "suggested_unit_type": infer_unit_type(
                d.get("model"), d.get("device_type"), d.get("endpoint_type")),
        }
        for d in devices
    ]
    return {"has_units": False, "count": 0, "suggestions": suggestions}


def summarize_scorecard(labels: list[str]) -> dict:
    out = {k: 0 for k in SCORECARD_LABELS}
    for lab in labels:
        out[lab] = out.get(lab, 0) + 1
    return out


# ── DB load (read-only) ──────────────────────────────────────────────────
async def _load(db, tenant_id: str) -> dict:
    from sqlalchemy import func, select

    from app.models.tenant import Tenant
    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.models.device import Device
    from app.models.user import User

    is_active = (await db.execute(
        select(Tenant.is_active).where(Tenant.tenant_id == tenant_id))).scalar_one_or_none()

    customers = int((await db.execute(
        select(func.count()).select_from(Customer).where(Customer.tenant_id == tenant_id))).scalar() or 0)
    users = int((await db.execute(
        select(func.count()).select_from(User).where(User.tenant_id == tenant_id))).scalar() or 0)
    units = int((await db.execute(
        select(func.count()).select_from(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalar() or 0)

    sites = [{
        "site_id": s.site_id, "name": s.site_name, "status": s.status,
        "customer_id": s.customer_id, "tenant_id": s.tenant_id,
        "e911_street": s.e911_street, "e911_city": s.e911_city,
        "e911_state": s.e911_state, "e911_zip": s.e911_zip,
        "e911_status": s.e911_status, "onboarding_status": s.onboarding_status,
        "address_source": s.address_source,
    } for s in (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id).order_by(Site.site_id))).scalars().all()]

    devices = [{
        "device_id": d.device_id, "site_id": d.site_id, "status": d.status,
        "device_type": d.device_type, "model": d.model, "endpoint_type": None,
        "manufacturer": d.manufacturer, "hardware_model_id": d.hardware_model_id,
        "carrier": d.carrier, "telemetry_source": d.telemetry_source,
        "serial_number": d.serial_number, "imei": d.imei, "iccid": d.iccid,
        "msisdn": d.msisdn, "vola_org_id": d.vola_org_id, "starlink_id": d.starlink_id,
        "last_heartbeat": d.last_heartbeat,
    } for d in (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id).order_by(Device.site_id))).scalars().all()]

    return {
        "tenant_id": tenant_id, "exists": is_active is not None,
        "is_active": bool(is_active) if is_active is not None else False,
        "customers": customers, "users": users, "service_units": units,
        "sites": sites, "devices": devices,
    }


async def _scorecard(db, tenant_id: str, site_ids: list[str]) -> dict:
    """Run each site through the REAL Assurance engine. Read-only."""
    from app.services.assurance import compute_site_assurance
    from app.services.assurance.loader import load_site_assurance_signals

    labels: list[str] = []
    per_site: dict[str, dict] = {}
    for sid in site_ids:
        signals = await load_site_assurance_signals(db, tenant_id, sid)
        if signals is None:
            labels.append("Unknown")
            per_site[sid] = {"label": "Unknown", "reasons": ("site-not-found",)}
            continue
        res = compute_site_assurance(signals)
        labels.append(res.label.value)
        per_site[sid] = {"label": res.label.value, "reasons": res.reason_codes}
    return {"labels": labels, "per_site": per_site, "summary": summarize_scorecard(labels)}


# ── reporting ────────────────────────────────────────────────────────────
def _print(data: dict, scorecard: dict) -> None:
    from app.services.device_health.classifier import classify

    sites, devices = data["sites"], data["devices"]
    print("=" * 70)
    print(f"Restoration Hardware readiness audit — READ-ONLY  (tenant: {data['tenant_id']})")
    print("=" * 70)
    if not data["exists"]:
        print("  Tenant does not exist — check the slug in Admin → Tenants.")
        return
    print(f"  active={data['is_active']}  customers={data['customers']}  "
          f"users={data['users']}  sites={len(sites)}  devices={len(devices)}  "
          f"service_units={data['service_units']}")

    # 1 + 5 — sites + E911 readiness
    buckets: dict[str, int] = {}
    print("\n--- SITES + E911 READINESS ---")
    for s in sites:
        b = e911_readiness(s)
        buckets[b] = buckets.get(b, 0) + 1
        miss = missing_e911_parts(s)
        miss_s = "" if not miss else f"  missing={[p.replace('e911_', '') for p in miss]}"
        print(f"  {s['site_id']:<22} {s['status']:<10} e911_status={str(s['e911_status']):<10} "
              f"cust={str(s['customer_id']):<5} -> {b}{miss_s}")
    print("  E911 buckets:", dict(sorted(buckets.items())))

    # 2 + 3 — devices + monitorability diagnosis
    print("\n--- DEVICES + MONITORABILITY ---")
    reason_tally: dict[str, int] = {}
    monitorable = 0
    for d in devices:
        cls = classify(model=d.get("model"), device_type=d.get("device_type"),
                       hardware_model_id=d.get("hardware_model_id"),
                       manufacturer=d.get("manufacturer"), carrier=d.get("carrier"))
        ok = device_monitorable(d, cls.probe_vendors)
        monitorable += int(ok)
        reasons = diagnose_device(d, cls.probe_vendors)
        for r in reasons:
            reason_tally[r] = reason_tally.get(r, 0) + 1
        print(f"  {d['device_id']:<18} site={str(d['site_id']):<20} {str(d['model']):<14} "
              f"probes={list(cls.probe_vendors) or '-'}  hb={d['last_heartbeat']}  "
              f"{'MONITORABLE' if ok else 'NOT-MONITORABLE'}")
    print(f"\n  Monitorable now: {monitorable}/{len(devices)}")
    print("  Why device health is 0 (reason tally):")
    for r, n in sorted(reason_tally.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>3} × {r}")

    # 4 — service-unit gap
    gap = service_unit_gap(data["service_units"], devices)
    print("\n--- SERVICE-UNIT GAP ---")
    if gap["has_units"]:
        print(f"  {gap['count']} service unit(s) exist.")
    else:
        type_tally: dict[str, int] = {}
        for sug in gap["suggestions"]:
            type_tally[sug["suggested_unit_type"]] = type_tally.get(sug["suggested_unit_type"], 0) + 1
        print(f"  0 service units for {len(devices)} device(s). Recommend creating one "
              f"emergency service unit per device (NOT created here):")
        for t, n in sorted(type_tally.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>3} × {t}")

    # 6 — scorecard (real Assurance engine)
    print("\n--- PORTFOLIO SCORECARD (Assurance engine) ---")
    for lab in SCORECARD_LABELS:
        print(f"  {lab:<24} {scorecard['summary'].get(lab, 0)}")
    print("\n  (Findings only — this script writes nothing.)")


async def run(tenant_id: str) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        data = await _load(db, tenant_id)
        scorecard = await _scorecard(db, tenant_id, [s["site_id"] for s in data["sites"]]) \
            if data["exists"] else {"summary": {}, "labels": [], "per_site": {}}
    _print(data, scorecard)


def main() -> None:
    try:
        asyncio.run(run(RH_TENANT))
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: audit aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
