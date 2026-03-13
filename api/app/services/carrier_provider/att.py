"""AT&T IoT carrier provider — stub.

AT&T IoT platform integration will be implemented
when AT&T developer credentials are provisioned.
"""

import logging

from .base import CarrierProvider, CarrierProviderError, CarrierSim

logger = logging.getLogger("true911.carrier_provider.att")


class ATTProvider(CarrierProvider):
    carrier_name = "att"

    @property
    def is_configured(self) -> bool:
        return False

    async def fetch_sims(self, max_results: int = 500) -> list[CarrierSim]:
        raise CarrierProviderError(
            "AT&T IoT platform integration is not yet configured. "
            "Use manual SIM entry for AT&T SIMs."
        )

    def config_summary(self) -> dict:
        return {
            "carrier": self.carrier_name,
            "configured": False,
            "note": "AT&T IoT platform integration pending — use manual SIM entry.",
        }
