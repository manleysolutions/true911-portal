from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class AutonomousAction(Base):
    __tablename__ = "autonomous_actions"

    id = Column(Integer, primary_key=True)
    action_id = Column(String(50), unique=True, nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)
    trigger_source = Column(String(100), nullable=False)
    site_id = Column(String(50), nullable=True, index=True)
    device_id = Column(String(50), nullable=True)
    incident_id = Column(String(50), nullable=True)
    summary = Column(Text, nullable=False)
    detail_json = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, server_default="completed")
    result = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
