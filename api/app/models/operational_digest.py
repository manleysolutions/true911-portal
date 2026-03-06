from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class OperationalDigest(Base):
    __tablename__ = "operational_digests"

    id = Column(Integer, primary_key=True)
    digest_id = Column(String(50), unique=True, nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    digest_type = Column(String(30), nullable=False)  # daily, weekly
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    summary_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
