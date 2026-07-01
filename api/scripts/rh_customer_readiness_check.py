"""RH Customer Login Readiness Check (READ-ONLY).

Produces a go/no-go readiness report for putting a customer tenant (default
``restoration-hardware`` / Judy) into the customer login experience:

  * config — customer API + Customer Preview/Assurance Mode flags & allowlists,
  * access — the tenant exists/active and has customer users (Judy if present),
  * inventory — locations / devices / service-unit counts,
  * E911 — the safety-critical axis: address present, verified (stored status),
    and per-endpoint detail (ServiceUnit / callback) — the gaps that must be
    corrected before the customer E911 view can be trusted.

NEVER writes — only SELECTs.  Never prints secrets (no password hashes, tokens,
invite tokens, or env-var values — only whether a flag is set/allowlisted).

The operational-status greening for the customer is a *presentation* bridge
(Customer Assurance Mode / preview — see docs/customer/ASSURANCE_ENGINE.md); this
check deliberately holds E911 to the truth: E911 gaps are BLOCKERS, never greened.

Usage:
    python -m scripts.rh_customer_readiness_check                 # console
    python -m scripts.rh_customer_readiness_check --json          # machine-readable
    python -m scripts.rh_customer_readiness_check --tenant acme   # other tenant

Exit codes:
    0  READY   — tenant configured + customer users + no E911 gaps
    1  BLOCKED — config present but data blockers (E911 gaps / no users / no sites)
    2  CONFIG  — required flags/allowlist missing, tenant missing, or cannot evaluate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RH_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")

READY, BLOCKED, CONFIG = 0, 1, 2

# The customer-facing "verified" definition is owned by the serializer; import it
# so this check reports EXACTLY what the customer E911 view would show verified.
try:  # pragma: no cover - import shape depends on run context
    from app.services.customer.serialize import _E911_VERIFIED as CUSTOMER_VERIFIED
except Exception:  # pragma: no cover
    CUSTOMER_VERIFIED = {"validated", "verified"}

_E911_PARTS = ("e911_street", "e911_city", "e911_state", "e911_zip")


# ── pure helpers (unit-tested, no DB) ────────────────────────────────────
def _mask_email(email: str | None) -> str:
    """Show enough to identify a user, never the full local part."""
    if not email or "@" not in email:
        return "—"
    local, _, domain = email.partition("@")
    head = local[0] if local else ""
    return f"{head}***@{domain}"


def _address_present(site: dict) -> bool:
    return all((site.get(p) or "").strip() for p in _E911_PARTS)


def _is_verified(site: dict) -> bool:
    return (site.get("e911_status") or "").strip().lower() in CUSTOMER_VERIFIED


def is_customer_role(role: str | None) -> bool:
    """True for any customer-plane role (CUSTOMER_*)."""
    if not role:
        return False
    try:
        from app.services.rbac import normalize_role
        role = normalize_role(role)
    except Exception:  # pragma: no cover - normalize is best-effort here
        pass
    return str(role).upper().startswith("CUSTOMER_")


def summarize_e911(sites: list[dict], units_by_site: dict[str, list[dict]]) -> dict:
    """Aggregate the E911 posture across a tenant's sites.  ``units_by_site`` maps
    site_id -> list of {unit_type, floor, location_description, callback_number}.

    Reuses services.e911_gaps.compute_site_e911_gaps for per-endpoint detail so
    the "missing endpoint detail" definition matches the internal gaps worklist.
    """
    from app.services.e911_gaps import compute_site_e911_gaps

    total = len(sites)
    with_address = verified = missing_or_unverified = missing_endpoint_detail = 0
    gap_sites: list[dict] = []
    for s in sites:
        sid = s.get("site_id")
        units = units_by_site.get(sid, [])
        addr = _address_present(s)
        ver = _is_verified(s)
        with_address += int(addr)
        verified += int(ver)
        if not (addr and ver):
            missing_or_unverified += 1

        # per-endpoint detail: a site with zero service units OR any unit missing
        # type/location/callback counts as "missing endpoint detail".
        unit_objs = [
            type("U", (), {
                "unit_id": u.get("unit_id"), "unit_name": u.get("unit_name"),
                "unit_type": u.get("unit_type"), "floor": u.get("floor"),
                "location_description": u.get("location_description"),
            })()
            for u in units
        ]
        pairs = [(u, units[i].get("callback_number")) for i, u in enumerate(unit_objs)]
        gap = compute_site_e911_gaps(_SiteView(s), pairs)
        no_units = len(units) == 0
        if no_units or (gap and gap.get("endpoint_gaps")):
            missing_endpoint_detail += 1
        if gap is not None or no_units:
            gap_sites.append({
                "site_id": sid, "site_name": s.get("site_name"),
                "address_present": addr, "verified": ver,
                "service_units": len(units),
                "missing": (gap or {}).get("missing", []),
                "endpoint_gaps": (gap or {}).get("endpoint_gaps", []),
            })
    return {
        "total_locations": total,
        "with_address": with_address,
        "verified": verified,
        "missing_or_unverified": missing_or_unverified,
        "missing_endpoint_detail": missing_endpoint_detail,
        "gap_sites": gap_sites,
    }


class _SiteView:
    """Adapts a plain site dict to the attribute access compute_site_e911_gaps
    expects (e911_* + e911_status)."""

    def __init__(self, s: dict):
        self.e911_street = s.get("e911_street")
        self.e911_city = s.get("e911_city")
        self.e911_state = s.get("e911_state")
        self.e911_zip = s.get("e911_zip")
        self.e911_status = s.get("e911_status")
        self.site_id = s.get("site_id")
        self.site_name = s.get("site_name")


# ── pure evaluation → (report, exit_code) ────────────────────────────────
def evaluate(snapshot: dict) -> tuple[dict, int]:
    """Turn a read-only snapshot into a verdict.  Pure: no DB, no settings, no
    I/O — so tests can drive every exit path deterministically."""
    cfg = snapshot.get("config", {})
    e911 = snapshot.get("e911", {})
    users = snapshot.get("customer_users", [])
    counts = snapshot.get("counts", {})

    config_missing: list[str] = []
    if not snapshot.get("tenant_exists"):
        return ({
            "tenant": snapshot.get("tenant_id"), "verdict": "CONFIG",
            "cannot_evaluate": True,
            "blockers": [f"Tenant '{snapshot.get('tenant_id')}' does not exist — "
                         "check the slug (Admin → Tenants)."],
            "warnings": [], "config": cfg, "counts": counts, "e911": e911,
            "customer_users": users,
        }, CONFIG)

    if not cfg.get("feature_customer_api"):
        config_missing.append("Set FEATURE_CUSTOMER_API=true (api + worker).")
    if not cfg.get("api_allowlisted"):
        config_missing.append(
            f"Add '{snapshot.get('tenant_id')}' to CUSTOMER_API_TENANT_ALLOWLIST.")
    if not cfg.get("feature_customer_preview"):
        config_missing.append("Set FEATURE_CUSTOMER_PREVIEW=true (api + worker).")
    if not cfg.get("preview_allowlisted"):
        config_missing.append(
            f"Add '{snapshot.get('tenant_id')}' to CUSTOMER_PREVIEW_TENANT_ALLOWLIST.")

    blockers: list[str] = []
    warnings: list[str] = []

    if not snapshot.get("tenant_active", True):
        warnings.append("Tenant is marked inactive (is_active=false).")

    if not users:
        blockers.append("No customer-plane (CUSTOMER_*) users exist for this tenant "
                        "— create the account owner (see RH_GO_LIVE_RUNBOOK).")
    elif not snapshot.get("judy_present"):
        warnings.append("No user obviously named 'Judy' found — confirm the RH "
                        "account owner is provisioned (customer users do exist).")
    if not any(u.get("is_active") for u in users):
        if users:
            blockers.append("Customer users exist but none are active (is_active=false).")

    if counts.get("locations", 0) == 0:
        blockers.append("Tenant has 0 locations — nothing for the customer to see.")

    if e911.get("missing_or_unverified", 0) > 0:
        blockers.append(
            f"{e911['missing_or_unverified']} location(s) have missing or UNVERIFIED "
            "E911 — correct + verify before trusting the customer E911 view "
            "(E911 is never greened by preview).")
    if e911.get("missing_endpoint_detail", 0) > 0:
        blockers.append(
            f"{e911['missing_endpoint_detail']} location(s) missing ServiceUnit / "
            "emergency-endpoint detail (callback/floor/type).")

    if config_missing:
        verdict, code = "CONFIG", CONFIG
    elif blockers:
        verdict, code = "BLOCKED", BLOCKED
    else:
        verdict, code = "READY", READY

    return ({
        "tenant": snapshot.get("tenant_id"),
        "verdict": verdict,
        "config": cfg,
        "config_missing": config_missing,
        "blockers": blockers,
        "warnings": warnings,
        "counts": counts,
        "e911": {k: v for k, v in e911.items() if k != "gap_sites"},
        "e911_gap_sites": e911.get("gap_sites", []),
        "customer_users": users,
    }, code)


# ── read-only DB load ────────────────────────────────────────────────────
async def load_snapshot(db, tenant_id: str) -> dict:
    from sqlalchemy import func, select

    from app.config import settings
    from app.models.device import Device
    from app.models.line import Line
    from app.models.service_unit import ServiceUnit
    from app.models.site import Site
    from app.models.tenant import Tenant
    from app.models.user import User

    tenant = (await db.execute(
        select(Tenant).where(Tenant.tenant_id == tenant_id))).scalar_one_or_none()

    devices_n = int((await db.execute(
        select(func.count()).select_from(Device).where(Device.tenant_id == tenant_id))).scalar() or 0)
    units_n = int((await db.execute(
        select(func.count()).select_from(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalar() or 0)

    user_rows = (await db.execute(
        select(User).where(User.tenant_id == tenant_id))).scalars().all()
    customer_users = [
        {"email": _mask_email(u.email), "role": u.role, "is_active": bool(u.is_active),
         "name": (u.name or "")}
        for u in user_rows if is_customer_role(u.role)
    ]
    judy_present = any("judy" in (u["name"] or "").lower()
                       or (u["email"] or "").lower().startswith("j")
                       for u in customer_users)

    sites = [{
        "site_id": s.site_id, "site_name": s.site_name, "status": s.status,
        "e911_street": s.e911_street, "e911_city": s.e911_city,
        "e911_state": s.e911_state, "e911_zip": s.e911_zip,
        "e911_status": s.e911_status,
    } for s in (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id).order_by(Site.site_name))).scalars().all()]

    # service units per site + resolved callback (Line.did, else Device.msisdn)
    units_by_site: dict[str, list[dict]] = {}
    for u in (await db.execute(
        select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all():
        callback = None
        if u.line_id:
            callback = (await db.execute(select(Line.did).where(
                Line.line_id == u.line_id, Line.tenant_id == tenant_id))).scalar_one_or_none()
        if not callback and u.device_id:
            callback = (await db.execute(select(Device.msisdn).where(
                Device.device_id == u.device_id, Device.tenant_id == tenant_id))).scalar_one_or_none()
        units_by_site.setdefault(u.site_id, []).append({
            "unit_id": u.unit_id, "unit_name": u.unit_name, "unit_type": u.unit_type,
            "floor": u.floor, "location_description": u.location_description,
            "callback_number": callback,
        })

    e911 = summarize_e911(sites, units_by_site)

    return {
        "tenant_id": tenant_id,
        "tenant_exists": tenant is not None,
        "tenant_active": bool(tenant.is_active) if tenant is not None else False,
        "config": {
            "feature_customer_api": settings.FEATURE_CUSTOMER_API == "true",
            "api_allowlisted": tenant_id in settings.customer_api_tenant_id_set,
            "feature_customer_preview": settings.FEATURE_CUSTOMER_PREVIEW == "true",
            "preview_allowlisted": tenant_id in settings.customer_preview_tenant_id_set,
        },
        "customer_users": customer_users,
        "judy_present": judy_present,
        "counts": {
            "locations": len(sites), "devices": devices_n, "service_units": units_n,
        },
        "e911": e911,
    }


# ── rendering ────────────────────────────────────────────────────────────
def _flag(v: bool) -> str:
    return "ON " if v else "off"


def render_console(report: dict) -> None:
    print("=" * 72)
    print(f"RH CUSTOMER LOGIN READINESS — tenant: {report['tenant']}   [READ-ONLY]")
    print("=" * 72)
    cfg = report.get("config", {})
    print("\nCONFIG (customer login + Customer Assurance Mode)")
    print(f"  FEATURE_CUSTOMER_API           {_flag(cfg.get('feature_customer_api'))}")
    print(f"  in CUSTOMER_API_TENANT_ALLOWLIST     {_flag(cfg.get('api_allowlisted'))}")
    print(f"  FEATURE_CUSTOMER_PREVIEW       {_flag(cfg.get('feature_customer_preview'))}")
    print(f"  in CUSTOMER_PREVIEW_TENANT_ALLOWLIST {_flag(cfg.get('preview_allowlisted'))}")

    users = report.get("customer_users", [])
    print(f"\nCUSTOMER USERS ({len(users)})")
    for u in users:
        print(f"  {u['email']:<28} {u['role']:<16} active={u['is_active']}")
    if not users:
        print("  (none)")

    c = report.get("counts", {})
    print(f"\nINVENTORY  locations={c.get('locations', 0)}  "
          f"devices={c.get('devices', 0)}  service_units={c.get('service_units', 0)}")

    e = report.get("e911", {})
    print("\nE911 (safety-critical — never greened by preview)")
    print(f"  total locations           {e.get('total_locations', 0)}")
    print(f"  with service address      {e.get('with_address', 0)}")
    print(f"  verified (stored status)  {e.get('verified', 0)}")
    print(f"  missing / unverified      {e.get('missing_or_unverified', 0)}")
    print(f"  missing endpoint detail   {e.get('missing_endpoint_detail', 0)}")
    gaps = report.get("e911_gap_sites", [])
    if gaps:
        print("  gap detail (first 15):")
        for g in gaps[:15]:
            bits = []
            if g.get("missing"):
                bits.append("+".join(g["missing"]))
            if g.get("service_units", 0) == 0:
                bits.append("no service units")
            if g.get("endpoint_gaps"):
                bits.append(f"{len(g['endpoint_gaps'])} endpoint gap(s)")
            print(f"    {str(g.get('site_name'))[:34]:<34} {', '.join(bits)}")

    if report.get("config_missing"):
        print("\nCONFIG MISSING (blocks a real customer login):")
        for m in report["config_missing"]:
            print(f"  • {m}")
    if report.get("blockers"):
        print("\nBLOCKERS:")
        for b in report["blockers"]:
            print(f"  ✗ {b}")
    if report.get("warnings"):
        print("\nWARNINGS:")
        for w in report["warnings"]:
            print(f"  ! {w}")

    print("\n" + "-" * 72)
    print(f"VERDICT: {report['verdict']}")
    print("-" * 72)
    print("(Read-only — this script writes nothing and prints no secrets.)")


async def _run(tenant_id: str) -> tuple[dict, int]:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        snapshot = await load_snapshot(db, tenant_id)
    return evaluate(snapshot)


def main() -> None:
    ap = argparse.ArgumentParser(description="RH customer login readiness (read-only).")
    ap.add_argument("--tenant", default=RH_TENANT, help="tenant_id/slug (default: %(default)s)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of console text")
    args = ap.parse_args()

    try:
        report, code = asyncio.run(_run(args.tenant))
    except Exception as exc:  # connectivity / config edge — cannot evaluate
        msg = f"{type(exc).__name__}: {exc}"
        if args.json:
            print(json.dumps({"verdict": "CONFIG", "cannot_evaluate": True, "error": msg}))
        else:
            print(f"CONFIG: cannot evaluate — {msg}")
        raise SystemExit(CONFIG)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        render_console(report)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
