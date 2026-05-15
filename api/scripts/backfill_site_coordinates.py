#!/usr/bin/env python3
"""Safely backfill ``sites.lat`` / ``sites.lng`` from E911 address fields.

DRY-RUN BY DEFAULT.  Real writes require either ``--apply`` *or*
``DRY_RUN=false`` in the environment.  Anything else (including the
default, or ``DRY_RUN=true``) is a dry-run and performs zero UPDATE
statements.

Only ``lat`` and ``lng`` are ever written.  No other column, table, or
row is touched.  Specifically untouched:
  * tenant_id, customer_id, site_name, site_id
  * devices, registrations, registration_locations
  * e911_* fields, address_source, e911_status
  * any API-sync / reconciliation column

Selection rules (one pass over the ``sites`` table):
  1. ``has_valid_coords(lat, lng)`` is True             → already_ok, skip
  2. No e911_* address parts at all                     → skipped_incomplete, log
  3. Address present, geocoder returns coords          → geocoded (UPDATE)
  4. Address present, geocoder returns None            → failed, log

Safety guarantees:
  * Dry-run is the default.  No writes happen without explicit opt-in.
  * The UPDATE is conditioned on both ``lat IS NULL`` and ``lng IS NULL``
    so a row whose coords were filled in by another path (the auto-
    geocode in the API, the admin bulk endpoint, manual edit) is never
    overwritten by this script.  Re-running is safe.
  * Each batch is selected with ``FOR UPDATE SKIP LOCKED`` in apply
    mode, so the script does not block live API writes.
  * The geocoder enforces 1 req/sec to Nominatim internally; we add a
    small inter-batch pause so a long run is gentle on the DB pool too.

Usage on the Render shell (``true911-api`` service):

    cd api
    # 1. Dry-run (default) — prints the summary, writes nothing.
    DRY_RUN=true python -m scripts.backfill_site_coordinates

    # 2. Review the summary, then apply for real.
    DRY_RUN=false python -m scripts.backfill_site_coordinates --apply
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

# Make ``app.*`` importable when invoked either as ``python -m`` or directly.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import select, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.services.geocoding import geocode_address, has_valid_coords  # noqa: E402


logger = logging.getLogger("backfill_site_coordinates")


def _banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def _env_dry_run_default_true() -> bool:
    """Read DRY_RUN from env.  Missing / unrecognized → True (safe)."""
    raw = os.getenv("DRY_RUN")
    if raw is None:
        return True
    return raw.strip().lower() not in {"false", "0", "no", "off"}


def _has_any_address(site: Site) -> bool:
    return any(
        (site.e911_street, site.e911_city, site.e911_state, site.e911_zip)
    )


def _short_addr(site: Site) -> str:
    parts = [
        (site.e911_street or "").strip(),
        (site.e911_city or "").strip(),
        (site.e911_state or "").strip(),
        (site.e911_zip or "").strip(),
    ]
    return ", ".join(p for p in parts if p) or "<no address>"


async def _process(
    db: AsyncSession,
    apply_writes: bool,
    tenant_filter: Optional[str],
    batch_size: int,
    pace_ms: int,
    limit: Optional[int],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    last_id = 0

    while True:
        if limit is not None and counts["total_checked"] >= limit:
            print(f"  reached --limit ({limit}); stopping")
            break

        remaining = batch_size
        if limit is not None:
            remaining = min(batch_size, limit - counts["total_checked"])

        # Narrow the read at the DB: only rows that *might* need a backfill.
        # ``has_valid_coords`` (in Python) is the source of truth and also
        # filters (0,0) and out-of-range values, but pulling only the
        # NULL-coord rows from the DB keeps the working set small.
        q = (
            select(Site)
            .where((Site.lat.is_(None)) | (Site.lng.is_(None)))
            .where(Site.id > last_id)
            .order_by(Site.id)
            .limit(remaining)
        )
        if tenant_filter:
            q = q.where(Site.tenant_id == tenant_filter)
        if apply_writes:
            q = q.with_for_update(skip_locked=True)

        result = await db.execute(q)
        sites = result.scalars().all()
        if not sites:
            break

        for site in sites:
            counts["total_checked"] += 1

            if has_valid_coords(site.lat, site.lng):
                # Shouldn't happen given the WHERE clause, but harmless.
                counts["already_ok"] += 1
                continue

            counts["missing_coordinates"] += 1

            if not _has_any_address(site):
                counts["skipped_incomplete"] += 1
                logger.info(
                    "SKIP incomplete address  site_id=%s tenant=%s name=%r",
                    site.site_id,
                    site.tenant_id,
                    site.site_name,
                )
                continue

            try:
                coords = await geocode_address(
                    site.e911_street,
                    site.e911_city,
                    site.e911_state,
                    site.e911_zip,
                )
            except Exception:
                # geocode_address is already defensive, but be paranoid:
                # an unexpected error must never abort the whole run.
                logger.exception(
                    "geocode exception  site_id=%s addr=%r",
                    site.site_id,
                    _short_addr(site),
                )
                coords = None

            if coords is None:
                counts["failed_geocode"] += 1
                logger.warning(
                    "FAIL  site_id=%s tenant=%s addr=%r",
                    site.site_id,
                    site.tenant_id,
                    _short_addr(site),
                )
                continue

            lat, lng = coords

            if apply_writes:
                # Idempotent: only fill in when both coords are still NULL.
                # Core UPDATE so the statement carries *only* lat/lng —
                # the ORM session is never asked to flush any other
                # attribute of this row.
                upd = (
                    update(Site)
                    .where(Site.id == site.id)
                    .where(Site.lat.is_(None))
                    .where(Site.lng.is_(None))
                    .values(lat=lat, lng=lng)
                )
                res = await db.execute(upd)
                if res.rowcount == 1:
                    counts["geocoded"] += 1
                    logger.info(
                        "OK    site_id=%s -> (%.6f, %.6f)  addr=%r",
                        site.site_id,
                        lat,
                        lng,
                        _short_addr(site),
                    )
                else:
                    # Another writer beat us to it — treat as a no-op skip.
                    counts["concurrent_skip"] += 1
            else:
                counts["geocoded"] += 1  # would-be updates in dry-run
                logger.info(
                    "DRY   site_id=%s -> (%.6f, %.6f)  addr=%r",
                    site.site_id,
                    lat,
                    lng,
                    _short_addr(site),
                )

        if apply_writes:
            await db.commit()
        else:
            await db.rollback()

        last_id = sites[-1].id
        if len(sites) < remaining:
            break
        if pace_ms > 0:
            await asyncio.sleep(pace_ms / 1000.0)

    return counts


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply writes.  Without --apply (or with DRY_RUN!=false), the "
             "script performs a dry-run and issues no UPDATE statements.",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Optional: restrict to a single tenant_id.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Sites per batch (default 200).  Geocoder is rate-limited to "
             "~1 rps, so batch size mostly controls DB pool pressure.",
    )
    parser.add_argument(
        "--pace-ms",
        type=int,
        default=200,
        help="Sleep between batches in milliseconds (default 200).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Hard cap on total sites considered (safety for first runs).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Dry-run unless --apply *and* DRY_RUN is not "true"-ish.
    env_dry = _env_dry_run_default_true()
    apply_writes = args.apply and not env_dry

    mode_str = "APPLY (writes will occur)" if apply_writes else "DRY-RUN (no writes)"
    if args.apply and env_dry:
        mode_str += "  [--apply was passed but DRY_RUN env forced dry-run]"

    started = datetime.now(timezone.utc)
    _banner(f"backfill_site_coordinates  [{mode_str}]")
    print(f"  started    : {started.isoformat()}")
    print(f"  scope      : {'tenant=' + args.tenant if args.tenant else 'all tenants'}")
    print(f"  batch_size : {args.batch_size}")
    print(f"  pace_ms    : {args.pace_ms}")
    print(f"  limit      : {args.limit if args.limit is not None else 'none'}")
    print(f"  DRY_RUN env: {os.getenv('DRY_RUN', '<unset, treated as true>')}")
    if not apply_writes:
        print("  >> dry-run: no UPDATE statements will be issued <<")

    async with AsyncSessionLocal() as db:
        counts = await _process(
            db,
            apply_writes=apply_writes,
            tenant_filter=args.tenant,
            batch_size=args.batch_size,
            pace_ms=args.pace_ms,
            limit=args.limit,
        )

    finished = datetime.now(timezone.utc)

    _banner("Summary")
    print(f"  mode                       : {'apply' if apply_writes else 'dry_run'}")
    print(f"  duration                   : {(finished - started).total_seconds():.2f}s")
    print(f"  total sites checked        : {counts.get('total_checked', 0)}")
    print(f"  missing coordinates        : {counts.get('missing_coordinates', 0)}")
    if apply_writes:
        print(f"  successfully geocoded      : {counts.get('geocoded', 0)}")
        print(f"  concurrent-write skips     : {counts.get('concurrent_skip', 0)}")
    else:
        print(f"  would-be geocoded (dry-run): {counts.get('geocoded', 0)}")
    print(f"  skipped incomplete address : {counts.get('skipped_incomplete', 0)}")
    print(f"  failed geocodes            : {counts.get('failed_geocode', 0)}")
    print()
    if not apply_writes:
        print("  Re-run with --apply (and DRY_RUN=false) to write these.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
