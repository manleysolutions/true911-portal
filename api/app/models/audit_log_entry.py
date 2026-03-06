from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class AuditLogEntry(Base):
    __tablename__ = "audit_log_entries"

    id = Column(Integer, primary_key=True)
    entry_id = Column(String(50), unique=True, nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=False)  # device, firmware, verification, incident, config, network
    action = Column(String(100), nullable=False)
    actor = Column(String(255), nullable=True)
    target_type = Column(String(100), nullable=True)  # device, site, incident, test
    target_id = Column(String(100), nullable=True)
    site_id = Column(String(50), nullable=True)
    device_id = Column(String(50), nullable=True)
    summary = Column(Text, nullable=False)
    detail_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
