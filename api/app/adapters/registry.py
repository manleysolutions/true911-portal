"""Adapter registry — selects the right adapter for a device."""

from __future__ import annotations

from app.adapters.base import DeviceAdapter
from app.adapters.generic_adapter import GenericAdapter
from app.adapters.inseego_adapter import InsegoAdapter
from app.adapters.pr12_adapter import PR12Adapter

_PR12_IDENTIFIERS: frozenset[str] = frozenset({
    "pr12", "csa", "pr12-csa",
})

_INSEEGO_IDENTIFIERS: frozenset[str] = frozenset({
    "inseego", "fw3100", "inseego-fw3100",
})

_generic = GenericAdapter()
_pr12 = PR12Adapter()
_inseego = InsegoAdapter()


def get_adapter(device_type: str | None, model: str | None) -> DeviceAdapter:
    """Return the adapter for a device based on its type/model fields.

    Selection order:
    1. If ``model`` or ``device_type`` matches a PR12 identifier → PR12Adapter
    2. If ``model`` or ``device_type`` matches an Inseego identifier → InsegoAdapter
    3. Otherwise → GenericAdapter

    Also checks ``hardware_model_id`` if passed as ``model`` (e.g. "flyingvoice-pr12"
    or "inseego-fw3100" from the hardware_models table).
    """
    for value in (model, device_type):
        if not value:
            continue
        lowered = value.lower().strip()
        if lowered in _PR12_IDENTIFIERS:
            return _pr12
        if lowered in _INSEEGO_IDENTIFIERS:
            return _inseego
    return _generic
