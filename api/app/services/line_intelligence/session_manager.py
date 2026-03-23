"""
Line Intelligence Engine — Session manager.

Orchestrates the full pipeline:
    observe → detect → classify → assign profile → produce decision.

A session is a stateless pipeline invocation; it does not hold
long-lived state. Persistence of results is handled separately.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from .classifier import LineClassifier
from .constants import DEFAULT_CONFIDENCE_THRESHOLD, LineType
from .detector import LineDetector
from .models import (
    ClassificationResult,
    Observation,
    ProtocolProfile,
    SessionDecision,
)
from .persistence import PersistenceBackend
from .protocol_profiles import get_profile_for_line_type
from .telemetry import TelemetryCollector


class LineIntelligenceSession:
    """
    Entry-point for the Line Intelligence Engine.

    Usage::

        session = LineIntelligenceSession()
        decision = session.process(observation)

    The session can optionally be configured with:
    - a custom confidence threshold
    - a persistence backend (to store decisions)
    - a telemetry collector (to emit structured metrics)
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        persistence: Optional[PersistenceBackend] = None,
        telemetry: Optional[TelemetryCollector] = None,
    ) -> None:
        self._detector = LineDetector()
        self._classifier = LineClassifier(confidence_threshold=confidence_threshold)
        self._persistence = persistence
        self._telemetry = telemetry

    def process(self, observation: Observation) -> SessionDecision:
        """
        Run the full detection → classification → profile pipeline.

        Returns a SessionDecision containing classification, assigned
        profile, and metadata.
        """
        # 1. Detect
        signals = self._detector.detect(observation)

        # 2. Classify
        classification = self._classifier.classify(signals)

        # 3. Assign profile
        profile = get_profile_for_line_type(classification.line_type)

        # 4. Build decision
        decision = SessionDecision(
            decision_id=str(uuid.uuid4()),
            line_id=observation.line_id,
            tenant_id=observation.tenant_id,
            observation_id=observation.observation_id,
            timestamp=datetime.now(timezone.utc),
            classification=classification,
            assigned_profile=profile,
            pipeline_version="1.0.0",
        )

        # 5. Persist (if backend configured)
        if self._persistence is not None:
            self._persistence.save_decision(decision)

        # 6. Emit telemetry (if collector configured)
        if self._telemetry is not None:
            self._telemetry.record_decision(decision)

        return decision

    def process_with_override(
        self,
        observation: Observation,
        override_line_type: LineType,
        override_reason: str,
    ) -> SessionDecision:
        """
        Run detection/classification but override the final assignment.

        This preserves the analytical output for auditing while applying
        the operator's manual determination.
        """
        # Run normal pipeline for audit trail
        signals = self._detector.detect(observation)
        classification = self._classifier.classify(signals)

        # Override profile
        profile = get_profile_for_line_type(override_line_type)

        decision = SessionDecision(
            decision_id=str(uuid.uuid4()),
            line_id=observation.line_id,
            tenant_id=observation.tenant_id,
            observation_id=observation.observation_id,
            timestamp=datetime.now(timezone.utc),
            classification=classification,
            assigned_profile=profile,
            manual_override=True,
            override_reason=override_reason,
            pipeline_version="1.0.0",
        )

        if self._persistence is not None:
            self._persistence.save_decision(decision)
        if self._telemetry is not None:
            self._telemetry.record_decision(decision)

        return decision
