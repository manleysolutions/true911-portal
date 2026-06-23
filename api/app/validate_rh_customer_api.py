"""Restoration Hardware — customer-API render validation (READ-ONLY).

P4 of the RH go-live chain (docs/P4_RH_CUSTOMER_API_VALIDATION_SPEC.md). Proves the
data remediation (P0-P3) produces a clean customer-facing render BEFORE
``FEATURE_CUSTOMER_API`` is enabled for RH — no false green, no unexplained red,
Unknown minimized, no hidden-field leaks.

Core idea: the endpoints 404 while the flag is off, but the serializer + portfolio
functions that PRODUCE the customer JSON are plain, pure, read-only callables. This
tool composes the REAL customer JSON for RH via those same functions (flag-free, no
HTTP surface) and asserts the 10 conditions. It NEVER writes, NEVER enables a flag,
NEVER calls a vendor, and touches only the RH tenant.

Conditions (5/6/8 are CRITICAL — any failure ⇒ non-zero exit):
  1 dashboard renders        2 N locations appear     3 services per location
  4 E911 verified state ok    5 NO false green*        6 every non-green has a reason*
  7 Unknown minimized         8 NO hidden-field leak*  9 billing deferred  10 support deferred

Run:
    python -m app.validate_rh_customer_api
    python -m app.validate_rh_customer_api --export /tmp/rh_p4.json
    python -m app.validate_rh_customer_api --only leaks
    RH_VALIDATE_STRICT=true python -m app.validate_rh_customer_api   # non-zero exit on hard fail
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RH_TENANT = os.environ.get("RH_CUSTOMER_TENANT", "restoration-hardware")

# Hidden fields whose real values must never appear in a customer response.
_LEAK_VALUE_FIELDS = (
    "iccid", "imei", "msisdn", "imsi", "serial_number", "mac_address",
    "firmware_version", "container_version", "provision_code", "carrier",
    "wan_ip", "lan_ip", "vola_org_id", "starlink_id",
    "static_ip", "device_serial", "device_firmware", "csa_model",
    "psap_id", "ng911_uri", "emergency_class", "zoho_account_id",
)
# Forbidden KEY names in any customer payload (jargon / internal / commercial).
_LEAK_KEYS = (
    "iccid", "imei", "msisdn", "imsi", "serial_number", "mac_address",
    "firmware_version", "carrier", "wan_ip", "lan_ip", "vola_org_id",
    "psap_id", "ng911_uri", "emergency_class", "zoho_account_id",
    "internal_summary", "raw_payload", "probable_cause", "correlation_id",
    "mrr", "monthly_cost", "external_subscription_id", "handoff_summary",
    "zoho_ticket_id",
)
_BILLING_KEYS = ("mrr", "monthly_cost", "plan", "services_covered", "external_subscription_id", "renews_on")
_SUPPORT_INTERNAL_KEYS = ("internal_summary", "raw_payload", "probable_cause", "handoff_summary", "zoho_ticket_id")
_SIX = {"Protected", "Attention Needed", "Critical", "Pending Install", "Inactive", "Unknown"}


@dataclass
class Check:
    name: str
    passed: bool
    hard: bool = False           # hard/critical (5,6,8) — failure forces NO-GO / non-zero exit
    summary: str = ""
    samples: list = field(default_factory=list)


# ── Helpers over the composed "view" ─────────────────────────────────
def _iter_protections(view):
    """Every StatusObject in the composed customer JSON."""
    for p in view.get("all_protections", []):
        if isinstance(p, dict) and "status" in p:
            yield p


# ── The 10 checks (pure over a composed view) ────────────────────────
def check_dashboard(view) -> Check:
    d = view.get("dashboard") or {}
    pf = d.get("portfolio") or {}
    ok = (
        bool(d.get("company"))
        and isinstance(pf, dict)
        and "total" in pf
        and sum(v for k, v in pf.items() if k != "total") == pf.get("total")
        and isinstance(d.get("headline"), str) and d["headline"]
        and d.get("recent_manley_activity") == []
        and isinstance(d.get("attention_feed"), list)
    )
    return Check("dashboard", ok, summary=f"company={d.get('company')!r} total={pf.get('total')}")


def check_locations(view) -> Check:
    items = view.get("locations", [])
    exp = view.get("expected_sites")
    ok = (exp is None or len(items) == exp) and all(
        i.get("location") and i.get("location_ref", "").startswith("loc_") and i.get("protection")
        for i in items
    )
    return Check("locations", ok, summary=f"{len(items)} locations (expected {exp})")


def check_services(view) -> Check:
    total = len(view.get("services", []))
    exp = view.get("expected_services")
    shape_ok = all(
        s.get("service_ref", "").startswith("svc_") and s.get("protection") for s in view.get("services", [])
    )
    ok = (exp is None or total == exp) and shape_ok
    return Check("services", ok, summary=f"{total} services (expected {exp})")


def check_e911(view) -> Check:
    bad, verified, critical = [], 0, 0
    for e in view.get("e911", []):
        ver = e.get("verification") or {}
        state, is_crit, active = ver.get("state"), ver.get("is_critical"), e.get("active")
        if state == "Verified":
            verified += 1
            if is_crit:
                bad.append(e.get("location"))           # verified must not be critical
        elif active and state != "Verified" and not is_crit:
            bad.append(e.get("location"))               # active+unverified MUST be critical
        if is_crit:
            critical += 1
    return Check("e911", not bad, summary=f"verified={verified} critical={critical}", samples=bad[:5])


def check_no_false_green(view) -> Check:
    bad = [p for p in _iter_protections(view)
           if p.get("status") == "Protected" and (not p.get("evidence") or not p.get("evidence", {}).get("signals") or not p.get("as_of"))]
    return Check("no_false_green", not bad, hard=True,
                 summary=f"{len(bad)} Protected-without-evidence", samples=bad[:5])


def check_reasons(view) -> Check:
    bad = [p for p in _iter_protections(view)
           if p.get("status") != "Protected" and not (p.get("reason") or "").strip()]
    return Check("reasons", not bad, hard=True,
                 summary=f"{len(bad)} non-green without a reason", samples=bad[:5])


def check_unknown(view) -> Check:
    unknown = [p for p in _iter_protections(view) if p.get("status") == "Unknown"]
    max_unknown = view.get("max_unknown", 0)
    ok = len(unknown) <= max_unknown
    return Check("unknown", ok, summary=f"{len(unknown)} Unknown (max {max_unknown})")


def check_no_leak(view) -> Check:
    blob = view.get("blob", "")
    offenders = []
    for v in view.get("forbidden_values", []):
        if v and len(v) >= 6 and v in blob:
            offenders.append(f"value:{v[:6]}…")
    for k in _LEAK_KEYS:
        if f'"{k}"' in blob:
            offenders.append(f"key:{k}")
    return Check("leaks", not offenders, hard=True,
                 summary=f"{len(offenders)} hidden-field leak(s)", samples=offenders[:8])


def check_billing_deferred(view) -> Check:
    blob = view.get("blob", "")
    found = [k for k in _BILLING_KEYS if f'"{k}"' in blob]
    return Check("billing_deferred", not found, summary=f"billing keys present: {found or 'none'}")


def check_support_deferred(view) -> Check:
    blob = view.get("blob", "")
    found = [k for k in _SUPPORT_INTERNAL_KEYS if f'"{k}"' in blob]
    return Check("support_deferred", not found, summary=f"support internals present: {found or 'none'}")


_CHECKS = {
    "dashboard": check_dashboard, "locations": check_locations, "services": check_services,
    "e911": check_e911, "no_false_green": check_no_false_green, "reasons": check_reasons,
    "unknown": check_unknown, "leaks": check_no_leak,
    "billing_deferred": check_billing_deferred, "support_deferred": check_support_deferred,
}


def run_checks(view, only=None) -> list[Check]:
    names = [only] if only else list(_CHECKS)
    return [_CHECKS[n](view) for n in names if n in _CHECKS]


# ── Composition (read-only DB glue) ──────────────────────────────────
async def _collect(db, tenant_id: str) -> dict:
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models.device import Device
    from app.models.service_unit import ServiceUnit
    from app.models.site import Site
    from app.services.customer import portfolio as cp
    from app.services.customer import serialize as cs

    now = datetime.now(timezone.utc)
    protections, e911, services, equipment, details = [], [], [], [], []

    portfolio = await cp.load_portfolio(db, tenant_id, now)
    company = await cp.company_name(db, tenant_id)
    counts = cs.portfolio_counts([p["status"] for _, p in portfolio])
    feed = [cs.attention_item(s, protection=p) for s, p in portfolio if p["status"] != "Protected"]
    dashboard = {"company": company, "portfolio": counts,
                 "headline": cs.headline(counts, now.isoformat()),
                 "attention_feed": feed, "recent_manley_activity": []}
    locations = [cs.location_summary(s, protection=p) for s, p in portfolio]
    protections += [p for _, p in portfolio]

    for s, _p in portfolio:
        resolved = await cp.resolve_location(db, tenant_id, cs.encode_ref("loc", s.id), now)
        if resolved:
            site, prot, svc_prev = resolved
            details.append(cs.location_detail(site, protection=prot, services=svc_prev))
            protections += [sp["protection"] for sp in svc_prev if "protection" in sp]
        # E911 axis (separate)
        site2 = await cp.resolve_site(db, tenant_id, cs.encode_ref("loc", s.id))
        if site2 is not None:
            logs = await cp.load_e911_history(db, tenant_id, site2.site_id)
            summ = cs.e911_summary(site2, history=[cs.e911_history_item(x) for x in logs])
            summ["active"] = (site2.status or "").lower() == "active"
            e911.append(summ)

    units = (await db.execute(select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all()
    for u in units:
        rs = await cp.resolve_service(db, tenant_id, cs.encode_ref("svc", u.id), now)
        if rs:
            unit, device, svc_prot, eq_prot = rs
            eq = cs.equipment_from_device(device, protection=eq_prot) if device is not None else None
            services.append(cs.service_from_unit(unit, protection=svc_prot, equipment=eq))
            equipment.append(eq or {"equipment": None, "protection": eq_prot})
            protections += [svc_prot, eq_prot]

    # Forbidden values from the REAL rows (strongest leak test).
    forbidden = set()
    for d in (await db.execute(select(Device).where(Device.tenant_id == tenant_id))).scalars().all():
        for f in _LEAK_VALUE_FIELDS:
            val = getattr(d, f, None)
            if isinstance(val, str) and val.strip():
                forbidden.add(val.strip())
    for s in (await db.execute(select(Site).where(Site.tenant_id == tenant_id))).scalars().all():
        for f in _LEAK_VALUE_FIELDS:
            val = getattr(s, f, None)
            if isinstance(val, str) and val.strip():
                forbidden.add(val.strip())

    everything = {"dashboard": dashboard, "locations": locations, "details": details,
                  "services": services, "equipment": equipment, "e911": e911}
    return {
        **everything,
        "all_protections": protections,
        "expected_sites": len(portfolio),
        "expected_services": len(units),
        "max_unknown": int(os.environ.get("RH_VALIDATE_MAX_UNKNOWN", "0")),
        "forbidden_values": forbidden,
        "blob": json.dumps(everything, default=str),
    }


async def run(strict: bool = True, only=None) -> list[Check]:
    from app.database import AsyncSessionLocal
    print("=" * 72)
    print(f"RH customer-API render validation — tenant '{RH_TENANT}' (READ-ONLY, flag-off)")
    print("=" * 72)
    async with AsyncSessionLocal() as db:
        view = await _collect(db, RH_TENANT)
        await db.rollback()  # never write
    checks = run_checks(view, only=only)
    _report(checks, view)
    export = _export_path()
    if export:
        jp, cp = _write_reports(export, checks, view)
        print(f"\n  JSON artifact: {jp}\n  CSV summary:   {cp}")
    hard_fail = any((not c.passed) and c.hard for c in checks)
    if strict and hard_fail:
        raise SystemExit(2)
    return checks


def verdict(checks) -> tuple[str, str]:
    """PASS / CONDITIONAL PASS / FAIL + the go/no-go recommendation.

    A hard/critical failure (no-false-green, unexplained-red, hidden-field leak)
    is FAIL/NO-GO and is never waived. Only soft failures (e.g. services not yet
    created, Unknown above threshold) yield CONDITIONAL PASS."""
    hard = [c.name for c in checks if not c.passed and c.hard]
    soft = [c.name for c in checks if not c.passed and not c.hard]
    if hard:
        return "FAIL", "NO-GO"
    if soft:
        return "CONDITIONAL PASS", "CONDITIONAL GO — review data gaps"
    return "PASS", "GO"


def _report(checks, view) -> None:
    print(f"\nExpected sites={view.get('expected_sites')} services={view.get('expected_services')} "
          f"max_unknown={view.get('max_unknown')}\n")
    for c in checks:
        mark = "PASS" if c.passed else ("FAIL*" if c.hard else "FAIL")
        print(f"  [{mark:<5}] {c.name:<18} {c.summary}")
        if not c.passed and c.samples:
            print(f"            e.g. {c.samples}")
    status, rec = verdict(checks)
    print(f"\n  RESULT: {status}    →    RECOMMENDATION: {rec}")
    hard = [c.name for c in checks if not c.passed and c.hard]
    soft = [c.name for c in checks if not c.passed and not c.hard]
    if hard:
        print(f"  hard failures (never waived): {hard}")
    if soft:
        print(f"  soft failures (review): {soft}")


def _write_reports(base, checks, view) -> tuple[str, str]:
    """Write the JSON validation artifact + the CSV summary. Returns their paths."""
    import csv as _csv
    import io as _io

    status, rec = verdict(checks)
    json_path = base if base.endswith(".json") else base + ".json"
    csv_path = (base[:-5] if base.endswith(".json") else base) + ".csv"

    out = {"tenant": RH_TENANT, "result": status, "recommendation": rec,
           "expected_sites": view.get("expected_sites"),
           "expected_services": view.get("expected_services"),
           "checks": [{"name": c.name, "passed": c.passed, "hard": c.hard,
                       "summary": c.summary, "samples": c.samples} for c in checks]}
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=["name", "status", "hard", "summary"])
    w.writeheader()
    for c in checks:
        w.writerow({"name": c.name, "status": "PASS" if c.passed else "FAIL",
                    "hard": c.hard, "summary": c.summary})
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    return json_path, csv_path


def _export_path():
    if "--export" in sys.argv:
        i = sys.argv.index("--export")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _only_arg():
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main() -> None:
    strict = os.environ.get("RH_VALIDATE_STRICT", "true").strip().lower() not in ("0", "false", "no", "off")
    try:
        asyncio.run(run(strict=strict, only=_only_arg()))
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - connectivity edge
        print(f"\nERROR: validation aborted — {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
