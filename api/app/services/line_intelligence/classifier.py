"""
Line Intelligence Engine — Classifier.

Consumes DetectionSignals, applies rule-based scoring, and produces
a ClassificationResult with line type, confidence, evidence, and
recommended profile.

v1: deterministic rules only, no ML.
"""

from __future__ import annotations

from .constants import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
    Confidence,
    LineType,
)
from .detector import DetectionSignals
from .models import ClassificationResult, EvidenceItem
from .protocol_profiles import get_profile_for_line_type


class LineClassifier:
    """
    Rule-based line type classifier.

    Scoring approach:
    - Each signal contributes weighted evidence toward candidate types.
    - The highest-scoring candidate becomes the classification.
    - If no candidate exceeds the confidence threshold, ``unknown`` is
      returned with a safe fallback profile.
    """

    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        self._threshold = confidence_threshold

    def classify(self, signals: DetectionSignals) -> ClassificationResult:
        """Classify a line based on extracted detection signals."""
        candidates: dict[LineType, _CandidateScore] = {
            lt: _CandidateScore(line_type=lt) for lt in LineType if lt != LineType.UNKNOWN
        }

        # --- Score each candidate ----------------------------------------
        self._score_contact_id(signals, candidates[LineType.FACCP_CONTACT_ID])
        self._score_elevator_voice(signals, candidates[LineType.ELEVATOR_VOICE])
        self._score_fax(signals, candidates[LineType.FAX])
        self._score_scada_modem(signals, candidates[LineType.SCADA_MODEM])

        # --- Pick winner -------------------------------------------------
        best = max(candidates.values(), key=lambda c: c.score)

        if best.score < self._threshold:
            return self._fallback_result(signals, best)

        confidence_tier = self._tier(best.score)
        profile = get_profile_for_line_type(best.line_type)

        return ClassificationResult(
            line_type=best.line_type,
            confidence_score=round(best.score, 4),
            confidence_tier=confidence_tier,
            evidence=best.evidence,
            recommended_profile_id=profile.profile_id,
            is_actionable=True,
            fallback_applied=False,
            notes=best.notes,
        )

    # ------------------------------------------------------------------
    # Scoring rules
    # ------------------------------------------------------------------

    def _score_contact_id(
        self, sig: DetectionSignals, c: _CandidateScore
    ) -> None:
        if sig.dtmf_pattern_looks_contact_id:
            c.add("dtmf_contact_id_pattern", "DTMF sequence matches Contact ID heuristic", 0.55)
        if sig.dtmf_event_count >= 10:
            c.add("dtmf_high_count", f"{sig.dtmf_event_count} DTMF events", 0.20)
        elif sig.dtmf_event_count >= 4:
            c.add("dtmf_moderate_count", f"{sig.dtmf_event_count} DTMF events", 0.10)
        if not sig.voice_activity_detected and not sig.fax_tone_detected:
            c.add("no_competing_signals", "No voice or fax detected", 0.10)

    def _score_elevator_voice(
        self, sig: DetectionSignals, c: _CandidateScore
    ) -> None:
        if sig.voice_activity_detected:
            c.add("voice_activity", f"Voice energy {sig.voice_energy:.2f}", 0.45)
        if not sig.dtmf_pattern_looks_contact_id and sig.dtmf_event_count <= 2:
            c.add("low_dtmf", "No significant DTMF pattern", 0.10)
        if not sig.fax_tone_detected and not sig.modem_carrier_detected:
            c.add("no_data_signals", "No fax or modem tones", 0.15)
        if not sig.mostly_silent:
            c.add("not_silent", "Line not predominantly silent", 0.10)

    def _score_fax(
        self, sig: DetectionSignals, c: _CandidateScore
    ) -> None:
        if sig.fax_tone_detected:
            c.add("fax_tone", "CNG/CED fax tone detected", 0.60)
        if not sig.voice_activity_detected:
            c.add("no_voice", "No voice activity", 0.10)
        if not sig.modem_carrier_detected:
            c.add("no_modem_carrier", "No modem carrier (distinguishes from SCADA)", 0.10)

    def _score_scada_modem(
        self, sig: DetectionSignals, c: _CandidateScore
    ) -> None:
        if sig.modem_carrier_detected:
            c.add("modem_carrier", "Modem carrier tone detected", 0.55)
        if not sig.fax_tone_detected:
            c.add("no_fax_tone", "No fax tone (distinguishes from fax)", 0.10)
        if not sig.voice_activity_detected:
            c.add("no_voice", "No voice activity", 0.10)
        if sig.mostly_silent:
            c.add("mostly_silent", f"Silence ratio {sig.silence_ratio:.2f}", 0.05)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fallback_result(
        self, sig: DetectionSignals, best: _CandidateScore
    ) -> ClassificationResult:
        """Return a safe unknown classification with fallback profile."""
        profile = get_profile_for_line_type(LineType.UNKNOWN)
        notes = ["Below confidence threshold — safe fallback applied"]
        if sig.signal_count == 0:
            notes.append("No signals detected in observation window")
        if best.score > 0:
            notes.append(
                f"Closest candidate: {best.line_type.value} "
                f"(score={best.score:.2f})"
            )
        return ClassificationResult(
            line_type=LineType.UNKNOWN,
            confidence_score=round(best.score, 4),
            confidence_tier=Confidence.NONE,
            evidence=best.evidence,
            recommended_profile_id=profile.profile_id,
            is_actionable=False,
            fallback_applied=True,
            notes=notes,
        )

    @staticmethod
    def _tier(score: float) -> Confidence:
        if score >= HIGH_CONFIDENCE_THRESHOLD:
            return Confidence.HIGH
        if score >= MEDIUM_CONFIDENCE_THRESHOLD:
            return Confidence.MEDIUM
        return Confidence.LOW


# ------------------------------------------------------------------
# Internal scoring accumulator
# ------------------------------------------------------------------

class _CandidateScore:
    """Mutable accumulator for scoring a single candidate line type."""

    __slots__ = ("line_type", "score", "evidence", "notes")

    def __init__(self, line_type: LineType) -> None:
        self.line_type = line_type
        self.score: float = 0.0
        self.evidence: list[EvidenceItem] = []
        self.notes: list[str] = []

    def add(self, signal: str, value: str, weight: float) -> None:
        self.score += weight
        self.evidence.append(EvidenceItem(signal=signal, value=value, weight=weight))
