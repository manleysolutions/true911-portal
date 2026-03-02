"""Geocode E911 addresses to lat/lng via OpenStreetMap Nominatim."""

import httpx


async def geocode_address(
    street: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> tuple[float, float] | None:
    """Return (lat, lng) for the given address, or None on failure."""
    parts = [p for p in (street, city, state, zip_code) if p]
    if not parts:
        return None

    query = ", ".join(parts)
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
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None
