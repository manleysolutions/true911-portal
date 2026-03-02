"""Geocode E911 addresses to lat/lng via OpenStreetMap Nominatim."""

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# In-memory cache: normalized address → (lat, lng) or None
_cache: dict[str, tuple[float, float] | None] = {}
_rate_lock = asyncio.Lock()
_last_request_time: float = 0.0


def has_valid_coords(lat: float | None, lng: float | None) -> bool:
    """Return True if lat/lng are present and within valid ranges."""
    if lat is None or lng is None:
        return False
    if lat == 0 and lng == 0:
        return False
    return -90 <= lat <= 90 and -180 <= lng <= 180


def _normalize_address(
    street: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> str:
    """Build a normalized cache key from address parts."""
    return ", ".join(p.strip().lower() for p in (street, city, state, zip_code) if p)


async def geocode_address(
    street: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> tuple[float, float] | None:
    """Return (lat, lng) for the given address, or None on failure.

    Includes in-memory caching and 1-request-per-second rate limiting
    to comply with Nominatim usage policy.
    """
    global _last_request_time

    parts = [p for p in (street, city, state, zip_code) if p]
    if not parts:
        return None

    cache_key = _normalize_address(street, city, state, zip_code)

    # Check cache first
    if cache_key in _cache:
        result = _cache[cache_key]
        logger.debug("Geocode cache hit for %r → %s", cache_key, result)
        return result

    query = ", ".join(parts)

    async with _rate_lock:
        # Enforce 1 request/sec spacing for Nominatim
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "json", "limit": 1},
                    headers={"User-Agent": "True911-Portal/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()
                if data:
                    result = float(data[0]["lat"]), float(data[0]["lon"])
                    logger.info("Geocoded %r → %s", query, result)
                    _cache[cache_key] = result
                    return result
                else:
                    logger.warning("Geocode returned no results for %r", query)
                    _cache[cache_key] = None
                    return None
        except Exception:
            logger.exception("Geocode failed for %r", query)
            return None
        finally:
            _last_request_time = time.monotonic()
