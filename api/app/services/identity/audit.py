"""Identity Audit aggregation (Phase 0 / PR-1b1).

Pure: given an ``IdentityDataset`` (built by the read-only loader), run the pure
resolver over every device and aggregate the verdicts into a report.  No I/O, no
clock (``generated_at`` is passed in), no writes.

The report answers "how many records resolve into the canonical hierarchy?" and
exposes the component seeds the Truth Score (a later PR) will compose.  Internal
verdicts only (Resolved / Ambiguous / Orphan); the internal->external vocabulary
(Verified / Supported / Suggested / Unknown) is a presentation concern for the
endpoint PR (DECISIONS D-014).
"""

from __future__ import annotations

from collections import Counter

from . import reason_codes as rc
from .loader import IdentityDataset
from .resolver import ResolutionStatus, resolve_device


def _round(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def run_identity_audit(
    dataset: IdentityDataset,
    *,
    generated_at: str,
    tenant_id: str | None = None,
    sample_limit: int = 50,
) -> dict:
    """Aggregate per-device resolutions + data-quality metrics. Pure."""
    resolutions = [resolve_device(dataset.resolver_input(d)) for d in dataset.devices]
    total = len(resolutions)

    status_counts = Counter(r.status.value for r in resolutions)
    by_reason: Counter[str] = Counter()
    by_match_basis: Counter[str] = Counter()
    for r in resolutions:
        by_reason.update(r.reason_codes)
        by_match_basis.update(r.match_basis)

    def _devices_with(code: str) -> int:
        return sum(1 for r in resolutions if code in r.reason_codes)

    resolved = status_counts.get(ResolutionStatus.RESOLVED.value, 0)
    ambiguous = status_counts.get(ResolutionStatus.AMBIGUOUS.value, 0)
    orphan = status_counts.get(ResolutionStatus.ORPHAN.value, 0)

    # ── SIM-level data quality ──
    unassigned_sims = sum(1 for s in dataset.sims if not s.device_id)
    iccid_counts = Counter(s.iccid for s in dataset.sims if s.iccid)
    msisdn_counts = Counter(s.msisdn for s in dataset.sims if s.msisdn)
    duplicate_iccid = sum(1 for n in iccid_counts.values() if n > 1)
    duplicate_msisdn = sum(1 for n in msisdn_counts.values() if n > 1)

    # ── E911 site-level (Option 3 — three distinct dimensions, not collapsed) ──
    sites_total = len(dataset.site_e911)
    address_present = sum(1 for s in dataset.site_e911 if s.e911_address_present)
    verified = sum(1 for s in dataset.site_e911 if s.e911_verified)
    confirmation_required = sum(1 for s in dataset.site_e911 if s.e911_confirmation_required)
    missing_e911_address = sites_total - address_present
    # "Has an address but it is not verified" — the meaningful needs-verification bucket.
    unverified_e911 = sum(
        1 for s in dataset.site_e911 if s.e911_address_present and not s.e911_verified
    )

    gaps = {
        # device-level (from resolver reason codes)
        "missing_site": _devices_with(rc.ORPHAN_NO_SITE.code),
        "missing_customer": _devices_with(rc.ORPHAN_NO_CUSTOMER.code),
        "missing_sim_cellular": _devices_with(rc.ORPHAN_CELLULAR_NO_SIM.code),
        "missing_msisdn": _devices_with(rc.MISSING_MSISDN.code),
        "unmatched_iccid": _devices_with(rc.UNMATCHED_ICCID.code),
        "unknown_carrier": _devices_with(rc.UNKNOWN_CARRIER.code),
        "missing_service_unit": _devices_with(rc.MISSING_SERVICE_UNIT.code),
        "orphan_devices": orphan,
        # SIM-level
        "unassigned_sims": unassigned_sims,
        "duplicate_iccid": duplicate_iccid,
        "duplicate_msisdn": duplicate_msisdn,
        # E911 site-level (three distinct, per DECISIONS Option 3)
        "missing_e911_address": missing_e911_address,
        "unverified_e911": unverified_e911,
        "e911_confirmation_required": confirmation_required,
    }

    # ── Truth Score component seeds (composite built in a later PR) ──
    hierarchy_complete = sum(
        1 for r in resolutions if r.site_id is not None and r.customer_id is not None
    )
    truth_components = {
        "identity": _round(resolved, total),
        "hierarchy": _round(hierarchy_complete, total),
        "e911": _round(verified, sites_total),
    }

    def _sample(status: ResolutionStatus) -> list[dict]:
        out = []
        for r in resolutions:
            if r.status == status:
                out.append({
                    "device_id": r.device_id,
                    "status": r.status.value,
                    "reason_codes": list(r.reason_codes),
                    "match_basis": list(r.match_basis),
                    "confidence": r.confidence,
                })
                if len(out) >= sample_limit:
                    break
        return out

    return {
        "feature": "identity_audit",
        "generated_at": generated_at,
        "scope": {"tenant_id": tenant_id or "ALL"},
        "totals": {
            "devices_total": total,
            "resolved": resolved,
            "ambiguous": ambiguous,
            "orphan": orphan,
            "resolution_rate": _round(resolved, total),
        },
        "by_reason": dict(by_reason),
        "by_match_basis": dict(by_match_basis),
        "gaps": gaps,
        "e911": {
            "sites_total": sites_total,
            "address_present": address_present,
            "verified": verified,
            "confirmation_required": confirmation_required,
        },
        "truth_components": truth_components,
        "samples": {
            "orphan": _sample(ResolutionStatus.ORPHAN),
            "ambiguous": _sample(ResolutionStatus.AMBIGUOUS),
        },
        "sample_limit": sample_limit,
        "read_only": True,
    }
