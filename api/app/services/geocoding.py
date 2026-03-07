"""Geocode E911 addresses to lat/lng via OpenStreetMap Nominatim.

Supports international addresses with multiple fallback strategies:
1. Structured query (street, city, state, country)
2. Free-form full address
3. City + state/province + country only
4. City + country only
"""

import asyncio
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

# In-memory cache: normalized address → (lat, lng) or None
_cache: dict[str, tuple[float, float] | None] = {}
_rate_lock = asyncio.Lock()
_last_request_time: float = 0.0

# US state abbreviations → full names (for better Nominatim matching)
_US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

# Canadian province abbreviations → full names
_CA_PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia", "NT": "Northwest Territories", "NU": "Nunavut",
    "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}

# Canadian city → correct province (for common mismatches in data)
_CA_CITY_PROVINCE: dict[str, str] = {
    "edmonton": "Alberta", "calgary": "Alberta", "red deer": "Alberta",
    "lethbridge": "Alberta", "medicine hat": "Alberta", "grande prairie": "Alberta",
    "vancouver": "British Columbia", "victoria": "British Columbia",
    "surrey": "British Columbia", "burnaby": "British Columbia",
    "kelowna": "British Columbia", "kamloops": "British Columbia",
    "winnipeg": "Manitoba", "brandon": "Manitoba",
    "toronto": "Ontario", "ottawa": "Ontario", "mississauga": "Ontario",
    "hamilton": "Ontario", "london": "Ontario", "kitchener": "Ontario",
    "windsor": "Ontario", "markham": "Ontario", "vaughan": "Ontario",
    "brampton": "Ontario", "barrie": "Ontario",
    "montreal": "Quebec", "quebec city": "Quebec", "laval": "Quebec",
    "gatineau": "Quebec", "sherbrooke": "Quebec",
    "halifax": "Nova Scotia", "sydney": "Nova Scotia",
    "saint john": "New Brunswick", "moncton": "New Brunswick",
    "fredericton": "New Brunswick",
    "regina": "Saskatchewan", "saskatoon": "Saskatchewan",
    "st. john's": "Newfoundland and Labrador",
    "charlottetown": "Prince Edward Island",
    "yellowknife": "Northwest Territories",
    "whitehorse": "Yukon", "iqaluit": "Nunavut",
}

# Pattern to detect Zoho-style IDs that shouldn't be in address queries
_ZOHO_ID_RE = re.compile(r"zcrm_\d+", re.IGNORECASE)


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


def _clean_part(value: str | None) -> str:
    """Strip a part and remove Zoho IDs or other noise."""
    if not value:
        return ""
    cleaned = value.strip()
    # Remove Zoho CRM IDs (zcrm_337391000041952187)
    cleaned = _ZOHO_ID_RE.sub("", cleaned).strip()
    # Remove leftover commas/spaces
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(", ")
    return cleaned


def _detect_country(state: str | None, city: str | None, zip_code: str | None) -> str | None:
    """Detect country from state/province or other clues."""
    s = (state or "").strip().upper()
    # Check if it's a US state
    if s in _US_STATES or s.title() in _US_STATES.values():
        return "United States"
    # Check if it's a Canadian province
    if s in _CA_PROVINCES or s.title() in _CA_PROVINCES.values():
        return "Canada"
    # Check if state field contains "Canada" or "US"/"USA"
    state_lower = (state or "").strip().lower()
    if "canada" in state_lower:
        return "Canada"
    if state_lower in ("us", "usa", "united states"):
        return "United States"
    # Canadian postal codes: letter-digit-letter digit-letter-digit
    if zip_code and re.match(r"^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$", zip_code.strip()):
        return "Canada"
    # Check city name for known Canadian cities
    if city and city.strip().lower() in _CA_CITY_PROVINCE:
        return "Canada"
    return None


def _fix_province(city: str | None, state: str | None) -> str | None:
    """Auto-correct mismatched city/province (e.g. Edmonton + Ontario → Alberta)."""
    if not city:
        return state
    city_lower = city.strip().lower()
    correct_province = _CA_CITY_PROVINCE.get(city_lower)
    if not correct_province:
        return state
    # If state doesn't match the correct province, fix it
    s = (state or "").strip()
    s_upper = s.upper()
    current_full = _CA_PROVINCES.get(s_upper, s.title())
    if current_full != correct_province:
        logger.info("Auto-corrected province for %s: %r → %r", city, state, correct_province)
        return correct_province
    return state


