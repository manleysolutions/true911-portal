"""Health Normalization Layer — MVP (additive, flag-gated).

Phase 1 consumer: AI Health Summary only.  No other surface reads
this package in the MVP — see ``docs/HEALTH_NORMALIZER_MVP.md`` for
the rollout plan (Devices → Command Center → Map → Attention engine
in later phases).

Everything in this package is no-op when
``settings.FEATURE_HEALTH_NORMALIZER`` is not exactly ``"true"``.

Public surface is exported here once each module lands.  The
__init__ is structured so partial commits remain importable — each
commit re-exports only what exists.
"""

from app.services.health.normalizer import (
    compute_device_state,
    compute_site_state,
)
from app.services.health.signals import HealthSignals
from app.services.health.states import (
    CanonicalDeviceState,
    CanonicalSiteState,
)

# Commit 2: HealthSignals + compute_*_state landed; load_signals_for_tenant
# arrives in commit 3 and will be added then.

__all__ = [
    "CanonicalDeviceState",
    "CanonicalSiteState",
    "HealthSignals",
    "compute_device_state",
    "compute_site_state",
]
