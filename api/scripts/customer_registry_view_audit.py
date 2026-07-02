"""Customer Portfolio-Registry view audit (READ-ONLY diagnostic).

Explains, at a glance, WHY the customer dashboard shows N locations: is it reading
legacy Site rows, the approved Portfolio Registry, or falling back to legacy because
the registry has no visible buildings yet?

Reports, for a tenant:
  * feature-flag state (registry mode / show-pending / preview-pending)
  * approved registry buildings · pending review buildings · pending PortfolioBuilding rows
  * legacy Site count
  * customer-visible building count (what the customer would actually see)
  * the effective customer endpoint mode:
        legacy_site_mode | registry_mode | fallback_mode

Read-only: only SELECTs; never writes anything.

Usage:
    python -m scripts.customer_registry_view_audit --tenant restoration-hardware
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_TENANT = os.environ.get("RH_READINESS_TENANT", "restoration-hardware")


async def _audit(tenant: str) -> dict:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.portfolio_registry import PortfolioBuilding, PortfolioReviewItem
    from app.models.site import Site
    from app.services.customer import portfolio_registry_view as prv

    async with AsyncSessionLocal() as db:
        buildings = (await db.execute(select(PortfolioBuilding).where(
            PortfolioBuilding.tenant_id == tenant))).scalars().all()
        approved = sum(1 for b in buildings if b.approved)
        pending_rows = sum(1 for b in buildings if not b.approved)

        pending_reviews = (await db.execute(select(func.count()).select_from(
            PortfolioReviewItem).where(PortfolioReviewItem.tenant_id == tenant,
                                       PortfolioReviewItem.status == "pending"))).scalar() or 0
        legacy_sites = (await db.execute(select(func.count()).select_from(
            Site).where(Site.tenant_id == tenant))).scalar() or 0

        registry_on = prv.registry_mode_enabled(tenant)
        include_pending = prv._include_pending(tenant)
        visible_building_rows = approved + (pending_rows if include_pending else 0)

        if not registry_on:
            mode = "legacy_site_mode"
            customer_visible = legacy_sites
        elif visible_building_rows == 0:
            mode = "fallback_mode"       # registry on, but nothing visible -> legacy
            customer_visible = legacy_sites
        else:
            mode = "registry_mode"
            customer_visible = visible_building_rows

    return {
        "tenant": tenant,
        "flags": {
            "FEATURE_CUSTOMER_PORTFOLIO_REGISTRY": _flag("FEATURE_CUSTOMER_PORTFOLIO_REGISTRY"),
            "registry_mode_enabled": registry_on,
            "CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS": _flag("CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS"),
            "preview_pending_enabled": prv.preview_pending_enabled(tenant),
        },
        "registry_buildings_approved": approved,
        "registry_buildings_pending_rows": pending_rows,
        "registry_review_items_pending": pending_reviews,
        "legacy_site_count": legacy_sites,
        "customer_visible_count": customer_visible,
        "customer_endpoint_mode": mode,
    }


def _flag(name):
    from app.config import settings
    return getattr(settings, name, None)


def _print(a: dict) -> None:
    print("=" * 68)
    print(f"Customer Portfolio-Registry view audit — {a['tenant']}")
    print("=" * 68)
    print(f"  registry mode enabled : {a['flags']['registry_mode_enabled']}")
    print(f"  show-pending flag      : {a['flags']['CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS']}")
    print(f"  preview-pending        : {a['flags']['preview_pending_enabled']}")
    print("-" * 68)
    print(f"  registry buildings approved     : {a['registry_buildings_approved']}")
    print(f"  registry buildings pending rows : {a['registry_buildings_pending_rows']}")
    print(f"  registry review items pending   : {a['registry_review_items_pending']}")
    print(f"  legacy Site count               : {a['legacy_site_count']}")
    print(f"  CUSTOMER-VISIBLE count          : {a['customer_visible_count']}")
    print("-" * 68)
    print(f"  >>> customer endpoint mode: {a['customer_endpoint_mode'].upper()} <<<")
    if a["customer_endpoint_mode"] == "fallback_mode":
        print("      (registry mode is ON, but 0 visible buildings — customer sees legacy")
        print("       Site rows. Approve registry buildings to switch to registry_mode.)")
    print("  (Read-only — wrote nothing.)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Customer Portfolio-Registry view audit (read-only).")
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()
    try:
        out = asyncio.run(_audit(args.tenant))
    except Exception as exc:
        print(f"ERROR: audit failed — {type(exc).__name__}: {exc}")
        raise SystemExit(3)
    if args.json:
        import json
        print(json.dumps(out, indent=2, default=str))
    else:
        _print(out)


if __name__ == "__main__":
    main()
