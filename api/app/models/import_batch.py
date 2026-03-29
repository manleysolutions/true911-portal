from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportBatch(Base):
    """Tracks a single subscriber import session (preview + commit)."""
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), server_default="pending")
    # pending | previewed | committed | failed
    total_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rows_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rows_updated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rows_matched: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rows_failed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rows_flagged: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tenants_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sites_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    devices_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lines_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
