import datetime as _dt
from datetime import datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50))  # provisioning, active, inactive, decommissioned
    device_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    imei: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    iccid: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    msisdn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    container_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provision_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_interval: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hardware_model_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("hardware_models.id"), nullable=True
    )
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    starlink_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    identifier_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # cellular, ata, starlink
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activated_at: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)
    term_end_date: Mapped[Optional[_dt.date]] = mapped_column(Date, nullable=True)
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # Phase 7 columns
    carrier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sim_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    imsi: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    network_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    data_usage_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_network_event: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    telemetry_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
