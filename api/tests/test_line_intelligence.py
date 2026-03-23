"""
Unit tests for the Line Intelligence Engine.

Covers:
- Contact ID-like DTMF behavior
- Voice-like behavior (elevator)
- Fax tone detection path
- Modem-like signal path
- Ambiguous / unknown path
- Safe fallback profile assignment
- Session pipeline orchestration
- Persistence round-trips
- Telemetry aggregation
- Manual override
"""

import uuid

import pytest

from app.services.line_intelligence import (
    ClassificationResult,
    Confidence,
    DEFAULT_CONFIDENCE_THRESHOLD,
    LineClassifier,
    LineDetector,
    LineIntelligenceSession,
    LineType,
    Observation,
    ProtocolProfile,
    SessionDecision,
)
from app.services.line_intelligence.detector import DetectionSignals
from app.services.line_intelligence.models import DtmfEvent
from app.services.line_intelligence.persistence import InMemoryPersistence
from app.services.line_intelligence.protocol_profiles import (
    get_all_profiles,
    get_profile_for_line_type,
    get_safe_fallback_profile,
)
from app.services.line_intelligence.telemetry import TelemetryCollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _obs(
    dtmf_digits: str = "",
    fax: bool = False,
    modem: bool = False,
    voice_energy: float = 0.0,
    silence_ratio: float = 0.0,
    window_ms: int = 5000,
) -> Observation:
    """Build an Observation with specified signals."""
    events = [
        DtmfEvent(digit=d, timestamp_ms=i * 100, duration_ms=50)
        for i, d in enumerate(dtmf_digits)
    ]
    return Observation(
        observation_id=str(uuid.uuid4()),
        line_id="line-test-1",
        tenant_id="tenant-test",
        dtmf_events=events,
        fax_tone_present=fax,
        modem_carrier_present=modem,
        voice_energy_estimate=voice_energy,
        silence_ratio=silence_ratio,
        window_duration_ms=window_ms,
        source="unit_test",
    )


# ===================================================================
# Detector tests
# ===================================================================

class TestLineDetector:

    def setup_method(self) -> None:
        self.detector = LineDetector()

    def test_empty_observation_produces_no_signals(self) -> None:
        obs = _obs()
        sig = self.detector.detect(obs)
        assert sig.dtmf_event_count == 0
        assert not sig.fax_tone_detected
        assert not sig.modem_carrier_detected
        assert not sig.voice_activity_detected
        assert sig.signal_count == 0

    def test_contact_id_dtmf_pattern(self) -> None:
        # Standard DTMF digits only: 0-9, A-D, *, #
        obs = _obs(dtmf_digits="1234567890ABCD*#")
        sig = self.detector.detect(obs)
        assert sig.dtmf_event_count == 16
        assert sig.dtmf_pattern_looks_contact_id is True

    def test_short_dtmf_not_contact_id(self) -> None:
        obs = _obs(dtmf_digits="12")
        sig = self.detector.detect(obs)
        assert sig.dtmf_pattern_looks_contact_id is False

    def test_fax_tone_detected(self) -> None:
        obs = _obs(fax=True)
        sig = self.detector.detect(obs)
        assert sig.fax_tone_detected is True
        assert sig.signal_count == 1

    def test_modem_carrier_detected(self) -> None:
        obs = _obs(modem=True)
        sig = self.detector.detect(obs)
        assert sig.modem_carrier_detected is True

    def test_voice_activity_threshold(self) -> None:
        obs_low = _obs(voice_energy=0.10)
        obs_high = _obs(voice_energy=0.50)
        assert self.detector.detect(obs_low).voice_activity_detected is False
        assert self.detector.detect(obs_high).voice_activity_detected is True

    def test_silence_ratio_threshold(self) -> None:
        obs = _obs(silence_ratio=0.90)
        sig = self.detector.detect(obs)
        assert sig.mostly_silent is True

    def test_conflicting_signals_warning(self) -> None:
        obs = _obs(dtmf_digits="12345", fax=True)
        sig = self.detector.detect(obs)
        assert "conflicting_dtmf_and_fax_signals" in sig.warnings

    def test_short_window_warning(self) -> None:
        obs = _obs(window_ms=500)
        sig = self.detector.detect(obs)
        assert "observation_window_too_short" in sig.warnings


# ===================================================================
# Classifier tests
# ===================================================================

