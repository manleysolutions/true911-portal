"""True911 Assurance Engine — read-only, deterministic, explainable.

Composes operational health, commercial lifecycle, deployment lifecycle, and
E911/compliance into a single customer-facing label WITHOUT overwriting any
source-of-truth axis.  Pure engine in ``engine.py``; read-only DB assembly in
``loader.py``.  Flag-gated by ``FEATURE_ASSURANCE_ENGINE`` at the API layer.

See docs/ASSURANCE_ENGINE.md.
"""

from app.services.assurance.engine import (
    compute_device_assurance,
    compute_site_assurance,
)
from app.services.assurance.signals import (
    AssuranceLabel,
    AssuranceResult,
    AssuranceSignals,
    DeviceAssurance,
    DeviceSignal,
    LineSignal,
    ServiceUnitSignal,
    TestRecord,
)

__all__ = [
    "AssuranceLabel",
    "AssuranceResult",
    "AssuranceSignals",
    "DeviceAssurance",
    "DeviceSignal",
    "LineSignal",
    "ServiceUnitSignal",
    "TestRecord",
    "compute_device_assurance",
    "compute_site_assurance",
]
