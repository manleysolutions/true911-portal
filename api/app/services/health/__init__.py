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

# Commit 1: scaffolding only.  states.py + thresholds.py are landed;
# signals.py / normalizer.py / signals_loader.py arrive in commits
# 2-3 and will be added to __all__ then.
from app.services.health.states import (
    CanonicalDeviceState,
    CanonicalSiteState,
)

__all__ = [
    "CanonicalDeviceState",
    "CanonicalSiteState",
]
