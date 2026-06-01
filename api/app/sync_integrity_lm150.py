"""Pilot alias — runs the generic device-health sync scoped to the Integrity
Property Management / Belle Terre at Sunrise LM150 deployment.

This is a thin convenience wrapper.  It contains NO Integrity-specific logic —
it only sets the tenant/site scope and delegates to the generic
``app.sync_device_health``.  All hardware/vendor handling stays in the generic
core + adapters.

    # dry run (default)
    python -m app.sync_integrity_lm150

    # apply
    DRY_RUN=false python -m app.sync_integrity_lm150
"""

from __future__ import annotations

import os

# Pilot dataset scope (seed/test data only — see app.seed_integrity).
PILOT_TENANT = "integrity-pm"
PILOT_SITE = "IPM-BELLE-TERRE"


def main() -> None:
    # Default the scope to the pilot unless the operator overrides it.
    os.environ.setdefault("DEVICE_HEALTH_TENANT", PILOT_TENANT)
    os.environ.setdefault("DEVICE_HEALTH_SITE", PILOT_SITE)
    from app.sync_device_health import main as generic_main
    generic_main()


if __name__ == "__main__":
    main()
