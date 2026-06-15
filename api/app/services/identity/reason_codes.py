"""Identity Engine reason codes (``IDENTITY.*``).

Machine-stable codes that explain an identity resolution.  Mirrors the pattern of
``services/assurance/reason_codes.py``.  The customer-facing layer (a later PR)
maps these to plain language; the resolver itself only emits codes.

This catalog is the authority for the codes the pure ``IdentityResolver`` may emit
(see ``docs/TRUTH_ENGINE.md`` §9).  Adding a code here is a deliberate act.
"""

from __future__ import annotations

from dataclasses import dataclass

# Severity vocabulary (ordered, informally): info < warning < critical < gate.
INFO = "info"
WARNING = "warning"
CRITICAL = "critical"


@dataclass(frozen=True)
class ReasonCode:
    code: str
    severity: str
    description: str
    steward_action: str


def _c(short: str, severity: str, description: str, steward_action: str) -> ReasonCode:
    return ReasonCode(f"IDENTITY.{short}", severity, description, steward_action)


# ── Resolved (positive) ──────────────────────────────────────────────
RESOLVED_ICCID = _c(
    "RESOLVED_ICCID", INFO,
    "Device matched a SIM by globally-unique ICCID.",
    "None.",
)
RESOLVED_IMEI = _c(
    "RESOLVED_IMEI", INFO,
    "Device matched a SIM by IMEI.",
    "None.",
)
RESOLVED_MSISDN = _c(
    "RESOLVED_MSISDN", INFO,
    "Device matched a single SIM by MSISDN.",
    "Consider confirming with a stronger key (ICCID).",
)
RESOLVED_EXTERNAL_MAP = _c(
    "RESOLVED_EXTERNAL_MAP", INFO,
    "Link resolved via a confirmed external_record_map entry.",
    "None.",
)

# ── Gaps (do not block RESOLVED) ─────────────────────────────────────
MISSING_E911 = _c(
    "MISSING_E911", WARNING,
    "Site has no present dispatchable E911 address.",
    "Complete and verify the E911 address for this site.",
)
MISSING_SERVICE_UNIT = _c(
    "MISSING_SERVICE_UNIT", INFO,
    "Device is not linked to exactly one service unit.",
    "Attach the device to its service unit (elevator/communicator).",
)
MISSING_MSISDN = _c(
    "MISSING_MSISDN", INFO,
    "No MSISDN found on the matched SIM or device.",
    "Populate the MSISDN from the carrier record.",
)
UNKNOWN_CARRIER = _c(
    "UNKNOWN_CARRIER", INFO,
    "No carrier on the device or matched SIM.",
    "Set the carrier from the provisioning/carrier record.",
)
UNMATCHED_ICCID = _c(
    "UNMATCHED_ICCID", WARNING,
    "Device declares an ICCID with no matching SIM record.",
    "Import/reconcile the SIM, or correct the device ICCID.",
)

# ── Missing required links (contribute to ORPHAN) ────────────────────
MISSING_SITE = _c(
    "MISSING_SITE", CRITICAL,
    "Device is not linked to a known site.",
    "Assign the device to its site.",
)
MISSING_CUSTOMER = _c(
    "MISSING_CUSTOMER", CRITICAL,
    "Site is not linked to a customer.",
    "Backfill sites.customer_id for this site.",
)
MISSING_SIM = _c(
    "MISSING_SIM", CRITICAL,
    "Cellular device has no matching SIM.",
    "Match/import the SIM by ICCID or MSISDN.",
)

# ── Ambiguity (untrustworthy identity) ───────────────────────────────
AMBIGUOUS_MSISDN = _c(
    "AMBIGUOUS_MSISDN", CRITICAL,
    "MSISDN matches more than one SIM; cannot resolve safely.",
    "Disambiguate by ICCID; deactivate stale duplicate SIMs.",
)
AMBIGUOUS_ICCID_SITE_MISMATCH = _c(
    "AMBIGUOUS_ICCID_SITE_MISMATCH", CRITICAL,
    "ICCID-matched SIM is assigned to a different site than the device.",
    "Reconcile the SIM-site vs device-site assignment.",
)

# ── Decision-level orphan reasons ────────────────────────────────────
ORPHAN_NO_SITE = _c(
    "ORPHAN_NO_SITE", CRITICAL,
    "Device cannot be placed: no resolvable site.",
    "Assign the device to its site.",
)
ORPHAN_NO_CUSTOMER = _c(
    "ORPHAN_NO_CUSTOMER", CRITICAL,
    "Device cannot be placed: site has no customer.",
    "Backfill the site's customer.",
)
ORPHAN_CELLULAR_NO_SIM = _c(
    "ORPHAN_CELLULAR_NO_SIM", CRITICAL,
    "Cellular device cannot be placed: no SIM identity.",
    "Match/import the SIM.",
)

# ── Heuristic (recommend only; never auto-resolve) ───────────────────
HEURISTIC_SUGGESTED = _c(
    "HEURISTIC_SUGGESTED", INFO,
    "A heuristic suggests a link; not auto-applied — needs steward approval.",
    "Review and confirm the suggested link.",
)


ALL: dict[str, ReasonCode] = {
    rc.code: rc
    for rc in (
        RESOLVED_ICCID, RESOLVED_IMEI, RESOLVED_MSISDN, RESOLVED_EXTERNAL_MAP,
        MISSING_E911, MISSING_SERVICE_UNIT, MISSING_MSISDN, UNKNOWN_CARRIER,
        UNMATCHED_ICCID, MISSING_SITE, MISSING_CUSTOMER, MISSING_SIM,
        AMBIGUOUS_MSISDN, AMBIGUOUS_ICCID_SITE_MISMATCH,
        ORPHAN_NO_SITE, ORPHAN_NO_CUSTOMER, ORPHAN_CELLULAR_NO_SIM,
        HEURISTIC_SUGGESTED,
    )
}
