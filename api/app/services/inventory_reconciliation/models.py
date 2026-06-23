"""Canonical reconciliation data model — vendor- and customer-agnostic."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Result(str, Enum):
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    MISSING_IN_TRUE911 = "MISSING_IN_TRUE911"
    MISSING_IN_VENDOR = "MISSING_IN_VENDOR"
    DUPLICATE = "DUPLICATE"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class VendorRecord:
    """One row from a vendor export, normalized by an adapter into canonical
    fields. ``raw`` is intentionally NOT a dump of the source row — adapters
    pass only non-sensitive extras to avoid leaking carrier account/CS data."""
    vendor: str
    radio_number: Optional[str] = None
    iccid: Optional[str] = None
    subscriber_name: Optional[str] = None
    customer_hint: Optional[str] = None
    site_hint: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class True911Item:
    """A True911 inventory device + its resolved linkage (site/customer/service/
    E911/telemetry). Built read-only by ``inventory.load_true911_inventory``."""
    device_id: str
    iccid: Optional[str] = None
    radio_number: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    customer_name: Optional[str] = None
    service_unit_id: Optional[str] = None
    e911_status: Optional[str] = None
    last_telemetry: Optional[str] = None


@dataclass
class ReconRow:
    customer: Optional[str]
    site: Optional[str]
    radio_number: Optional[str]
    iccid: Optional[str]
    subscriber_name: Optional[str]
    true911_device_id: Optional[str]
    true911_site: Optional[str]
    true911_customer: Optional[str]
    service_unit_id: Optional[str]
    e911_status: Optional[str]
    last_telemetry: Optional[str]
    confidence: float
    result: str
    notes: str = ""


# The required output column order (INVENTORY_RECONCILIATION.csv).
CSV_COLUMNS = [
    "Customer", "Site", "RadioNumber", "ICCID", "SubscriberName",
    "True911DeviceID", "True911Site", "True911Customer", "ServiceUnitID",
    "E911Status", "LastTelemetry", "Confidence", "Result", "Notes",
]
