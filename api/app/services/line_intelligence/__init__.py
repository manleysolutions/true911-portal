"""
Line Intelligence Engine — Phase 1 (Rule-Based)

Classifies analog line types (FACCP Contact ID, elevator voice, fax,
SCADA modem, unknown) from normalized observation inputs and assigns
optimal protocol profiles for ATA / CSAS configuration.

This module is additive and does not modify existing routes, models,
migrations, or startup behavior.
"""

from .constants import LineType, Confidence, DEFAULT_CONFIDENCE_THRESHOLD
from .models import (
    Observation,
    ClassificationResult,
    ProtocolProfile,
    SessionDecision,
)
from .detector import LineDetector
from .classifier import LineClassifier
from .session_manager import LineIntelligenceSession

__all__ = [
    "LineType",
    "Confidence",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "Observation",
    "ClassificationResult",
    "ProtocolProfile",
    "SessionDecision",
    "LineDetector",
    "LineClassifier",
    "LineIntelligenceSession",
]
