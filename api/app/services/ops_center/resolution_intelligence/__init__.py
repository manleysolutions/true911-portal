"""Ops Center Phase 1.6 — Resolution Intelligence (foundations).

A structured, DETERMINISTIC library of operational knowledge used by Manley
Solutions technicians, NOC, carrier-support, installers, and customer-support
staff for life-safety communications:

  * known issues          (symptoms / probable causes, per vendor/carrier/hardware)
  * diagnostic workflows   (ordered troubleshooting steps)
  * resolution workflows   (actual fix procedures)
  * resolution outcomes    (what actually happened)

and a **rules-based** recommendation engine that maps an inbound issue to
matching known issues + the right diagnostic/resolution workflow + an
escalation queue, with an EXPLAINABLE confidence score.

Constitutional posture (``CONSTITUTION.md``):
  * §4.4 deterministic-before-AI — NO LLM; pure rules + a static catalog.
  * §5 explainable — every recommendation carries reason codes.
  * §4.1/§4.2 additive + flag-gated — new tables only; nothing reads this at
    runtime yet; the whole module stays behind ``FEATURE_OPS_CENTER`` (off).
  * §7.1 — the ``confidence`` score is INTERNAL (tech/NOC) only; it is never a
    customer-facing readiness score and no customer surface reads it.
"""

from app.services.ops_center.resolution_intelligence.constants import (
    EscalationQueue,
    OutcomeType,
)
from app.services.ops_center.resolution_intelligence.known_issues import (
    all_known_issues,
    find_matching_issues,
    get_known_issue,
)
from app.services.ops_center.resolution_intelligence.recommendations import recommend

__all__ = [
    "EscalationQueue",
    "OutcomeType",
    "recommend",
    "find_matching_issues",
    "all_known_issues",
    "get_known_issue",
]
