"""Identity Engine — pure deterministic identity resolution (Phase 0 / PR-1a).

First layer of the stack: Reality -> Identity Engine -> Truth Engine -> Assurance
Engine -> AI -> Automation.  Read-only, side-effect free, never guesses.
See ``docs/TRUTH_ENGINE.md``.
"""

from __future__ import annotations

from . import reason_codes
from .resolver import (
    CustomerFacts,
    DeviceFacts,
    ExternalMapFacts,
    HierarchyResolution,
    LinkKind,
    LinkStatus,
    MatchBasis,
    ProofLink,
    ResolutionStatus,
    ResolverInput,
    ServiceUnitFacts,
    SimFacts,
    SiteFacts,
    resolve_device,
)

__all__ = [
    "reason_codes",
    "resolve_device",
    "ResolverInput",
    "HierarchyResolution",
    "ProofLink",
    "ResolutionStatus",
    "LinkKind",
    "LinkStatus",
    "MatchBasis",
    "DeviceFacts",
    "SimFacts",
    "SiteFacts",
    "CustomerFacts",
    "ServiceUnitFacts",
    "ExternalMapFacts",
]
