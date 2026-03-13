"""T-Mobile IoT carrier provider — stub.

T-Mobile IoT SIM management API integration will be implemented
when T-Mobile developer credentials are provisioned.
"""

import logging

from .base import CarrierProvider, CarrierProviderError, CarrierSim

logger = logging.getLogger("true911.carrier_provider.tmobile")


class TMobileProvider(CarrierProvider):
    carrier_name = "tmobile"

    @property
    def is_configured(self) -> bool:
        return False

    async def fetch_sims(self, max_results: int = 500) -> list[CarrierSim]:
        raise CarrierProviderError(
            "T-Mobile IoT API integration is not yet configured. "
            "Use manual SIM entry for T-Mobile SIMs."
        )

    def config_summary(self) -> dict:
        return {
            "carrier": self.carrier_name,
            "configured": False,
            "note": "T-Mobile IoT API integration pending — use manual SIM entry.",
        }
