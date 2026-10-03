"""READ-ONLY preview of the customer-safe canonical SERVICE INVENTORY (#186b).

Prints exactly the service-inventory blocks the customer API would serve for a
tenant - per location and for the portfolio - WHATEVER the feature flag says, so
an operator can review them before anyone enables FEATURE_CANONICAL_SERVICE_MODEL.
It also scans the would-be customer payload for internal identifiers (canonical
keys, radio / SIM / IMEI values, internal name markers) and reports whether the
view WOULD currently be served (flag, allowlist, durable ref secret).

Writes nothing: SELECTs only, the session is rolled back.  Refs are not printed.

Usage (Render shell, api service):
    python -m scripts.canonical_customer_preview --tenant restoration-hardware
    python -m scripts.canonical_customer_preview --tenant restoration-hardware --json /tmp/inv.json
Exit: 0 ok - 2 leak scan failed - 3 error / no applied projection
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_KEY_RE = re.compile(r"\b(?:FACP|ELEV|EPH|UNCL):|\b(?:radio|tel|zoho|device|registry):", re.I)


def leak_scan(payload, secrets) -> list[str]:
    """Problems found in the serialised customer payload (empty = clean)."""
    from app.services.customer.serialize import _INTERNAL_NAME_MARKERS
    text = json.dumps(payload, default=str)
    out = []
    if _KEY_RE.search(text):
        out.append("canonical / source key pattern present")
    if _INTERNAL_NAME_MARKERS.search(text):
        out.append("internal name marker present")
    for v in secrets:
        if v and len(v) >= 6 and v in text:
            out.append("internal identifier value present (masked: ***%s)" % v[-4:])
    return out


async def preview(db, tenant: str) -> dict:
    from sqlalchemy import select

    from app.config import settings
    from app.models.canonical import CommunicationsAsset
    from app.models.portfolio_registry import PortfolioBuilding
    from app.services.canonical import vocab as V
    from app.services.customer import canonical_view as cv
    from app.services.customer import refs
    from app.services.customer.serialize import building_display_name, valid_store_number

    inv = await cv.load_inventory(db, tenant, force=True)
    if inv is None:
        return {"error": "no clean APPLY canonical projection for tenant %r" % tenant}
    rows = (await db.execute(select(PortfolioBuilding).where(
        PortfolioBuilding.tenant_id == tenant))).scalars().all()
    locations = []
    for b in sorted(rows, key=lambda x: (x.canonical_name or "")):
        active = (b.status or "active").strip().lower() == "active"
        if not (b.approved and active):
            continue                          # never shown to the customer (CG-1 L4)
        blk = cv.building_inventory(inv, b.id, approved=True, active=True, pending=False)
        store = b.store_number if valid_store_number(b.store_number) else None
        locations.append({"location": building_display_name(b.canonical_name, store, b.city,
                                                            b.site_type),
                          "service_inventory": blk})
    portfolio = cv.portfolio_inventory([x["service_inventory"] for x in locations], inv["as_of"])
    secrets = [a.normalized_value for a in (await db.execute(select(CommunicationsAsset).where(
        CommunicationsAsset.tenant_id == tenant,
        CommunicationsAsset.asset_type.in_([V.NAPCO_RADIO, V.SIM_ICCID, V.DEVICE_IMEI])))).scalars()]
    payload = {"portfolio": portfolio, "locations": locations}
    return {
        "would_be_served": {
            "FEATURE_CANONICAL_SERVICE_MODEL": settings.FEATURE_CANONICAL_SERVICE_MODEL,
            "tenant_allowlisted": tenant in settings.canonical_service_model_tenant_id_set,
            "CUSTOMER_REF_SECRET_configured": refs.dedicated_secret_configured(),
            "served_now": cv.canonical_mode_enabled(tenant) and refs.dedicated_secret_configured(),
        },
        "projection_run": {"id": inv["run_id"], "as_of": inv["as_of"]},
        "payload": payload,
        "leak_scan": leak_scan(payload, secrets),
    }


def render(res: dict) -> str:
    L = ["=== CANONICAL CUSTOMER SERVICE-INVENTORY PREVIEW (READ-ONLY) ==="]
    L.append("would be served now: %s" % json.dumps(res["would_be_served"], sort_keys=True))
    L.append("projection run: %s" % json.dumps(res["projection_run"]))
    p = res["payload"]["portfolio"]
    L.append("")
    L.append("=== PORTFOLIO ===")
    for k in ("locations_total", "locations_ready", "locations_partially_ready",
              "locations_being_finalized", "locations_no_services_on_record",
              "records_being_finalized"):
        L.append("%-34s %s" % (k, p[k]))
    L.append("ready services by type: %s" % (", ".join(
        "%s=%d" % (x["service"], x["count"]) for x in p["ready_services_by_type"]) or "none"))
    L.append("")
    L.append("=== LOCATIONS ===")
    for loc in res["payload"]["locations"]:
        b = loc["service_inventory"]
        L.append("%s | %s | %s" % (loc["location"], b["state"], b["message"]))
        for s in b["ready_services"]:
            L.append("    READY  %s | %s | required_paths=%d | telephone=%s" % (
                s["service"], s["name"], s["required_paths"], s["telephone_number"] or "-"))
    L.append("")
    L.append("=== LEAK SCAN ===")
    L.append("CLEAN" if not res["leak_scan"] else "FAIL: " + "; ".join(res["leak_scan"]))
    L.append("(READ-ONLY: nothing was written; refs not printed)")
    return "\n".join(L)


async def run(args) -> int:
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        res = await preview(db, args.tenant)
        await db.rollback()
    if "error" in res:
        print(res["error"])
        return 3
    print(render(res))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, default=str)
        print("json written: %s" % args.json)
    return 2 if res["leak_scan"] else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tenant", required=True)
    p.add_argument("--json", help="also write the preview as JSON to this path")
    args = p.parse_args()
    try:
        code = asyncio.run(run(args))
    except Exception as exc:
        print("ERROR: %s: %s" % (type(exc).__name__, exc))
        code = 3
    sys.exit(code)


if __name__ == "__main__":
    main()
