"""Adapter registry — selects the right adapter for a device."""

from __future__ import annotations

from app.adapters.base import DeviceAdapter
from app.adapters.generic_adapter import GenericAdapter
from app.adapters.pr12_adapter import PR12Adapter

_PR12_IDENTIFIERS: frozenset[str] = frozenset({
    "pr12", "csa", "pr12-csa",
})

_generic = GenericAdapter()
_pr12 = PR12Adapter()


def get_adapter(device_type: str | None, model: str | None) -> DeviceAdapter:
    """Return the adapter for a device based on its type/model fields.

    Selection order:
    1. If ``model`` (lowered) matches a known PR12 identifier → PR12Adapter
    2. If ``device_type`` (lowered) matches → PR12Adapter
    3. Otherwise → GenericAdapter
    """
    for value in (model, device_type):
        if value and value.lower().strip() in _PR12_IDENTIFIERS:
            return _pr12
    return _generic
