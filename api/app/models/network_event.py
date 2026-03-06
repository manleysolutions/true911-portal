from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class NetworkEvent(Base):
    __tablename__ = "network_events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(50), unique=True, nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    device_id = Column(String(50), nullable=False, index=True)
    site_id = Column(String(50), nullable=True, index=True)
    carrier = Column(String(50), nullable=True)
    event_type = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False, server_default="info")
    summary = Column(Text, nullable=False)
    detail_json = Column(Text, nullable=True)
    signal_dbm = Column(Float, nullable=True)
    network_status = Column(String(50), nullable=True)
    roaming = Column(Boolean, nullable=True, server_default="false")
    resolved = Column(Boolean, nullable=False, server_default="false")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    incident_id = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
