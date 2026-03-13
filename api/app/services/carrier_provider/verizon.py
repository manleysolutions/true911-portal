"""Verizon ThingSpace carrier provider.

Delegates to the existing VerizonThingSpaceClient for actual API calls.
"""

import logging

from .base import CarrierProvider, CarrierProviderError, CarrierSim

logger = logging.getLogger("true911.carrier_provider.verizon")


class VerizonProvider(CarrierProvider):
    carrier_name = "verizon"

    def __init__(self):
        from app.services.verizon_thingspace import get_verizon_client
        self._client = get_verizon_client()

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    async def fetch_sims(self, max_results: int = 500) -> list[CarrierSim]:
        if not self.is_configured:
            raise CarrierProviderError(
                "Verizon ThingSpace is not configured. "
                "Set VERIZON_THINGSPACE_* environment variables."
            )

        from app.services.verizon_thingspace import (
            VerizonThingSpaceError,
            normalize_verizon_device,
        )

        try:
            raw_devices = await self._client.fetch_devices(display_count=max_results)
        except VerizonThingSpaceError as e:
            raise CarrierProviderError(f"Verizon API error: {e}") from e

        results = []
        for raw in raw_devices:
            norm = normalize_verizon_device(raw)
            iccid = norm.get("iccid")
            if not iccid:
                continue
            results.append(CarrierSim(
                iccid=iccid,
                carrier="verizon",
                msisdn=norm.get("msisdn"),
                status=_map_status(norm.get("activation_status")),
                external_id=norm.get("external_id"),
                imei=norm.get("imei"),
                raw=norm.get("raw_payload"),
            ))
        return results

    def config_summary(self) -> dict:
        base = super().config_summary()
        base.update(self._client.config_summary())
        return base


def _map_status(raw: str | None) -> str:
    if not raw:
        return "inventory"
    s = raw.lower()
    if s in ("active", "connected", "activated"):
        return "active"
    if s in ("suspended", "suspend"):
        return "suspended"
    if s in ("deactivated", "deactive", "terminated", "disconnected"):
        return "terminated"
    return "inventory"
