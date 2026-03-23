"""
Line Intelligence Engine — Adaptation layer.

Provides interfaces for future integrations with:
- Audio / DSP signal processing
- SIP event stream ingestion
- ATA / TR-069 parameter push
- Hardware modem / fax tone detection

v1 contains only abstract interfaces and safe stubs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .models import Observation, ProtocolProfile


# ---------------------------------------------------------------------------
# Observation sources — future hardware / integration adapters
# ---------------------------------------------------------------------------

class ObservationSource(ABC):
    """
    Abstract interface for producing Observations from a signal source.

    Implementations will wrap SIP event monitors, audio capture rigs,
    TR-069 diagnostic reads, etc.
    """

    @abstractmethod
    def capture(self, line_id: str, tenant_id: str, duration_ms: int = 5000) -> Observation:
        """Capture and return a normalized Observation from the source."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the source is connected and ready."""
        ...


class StubObservationSource(ObservationSource):
    """
    Placeholder observation source for testing and development.

    Returns an empty observation — no signals detected.
    """

    def capture(self, line_id: str, tenant_id: str, duration_ms: int = 5000) -> Observation:
        import uuid

        return Observation(
            observation_id=str(uuid.uuid4()),
            line_id=line_id,
            tenant_id=tenant_id,
            window_duration_ms=duration_ms,
            source="stub",
        )

    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Profile applicators — future ATA / gateway configuration push
# ---------------------------------------------------------------------------

class ProfileApplicator(ABC):
    """
    Abstract interface for applying a ProtocolProfile to a device or line.

    Implementations will push configuration via TR-069, SIP REFER,
    provisioning APIs, etc.
    """

    @abstractmethod
    def apply(
        self,
        profile: ProtocolProfile,
        device_id: str,
        line_id: str,
        dry_run: bool = False,
    ) -> ProfileApplyResult:
        """
        Apply the profile to the target device/line.

        If dry_run is True, validate and return what would be changed
        without actually pushing configuration.
        """
        ...


class ProfileApplyResult:
    """Outcome of a profile application attempt."""

    __slots__ = ("success", "device_id", "line_id", "changes_applied", "error")

    def __init__(
        self,
        success: bool,
        device_id: str,
        line_id: str,
        changes_applied: Optional[list[str]] = None,
        error: Optional[str] = None,
    ) -> None:
        self.success = success
        self.device_id = device_id
        self.line_id = line_id
        self.changes_applied = changes_applied or []
        self.error = error


class StubProfileApplicator(ProfileApplicator):
    """
    Placeholder applicator that logs intent but performs no changes.
    """

    def apply(
        self,
        profile: ProtocolProfile,
        device_id: str,
        line_id: str,
        dry_run: bool = False,
    ) -> ProfileApplyResult:
        return ProfileApplyResult(
            success=True,
            device_id=device_id,
            line_id=line_id,
            changes_applied=[
                f"[stub] Would apply profile '{profile.profile_id}' to "
                f"device={device_id} line={line_id}"
            ],
        )