def _build_query_strategies(
    street: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> list[dict]:
    """Build a list of Nominatim query strategies, best to worst."""
    street_clean = _clean_part(street)
    city_clean = _clean_part(city)
    state_clean = _clean_part(state)
    zip_clean = _clean_part(zip_code)

    country = _detect_country(state_clean, city_clean, zip_clean)

    # Auto-correct province for Canadian cities
    if country == "Canada":
        state_clean = _fix_province(city_clean, state_clean) or state_clean
        # Strip "Canada" from state if it's appended there
        state_clean = re.sub(r"\s*canada\s*$", "", state_clean, flags=re.IGNORECASE).strip()

    strategies = []

    # Strategy 1: Structured query with all parts
    if street_clean and city_clean:
        params = {"street": street_clean, "city": city_clean, "format": "json", "limit": 1}
        if state_clean:
            params["state"] = state_clean
        if zip_clean:
            params["postalcode"] = zip_clean
        if country:
            params["country"] = country
        strategies.append(params)

    # Strategy 2: Free-form query with all clean parts
    free_parts = [p for p in (street_clean, city_clean, state_clean, zip_clean) if p]
    if country and country not in " ".join(free_parts).lower():
        free_parts.append(country)
    if free_parts:
        strategies.append({"q": ", ".join(free_parts), "format": "json", "limit": 1})

    # Strategy 3: City + state + country (drop street — useful for store names as streets)
    if city_clean and (state_clean or country):
        city_parts = [city_clean]
        if state_clean:
            city_parts.append(state_clean)
        if country:
            city_parts.append(country)
        strategies.append({"q": ", ".join(city_parts), "format": "json", "limit": 1})

    # Strategy 4: City + country only
    if city_clean and country:
        strategies.append({"q": f"{city_clean}, {country}", "format": "json", "limit": 1})

    # Strategy 5: Just city (last resort)
    if city_clean and not strategies:
        strategies.append({"q": city_clean, "format": "json", "limit": 1})

    return strategies


async def _nominatim_query(client: httpx.AsyncClient, params: dict) -> tuple[float, float] | None:
    """Execute a single Nominatim query and return (lat, lng) or None."""
    global _last_request_time

    # Enforce 1 request/sec spacing
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < 1.0:
        await asyncio.sleep(1.0 - elapsed)

    resp = await client.get(
        "https://nominatim.openstreetmap.org/search",
        params=params,
        headers={"User-Agent": "True911-Portal/1.0"},
    )
    _last_request_time = time.monotonic()
    resp.raise_for_status()
    data = resp.json()
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])
    return None


async def geocode_address(
    street: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> tuple[float, float] | None:
    """Return (lat, lng) for the given address, or None on failure.

    Tries multiple query strategies with fallbacks for international
    and incomplete addresses. Includes in-memory caching and
    1-request-per-second rate limiting for Nominatim compliance.
    """
    parts = [p for p in (street, city, state, zip_code) if p]
    if not parts:
        return None

    cache_key = _normalize_address(street, city, state, zip_code)

    # Check cache first
    if cache_key in _cache:
        result = _cache[cache_key]
        logger.debug("Geocode cache hit for %r → %s", cache_key, result)
        return result

    strategies = _build_query_strategies(street, city, state, zip_code)
    if not strategies:
        return None

    async with _rate_lock:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for i, params in enumerate(strategies):
                    query_desc = params.get("q") or f"structured:{params.get('street','')},{params.get('city','')}"
                    try:
                        result = await _nominatim_query(client, params)
                        if result:
                            logger.info("Geocoded %r (strategy %d) → %s", query_desc, i + 1, result)
                            _cache[cache_key] = result
                            return result
                        logger.debug("Strategy %d returned no results for %r", i + 1, query_desc)
                    except Exception:
                        logger.warning("Strategy %d failed for %r", i + 1, query_desc, exc_info=True)
                        continue

                # All strategies exhausted
                logger.warning("All geocode strategies failed for %r", cache_key)
                _cache[cache_key] = None
                return None
        except Exception:
            logger.exception("Geocode failed for %r", cache_key)
            return None
