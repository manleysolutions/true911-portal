#!/usr/bin/env python3
"""Read-only tenant data audit.

Prints, for every tenant_id present in the system across the major
tables, a row count.  Used to decide which tenant should be the
operational workspace for the onboarding team.

Run on Render shell from the api/ directory:

    cd api
    python -m scripts.inspect_tenant_data

Read-only.  Does not write to any table.  Does not change auth behavior.
"""

import asyncio
import os
import sys
from collections import defaultdict

# Make `app.*` importable from either invocation form.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.line import Line  # noqa: E402
from app.models.service_unit import ServiceUnit  # noqa: E402
from app.models.sim import Sim  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402

# Models to audit, in display order.
_TABLES: list[tuple[str, type]] = [
    ("users",         User),
    ("customers",     Customer),
    ("sites",         Site),
    ("devices",       Device),
    ("lines",         Line),
    ("sims",          Sim),
    ("service_units", ServiceUnit),
]


def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


async def main() -> int:
    async with AsyncSessionLocal() as db:
        # ── tenants table itself ──────────────────────────────────
        _banner("Tenants table")
        result = await db.execute(
            select(Tenant.tenant_id, Tenant.name, Tenant.is_active, Tenant.org_type)
            .order_by(Tenant.tenant_id)
        )
        tenants = list(result.all())
        if not tenants:
            print("  (no tenants found)")
        else:
            print(f"  {'tenant_id':<28} {'is_active':<10} {'org_type':<14} name")
            print(f"  {'-'*28} {'-'*10} {'-'*14} {'-'*30}")
            for slug, name, is_active, org_type in tenants:
                print(f"  {slug:<28} {str(is_active):<10} {str(org_type or ''):<14} {name}")

        all_tenant_slugs = {t[0] for t in tenants}

        # ── per-tenant counts per table ───────────────────────────
        _banner("Row counts by tenant_id (only nonzero shown)")
        # Collect: counts[tenant_id][table] = N
        counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        seen_slugs: set[str] = set()
        for label, model in _TABLES:
            r = await db.execute(
                select(model.tenant_id, func.count())
                .group_by(model.tenant_id)
            )
            for slug, n in r.all():
                if n:
                    counts[slug or "<NULL>"][label] = int(n)
                    seen_slugs.add(slug or "<NULL>")

        if not seen_slugs:
            print("  (no rows in any tenant)")
        else:
            header = f"  {'tenant_id':<28} " + "  ".join(f"{lbl:>13}" for lbl, _ in _TABLES)
            print(header)
            print("  " + "-" * (len(header) - 2))
            # Sort: known tenants first by slug, then any orphan slugs.
            orphan_slugs = seen_slugs - all_tenant_slugs
            for slug in sorted(seen_slugs - orphan_slugs):
                row = f"  {slug:<28} "
                row += "  ".join(f"{counts[slug].get(lbl, 0):>13}" for lbl, _ in _TABLES)
                print(row)
            if orphan_slugs:
                print()
                print("  (orphan tenant_ids — present on rows but missing from tenants table)")
                for slug in sorted(orphan_slugs):
                    row = f"  {slug:<28} "
                    row += "  ".join(f"{counts[slug].get(lbl, 0):>13}" for lbl, _ in _TABLES)
                    print(row)

        # ── totals row ────────────────────────────────────────────
        totals: dict[str, int] = defaultdict(int)
        for slug_counts in counts.values():
            for lbl, n in slug_counts.items():
                totals[lbl] += n
        print()
        print("  " + "-" * (len(header) - 2))
        row = f"  {'TOTAL':<28} " + "  ".join(f"{totals.get(lbl, 0):>13}" for lbl, _ in _TABLES)
        print(row)

        # ── interpretation hint ───────────────────────────────────
        _banner("Interpretation")
        # Find the tenant with the most onboarding records (sum of customers+sites+devices).
        if counts:
            score = {
                slug: c.get("customers", 0) + c.get("sites", 0) + c.get("devices", 0)
                for slug, c in counts.items()
            }
            top = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
            print("  Tenants ranked by onboarding-data weight (customers+sites+devices):")
            for slug, weight in top[:5]:
                print(f"    {slug:<28}  weight={weight}")
            top_slug, _ = top[0]
            print()
            print(f"  → '{top_slug}' currently holds the most onboarding data.")
            print("    This is a strong candidate for the operational tenant.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
