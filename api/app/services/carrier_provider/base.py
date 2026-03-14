"""Abstract base for carrier SIM inventory providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CarrierSim:
    """Normalized SIM record from a carrier API."""
    iccid: str
    carrier: str
    msisdn: str | None = None
    imsi: str | None = None
    imei: str | None = None
    status: str = "inventory"
    activation_status: str | None = None
    network_status: str | None = None
    plan: str | None = None
    apn: str | None = None
    external_id: str | None = None
    raw: dict | None = None
    # User-defined label from carrier portal (e.g., site name, customer name)
    carrier_label: str | None = None
    # Carrier-inferred location (NOT E911-valid)
    inferred_lat: float | None = None
    inferred_lng: float | None = None
    inferred_location_source: str | None = None


@dataclass
class CarrierSyncResult:
    """Summary of a carrier sync operation."""
    carrier: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged + self.skipped + self.failed


class CarrierProvider(ABC):
    """Base class for carrier SIM inventory providers."""

    carrier_name: str = ""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the provider has valid credentials configured."""
        ...

    @abstractmethod
    async def fetch_sims(self, max_results: int = 500) -> list[CarrierSim]:
        """Fetch SIM inventory from the carrier API."""
        ...

    def config_summary(self) -> dict:
        """Return a safe (no secrets) summary of provider configuration."""
        return {
            "carrier": self.carrier_name,
            "configured": self.is_configured,
        }


class CarrierProviderError(Exception):
    """Raised when a carrier API call fails."""
    pass
