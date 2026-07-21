"""Normalized, read-only carrier snapshot.

A carrier-agnostic view of what a carrier last told us about one line, built
from a typed response envelope. It exists so the later live-synchronization work
has a stable shape to persist and to render, without that work having to know
anything T-Mobile-specific.

Deliberately inert: building a snapshot performs no network call, schedules
nothing, and writes nothing. It is a value object.

Identifiers are display-safe by construction — the snapshot stores only masked
forms, because its whole purpose is to be handed to layers (persistence,
dashboards, digests) that have no business seeing a full subscriber identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.integrations.tmobile_contracts import (
    NormalizedStatus,
    TMobileResponseEnvelope,
    normalize_status,
)
from app.integrations.tmobile_evidence import mask_tail

#: Beyond this, an observation is labelled stale rather than silently trusted.
DEFAULT_FRESHNESS_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class TMobileCarrierSnapshot:
    """One carrier observation, normalized and safe to persist or display."""

    carrier: str = "tmobile"
    tenant_id: str | None = None
    account_ref: str | None = None

    msisdn_masked: str | None = None
    iccid_masked: str | None = None
    imsi_masked: str | None = None

    sim_network_type: str | None = None
    subscriber_status_raw: str | None = None
    subscriber_status_normalized: NormalizedStatus = NormalizedStatus.UNKNOWN
    network_registration_state: str | None = None
    network_technology: str | None = None
    usage_summary: dict[str, Any] = field(default_factory=dict)

    observed_at: datetime | None = None
    source_operation: str | None = None
    source_transaction_id: str | None = None

    reconciliation_status: str = "not_reconciled"
    raw_extra_field_count: int = 0
    audit_ref: str | None = None

    def is_stale(self, *, now: datetime | None = None,
                 window: timedelta = DEFAULT_FRESHNESS_WINDOW) -> bool:
        """A snapshot with no observation time is stale, not fresh.

        Failing toward stale matters: an unknown age must never be presented as
        current data on a life-safety surface.
        """
        if self.observed_at is None:
            return True
        return (now or datetime.now(timezone.utc)) - self.observed_at > window

    def age(self, *, now: datetime | None = None) -> timedelta | None:
        if self.observed_at is None:
            return None
        return (now or datetime.now(timezone.utc)) - self.observed_at

    @classmethod
    def from_envelope(
        cls,
        envelope: TMobileResponseEnvelope,
        *,
        tenant_id: str | None = None,
        account_ref: str | None = None,
        audit_ref: str | None = None,
    ) -> "TMobileCarrierSnapshot":
        """Build a snapshot from a typed response. Performs no I/O."""
        return cls(
            tenant_id=tenant_id,
            account_ref=mask_tail(account_ref) if account_ref else None,
            msisdn_masked=mask_tail(envelope.msisdn),
            iccid_masked=mask_tail(envelope.iccid),
            imsi_masked=mask_tail(envelope.imsi),
            sim_network_type=envelope.sim_network_type,
            subscriber_status_raw=envelope.subscriber_status_raw,
            subscriber_status_normalized=normalize_status(
                envelope.subscriber_status_raw),
            observed_at=envelope.received_at,
            source_operation=envelope.operation,
            source_transaction_id=envelope.partner_transaction_id,
            raw_extra_field_count=len(envelope.raw_extra_fields),
            audit_ref=audit_ref,
        )
