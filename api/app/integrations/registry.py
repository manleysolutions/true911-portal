"""Provider client factory — maps provider slugs to client classes.

Note: VOLA uses its own service layer (app.services.vola_service) instead of
the generic BaseProviderClient pattern, so it is not registered here.
"""

from __future__ import annotations

from app.integrations.base import BaseProviderClient
from app.integrations.telnyx import TelnyxClient
from app.integrations.tmobile import TMobileClient

_REGISTRY: dict[str, type[BaseProviderClient]] = {
    "telnyx": TelnyxClient,
    "tmobile": TMobileClient,
}


def get_client(
    provider_type: str,
    api_key: str,
    api_secret: str | None = None,
) -> BaseProviderClient:
    """Instantiate the correct provider client by slug.

    Raises ValueError if the provider type is not registered.
    """
    cls = _REGISTRY.get(provider_type)
    if cls is None:
        raise ValueError(f"Unknown provider type: {provider_type!r}. Available: {list(_REGISTRY)}")
    return cls(api_key=api_key, api_secret=api_secret)