class TestLineClassifier:

    def setup_method(self) -> None:
        self.classifier = LineClassifier()

    def test_contact_id_classification(self) -> None:
        obs = _obs(dtmf_digits="1234567890ABCD*#")
        sig = LineDetector().detect(obs)
        result = self.classifier.classify(sig)
        assert result.line_type == LineType.FACCP_CONTACT_ID
        assert result.confidence_score >= DEFAULT_CONFIDENCE_THRESHOLD
        assert result.is_actionable is True
        assert result.fallback_applied is False

    def test_elevator_voice_classification(self) -> None:
        obs = _obs(voice_energy=0.65, silence_ratio=0.20)
        sig = LineDetector().detect(obs)
        result = self.classifier.classify(sig)
        assert result.line_type == LineType.ELEVATOR_VOICE
        assert result.confidence_score >= DEFAULT_CONFIDENCE_THRESHOLD
        assert result.is_actionable is True

    def test_fax_classification(self) -> None:
        obs = _obs(fax=True)
        sig = LineDetector().detect(obs)
        result = self.classifier.classify(sig)
        assert result.line_type == LineType.FAX
        assert result.confidence_score >= DEFAULT_CONFIDENCE_THRESHOLD
        assert result.recommended_profile_id == "profile_fax_v1"

    def test_scada_modem_classification(self) -> None:
        obs = _obs(modem=True, silence_ratio=0.85)
        sig = LineDetector().detect(obs)
        result = self.classifier.classify(sig)
        assert result.line_type == LineType.SCADA_MODEM
        assert result.is_actionable is True

    def test_unknown_fallback_when_no_signals(self) -> None:
        obs = _obs()
        sig = LineDetector().detect(obs)
        result = self.classifier.classify(sig)
        assert result.line_type == LineType.UNKNOWN
        assert result.fallback_applied is True
        assert result.is_actionable is False
        assert result.recommended_profile_id == "profile_unknown_safe_v1"

    def test_low_confidence_triggers_fallback(self) -> None:
        # All signals weakly present — ambiguous, nothing dominant
        obs = _obs(voice_energy=0.10, silence_ratio=0.50)
        sig = LineDetector().detect(obs)
        result = self.classifier.classify(sig)
        # No strong signal → should fall back to unknown
        assert result.fallback_applied is True
        assert result.line_type == LineType.UNKNOWN

    def test_evidence_populated(self) -> None:
        obs = _obs(fax=True)
        sig = LineDetector().detect(obs)
        result = self.classifier.classify(sig)
        assert len(result.evidence) > 0
        signal_names = [e.signal for e in result.evidence]
        assert "fax_tone" in signal_names


# ===================================================================
# Protocol profile tests
# ===================================================================

class TestProtocolProfiles:

    def test_all_line_types_have_profiles(self) -> None:
        for lt in LineType:
            profile = get_profile_for_line_type(lt)
            assert profile.line_type == lt

    def test_fax_profile_has_t38(self) -> None:
        profile = get_profile_for_line_type(LineType.FAX)
        assert profile.t38_enabled is True

    def test_contact_id_disables_echo_cancel(self) -> None:
        from app.services.line_intelligence.constants import EchoCancellation
        profile = get_profile_for_line_type(LineType.FACCP_CONTACT_ID)
        assert profile.echo_cancellation == EchoCancellation.DISABLED

    def test_scada_uses_passthrough(self) -> None:
        from app.services.line_intelligence.constants import CodecPreference
        profile = get_profile_for_line_type(LineType.SCADA_MODEM)
        assert profile.codec_preference == CodecPreference.PASSTHROUGH

    def test_unknown_safe_fallback(self) -> None:
        profile = get_safe_fallback_profile()
        assert profile.line_type == LineType.UNKNOWN
        assert profile.passthrough_enabled is False

    def test_get_all_profiles_returns_all(self) -> None:
        profiles = get_all_profiles()
        assert len(profiles) == len(LineType)


# ===================================================================
# Session manager (full pipeline) tests
# ===================================================================

