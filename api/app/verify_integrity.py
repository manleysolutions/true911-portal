"""Read-only verification for the Integrity / Belle Terre onboarding.

Writes nothing.  Three checks:

  1. DB visibility — counts + lists every tenant-scoped record so you can
     confirm what the Integrity portal users will see.
  2. Vola Cloud — looks up each LM150 by serial number and reports
     online/offline status, last heartbeat and firmware (logs any serial the
     Vola API does not return).
  3. T-Mobile — reports which credentials / feature flags are present and what
     lookup paths are live (callback ingest vs. synchronous TAAP).

Run
---
    python -m app.verify_integrity

Vola / T-Mobile checks degrade gracefully: if credentials are absent the
script reports "not configured" rather than raising, so it is safe to run in
any environment.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.seed_integrity import (  # noqa: E402
    TENANT_ID,
    EXPECTED_SERIALS,
    EXPECTED_ICCIDS,
    BELLE_TERRE_SITE_ID,
)


# ── Vola (live, read-only) ───────────────────────────────────────────
async def check_vola_devices(client, serials: list[str]) -> dict:
    """Look up each serial in the Vola device list.

    Returns ``{"ok": bool, "devices": {serial: {...}}, "missing": [...],
    "error": str|None}``.  Pure with respect to the DB — only touches the
    Vola API through ``client``.
    """
    from app.integrations.vola import extract_device_list

    try:
        data = await client.get_device_list("inUse")
    except Exception as exc:  # network / auth / config failure
        return {"ok": False, "devices": {}, "missing": list(serials),
                "error": f"{type(exc).__name__}: {exc}"}

    raw = extract_device_list(data) or []
    by_serial = {item.get("deviceSN"): item for item in raw if item.get("deviceSN")}

    found: dict[str, dict] = {}
    missing: list[str] = []
    for sn in serials:
        item = by_serial.get(sn)
        if item is None:
            missing.append(sn)
            continue
        found[sn] = {
            "status": (item.get("status") or "").lower() or "unknown",
            "firmware": item.get("softwareVersion"),
            "last_heartbeat": item.get("lastUpdateTime"),
            "model": item.get("deviceModel"),
            "org": item.get("orgName") or item.get("orgId"),
        }
    return {"ok": True, "devices": found, "missing": missing, "error": None}


# ── T-Mobile (pure config readiness) ─────────────────────────────────
def tmobile_readiness(settings) -> dict:
    """Report which T-Mobile capabilities are wired in this environment.

    Pure — reads only the settings object, makes no network calls.
    """
    def _truthy(v) -> bool:
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    callback_ingest = _truthy(getattr(settings, "FEATURE_TMOBILE_CALLBACK_INGEST", "false"))
    taap_fields = {
        "TMOBILE_BASE_URL": getattr(settings, "TMOBILE_BASE_URL", ""),
        "TMOBILE_TOKEN_URL": getattr(settings, "TMOBILE_TOKEN_URL", ""),
        "TMOBILE_CONSUMER_KEY": getattr(settings, "TMOBILE_CONSUMER_KEY", ""),
        "TMOBILE_CONSUMER_SECRET": getattr(settings, "TMOBILE_CONSUMER_SECRET", ""),
        "TMOBILE_ACCOUNT_ID": getattr(settings, "TMOBILE_ACCOUNT_ID", ""),
    }
    taap_present = [k for k, v in taap_fields.items() if str(v).strip()]
    taap_missing = [k for k, v in taap_fields.items() if not str(v).strip()]

    return {
        "callback_ingest_enabled": callback_ingest,
        "taap_env": getattr(settings, "TMOBILE_ENV", "?"),
        "taap_present": taap_present,
        "taap_missing": taap_missing,
        # The synchronous carrier provider is an explicit stub today.
        "sync_lookup_live": False,
        "notes": [
            "Inbound callback ingest is the live path: it matches by ICCID, "
            "then MSISDN, then a Device fallback (serial-less). It updates "
            "Device.last_network_event on a verified hit.",
            "Synchronous ICCID/IMEI/MSISDN lookup + VoLTE/usage/static-IP "
            "pull is NOT live (carrier_provider/tmobile.py is a stub). It "
            "requires the TAAP credentials above plus client implementation.",
        ],
    }


# ── DB visibility (read-only) ────────────────────────────────────────
async def db_visibility_report(tenant_id: str = TENANT_ID) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.tenant import Tenant
    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.models.device import Device
    from app.models.sim import Sim
    from app.models.user import User

    out: dict = {"tenant_id": tenant_id}
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id))).scalar_one_or_none()
        out["tenant_exists"] = tenant is not None
        out["zoho_account_id"] = getattr(tenant, "zoho_account_id", None)

        customers = (await db.execute(
            select(Customer).where(Customer.tenant_id == tenant_id))).scalars().all()
        out["customers"] = [c.name for c in customers]

        sites = (await db.execute(
            select(Site).where(Site.tenant_id == tenant_id))).scalars().all()
        out["sites"] = [
            {"site_id": s.site_id, "name": s.site_name, "status": s.status,
             "e911": bool(s.e911_street)} for s in sites]

        units = (await db.execute(
            select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all()
        out["service_units"] = [
            {"unit_id": u.unit_id, "name": u.unit_name, "type": u.unit_type,
             "device_id": u.device_id} for u in units]

        devices = (await db.execute(
            select(Device).where(Device.tenant_id == tenant_id))).scalars().all()
        out["devices"] = [
            {"device_id": d.device_id, "serial": d.serial_number, "model": d.model,
             "carrier": d.carrier, "iccid": d.iccid, "msisdn": d.msisdn,
             "status": d.status, "site_id": d.site_id,
             "last_network_event": str(d.last_network_event) if d.last_network_event else None}
            for d in devices]

        sims = (await db.execute(
            select(Sim).where(Sim.tenant_id == tenant_id))).scalars().all()
        out["sims"] = [
            {"iccid": s.iccid, "msisdn": s.msisdn, "carrier": s.carrier,
             "status": s.status, "volte": bool((s.meta or {}).get("volte_enabled"))}
            for s in sims]

        users = (await db.execute(
            select(User).where(User.tenant_id == tenant_id))).scalars().all()
        out["users"] = [
            {"email": u.email, "role": u.role, "active": u.is_active,
             "invite_pending": bool(u.invite_token)} for u in users]

    return out


def _expected_gaps(report: dict) -> list[str]:
    gaps = []
    serials = {d["serial"] for d in report.get("devices", [])}
    for sn in EXPECTED_SERIALS:
        if sn not in serials:
            gaps.append(f"device serial {sn} not present in DB")
    iccids = {s["iccid"] for s in report.get("sims", [])}
    for ic in EXPECTED_ICCIDS:
        if ic not in iccids:
            gaps.append(f"SIM iccid {ic} not present in DB")
    if not any(s["site_id"] == BELLE_TERRE_SITE_ID for s in report.get("sites", [])):
        gaps.append("Belle Terre site not present in DB")
    return gaps


async def _amain() -> None:
    from app.config import settings

    print("=" * 64)
    print("VERIFY — Integrity Property Management / Belle Terre at Sunrise")
    print("=" * 64)

    # 1) DB visibility
    print("\n[1] DB visibility (tenant-scoped — what Integrity users will see)")
    try:
        report = await db_visibility_report()
        print(f"    tenant_exists : {report['tenant_exists']}  "
              f"(zoho {report.get('zoho_account_id')})")
        print(f"    customers     : {report['customers']}")
        print(f"    sites         : {len(report['sites'])}")
        for s in report["sites"]:
            print(f"        - {s['site_id']:18} {s['name']:30} "
                  f"[{s['status']}] e911={'yes' if s['e911'] else 'NO'}")
        print(f"    service_units : {len(report['service_units'])}")
        for u in report["service_units"]:
            print(f"        - {u['unit_id']:22} {u['name']:12} -> {u['device_id']}")
        print(f"    devices       : {len(report['devices'])}")
        for d in report["devices"]:
            print(f"        - {d['serial']:18} {d['model']:8} {d['carrier']:8} "
                  f"[{d['status']}] last_net={d['last_network_event']}")
        print(f"    sims          : {len(report['sims'])}")
        for s in report["sims"]:
            print(f"        - {s['iccid']:20} {s['msisdn']:12} "
                  f"[{s['status']}] volte={s['volte']}")
        print(f"    users         : {report['users']}")
        gaps = _expected_gaps(report)
        if gaps:
            print("    GAPS:")
            for g in gaps:
                print(f"        ! {g}")
        else:
            print("    all expected devices / SIMs / Belle Terre present.")
    except Exception as exc:
        print(f"    DB report failed: {type(exc).__name__}: {exc}")

    # 2) Vola
    print("\n[2] Vola Cloud device lookup (by serial)")
    if not (settings.VOLA_EMAIL and settings.VOLA_PASSWORD):
        print("    VOLA_EMAIL / VOLA_PASSWORD not set — skipping live lookup.")
    else:
        from app.services.vola_service import get_vola_client
        client = get_vola_client()
        result = await check_vola_devices(client, EXPECTED_SERIALS)
        if not result["ok"]:
            print(f"    Vola call FAILED: {result['error']}")
        else:
            for sn, info in result["devices"].items():
                print(f"        - {sn:18} status={info['status']:8} "
                      f"fw={info['firmware']} last={info['last_heartbeat']}")
            for sn in result["missing"]:
                print(f"        ! {sn} not returned by Vola device list")

    # 3) T-Mobile
    print("\n[3] T-Mobile readiness")
    tm = tmobile_readiness(settings)
    print(f"    callback ingest enabled : {tm['callback_ingest_enabled']}")
    print(f"    TAAP env                : {tm['taap_env']}")
    print(f"    TAAP creds present      : {tm['taap_present'] or 'none'}")
    print(f"    TAAP creds missing      : {tm['taap_missing'] or 'none'}")
    print(f"    synchronous lookup live : {tm['sync_lookup_live']}")
    for n in tm["notes"]:
        print(f"      - {n}")


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
