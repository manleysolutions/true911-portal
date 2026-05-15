#!/usr/bin/env python3
"""Backfill latitude/longitude for sites that have an E911 address but
no valid coordinates.

Defaults to DRY_RUN — no writes occur unless DRY_RUN=false is set.
Hits the same Nominatim service the API uses, with the same caching and
1-request-per-second rate limit.  Geocoding failures are non-fatal:
sites that don't resolve are reported and skipped.

Rate-limit safety
-----------------
Two layers of throttling are applied so a long backfill does not trip
Nominatim's 1 req/sec policy or its 429 response:

  * The geocoding service itself enforces 1 second between calls.
  * This script adds an additional ``INTER_REQUEST_SLEEP`` (1.1s) gap
    between sites and retries up to ``MAX_RETRIES`` times with a
    ``RETRY_WAIT_SECONDS`` pause whenever a call returns no result.

The underlying ``app.services.geocoding`` swallows transient HTTP
errors (including 429) and returns ``None``, so the script cannot
distinguish a 429 from a genuinely unresolvable address.  Both are
retried — that's intentional: a stuck address costs a small amount of
extra time but does not block the rest of the backfill.

Run:
    python -m scripts.backfill_geocode                   # dry run
    DRY_RUN=false python -m scripts.backfill_geocode     # apply

Optional filters (env vars):
    TENANT_SLUG=<slug>   restrict to one tenant (default: all tenants)
    LIMIT=<int>          stop after N attempts (default: no limit)
"""

import asyncio
import os
import sys
from typing import Optional

# Make app.* importable when run as `python -m scripts.backfill_geocode`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.services.geocoding import geocode_address, has_valid_coords  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────
TENANT_SLUG: Optional[str] = os.environ.get("TENANT_SLUG") or None
_LIMIT_RAW = os.environ.get("LIMIT", "").strip()
LIMIT: Optional[int] = int(_LIMIT_RAW) if _LIMIT_RAW.isdigit() else None

_DRY_ENV = os.environ.get("DRY_RUN", "true").strip().lower()
DRY_RUN = _DRY_ENV not in ("0", "false", "no", "off")

