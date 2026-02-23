from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("tenants.tenant_id"), index=True
    )
    site_name: Mapped[str] = mapped_column(String(255))
    customer_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50))
    last_checkin: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    e911_street: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    e911_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    e911_state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    e911_zip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    poc_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    poc_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    poc_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_firmware: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    kit_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    carrier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    static_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    signal_dbm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    network_tech: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    heartbeat_frequency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    heartbeat_next_due: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    endpoint_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    service_class: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_device_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_portal_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    container_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    csa_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    heartbeat_interval: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uptime_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    update_channel: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
