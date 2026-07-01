"""Customer preview mode — RH urgent go-live login preview.

When enabled for a tenant, the customer OPERATIONAL axis (site / service /
equipment protection, and equipment health) is presented as Active/Protected
even before live carrier/vendor telemetry is connected.  This lets a customer be
given a login immediately, seeing a calm "Active/Green" portfolio, while the real
telemetry integrations are still being wired up.

Strict boundaries (why this does not violate the no-false-green contract):
  * PRESENTATION-ONLY.  Nothing here writes or mutates Device / Site / API
    state.  The override is computed at serialize time in the customer
    composition layer (``services.customer.portfolio`` + ``serialize``).
    Internal / admin / assurance views read the real state and are unaffected.
  * EVIDENCED, not fabricated.  A preview "Protected" carries an honest operator
    attestation (``PREVIEW_SIGNAL``) — the operator confirms the service is active /
    being onboarded — NOT a fabricated live-telemetry claim ("N devices
    reporting").  It is deliberately free of "API pending" / "telemetry pending"
    language: the customer sees a plain Active state.
  * E911 IS EXCLUDED.  Emergency-address verification is life-safety and is
    ALWAYS derived from real stored data (``Site.e911_*`` / ``e911_status``);
    preview never forces "Verified".  See docs/CUSTOMER_DATA_BOUNDARY.md §6.

Two-key gate, mirroring the customer API (``gate.py``):
``FEATURE_CUSTOMER_PREVIEW == "true"`` AND the caller's tenant in
``CUSTOMER_PREVIEW_TENANT_ALLOWLIST``.  Default OFF everywhere.

Rollback: flip ``FEATURE_CUSTOMER_PREVIEW=false`` or drop the tenant from
``CUSTOMER_PREVIEW_TENANT_ALLOWLIST`` — instant, no deploy, no data change.
"""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.services.customer.serialize import evidence_object, status_object

# Honest operator-attestation evidence for a preview-Protected status.  NOT a
# fabricated telemetry claim, and free of "pending" language (the customer must
# see a calm Active state — see the preview requirement).
PREVIEW_SIGNAL = "Service active — operator-confirmed"
PREVIEW_SOURCE = "operator"


def preview_enabled(tenant_id: Optional[str]) -> bool:
    """True when the preview override is active for this tenant."""
    return (
        settings.FEATURE_CUSTOMER_PREVIEW == "true"
        and tenant_id in settings.customer_preview_tenant_id_set
    )


def preview_protection(now) -> dict:
    """A customer StatusObject forced to Active/Protected for preview, carrying
    operator-attestation evidence so the no-false-green invariant in
    ``status_object`` keeps it Protected (does not recode to Unknown)."""
    as_of = now.isoformat()
    return status_object(
        "Protected",
        as_of=as_of,
        evidence=evidence_object(as_of, [PREVIEW_SIGNAL], source=PREVIEW_SOURCE),
    )
