"""Vendor adapter protocol + registry (vendor-agnostic)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.inventory_reconciliation.models import VendorRecord


@runtime_checkable
class VendorAdapter(Protocol):
    vendor: str

    def parse(self, path: str) -> list[VendorRecord]:
        """Parse a vendor export file into canonical VendorRecords."""
        ...


_REGISTRY: dict = {}


def register(name: str, adapter) -> None:
    _REGISTRY[name] = adapter


def get_adapter(name: str):
    return _REGISTRY.get(name)


def available() -> list[str]:
    return sorted(_REGISTRY)
