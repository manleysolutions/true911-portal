from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class InfraTest(Base):
    __tablename__ = "infra_tests"

    id = Column(Integer, primary_key=True)
    test_id = Column(String(50), unique=True, nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    test_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    site_id = Column(String(50), nullable=True)
    device_id = Column(String(50), nullable=True)
    schedule_cron = Column(String(100), nullable=True)
    run_after_provision = Column(Boolean, nullable=False, server_default="false")
    enabled = Column(Boolean, nullable=False, server_default="true")
    config_json = Column(Text, nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_result = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
