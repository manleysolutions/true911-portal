"""
Line Intelligence Engine — Constants and enumerations.
"""

from enum import Enum


class LineType(str, Enum):
    """Classification targets for analog line types."""

    FACCP_CONTACT_ID = "faccp_contact_id"
    ELEVATOR_VOICE = "elevator_voice"
    FAX = "fax"
    SCADA_MODEM = "scada_modem"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    """Confidence tiers for classification results."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class DtmfMode(str, Enum):
    """DTMF transport modes for protocol profiles."""

    RFC2833 = "rfc2833"
    INBAND = "inband"
    SIP_INFO = "sip_info"
    AUTO = "auto"


class CodecPreference(str, Enum):
    """Audio codec options."""

    G711_ULAW = "g711_ulaw"
    G711_ALAW = "g711_alaw"
    G729 = "g729"
    T38 = "t38"
    PASSTHROUGH = "passthrough"


class JitterStrategy(str, Enum):
    """Jitter buffer strategies."""

    ADAPTIVE = "adaptive"
    FIXED_LOW = "fixed_low"
    FIXED_HIGH = "fixed_high"
    DISABLED = "disabled"


class EchoCancellation(str, Enum):
    """Echo cancellation modes."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    AGGRESSIVE = "aggressive"


class GainProfile(str, Enum):
    """Gain / volume profiles."""

    DEFAULT = "default"
    BOOSTED = "boosted"
    REDUCED = "reduced"
    PASSTHROUGH = "passthrough"


# ---------------------------------------------------------------------------
# Thresholds & defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIDENCE_THRESHOLD: float = 0.60
"""Minimum confidence to act on a classification.  Below this, fallback."""

HIGH_CONFIDENCE_THRESHOLD: float = 0.85
MEDIUM_CONFIDENCE_THRESHOLD: float = 0.60

# Detection thresholds
DTMF_MIN_EVENTS_CONTACT_ID: int = 4
"""Minimum DTMF events to consider Contact ID signalling."""

FAX_TONE_FREQUENCY_HZ: int = 1100
"""CNG tone frequency for fax detection (±tolerance applied in detector)."""

FAX_TONE_TOLERANCE_HZ: int = 50

MODEM_CARRIER_MIN_DURATION_MS: int = 500
"""Minimum carrier tone duration to flag modem presence."""

VOICE_ENERGY_THRESHOLD: float = 0.25
"""Normalized voice energy above which voice activity is considered present."""

SILENCE_RATIO_THRESHOLD: float = 0.80
"""Silence ratio above which the line is considered mostly silent."""

MAX_OBSERVATION_AGE_SECONDS: int = 300
"""Observations older than this are stale and should be discarded."""
