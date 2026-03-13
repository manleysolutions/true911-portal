"""Service Unit — represents a distinct emergency communications endpoint at a site.

Examples: elevator emergency phone, fire alarm communicator, emergency call station,
fax line, generic voice line.

Each service unit tracks its own communications capabilities, compliance state,
and video-readiness configuration independent of other units at the same site.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServiceUnit(Base):
    __tablename__ = "service_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)

    # ── Identity ─────────────────────────────────────────────────
    unit_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    unit_name: Mapped[str] = mapped_column(String(255))
    unit_type: Mapped[str] = mapped_column(String(50))
    # unit_type values:
    #   elevator_phone | fire_alarm | emergency_call_station | fax_line | voice_line | other

    # ── Physical location within site ────────────────────────────
    location_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # e.g. "Elevator #3, South Tower" or "Lobby emergency phone"
    floor: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # ── Install classification ───────────────────────────────────
    install_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # new | modernization | existing

    # ── Communications capabilities ──────────────────────────────
    voice_supported: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    video_supported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    text_supported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    visual_messaging_supported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    onsite_takeover_supported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    backup_power_supported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # ── Monitoring ───────────────────────────────────────────────
    monitoring_station_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # e.g. "UL-listed central station", "proprietary", "none"

    # ── Compliance ───────────────────────────────────────────────
    # NOTE: These are operational guidance states, NOT legal determinations.
    # True911 provides compliance tracking tools; it does not provide legal advice.
    compliance_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # compliant | partially_compliant | review_required | non_compliant | unknown
    compliance_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # e.g. "TX-dallas", "CA", "NYC"
    governing_code_edition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # e.g. "ASME A17.1-2019", "IBC 2021", "NFPA 72-2022"
    compliance_last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Video readiness ──────────────────────────────────────────
    camera_present: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    video_stream_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    video_transport_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # sip_video | rtsp | webrtc | hls | none
    video_encryption: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # srtp | tls | none | unknown
    video_retained: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    video_operator_visible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # ── Device / line linkage ────────────────────────────────────
    device_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    sim_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Status ───────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(30), default="active", server_default="active")
    # active | inactive | decommissioned | pending_install

    # ── Metadata ─────────────────────────────────────────────────
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
