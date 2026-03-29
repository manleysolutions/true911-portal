from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportRow(Base):
    """Per-row audit trail for a subscriber import batch."""
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(50), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), server_default="pending")
    # pending | created | matched | updated | failed | flagged | skipped
    action_summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tenant_action: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    site_action: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    device_action: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    line_action: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tenant_id_resolved: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    site_id_resolved: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_id_resolved: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    line_id_resolved: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reconciliation_status: Mapped[Optional[str]] = mapped_column(String(30), server_default="imported_unverified")
    # clean | needs_review | incomplete | duplicate_suspected | imported_unverified | verified
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
