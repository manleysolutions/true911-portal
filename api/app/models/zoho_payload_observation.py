from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ZohoPayloadObservation(Base):
    """Sanitized structural record of inbound Zoho webhook payloads.

    The Zoho webhook field mapping is NOT finalized, so this table captures what
    Zoho ACTUALLY sends — matched and unmatched — letting the real payload
    contract be derived from production data instead of assumptions.  Secrets are
    redacted before storage (see ``services/zoho_payload_sanitizer.py``).

    Read-only diagnostic only — nothing here drives a production write.  The full
    (unsanitized) body already lives on ``integration_events.payload_json``; this
    is the queryable, secret-free, structure-focused view.
    """
    __tablename__ = "zoho_payload_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(String(100), index=True)
    module: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    # Did the configurable routing layer classify this as a subscription event?
    matched_subscription: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False
    )
    top_level_keys: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    sanitized_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    integration_event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("integration_events.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
