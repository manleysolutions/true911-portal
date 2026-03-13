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

            raw_payload = norm.get("raw_payload") or {}
            activation = norm.get("activation_status")

            results.append(CarrierSim(
                iccid=iccid,
                carrier="verizon",
                msisdn=norm.get("msisdn"),
                imei=norm.get("imei"),
                status=_map_status(activation),
                activation_status=activation,
                network_status=norm.get("line_status") or norm.get("sim_status"),
                plan=raw_payload.get("servicePlan"),
                external_id=norm.get("external_id"),
                raw=raw_payload,
                # Verizon may include location data in extended device info
                inferred_lat=_safe_float(raw_payload.get("latitude")),
                inferred_lng=_safe_float(raw_payload.get("longitude")),
                inferred_location_source="verizon_thingspace" if raw_payload.get("latitude") else None,
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
        return "deactivated"
    return "inventory"


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f != 0.0 else None
    except (ValueError, TypeError):
        return None