class TestLineIntelligenceSession:

    def test_full_pipeline_contact_id(self) -> None:
        session = LineIntelligenceSession()
        obs = _obs(dtmf_digits="1234567890ABCD*#")
        decision = session.process(obs)
        assert isinstance(decision, SessionDecision)
        assert decision.classification.line_type == LineType.FACCP_CONTACT_ID
        assert decision.assigned_profile.profile_id == "profile_contact_id_v1"
        assert decision.manual_override is False

    def test_full_pipeline_fax(self) -> None:
        session = LineIntelligenceSession()
        decision = session.process(_obs(fax=True))
        assert decision.classification.line_type == LineType.FAX
        assert decision.assigned_profile.t38_enabled is True

    def test_full_pipeline_unknown(self) -> None:
        session = LineIntelligenceSession()
        decision = session.process(_obs())
        assert decision.classification.line_type == LineType.UNKNOWN
        assert decision.classification.fallback_applied is True

    def test_manual_override(self) -> None:
        session = LineIntelligenceSession()
        obs = _obs()  # empty → would be unknown
        decision = session.process_with_override(
            obs,
            override_line_type=LineType.ELEVATOR_VOICE,
            override_reason="Operator confirmed elevator phone",
        )
        assert decision.manual_override is True
        assert decision.assigned_profile.line_type == LineType.ELEVATOR_VOICE
        assert decision.override_reason == "Operator confirmed elevator phone"
        # Original classification still preserved for audit
        assert decision.classification.line_type == LineType.UNKNOWN

    def test_pipeline_with_persistence(self) -> None:
        store = InMemoryPersistence()
        session = LineIntelligenceSession(persistence=store)
        decision = session.process(_obs(fax=True))
        retrieved = store.get_decision(decision.decision_id)
        assert retrieved is not None
        assert retrieved.decision_id == decision.decision_id

    def test_pipeline_with_telemetry(self) -> None:
        telem = TelemetryCollector()
        session = LineIntelligenceSession(telemetry=telem)
        session.process(_obs(fax=True))
        session.process(_obs(modem=True))
        summary = telem.summary()
        assert summary.total_decisions == 2


# ===================================================================
# Persistence tests
# ===================================================================

class TestInMemoryPersistence:

    def test_save_and_retrieve(self) -> None:
        store = InMemoryPersistence()
        session = LineIntelligenceSession(persistence=store)
        d = session.process(_obs(fax=True))
        assert store.get_decision(d.decision_id) == d

    def test_retrieve_by_line(self) -> None:
        store = InMemoryPersistence()
        session = LineIntelligenceSession(persistence=store)
        session.process(_obs(fax=True))
        session.process(_obs(modem=True))
        decisions = store.get_decisions_for_line("line-test-1", "tenant-test")
        assert len(decisions) == 2

    def test_retrieve_by_tenant(self) -> None:
        store = InMemoryPersistence()
        session = LineIntelligenceSession(persistence=store)
        session.process(_obs(voice_energy=0.7))
        decisions = store.get_decisions_for_tenant("tenant-test")
        assert len(decisions) == 1

    def test_missing_decision_returns_none(self) -> None:
        store = InMemoryPersistence()
        assert store.get_decision("nonexistent") is None

    def test_clear(self) -> None:
        store = InMemoryPersistence()
        session = LineIntelligenceSession(persistence=store)
        session.process(_obs())
        store.clear()
        assert store.get_decisions_for_tenant("tenant-test") == []


# ===================================================================
# Telemetry tests
# ===================================================================

class TestTelemetryCollector:

    def test_summary_empty(self) -> None:
        t = TelemetryCollector()
        s = t.summary()
        assert s.total_decisions == 0
        assert s.avg_confidence == 0.0

    def test_summary_after_decisions(self) -> None:
        t = TelemetryCollector()
        session = LineIntelligenceSession(telemetry=t)
        session.process(_obs(fax=True))
        session.process(_obs(modem=True))
        session.process(_obs())  # unknown
        s = t.summary()
        assert s.total_decisions == 3
        assert s.fallback_count >= 1  # the unknown one
        assert s.avg_confidence > 0

    def test_tenant_summary(self) -> None:
        t = TelemetryCollector()
        session = LineIntelligenceSession(telemetry=t)
        session.process(_obs(fax=True))
        s = t.summary(tenant_id="tenant-test")
        assert s.total_decisions == 1
        assert s.tenant_id == "tenant-test"

    def test_reset(self) -> None:
        t = TelemetryCollector()
        session = LineIntelligenceSession(telemetry=t)
        session.process(_obs(fax=True))
        t.reset()
        assert t.summary().total_decisions == 0