# Throttling tunables.  Both can be overridden via env without code change.
INTER_REQUEST_SLEEP = float(os.environ.get("INTER_REQUEST_SLEEP", "1.1"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
RETRY_WAIT_SECONDS = float(os.environ.get("RETRY_WAIT_SECONDS", "5"))

# Schema-feature detection so this script keeps working both before and
# after any future migration that adds ``archived`` or a soft-delete
# column to ``sites``.  ``status`` always exists.
_SITE_COLS = set(Site.__table__.columns.keys())
_HAS_ARCHIVED = "archived" in _SITE_COLS
_HAS_DELETED_AT = "deleted_at" in _SITE_COLS
_HAS_IS_DELETED = "is_deleted" in _SITE_COLS
MERGED_STATUS = "merged"


def _banner(text: str) -> None:
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def _section(text: str) -> None:
    print()
    print(f"── {text} " + "─" * max(1, 68 - len(text)))


async def _geocode_with_retry(
    street: Optional[str],
    city: Optional[str],
    state: Optional[str],
    zip_code: Optional[str],
) -> tuple[Optional[tuple[float, float]], int]:
    """Wrap geocode_address with retry-on-None.

    Returns ``(coords_or_None, attempts_made)``.  Up to ``MAX_RETRIES``
    additional attempts are made after the initial call, each preceded
    by a ``RETRY_WAIT_SECONDS`` sleep so a 429 or transient network
    blip has time to clear.
    """
    total_attempts = 1 + MAX_RETRIES
    for attempt in range(1, total_attempts + 1):
        coords = await geocode_address(street, city, state, zip_code)
        if coords:
            return coords, attempt
        if attempt < total_attempts:
            print(
                f"    → no result on attempt {attempt}/{total_attempts}; "
                f"sleeping {RETRY_WAIT_SECONDS:g}s and retrying..."
            )
            await asyncio.sleep(RETRY_WAIT_SECONDS)
    return None, total_attempts


async def _candidates(db: AsyncSession) -> tuple[list[Site], dict[str, int]]:
    """Return ``(candidates, skip_counts)``.

    Candidates are sites missing coords that still have at least one
    address field AND are not in any "do not touch" state.  Sites that
    matched on coords/address but were excluded by a soft-deprecation
    state are counted in ``skip_counts`` so the operator can see why
    a row was passed over without burning a Nominatim request on it.
    """
    q = select(Site)
    if TENANT_SLUG:
        q = q.where(Site.tenant_id == TENANT_SLUG)
    result = await db.execute(q)
    sites = result.scalars().all()

    skip_counts = {"skipped_merged": 0, "skipped_archived": 0, "skipped_deleted": 0}
    candidates: list[Site] = []

    for s in sites:
        # Existing eligibility filters — unchanged.
        if has_valid_coords(s.lat, s.lng):
            continue
        if not any([s.e911_street, s.e911_city, s.e911_state, s.e911_zip]):
            continue

        # New exclusions — sites that have been soft-deprecated should
        # never be geocoded, both because the result is wasted work and
        # because 55+ merged synthetic rows from a bad import can drive
        # Nominatim into 429 throttling.
        if (s.status or "").strip().lower() == MERGED_STATUS:
            print(f"  Skipping merged site {s.site_id}")
            skip_counts["skipped_merged"] += 1
            continue
        if _HAS_ARCHIVED and bool(getattr(s, "archived", False)):
            print(f"  Skipping archived site {s.site_id}")
            skip_counts["skipped_archived"] += 1
            continue
        if (
            (_HAS_DELETED_AT and getattr(s, "deleted_at", None) is not None)
            or (_HAS_IS_DELETED and bool(getattr(s, "is_deleted", False)))
        ):
            print(f"  Skipping deleted site {s.site_id}")
            skip_counts["skipped_deleted"] += 1
            continue

        candidates.append(s)

    return candidates, skip_counts


async def main() -> int:
    mode = "DRY RUN — no writes will occur" if DRY_RUN else "APPLY MODE — changes WILL be written"
    _banner(mode)
    print(f"  TENANT_SLUG          = {TENANT_SLUG!r}  (None = all tenants)")
    print(f"  LIMIT                = {LIMIT!r}  (None = no limit)")
    print(f"  INTER_REQUEST_SLEEP  = {INTER_REQUEST_SLEEP}s")
    print(f"  MAX_RETRIES          = {MAX_RETRIES}")
    print(f"  RETRY_WAIT_SECONDS   = {RETRY_WAIT_SECONDS}s")

    async with AsyncSessionLocal() as db:
        _section("Scanning for sites missing coordinates")
        candidates, skip_counts = await _candidates(db)
        print(f"  {len(candidates)} site(s) match the backfill criteria")
        print()
        print("  Exclusions applied:")
        print(f"    skipped_merged    : {skip_counts['skipped_merged']}")
        print(
            f"    skipped_archived  : {skip_counts['skipped_archived']}"
            f"{' (column not present)' if not _HAS_ARCHIVED else ''}"
        )
        print(
            f"    skipped_deleted   : {skip_counts['skipped_deleted']}"
            f"{' (no soft-delete column present)' if not (_HAS_DELETED_AT or _HAS_IS_DELETED) else ''}"
        )

        if LIMIT is not None and len(candidates) > LIMIT:
            print(f"  Capping at LIMIT={LIMIT}")
            candidates = candidates[:LIMIT]

        if not candidates:
            _banner("Nothing to do — exiting cleanly")
            return 0

        _section("Per-site backfill")
        geocoded = 0
        failed: list[str] = []
        skipped = 0
        total = len(candidates)

        for idx, site in enumerate(candidates, start=1):
            # Pace requests on top of the geocoding service's own 1s lock.
            if idx > 1 and INTER_REQUEST_SLEEP > 0:
                await asyncio.sleep(INTER_REQUEST_SLEEP)

            label = (
                f"site_id={site.site_id!r}  tenant={site.tenant_id!r}  "
                f"name={site.site_name!r}"
            )
            address = f"{site.e911_street or '-'} | {site.e911_city or '-'}, {site.e911_state or '-'} {site.e911_zip or '-'}"
            print(f"  [{idx}/{total}] {label}")
            print(f"    address: {address}")

            coords, attempts = await _geocode_with_retry(
                site.e911_street, site.e911_city, site.e911_state, site.e911_zip
            )
            if not coords:
                failed.append(site.site_id)
                print(
                    f"    → geocode failed after {attempts} attempt(s) "
                    "(skipping, not blocking)"
                )
                print(f"    Processed {idx} / {total} sites")
                continue

            print(
                f"    → resolved lat={coords[0]:.6f}, lng={coords[1]:.6f}  "
                f"(in {attempts} attempt(s))"
            )

            if DRY_RUN:
                skipped += 1
                print(f"    Processed {idx} / {total} sites")
                continue

            site.lat, site.lng = coords
            geocoded += 1
            print(f"    Processed {idx} / {total} sites")

        if not DRY_RUN and geocoded > 0:
            await db.commit()

        _section("Summary")
        print(f"  candidates       : {len(candidates)}")
        print(f"  skipped_merged   : {skip_counts['skipped_merged']}")
        print(f"  skipped_archived : {skip_counts['skipped_archived']}")
        print(f"  skipped_deleted  : {skip_counts['skipped_deleted']}")
        if DRY_RUN:
            print(f"  would geocode    : {len(candidates) - len(failed)}")
            print(f"  would fail       : {len(failed)}")
        else:
            print(f"  geocoded         : {geocoded}")
            print(f"  failed           : {len(failed)}")
        if failed:
            print("  failed site_ids:")
            for sid in failed:
                print(f"    {sid}")

        if DRY_RUN:
            _banner("DRY RUN complete — no writes were performed")
            print("  Re-run with DRY_RUN=false to apply.")
        else:
            _banner("APPLY complete")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
