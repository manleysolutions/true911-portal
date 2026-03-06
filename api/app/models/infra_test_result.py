from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class InfraTestResult(Base):
    __tablename__ = "infra_test_results"

    id = Column(Integer, primary_key=True)
    result_id = Column(String(50), unique=True, nullable=False, index=True)
    test_id = Column(String(50), nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(50), nullable=True)
    device_id = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False)  # pass, fail, error, running
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    detail_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(100), nullable=True)  # schedule, manual, provision
    created_at = Column(DateTime(timezone=True), server_default=func.now())
