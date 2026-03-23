"""
Line Intelligence Engine — Detector.

Extracts structured detection signals from normalized Observations.
Rule-based only (v1). No direct hardware access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .constants import (
    DTMF_MIN_EVENTS_CONTACT_ID,
    MODEM_CARRIER_MIN_DURATION_MS,
    SILENCE_RATIO_THRESHOLD,
    VOICE_ENERGY_THRESHOLD,
)
from .models import Observation


@dataclass(frozen=True)
class DetectionSignals:
    """Structured detection output consumed by the classifier."""

    # DTMF / Contact ID
    dtmf_event_count: int = 0
    dtmf_digit_sequence: str = ""
    dtmf_pattern_looks_contact_id: bool = False

    # Fax
    fax_tone_detected: bool = False

    # Modem
    modem_carrier_detected: bool = False

    # Voice
    voice_activity_detected: bool = False
    voice_energy: float = 0.0

    # Silence
    mostly_silent: bool = False
    silence_ratio: float = 0.0

    # Quality / meta
    observation_window_ms: int = 0
    signal_count: int = 0
    warnings: list[str] = field(default_factory=list)


class LineDetector:
    """
    Extracts detection signals from a normalized Observation.

    Future versions may accept pluggable signal extractors (audio DSP,
    SIP event streams, etc.). v1 is rule-based over Observation fields.
    """

    # Contact ID messages typically have 16+ DTMF digits in a specific
    # pattern: account code (4 digits) + event qualifier (1) + event code (3)
    # + group/zone (3). We look for a minimum digit count and specific
    # digit-set characteristics.
    CONTACT_ID_DIGIT_SET = set("0123456789*#ABCD")

    def detect(self, observation: Observation) -> DetectionSignals:
        """Run all detectors against a single observation."""
        warnings: list[str] = []

        # --- DTMF / Contact ID ------------------------------------------
        dtmf_count = len(observation.dtmf_events)
        dtmf_seq = "".join(e.digit for e in observation.dtmf_events)
        contact_id_like = self._looks_like_contact_id(dtmf_seq, dtmf_count)

        # --- Fax ---------------------------------------------------------
        fax_detected = observation.fax_tone_present

        # --- Modem -------------------------------------------------------
        modem_detected = observation.modem_carrier_present

        # --- Voice -------------------------------------------------------
        voice_active = observation.voice_energy_estimate >= VOICE_ENERGY_THRESHOLD

        # --- Silence -----------------------------------------------------
        mostly_silent = observation.silence_ratio >= SILENCE_RATIO_THRESHOLD

        # --- Sanity warnings ---------------------------------------------
        if observation.window_duration_ms < 1000:
            warnings.append("observation_window_too_short")
        if dtmf_count > 0 and fax_detected:
            warnings.append("conflicting_dtmf_and_fax_signals")
        if voice_active and modem_detected:
            warnings.append("conflicting_voice_and_modem_signals")

        signal_count = sum([
            dtmf_count > 0,
            fax_detected,
            modem_detected,
            voice_active,
        ])

        return DetectionSignals(
            dtmf_event_count=dtmf_count,
            dtmf_digit_sequence=dtmf_seq,
            dtmf_pattern_looks_contact_id=contact_id_like,
            fax_tone_detected=fax_detected,
            modem_carrier_detected=modem_detected,
            voice_activity_detected=voice_active,
            voice_energy=observation.voice_energy_estimate,
            mostly_silent=mostly_silent,
            silence_ratio=observation.silence_ratio,
            observation_window_ms=observation.window_duration_ms,
            signal_count=signal_count,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _looks_like_contact_id(
        self, digit_sequence: str, count: int
    ) -> bool:
        """
        Heuristic: does the DTMF sequence resemble Ademco Contact ID?

        Contact ID frames are typically 16 digits, but partial captures
        with >= DTMF_MIN_EVENTS_CONTACT_ID digits composed only of the
        expected character set are flagged for further classification.
        """
        if count < DTMF_MIN_EVENTS_CONTACT_ID:
            return False
        if not all(c in self.CONTACT_ID_DIGIT_SET for c in digit_sequence):
            return False
        return True
