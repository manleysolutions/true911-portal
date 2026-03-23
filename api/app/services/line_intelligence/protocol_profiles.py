"""
Line Intelligence Engine — Protocol profiles.

Pre-built protocol configurations for each classified line type.
These profiles map to ATA / SIP gateway parameters that will later
be pushed via TR-069 (VOLA) or equivalent.
"""

from __future__ import annotations

from .constants import (
    CodecPreference,
    DtmfMode,
    EchoCancellation,
    GainProfile,
    JitterStrategy,
    LineType,
)
from .models import ProtocolProfile, RetryStrategy

# ---------------------------------------------------------------------------
# Profile registry — keyed by LineType
# ---------------------------------------------------------------------------

_PROFILES: dict[LineType, ProtocolProfile] = {
    LineType.FACCP_CONTACT_ID: ProtocolProfile(
        profile_id="profile_contact_id_v1",
        profile_name="FACCP Contact ID — Optimized",
        line_type=LineType.FACCP_CONTACT_ID,
        codec_preference=CodecPreference.G711_ULAW,
        dtmf_mode=DtmfMode.INBAND,
        jitter_strategy=JitterStrategy.FIXED_LOW,
        gain_profile=GainProfile.DEFAULT,
        echo_cancellation=EchoCancellation.DISABLED,
        retry_strategy=RetryStrategy(max_retries=5, backoff_seconds=1.0),
        t38_enabled=False,
        passthrough_enabled=True,
        silence_suppression=False,
        vad_enabled=False,
        notes=[
            "Contact ID requires in-band DTMF for reliable digit delivery.",
            "Echo cancellation disabled — interferes with tone detection.",
            "Silence suppression off — preserves inter-digit timing.",
            "VAD off — avoids clipping short tones.",
        ],
    ),
    LineType.ELEVATOR_VOICE: ProtocolProfile(
        profile_id="profile_elevator_voice_v1",
        profile_name="Elevator Voice — Standard",
        line_type=LineType.ELEVATOR_VOICE,
        codec_preference=CodecPreference.G711_ULAW,
        dtmf_mode=DtmfMode.RFC2833,
        jitter_strategy=JitterStrategy.ADAPTIVE,
        gain_profile=GainProfile.BOOSTED,
        echo_cancellation=EchoCancellation.AGGRESSIVE,
        retry_strategy=RetryStrategy(max_retries=3, backoff_seconds=2.0),
        t38_enabled=False,
        passthrough_enabled=False,
        silence_suppression=True,
        vad_enabled=True,
        notes=[
            "Elevator cabs are noisy — aggressive echo cancellation.",
            "Boosted gain compensates for handsfree speaker distance.",
            "Adaptive jitter handles variable cellular backhaul.",
        ],
    ),
    LineType.FAX: ProtocolProfile(
        profile_id="profile_fax_v1",
        profile_name="Fax — T.38 Preferred",
        line_type=LineType.FAX,
        codec_preference=CodecPreference.T38,
        dtmf_mode=DtmfMode.RFC2833,
        jitter_strategy=JitterStrategy.FIXED_LOW,
        gain_profile=GainProfile.DEFAULT,
        echo_cancellation=EchoCancellation.DISABLED,
        retry_strategy=RetryStrategy(
            max_retries=3,
            backoff_seconds=5.0,
            failover_codec=CodecPreference.G711_ULAW,
        ),
        t38_enabled=True,
        passthrough_enabled=True,
        silence_suppression=False,
        vad_enabled=False,
        notes=[
            "T.38 is the primary fax relay method.",
            "Fallback to G.711 passthrough if T.38 negotiation fails.",
            "Echo cancellation MUST be disabled for fax.",
            "Silence suppression off — fax relies on continuous carrier.",
        ],
    ),
    LineType.SCADA_MODEM: ProtocolProfile(
        profile_id="profile_scada_modem_v1",
        profile_name="SCADA Modem — Passthrough",
        line_type=LineType.SCADA_MODEM,
        codec_preference=CodecPreference.PASSTHROUGH,
        dtmf_mode=DtmfMode.INBAND,
        jitter_strategy=JitterStrategy.FIXED_HIGH,
        gain_profile=GainProfile.PASSTHROUGH,
        echo_cancellation=EchoCancellation.DISABLED,
        retry_strategy=RetryStrategy(max_retries=5, backoff_seconds=3.0),
        t38_enabled=False,
        passthrough_enabled=True,
        silence_suppression=False,
        vad_enabled=False,
        notes=[
            "SCADA modems require bit-transparent passthrough.",
            "No DSP processing — any manipulation corrupts modem framing.",
            "Fixed high jitter buffer absorbs backhaul variance.",
            "Higher retry count — SCADA polling is time-sensitive.",
        ],
    ),
    LineType.UNKNOWN: ProtocolProfile(
        profile_id="profile_unknown_safe_v1",
        profile_name="Unknown — Safe Fallback",
        line_type=LineType.UNKNOWN,
        codec_preference=CodecPreference.G711_ULAW,
        dtmf_mode=DtmfMode.RFC2833,
        jitter_strategy=JitterStrategy.ADAPTIVE,
        gain_profile=GainProfile.DEFAULT,
        echo_cancellation=EchoCancellation.ENABLED,
        retry_strategy=RetryStrategy(max_retries=3, backoff_seconds=2.0),
        t38_enabled=False,
        passthrough_enabled=False,
        silence_suppression=True,
        vad_enabled=True,
        notes=[
            "Conservative defaults — safe for any line type.",
            "Will not break fax or modem but is not optimal for them.",
            "Manual override recommended once line type is determined.",
        ],
    ),
}


def get_profile_for_line_type(line_type: LineType) -> ProtocolProfile:
    """Return the protocol profile for a given line type (never raises)."""
    return _PROFILES.get(line_type, _PROFILES[LineType.UNKNOWN])


def get_all_profiles() -> dict[LineType, ProtocolProfile]:
    """Return a copy of the full profile registry."""
    return dict(_PROFILES)


def get_safe_fallback_profile() -> ProtocolProfile:
    """Return the safe fallback profile for unknown / low-confidence lines."""
    return _PROFILES[LineType.UNKNOWN]
